"""Model architecture reviewer, with an explicitly labeled offline rule planner."""

import json
import os
import math
from collections import defaultdict
from pydantic import ValidationError
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .models import HarnessConfig, AGENTS, TOOLS


class MutationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnosis: str = Field(min_length=10, max_length=3000)
    rationale: str = Field(min_length=10, max_length=3000)
    expected_improvement: str = Field(min_length=5, max_length=1500)
    confidence: float = Field(ge=0, le=1)
    candidate: HarnessConfig


def diagnose(run):
    """Summarize measured development telemetry; never manufacture edge attribution."""
    metrics = run["metrics"]
    if run.get("scenario") == "city_commute":
        from .city_network import get_city_network
        network = get_city_network()
    else:
        from .network import get_network
        network = get_network()
    edges = {edge["id"]: edge for edge in network["edges"]}
    edge_stats = defaultdict(lambda: {"peak_observed_queue": 0, "sampled_queue_sum": 0,
                                     "queue_samples": 0, "denied_boardings": 0,
                                     "denied_transfer_boardings": 0, "max_denied_wait_minutes": 0})
    samples = {}
    traces = run.get("traces", [])
    for trace in traces:
        counts = trace.get("observed_queues", {})
        if trace.get("edge_id") and "observed_queue" in trace:
            counts = {**counts, trace["edge_id"]: trace["observed_queue"]}
        for edge_id, count in counts.items():
            key = (trace.get("minute"), edge_id)
            samples[key] = max(samples.get(key, 0), count)
    for (_, edge_id), count in samples.items():
        stats = edge_stats[edge_id]
        stats["peak_observed_queue"] = max(stats["peak_observed_queue"], count)
        stats["sampled_queue_sum"] += count
        stats["queue_samples"] += 1
    # Cohort denials at the same edge/minute are distinct real events, not repeated observations.
    trace_denials = [trace for trace in traces
                    if "denied" in trace.get("action", "") and trace.get("edge_id")]
    denial_records = trace_denials or [event for frame in run.get("frames", [])
                                      for event in frame.get("passenger_events", [])
                                      if "denied" in event.get("action", "") and event.get("edge_id")]
    denial_events = len(denial_records)
    for event in denial_records:
        stats = edge_stats[event["edge_id"]]
        count = event.get("count", 0)
        stats["denied_boardings"] += count
        stats["denied_transfer_boardings"] += count if event.get("transfer", False) else 0
        stats["max_denied_wait_minutes"] = max(stats["max_denied_wait_minutes"], event.get("wait_minutes", 0))
    ranked = []
    operators = defaultdict(lambda: {"peak_observed_edge_queue": 0, "denied_boardings": 0,
                                     "denied_transfer_boardings": 0, "sampled_queue_sum": 0})
    for edge_id, stats in edge_stats.items():
        edge = edges.get(edge_id, {})
        operator = edge.get("operator", "unknown")
        ranked.append(dict(edge_id=edge_id, operator=operator, service=edge.get("service"),
                           source=edge.get("source"), target=edge.get("target"), **stats))
        operators[operator]["peak_observed_edge_queue"] = max(operators[operator]["peak_observed_edge_queue"], stats["peak_observed_queue"])
        operators[operator]["denied_boardings"] += stats["denied_boardings"]
        operators[operator]["denied_transfer_boardings"] += stats["denied_transfer_boardings"]
        operators[operator]["sampled_queue_sum"] += stats["sampled_queue_sum"]
    ranked.sort(key=lambda row: (row["denied_boardings"], row["peak_observed_queue"]), reverse=True)
    config = run.get("config", {})
    transfer_ranked = sorted((row for row in ranked if row["denied_transfer_boardings"] > 0
                              or row["max_denied_wait_minutes"] > 0), key=lambda row: (
        row["denied_transfer_boardings"], row["max_denied_wait_minutes"]), reverse=True)
    return {"metrics": metrics, "accounting": run.get("accounting"),
            "current_policy": config.get("policy", {}), "current_rules": config.get("rules", []),
            "rule_telemetry": run.get("rule_telemetry", {}),
            "observations": traces[-35:], "top_failure_edges": ranked[:10],
            "top_transfer_wait_edges": transfer_ranked[:10],
            "operator_telemetry": dict(operators),
            "denial_attribution": ("actual cohort denial traces" if trace_denials else "actual passenger denial frame events") if denial_events else
                "No per-edge denial events recorded; global congestion remains available in metrics. Queue samples are not denial estimates.",
            "queue_sample_note": "Repeated agent observations deduplicated by minute/edge; sampled sums are not complete queue exposure.",
            "failure_signals": {key: value for key, value in metrics.items()
                if any(word in key for word in ("missed", "unserved", "queue", "delay", "denial", "boarding", "eta_", "crowding"))}}


