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
        missed = metrics.get("missed_transfers", 0)
        rules = candidate["rules"]
        rejected_holds = any(not item.get("accepted") and any(
            rule.get("action") == "hold_for_transfer" for rule in item.get("candidate", {}).get("rules", []))
            for item in (history or []))
        has_hold = any(rule["action"] == "hold_for_transfer" and rule.get("enabled", True) for rule in rules)
        if missed > 0 and not has_hold and not rejected_holds and len(rules) < 12:
            observed = [row["operator"] for row in failure.get("top_failure_edges", [])
                        if row["operator"] in {"Muni Bus", "Muni Metro", "BART", "Caltrain"}]
            scope = sorted(set(observed)) or ["Muni Bus", "Muni Metro", "BART", "Caltrain"]
            rate = missed / max(1, metrics.get("transfer_opportunities", 1))
            threshold = max(1, min(10, math.ceil(rate * 10)))
            candidate.update(coordination_mode="hub_and_spoke" if current.coordination_mode == "decentralized" else current.coordination_mode,
                             context_policy="transfer_neighbors" if current.context_policy == "local_only" else current.context_policy)
            candidate["active_agents"] = sorted(set(current.active_agents) | {"regional_coordinator"})
            candidate["active_tools"] = sorted(set(current.active_tools) | {"transfer_optimizer", "regional_coordination"})
            rule_id = "incoming_transfer_hold"
            existing_ids = {rule["id"] for rule in rules}
            if rule_id in existing_ids:
                rules = [rule for rule in rules if rule["id"] != rule_id]
            candidate["rules"] = rules + [dict(id=rule_id,
                description=f"Test a two-minute hold for incoming transfer riders after {missed} measured missed transfers.",
                signal="incoming_transfer_riders", comparator=">=", threshold=threshold,
                scope_operators=scope, action="hold_for_transfer", max_hold_minutes=2, priority=1.0, enabled=True)]
            diagnosis = f"The development run recorded {missed} missed transfers; existing rules lack a bounded incoming-rider connection hold."
            rationale = f"Test an incoming-transfer threshold of {threshold} riders and a maximum two-minute hold, with neighbor context/tool authorization. Actual held-out results decide whether the timing tradeoff helps."
        elif metrics["boarding_within_10_minutes_rate"] < .95 and "service_frequency_optimizer" not in current.active_tools:
            candidate.update(coordination_mode="regional", context_policy="regional_shared")
            candidate["active_agents"] = sorted(set(current.active_agents) | {"regional_coordinator"})
            candidate["active_tools"] = sorted(set(current.active_tools) | {"regional_coordination", "service_frequency_optimizer"})
            rejected_frequency = any(not item.get("accepted") and "service_frequency_optimizer" in item.get("candidate", {}).get("active_tools", []) for item in (history or []))
            if rejected_frequency:
                candidate["replanning_interval_minutes"] = max(5, current.replanning_interval_minutes - 10)
            else:
                candidate["policy"]["urgent_wait_minutes"] = max(3, current.policy.urgent_wait_minutes - 1)
            diagnosis = "Riders are missing the 10-minute first-boarding target; local service allocation does not prioritize waiting riders across providers."
            rationale = ("A slower service-frequency proposal was rejected; test faster replanning to act before deadlines within the same fleet and budget." if rejected_frequency else "Test shared service-frequency allocation and trigger urgent waits one minute earlier within unchanged resources and gross operating budget.")
        elif metrics.get("crowding_exposure_passenger_minutes", 0) > 0 and "passenger_advisory" not in current.active_tools:
            candidate.update(coordination_mode="regional", context_policy="regional_shared")
            candidate["active_agents"] = sorted(set(current.active_agents) | {"regional_coordinator"})
            candidate["active_tools"] = sorted(set(current.active_tools) | {"regional_coordination", "passenger_advisory"})
            diagnosis = "Recorded queue crowding remains; the current tool set cannot offer voluntary feasible alternatives."
            rationale = "Test advisory access and shared observed pressure. Keep destinations, original ETA, consent draws and evaluator frozen."
        else:
            queue_peak = max((row["peak_observed_queue"] for row in failure.get("top_failure_edges", [])), default=0)
            change = .05 if queue_peak > 0 and metrics["boarding_within_10_minutes_rate"] < .95 else -.05
            policy = candidate["policy"]
            policy["age_weight"] = round(max(0, min(1, current.policy.age_weight + change)), 4)
            if history and not history[-1].get("accepted", True):
                policy["dispatch_threshold_regional"] = round(min(3, current.policy.dispatch_threshold_regional + .1), 4)
            diagnosis = "Residual observed queues and prior proposal outcomes require a smaller controller-policy hypothesis rather than repeating an architectural bundle."
            rationale = "Test bounded age-priority tuning; after rejection, raise dispatch pressure threshold to reduce speculative reserve use. Independent evaluation preserves failed hypotheses."
        # Version IDs do not make an old policy hypothesis new. Avoid repeats
        # by testing a bounded age-priority increment justified by residual waits.
        tried=[]
        for item in history or []:
            try:
                prior=HarnessConfig.model_validate(item.get("candidate", {})).model_dump(exclude={"version"})
                tried.append(prior)
            except Exception:
                continue
        while HarnessConfig.model_validate(candidate).model_dump(exclude={"version"}) in tried and candidate["policy"]["age_weight"]<1:
            candidate["policy"]["age_weight"]=round(min(1,candidate["policy"]["age_weight"]+.05),4)
            rationale += " This architecture/cadence was previously tested; add a bounded age-priority increment to form a distinct residual-wait hypothesis."
        return MutationProposal(diagnosis=diagnosis, rationale=rationale,
            expected_improvement="Improve fixed journey targets or transfer reliability without changing demand, deadlines, consent, physical limits or evaluator.",
            confidence=.55, candidate=HarnessConfig(**candidate))
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
        "Return a full typed candidate with about four focused, justified configuration/policy/rule changes, preserving all other fields. "
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
    def supported(proposal):
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
