"""Recursive architecture loop with immutable paired evaluation and auditable mutations.

Workers run pure simulations; only the parent process writes the system of record.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from statistics import mean, pstdev
from time import perf_counter
from uuid import uuid4

from .models import HarnessConfig
from .simulator import simulate, EVALUATOR
from .planner import propose
from .store import now

EVALUATION_SEEDS = (1043, 2045, 3043, 4049, 5051)
CONTROL_SEED = 5003
MINIMUM_SEED_WINS = 3


def config_diff(before, after):
    """Architecture fields, individual policy parameters and ID-addressed typed rules.

    Version is identity metadata, already stored alongside the diff, not a behavior change.
    Rule order is ignored: the interpreter addresses declarative rules by stable ID.
    """
    before = before.model_dump() if hasattr(before, "model_dump") else before
    after = after.model_dump() if hasattr(after, "model_dump") else after
    changes = []
    for key in sorted((set(before) | set(after)) - {"version", "policy", "rules"}):
        if before.get(key) != after.get(key):
            changes.append(
                {"path": key, "before": before.get(key), "after": after.get(key)}
            )
    old_policy, new_policy = before.get("policy", {}), after.get("policy", {})
    for key in sorted(set(old_policy) | set(new_policy)):
        if old_policy.get(key) != new_policy.get(key):
            changes.append(
                {
                    "path": f"policy.{key}",
                    "before": old_policy.get(key),
                    "after": new_policy.get(key),
                }
            )
    old_rules = {rule["id"]: rule for rule in before.get("rules", [])}
    new_rules = {rule["id"]: rule for rule in after.get("rules", [])}
    for rule_id in sorted(set(old_rules) | set(new_rules)):
        old, new = old_rules.get(rule_id), new_rules.get(rule_id)
        if old != new:
            fields = []
            if old is not None and new is not None:
                for key in sorted(set(old) | set(new)):
                    if old.get(key) != new.get(key):
                        fields.append(
                            {
                                "path": f"rules.{rule_id}.{key}",
                                "before": old.get(key),
                                "after": new.get(key),
                            }
                        )
            changes.append(
                {
                    "path": f"rules.{rule_id}",
                    "before": old,
                    "after": new,
                    "operation": (
                        "add" if old is None else "remove" if new is None else "change"
                    ),
                    "changes": fields,
                }
            )
    return changes


def _persist_result(store, result, config, mode, elapsed_seconds=None):
    result.update(
        run_id=str(uuid4()),
        harness_version=config.version,
        started_at=now(),
        mode=mode,
        persistence="offline_preview" if store.offline else "atlas",
    )
    # Retain simulator-provided telemetry and append actual orchestration runtime.
    if elapsed_seconds is not None:
        result["telemetry"] = dict(
            result.get("telemetry") or {},
            simulation_runtime_seconds=round(elapsed_seconds, 6),
        )
    store.save_run(result)
    return result


def execute_run(
    store, config, seed, mode="fixed", scenario="event_surge", **scenario_parameters
):
    started = perf_counter()
    result = simulate(
        config, seed=seed, mode=mode, scenario=scenario, **scenario_parameters
    )
    return _persist_result(store, result, config, mode, perf_counter() - started)


def _simulate_job(spec):
    """Picklable pure worker entry point: no Store, credentials or persistence calls."""
    started = perf_counter()
    result = simulate(
        HarnessConfig.model_validate(spec["config"]),
        seed=spec["seed"],
        mode=spec["mode"],
        scenario=spec["scenario"],
        **spec["parameters"],
    )
    return result, perf_counter() - started


def parallel_runs(store, specs, progress=lambda stage: None):
    """Evaluate independently in processes, then persist in fixed specification order."""
    completed = {}
    with ProcessPoolExecutor(max_workers=min(4, len(specs))) as executor:
        futures = {
            executor.submit(_simulate_job, spec): index
            for index, spec in enumerate(specs)
        }
        for future in as_completed(futures):
            completed[futures[future]] = future.result()
            progress(
                f"Running held-out evaluation · {len(completed)}/{len(specs)} simulations complete"
            )
    runs = []
    for index, spec in enumerate(specs):
        result, elapsed = completed[index]
        runs.append(
            _persist_result(
                store,
                result,
                HarnessConfig.model_validate(spec["config"]),
                spec["mode"],
                elapsed,
            )
        )
    return runs


def initialize(store):
    if not store.get("control", "active_harness"):
        config = HarnessConfig()
        store.put(
            "harness_versions",
            config.version,
            {
                "version": config.version,
                "config": config.model_dump(),
                "parent_version": None,
                "mutation_summary": "Initial decentralized functional harness",
                "eligible": not store.offline,
            },
        )
        store.put("control", "active_harness", {"version": config.version})


def current_config(store,scenario=None):
    initialize(store)
    key="active_harness" if scenario is None else f"active_harness:{scenario}"
    pointer = store.get("control",key)
    if not pointer:
        historical=[v for v in store.list("harness_versions",limit=10000) if v.get("accepted") is True and v.get("benchmark_scope",v.get("scenario","event_surge"))==scenario]
        pointer={"version":historical[-1]["version"] if historical else "v1","scenario":scenario}
        store.put("control",key,pointer)
    return HarnessConfig.model_validate(
        store.get("harness_versions", pointer["version"])["config"]
    )


def aggregate(runs):
    metrics = [run["metrics"] for run in runs]
    return {
        key: round(mean(float(row[key]) for row in metrics), 6)
        for key in metrics[0]
        if isinstance(metrics[0][key], (int, float))
    }


def objective(metrics):
    for key in ("objective", "objective_score", "fitness", "score"):
        if key in metrics:
            return metrics[key]
    raise ValueError("Simulator did not report fixed evaluator objective")


def aggregate_rule_telemetry(runs):
    """Sum actual rule counters across runs, keeping rule IDs and action labels."""
    count_fields = (
        "evaluations",
        "fired",
        "dispatches",
        "holds",
        "hold_minutes",
        "riders_affected",
    )
    summary = {}
    for run in runs:
        for rule_id, telemetry in run.get("rule_telemetry", {}).items():
            if rule_id not in summary:
                summary[rule_id] = {
                    "action": telemetry["action"],
                    **{field: 0 for field in count_fields},
                }
            elif summary[rule_id]["action"] != telemetry["action"]:
                raise ValueError(
                    f"Rule {rule_id} changed action within one paired evaluation"
                )
            for field in count_fields:
                summary[rule_id][field] += telemetry.get(field, 0)
    return summary


def evaluation_distribution(before_runs, after_runs):
    if len(before_runs) != len(after_runs) or not before_runs:
        raise ValueError("Paired evaluation needs equal nonempty run sets")
    if any(
        before["seed"] != after["seed"]
        for before, after in zip(before_runs, after_runs)
    ):
        raise ValueError("Paired evaluation seed mismatch")
    pairs = []
    for before, after in zip(before_runs, after_runs):
        old, new = objective(before["metrics"]), objective(after["metrics"])
        pairs.append(
            {
                "seed": before["seed"],
                "before": before["metrics"],
                "after": after["metrics"],
                "before_run_id": before["run_id"],
                "after_run_id": after["run_id"],
                "objective_delta": round(new - old, 8),
                "improvement_percent": round((old - new) / max(old, 1e-9) * 100, 6),
                "won": new < old - 1e-9,
            }
        )

    def spread(runs):
        metrics = [run["metrics"] for run in runs]
        return {
            key: {
                "mean": round(mean(float(row[key]) for row in metrics), 6),
                "stddev": round(pstdev(float(row[key]) for row in metrics), 6),
                "min": min(row[key] for row in metrics),
                "max": max(row[key] for row in metrics),
            }
            for key in metrics[0]
            if isinstance(metrics[0][key], (int, float))
        }

    return {
        "per_seed": pairs,
        "seed_wins": sum(pair["won"] for pair in pairs),
        "required_seed_wins": MINIMUM_SEED_WINS,
        "seed_count": len(pairs),
        "before_distribution": spread(before_runs),
        "after_distribution": spread(after_runs),
    }


def promotion_gate(
    before, after, candidate_runs, control_before, control_after, seed_wins=None
):
    improvement = (objective(before) - objective(after)) / max(objective(before), 1e-9)
    violations = sum(
        run["metrics"].get(
            "feasibility_violations", run["metrics"].get("unsafe_actions", 0)
        )
        + run["metrics"].get("capacity_violations", 0)
        for run in candidate_runs
    )
    safe = violations == 0
    regression = objective(control_after) <= objective(control_before) * 1.05 + 1e-9
    majority = (
        seed_wins is not None
        and seed_wins >= MINIMUM_SEED_WINS
        and len(candidate_runs) >= len(EVALUATION_SEEDS)
    )
    accepted = improvement >= 0.02 and safe and regression and majority
    gates = [
        (improvement >= 0.02, "held-out improvement below 2%"),
        (safe, "feasibility violation"),
        (regression, "commuter objective regression exceeds 5%"),
        (majority, "fewer than 3 of 5 held-out seeds improved"),
    ]
    reason = (
        "Promoted: held-out objective improved by at least 2%, at least 3 of 5 paired seeds won, feasibility passed and commuter regression stayed within 5%."
        if accepted
        else "Rejected: "
        + "; ".join(message for passed, message in gates if not passed)
    )
    return accepted, reason, improvement * 100


def evolve(
    store,
    seed=42,
    iterations=None,
    use_llm=True,
    progress=lambda stage: None,
    scenario="city_commute",
    automatic_trigger=None,
    benchmark_scope=None,
    **scenario_parameters,
):
    iterations = (
        (3 if scenario == "city_commute" else 2) if iterations is None else iterations
    )
    if seed in EVALUATION_SEEDS or seed == CONTROL_SEED:
        raise ValueError(
            "Development seed must be disjoint from the fixed held-out and control seeds"
        )
    evaluator = EVALUATOR
    if scenario == "city_commute":
        from .city_simulator import CITY_EVALUATOR

        evaluator = CITY_EVALUATOR
    scope=benchmark_scope or (scenario if scenario_parameters.get("city_profile","standard")=="standard" else f"{scenario}:{scenario_parameters["city_profile"]}")
    current = current_config(store,scenario=scope)
    original = current
    decisions = []
    eval_seeds = list(EVALUATION_SEEDS)
    control_scenario = "city_commute" if scenario == "city_commute" else "commuter"
    control_parameters = dict(scenario_parameters)
    if scenario == "city_commute" and scenario_parameters.get("city_profile", "standard") != "standard":
        control_parameters["city_profile"] = "balanced_control"
    for iteration in range(iterations):
        progress(f"Reviewing rider journey traces · iteration {iteration+1}")
        development = execute_run(
            store, current, seed, "evolving", scenario, **scenario_parameters
        )
        progress("Proposing architecture mutation")
        lessons = {item["_id"]: item for item in store.list("agent_memory", limit=1000)}
        history = [
            {
                "candidate": item["candidate"],
                "accepted": item.get("accepted", False),
                "reason": item.get("reason"),
                "scenario": item.get("scenario"),
                "config_diff": item.get("config_diff", []),
                "lesson": lessons.get(item["_id"], {}).get("lesson"),
            }
            for item in store.list("mutation_proposals", limit=1000)
            if item.get("status") in ("promoted", "rejected") and item.get("benchmark_scope",item.get("scenario", "event_surge"))==scope
        ][-current.memory_window_steps :]
        proposal, planner = propose(current, development, use_llm, history)
        versions = store.list("harness_versions", limit=10000)
        version = "v" + str(max(int(item["version"][1:]) for item in versions) + 1)
        candidate = HarnessConfig.model_validate(
            dict(proposal.candidate.model_dump(), version=version)
        )
        diff = config_diff(current, candidate)
        mutation_id = str(uuid4())
        record = {
            "mutation_id": mutation_id,
            "proposal": proposal.model_dump(),
            "candidate": candidate.model_dump(),
            "parent_version": current.version,
            "planner": planner,
            "development_run_id": development["run_id"],
            "status": "validated",
            "evaluation_seeds": eval_seeds,
            "control_seed": CONTROL_SEED,
            "control_parameters":control_parameters,
            "benchmark_scope":scope,
            "evaluator": evaluator,
            "config_diff": diff,
            "iteration": iteration + 1,
            "scenario": scenario,
            "automatic_trigger": automatic_trigger,
            "benchmark_scope": scope,
            "scenario_parameters": scenario_parameters,
        }
        record["proposal"]["candidate"] = candidate.model_dump()
        store.put("mutation_proposals", mutation_id, record)
        progress("Validating candidate configuration and safety envelope")
        specs = []
        for held_seed in eval_seeds:
            for config in (current, candidate):
                specs.append(
                    dict(
                        config=config.model_dump(),
                        seed=held_seed,
                        mode="evolving",
                        scenario=scenario,
                        parameters=scenario_parameters,
                    )
                )
        for config in (current, candidate):
            specs.append(
                dict(
                    config=config.model_dump(),
                    seed=CONTROL_SEED,
                    mode="evolving",
                    scenario=control_scenario,
                    parameters=control_parameters,
                )
            )
        runs = parallel_runs(store, specs, progress)
        before_runs, after_runs = runs[:10:2], runs[1:10:2]
        control_before, control_after = runs[-2:]
        before, after = aggregate(before_runs), aggregate(after_runs)
        distribution = evaluation_distribution(before_runs, after_runs)
        baseline_rule_telemetry = aggregate_rule_telemetry(before_runs)
        candidate_rule_telemetry = aggregate_rule_telemetry(after_runs)
        progress("Comparing results against frozen promotion gates")
        accepted, reason, improvement = promotion_gate(
            before,
            after,
            after_runs + [control_after],
            control_before["metrics"],
            control_after["metrics"],
            distribution["seed_wins"],
        )
        evaluation = {
            "evaluation_id": mutation_id,
            "before": before,
            "after": after,
            "accepted": accepted,
            "reason": reason,
            "improvement_percent": improvement,
            "evaluation_seeds": eval_seeds,
            "control_seed": CONTROL_SEED,
            "control_parameters":control_parameters,
            "benchmark_scope":scope,
            "control_before": control_before["metrics"],
            "control_after": control_after["metrics"],
            "run_ids": [run["run_id"] for run in runs],
            "evaluator": evaluator,
            "config_diff": diff,
            "baseline_rule_telemetry": baseline_rule_telemetry,
            "candidate_rule_telemetry": candidate_rule_telemetry,
            **distribution,
        }
        store.put("evaluation_results", mutation_id, evaluation)
        store.put(
            "harness_versions",
            version,
            {
                "version": version,
                "config": candidate.model_dump(),
                "parent_version": current.version,
                "mutation_summary": proposal.rationale,
                "accepted": accepted,
                "evaluation_id": mutation_id,
                "scenario": scenario,
                "benchmark_scope": scope,
                "evaluator_version": evaluator["version"],
                "eligible": not store.offline,
                "config_diff": diff,
            },
        )
        progress(
            "Promoting candidate"
            if accepted
            else "Rejecting candidate; retaining current harness"
        )
        # Every audit write precedes pointer activation; the parent alone writes Atlas.
        record.update(
            status="promoted" if accepted else "rejected",
            accepted=accepted,
            reason=reason,
            baseline_rule_telemetry=baseline_rule_telemetry,
            candidate_rule_telemetry=candidate_rule_telemetry,
        )
        store.put("mutation_proposals", mutation_id, record)
        store.put(
            "deployment_decisions",
            mutation_id,
            {
                "version": version,
                "parent_version": current.version,
                "accepted": accepted,
                "reason": reason,
                "evaluation_id": mutation_id,
                "config_diff": diff,
                "seed_wins": distribution["seed_wins"],
                "improvement_percent": improvement,
                "baseline_rule_telemetry": baseline_rule_telemetry,
                "candidate_rule_telemetry": candidate_rule_telemetry,
            },
        )
        if accepted:
            store.put(
                "control",
                "active_harness",
                {"version": version, "evaluation_id": mutation_id},
            )
            store.put("control", f"active_harness:{scope}", {"version":version,"evaluation_id":mutation_id,"scenario":scenario,"benchmark_scope":scope,"evaluator_version":evaluator["version"]})
            current = candidate
        lesson = {
            "scenario": scenario,
            "accepted": accepted,
            "reason": reason,
            "measured_improvement_percent": round(improvement, 6),
            "seed_wins": distribution["seed_wins"],
            "config_diff": diff,
            "interpretation": "Measured result for this fixed model and evaluation suite; not a prediction or proof of real-world transit improvement.",
        }
        store.put(
            "agent_memory",
            mutation_id,
            {
                "failure_summary": proposal.diagnosis,
                "architecture_rationale": proposal.rationale,
                "accepted": accepted,
                "source_run_id": development["run_id"],
                "config_diff": diff,
                "lesson": lesson,
                "evaluation_id": mutation_id,
            },
        )
        decisions.append(
            dict(
                record,
                **{
                    key: evaluation[key]
                    for key in (
                        "before",
                        "after",
                        "improvement_percent",
                        "per_seed",
                        "seed_wins",
                        "required_seed_wins",
                        "before_distribution",
                        "after_distribution",
                        "baseline_rule_telemetry",
                        "candidate_rule_telemetry",
                    )
                },
            )
        )
    progress("Running three-way comparison on identical scenario and seed")
    static = execute_run(
        store, HarnessConfig(), seed, "static", scenario, **scenario_parameters
    )
    fixed = execute_run(
        store, HarnessConfig(), seed, "fixed", scenario, **scenario_parameters
    )
    final = execute_run(
        store, current, seed, "evolving", scenario, **scenario_parameters
    )
    return {
        "scenario": scenario,
        "current": current.model_dump(),
        "initial": original.model_dump(),
        "decisions": decisions,
        "comparison": {
            "static": static["metrics"],
            "fixed": fixed["metrics"],
            "evolved": final["metrics"],
        },
        "run_ids": {
            "static": static["run_id"],
            "fixed": fixed["run_id"],
            "evolved": final["run_id"],
        },
        "replay": final,
        "evaluation_seeds": eval_seeds,
        "evaluator": evaluator,
        "persistence": "offline_preview" if store.offline else "atlas",
    }