# One hypothesis per candidate: a single knob, rule or capability plus the companion
# fields the schema requires (for example a transfer hold needs its tool and context).
MAX_CHANGED_FIELDS = 3
TRANSIT_OPERATORS = ("Muni Bus", "Muni Metro", "BART", "Caltrain")


def changed_fields(current, candidate):
    """Configuration paths a candidate changes; agent/tool order is irrelevant."""
    a = current.model_dump(exclude={"version"})
    b = candidate.model_dump(exclude={"version"})
    paths = []
    for key in a:
        if key in ("policy", "rules"):
            continue
        before, after = a[key], b[key]
        if key in ("active_agents", "active_tools"):
            before, after = sorted(before), sorted(after)
        if before != after:
            paths.append(key)
    paths += [f"policy.{key}" for key in a["policy"] if a["policy"][key] != b["policy"][key]]
    before_rules = {rule["id"]: rule for rule in a["rules"]}
    after_rules = {rule["id"]: rule for rule in b["rules"]}
    paths += [f"rules.{rule_id}" for rule_id in sorted(set(before_rules) | set(after_rules))
              if before_rules.get(rule_id) != after_rules.get(rule_id)]
    return paths


def city_plan(current, failure, history=None):
    """Pick the most relevant single-hypothesis move that has not been tested yet."""
    metrics = failure["metrics"]
    edges = failure.get("top_failure_edges", [])
    operators = [row["operator"] for row in edges if row["operator"] in TRANSIT_OPERATORS]
    focus = operators[0] if operators else "Muni Bus"
    top = edges[0] if edges else {}
    slug = focus.lower().replace(" ", "_")
    boarded = metrics.get("boarding_within_10_minutes_rate", 0)
    missed = metrics.get("missed_transfers", 0)
    evidence = (f"{boarded:.0%} of riders boarded within 10 minutes; the worst segment "
                f"({top.get('operator', focus)} {top.get('service') or ''}) recorded "
                f"{top.get('denied_boardings', 0)} denied boardings").replace("  ", " ")
    policy = current.policy
    coordinated = current.coordination_mode != "decentralized"

    def rule(rule_id, action, signal, threshold, description, hold=0):
        return dict(id=rule_id, description=description, signal=signal, comparator=">=",
                    threshold=threshold, scope_operators=[focus], action=action,
                    max_hold_minutes=hold, priority=1.0, enabled=True)

    def with_tools(*tools):
        return sorted(set(current.active_tools) | set(tools))

    def with_coordinator():
        return dict(active_agents=sorted(set(current.active_agents) | {"regional_coordinator"}),
                    coordination_mode=current.coordination_mode if coordinated else "hub_and_spoke")

    moves = [
        ("earlier_local_dispatch",
         dict(policy=dict(dispatch_threshold_local=round(max(0.2, policy.dispatch_threshold_local - 0.2), 4))),
         f"Dispatch standby vehicles earlier: lower the local queue/capacity trigger from {policy.dispatch_threshold_local} to {round(max(0.2, policy.dispatch_threshold_local - 0.2), 4)}."),
        ("queue_dispatch_rule",
         dict(rules=[rule(f"{slug}_queue_dispatch", "standby_dispatch", "edge_queue_ratio", 0.9,
                          f"Dispatch a standby {focus} vehicle when a segment queue reaches 90% of a departure's capacity.")]),
         f"Add one standby-dispatch rule scoped to {focus}, where denials concentrate."),
        ("earlier_urgency",
         dict(policy=dict(urgent_wait_minutes=max(3, policy.urgent_wait_minutes - 2))),
         f"Treat waits as urgent after {max(3, policy.urgent_wait_minutes - 2)} minutes instead of {policy.urgent_wait_minutes}, so riders near the 10-minute target are served first."),
        ("faster_replanning",
         dict(replanning_interval_minutes=max(5, current.replanning_interval_minutes - 5)),
         f"Replan every {max(5, current.replanning_interval_minutes - 5)} minutes instead of {current.replanning_interval_minutes} to react before boarding deadlines pass."),
        ("older_riders_first",
         dict(policy=dict(age_weight=round(min(1.0, policy.age_weight + 0.15), 4))),
         "Weight waiting time more heavily when allocating vehicles, so long-waiting riders board first."),
    ]
    if missed > 0:
        moves += [
            ("transfer_priority_rule",
             dict(active_tools=with_tools("transfer_optimizer"),
                  rules=[rule(f"{slug}_transfer_priority", "transfer_boarding_priority", "edge_queue_ratio", 0.8,
                              f"Board transferring riders first on crowded {focus} segments.")]),
             f"{missed} transfers were missed; board transferring riders first on crowded {focus} segments."),
            ("transfer_hold_rule",
             dict(active_tools=with_tools("transfer_optimizer"),
                  context_policy="transfer_neighbors" if current.context_policy == "local_only" else current.context_policy,
                  rules=[rule(f"{slug}_transfer_hold", "hold_for_transfer", "incoming_transfer_riders", 5,
                              f"Hold a {focus} departure up to two minutes when five or more connecting riders are arriving.", hold=2)]),
             f"{missed} transfers were missed; hold a {focus} departure briefly for incoming connecting riders."),
        ]
    moves += [
        ("frequency_coordination",
         dict(**with_coordinator(), active_tools=with_tools("regional_coordination", "service_frequency_optimizer")),
         "Let a regional coordinator shift service frequency between operators within the same fleet and budget."),
        ("route_advice",
         dict(**with_coordinator(), active_tools=with_tools("regional_coordination", "passenger_advisory")),
         "Let a regional coordinator offer riders a less crowded valid route; destinations and original ETAs stay fixed."),
        ("longer_lookahead",
         dict(policy=dict(upstream_lookahead_minutes=min(60, policy.upstream_lookahead_minutes + 15))),
         "Look further upstream when estimating arriving demand before dispatching."),
    ]
    if coordinated:
        moves.append(("no_low_load_skips", dict(policy=dict(hold_load_fraction=0.0)),
                      "Stop skipping low-load departures; skipped runs may push riders past the 10-minute target."))

    tried = []
    for item in history or []:
        try:
            tried.append(HarnessConfig.model_validate(item.get("candidate", {})).model_dump(exclude={"version"}))
        except Exception:
            continue
    base = current.model_dump()
    for name, change, rationale in moves:
        candidate = dict(base, policy=dict(base["policy"]), rules=list(base["rules"]))
        for key, value in change.items():
            if key == "policy":
                candidate["policy"].update(value)
            elif key == "rules":
                ids = {item["id"] for item in value}
                candidate["rules"] = [item for item in candidate["rules"] if item["id"] not in ids] + value
            else:
                candidate[key] = value
        try:
            config = HarnessConfig(**candidate)
        except Exception:
            continue
        behaviour = config.model_dump(exclude={"version"})
        if behaviour == current.model_dump(exclude={"version"}) or behaviour in tried or len(config.rules) > 12:
            continue
        return MutationProposal(
            diagnosis=f"{evidence}. Hypothesis '{name}' is the most relevant single change not yet tested.",
            rationale=f"{rationale} Only this hypothesis changes, so the held-out result is attributable to it.",
            expected_improvement="Raise the share of riders boarding within 10 minutes or arriving by ETA + 10 without changing demand, deadlines, consent, resources or the evaluator.",
            confidence=0.5, candidate=config)
    step = round(min(1.0, policy.persistence_weight + 0.005), 4)
    candidate = dict(base, policy=dict(base["policy"], persistence_weight=step))
    return MutationProposal(
        diagnosis=f"{evidence}. Every single-change hypothesis in the menu has been tested.",
        rationale="Nudge queue-persistence weighting as a small residual hypothesis.",
        expected_improvement="Small residual improvement in waiting-rider allocation.",
        confidence=0.3, candidate=HarnessConfig(**candidate))


def rule_plan(current, failure, history=None):
    candidate = current.model_dump()
    metrics = failure["metrics"]
    rejected_neighbor_policy = any(
        not h.get("accepted")
        and h.get("candidate", {}).get("context_policy") == "transfer_neighbors"
        for h in (history or [])
    )
    rejected_forecasting = any(
        not h.get("accepted")
        and "demand_forecast" in h.get("candidate", {}).get("active_tools", [])
        for h in (history or [])
    )
    has_delay = any(
        float(v) > 0
        for k, v in metrics.items()
        if ("missed" in k or "delay" in k) and isinstance(v, (float, int))
    )
    if "boarding_within_10_minutes_rate" in metrics:
        return city_plan(current, failure, history)
    if (
        current.context_policy == "local_only"
        and has_delay
        and rejected_neighbor_policy
    ):
        candidate.update(
            coordination_mode="regional",
            context_policy="regional_shared",
            optimization_strategy="transfer_aware",
            replanning_interval_minutes=5,
            planning_horizon_minutes=60,
            verification_policy="strict",
        )
        candidate["active_agents"] = sorted(
            set(current.active_agents) | {"regional_coordinator"}
        )
        candidate["active_tools"] = sorted(
            set(current.active_tools)
            | {"regional_coordination", "transfer_optimizer", "feasibility_checker"}
        )
        diagnosis = "Delay remains and a neighbor-only coordination proposal was rejected. The narrow context and slow replanning may miss network-wide queue propagation."
        rationale = "Test regional shared observations and faster replanning, keeping the same physical fleet and frozen evaluator."
    elif current.context_policy == "local_only" and has_delay:
        candidate.update(
            coordination_mode="hub_and_spoke",
            context_policy="transfer_neighbors",
            optimization_strategy="transfer_aware",
        )
        candidate["active_agents"] = sorted(
            set(current.active_agents) | {"regional_coordinator"}
        )
        candidate["active_tools"] = sorted(
            set(current.active_tools)
            | {"regional_coordination", "transfer_optimizer", "feasibility_checker"}
        )
        candidate["verification_policy"] = "strict"
        diagnosis = "Delay and missed connections indicate that local agents cannot observe downstream transfer demand."
        rationale = "Share transfer-neighbor context and authorize a coordinator to synchronize connections within resource limits."
    elif (
        any(
            float(v) > 0
            for k, v in metrics.items()
            if ("unserved" in k or "delay" in k or "queue" in k)
            and isinstance(v, (float, int))
        )
        and "demand_forecast" not in current.active_tools
        and not rejected_forecasting
    ):
        candidate.update(
            coordination_mode="regional",
            context_policy="regional_shared",
            optimization_strategy="regional_predictive",
            planning_horizon_minutes=90,
            replanning_interval_minutes=5,
            memory_window_steps=18,
            verification_policy="strict",
        )
        candidate["active_agents"] = sorted(
            set(current.active_agents) | {"regional_coordinator", "demand_forecaster"}
        )
        candidate["active_tools"] = sorted(
            set(current.active_tools)
            | {
                "regional_coordination",
                "transfer_optimizer",
                "demand_forecast",
                "feasibility_checker",
            }
        )
        diagnosis = "Residual queues and delay persist after reactive dispatch; the controller lacks sufficient advance demand context."
        rationale = "Enable demand forecasting, a longer horizon and more frequent replanning to stage scarce reserves before observed scenario surges."
    else:
        candidate["replanning_interval_minutes"] = min(
            30, current.replanning_interval_minutes + 5
        )
        diagnosis = "The existing tool set already covers detected failures; frequent planning may consume resources without improving service."
        rationale = "Test a lower planning frequency. Independent evaluation will reject this change if passenger outcomes worsen."
    return MutationProposal(
        diagnosis=diagnosis,
        rationale=rationale,
        expected_improvement="Reduce the fixed passenger-delay and missed-transfer objective without violating fleet constraints.",
        confidence=0.65,
        candidate=HarnessConfig(**candidate),
    )


def redact(value):
    text = str(value)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "MONGODB_URI"):
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:1800]


def propose(current, run, use_llm=True, history=None):
    failure = diagnose(run)
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if provider == "auto":
        provider = "gemini" if gemini_key else "anthropic"
    system = (
        "Review a transit multi-agent harness using only measured development failures and evaluated proposal history. "
        "Return a full typed candidate that tests exactly one hypothesis: one policy parameter, one rule, or one capability, plus only the companion fields the schema requires. At most 3 configuration fields may change (agents and tools count as one field each); preserve all other fields. "
        "Prefer a falsifiable smaller hypothesis over enabling every feature. Policy contains bounded controller thresholds; rules are declarative "
        "signal/comparator/threshold/operator-scope/action objects, never code. A rule requires its action tool; incoming_transfer_riders requires shared context. "
        "For missed transfers consider a bounded incoming-rider hold, checking the cost of delaying already-boarded riders. "
        "Use top failure edges/operator telemetry to justify scope. Do not repeat a rejected change without a new hypothesis. "
        "Never change evaluator, seeds, demand, original ETA, consent, budgets, physical constraints or executable code. "
        "Expected improvement is a hypothesis, never a measured claim. Version is assigned independently after validation."
    )
    payload = {"current": current.model_dump(), "development_failure": failure,
               "mutation_history": history or [], "available_agents": sorted(AGENTS - ({"demand_forecaster"} if run.get("scenario")=="city_commute" else set())), "available_tools": sorted(TOOLS - ({"demand_forecast","feasibility_checker"} if run.get("scenario")=="city_commute" else set())),
               "constraints": run.get("resource_constraints", "Three shared Muni standby vehicle/driver pairs; no extra BART or Caltrain fleet."),
               "safety_envelope": "Harness schema is authoritative. Tools require companion agents/context. Journey deadlines, consent seeds, resource/operating budgets and scoring are frozen. Held-out per-seed numerical scores are unavailable; historical aggregate decision feedback is supplied in bounded memory lessons."}
    schema=MutationProposal.model_json_schema()
    if run.get("scenario")=="city_commute":
        schema["$defs"]["HarnessConfig"]["properties"]["optimization_strategy"]["enum"]=["local_greedy","transfer_aware"]
        schema["$defs"]["HarnessConfig"]["properties"]["active_tools"]["items"]={"type":"string","enum":payload["available_tools"]}
        schema["$defs"]["HarnessConfig"]["properties"]["active_agents"]["items"]={"type":"string","enum":payload["available_agents"]}
        payload["city_capabilities"]="Demand forecasting and regional_predictive are not implemented for city. Feasibility is enforced deterministically regardless of tool flags; strict verification additionally checks end-of-horizon arrivals. Propose actual rules, policy, shared context, dispatch, advisory or transfer actions."
    # Gemini structured output rejects this schema with maxItems (400 INVALID_ARGUMENT);
    # MutationProposal validation below still enforces every list limit.
    def without_max_items(node):
        if isinstance(node, dict): return {k: without_max_items(v) for k, v in node.items() if k != "maxItems"}
        if isinstance(node, list): return [without_max_items(v) for v in node]
        return node
    schema=without_max_items(schema)
    def supported(proposal):
        changes = changed_fields(current, proposal.candidate)
        if len(changes) > MAX_CHANGED_FIELDS:
            raise ValueError(f"Candidate changes {len(changes)} fields ({', '.join(changes)}); test one hypothesis with at most {MAX_CHANGED_FIELDS} changed fields, counting required companion fields.")
        if run.get("scenario")=="city_commute" and ("demand_forecast" in proposal.candidate.active_tools or "demand_forecaster" in proposal.candidate.active_agents or proposal.candidate.optimization_strategy=="regional_predictive"):
            raise ValueError("City commute has no executable demand_forecast/demand_forecaster/regional_predictive capability")
        return proposal
    if use_llm and provider == "gemini" and gemini_key:
        errors = []
        attempts = 0
        input_tokens = output_tokens = thinking_tokens = 0
        try:
            from google import genai
            from google.genai import types
            model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            with genai.Client(api_key=gemini_key, http_options=types.HttpOptions(
                    timeout=45000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
                for attempt in range(2):
                    attempts += 1
                    request_payload = dict(payload)
                    if errors:
                        request_payload["validation_feedback"] = errors[-1]
                        request_payload["retry_instruction"] = "Previous candidate failed schema validation. Repair those exact fields, preserve the intended hypothesis and return one complete valid candidate. This is the sole validation retry."
                    response = client.models.generate_content(model=model, contents=json.dumps(request_payload),
                        config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                            response_json_schema=schema, max_output_tokens=16384))
                    usage = response.usage_metadata
                    input_tokens += (usage.prompt_token_count or 0) if usage else 0
                    output_tokens += (usage.candidates_token_count or 0) if usage else 0
                    thinking_tokens += (usage.thoughts_token_count or 0) if usage else 0
                    try:
                        proposal = supported(MutationProposal.model_validate_json(response.text or ""))
                    except (ValidationError,ValueError) as exc:
                        errors.append({"attempt": attempts, "error_type": type(exc).__name__, "message": redact(exc)})
                        if attempt == 0:
                            continue
                        raise
                    return proposal, {"kind": "llm", "provider": "gemini", "model": response.model_version or model,
                        "requested_model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
                        "thinking_tokens": thinking_tokens, "attempts": attempts, "validation_errors": errors}
        except Exception as exc:
            if not errors or errors[-1]["attempt"] != attempts or not isinstance(exc, (ValidationError,ValueError)):
                errors.append({"attempt": attempts, "error_type": type(exc).__name__, "message": redact(getattr(exc, "message", str(exc)))})
            return rule_plan(current, failure, history), {"kind": "rule_based", "requested_provider": "gemini",
                "fallback_reason": f"Gemini unavailable or invalid response ({type(exc).__name__})",
                "provider_error": errors[-1]["message"], "attempts": attempts, "validation_errors": errors,
                "input_tokens": input_tokens, "output_tokens": output_tokens, "thinking_tokens": thinking_tokens}
    if use_llm and provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic(timeout=45, max_retries=0)
            response = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"), max_tokens=8192,
                system=system, messages=[{"role": "user", "content": json.dumps(payload)}],
                tools=[{"name": "propose_harness", "description": "Propose a bounded typed architecture/policy/rule hypothesis for independent evaluation.",
                        "input_schema": schema}], tool_choice={"type": "tool", "name": "propose_harness"})
            blocks = [block for block in response.content if block.type == "tool_use" and block.name == "propose_harness"]
            if len(blocks) != 1:
                raise ValueError("Expected exactly one proposal")
            proposal = supported(MutationProposal.model_validate(blocks[0].input))
            return proposal, {"kind": "llm", "provider": "anthropic", "model": response.model,
                "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "attempts": 1}
        except Exception as exc:
            return rule_plan(current, failure, history), {"kind": "rule_based", "requested_provider": "anthropic",
                "fallback_reason": f"Model unavailable or invalid response ({type(exc).__name__})",
                "provider_error": redact(getattr(exc, "body", str(exc)))}
    return rule_plan(current, failure, history), {"kind": "rule_based", "fallback_reason": "No model API key, or deterministic planner explicitly selected."}
