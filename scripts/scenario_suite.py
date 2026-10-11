"""Matched synthetic profiles: monitored evolution, actual decisions, optional fresh-seed check."""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.automation import operate
from backend.app.evolution import execute_run
from backend.app.models import HarnessConfig
from backend.app.store import Store, now


def summarize_case(result, lessons):
    """Separate architecture exploration/remembered outcomes from achieved gains."""
    decisions = result.get("decisions", [])
    # Version identifiers cannot make an otherwise repeated hypothesis distinct.
    signatures = {
        json.dumps({k: v for k, v in d["candidate"].items() if k != "version"}, sort_keys=True)
        for d in decisions
    }
    telemetry = {key: 0 for key in ("evaluations", "fired", "dispatches", "holds", "hold_minutes", "riders_affected")}
    for decision in decisions:
        for rule in decision.get("candidate_rule_telemetry", {}).values():
            for key in telemetry:
                telemetry[key] += rule.get(key, 0)
    comparison = result.get("comparison", {})
    fixed = comparison.get("fixed", {}).get("objective")
    evolved = comparison.get("evolved", {}).get("objective")
    gain = (100 * (fixed - evolved) / fixed) if fixed not in (None, 0) and evolved is not None else None
    return {
        "automatic_failure_detected": result.get("automatic_trigger") is not None,
        "proposals": len(decisions),
        "accepted": sum(bool(d.get("accepted")) for d in decisions),
        "rejected": sum(not d.get("accepted", False) for d in decisions),
        "distinct_policy_hypotheses": len(signatures),
        "architecture_changed_in_candidates": any(d.get("config_diff") for d in decisions),
        "measured_outcome_lessons": len(lessons),
        "later_hypothesis_after_recorded_outcome": len(decisions) > 1 and bool(lessons),
        "learning_interpretation": "Distinct tested hypotheses and remembered measured outcomes demonstrate feedback use; they do not establish a better champion or generalization.",
        "rule_telemetry": telemetry,
        "development_replay_improvement_percent": gain,
        "qualifying_promotion": any(d.get("accepted") for d in decisions),
        "planner_kinds": sorted({d.get("planner", {}).get("kind", "unknown") for d in decisions}),
    }


def run_case(profile, suite_id, *, offline, use_llm, seed, iterations, horizon_minutes):
    # An Atlas connection is not a fresh database. The unique benchmark scope
    # isolates its champion and memory without deleting any prior evidence.
    scope = f"suite:{suite_id}:{profile}"
    store = Store(offline=offline)
    store.ensure()
    from backend.app.main import seed_store
    from backend.app.city_scenarios import get_city_scenario
    seed_store(store)
    store.put("scenarios", scope, dict(get_city_scenario(profile).metadata(),
                                     benchmark_scope=scope, horizon_minutes=horizon_minutes,
                                     development_seed=seed))
    result = operate(
        store, seed=seed, iterations=iterations, use_llm=use_llm,
        scenario="city_commute", city_profile=profile,
        benchmark_scope=scope, horizon_minutes=horizon_minutes,
        progress=lambda stage: print(f"[{profile}] {stage}", file=sys.stderr, flush=True),
    )
    if result.get("initial", result.get("current", {})).get("version") != "v1":
        raise RuntimeError("Suite cases must begin at an isolated v1 champion")
    lessons = []
    for decision in result.get("decisions", []):
        persisted = store.get("evaluation_results", decision["mutation_id"])
        if not persisted or persisted.get("accepted") != decision.get("accepted"):
            raise RuntimeError("Persisted decision read-after-write mismatch")
        lesson = store.get("agent_memory", decision["mutation_id"])
        if lesson:
            lessons.append(lesson)
    output = {key: value for key, value in result.items() if key != "replay"}
    output.update(profile=profile, benchmark_scope=scope, measured_lessons=lessons,
                  evidence_summary=summarize_case(result, lessons), database_verification=store.status())
    observed = store.get("simulation_runs", result["observed_run_id"])
    output["observed_metrics"] = observed["metrics"]
    if "comparison" not in output:
        output["comparison"] = {"evolved": observed["metrics"]}
    return output, store


def cross_check(cases, store, profiles, horizon_minutes, seed=9001):
    """Final selected configurations on a fresh seed; never returned to the planner."""
    configs = {}
    for case in cases:
        config = HarnessConfig.model_validate(case["current"])
        signature = json.dumps(config.model_dump(exclude={"version"}), sort_keys=True)
        configs.setdefault(signature, {"config": config, "source_profiles": []})["source_profiles"].append(case["profile"])
    rows = []
    for profile in profiles:
        baseline = execute_run(store, HarnessConfig(), seed, "fixed", "city_commute", city_profile=profile, horizon_minutes=horizon_minutes)
        for item in configs.values():
            candidate = execute_run(store, item["config"], seed, "evolving", "city_commute", city_profile=profile, horizon_minutes=horizon_minutes)
            before, after = baseline["metrics"]["objective"], candidate["metrics"]["objective"]
            rows.append(dict(profile=profile, source_profiles=item["source_profiles"], seed=seed,
                             baseline_run_id=baseline["run_id"], candidate_run_id=candidate["run_id"],
                             before=baseline["metrics"], after=candidate["metrics"],
                             improvement_percent=100 * (before-after)/before if before else 0))
    return {"seed": seed, "feedback_to_planner": False,
            "interpretation": "One fresh seed across profiles; exploratory generalization evidence, not a statistical claim.", "results": rows}


def main():
    from backend.app.city_scenarios import CITY_SCENARIOS as PROFILES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Explicit in-memory preview; not Atlas evidence")
    parser.add_argument("--rule-based", action="store_true")
    parser.add_argument("--profiles", default=",".join(PROFILES))
    parser.add_argument("--iterations", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--horizon-minutes", type=int, choices=range(180, 1441), default=180, metavar="180..1440")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cross-check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("demo/scenario-suite.json"))
    args = parser.parse_args()
    profiles = list(dict.fromkeys(p.strip() for p in args.profiles.split(",") if p.strip()))
    unknown = set(profiles) - set(PROFILES)
    if not profiles or unknown:
        parser.error(f"Profiles must be selected from {', '.join(PROFILES)}; unknown={sorted(unknown)}")
    from backend.app.evolution import EVALUATION_SEEDS, CONTROL_SEED
    if args.seed in {*EVALUATION_SEEDS, CONTROL_SEED, 9001}:
        parser.error("Development seed must differ from promotion/control and fresh-check seed9001")
    artifact = dict(suite_id=str(uuid4()), created_at=now(), status="running",
                    synthetic=True, persistence="offline_preview" if args.offline else "atlas",
                    development_seed=args.seed, horizon_minutes=args.horizon_minutes,
                    iterations=args.iterations, requested_profiles=profiles,
                    profile_definitions=[PROFILES[p].metadata() for p in profiles], cases=[])
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact, indent=2))
    save()
    print("profile                 trigger  accepted/rejected  distinct  replay gain", flush=True)
    try:
        for profile in profiles:
            case, store = run_case(profile, artifact["suite_id"], offline=args.offline, use_llm=not args.rule_based,
                                   seed=args.seed, iterations=args.iterations, horizon_minutes=args.horizon_minutes)
            artifact["cases"].append(case)
            save()
            s = case["evidence_summary"]
            gain = s["development_replay_improvement_percent"]
            print(f"{profile:<23} {str(s['automatic_failure_detected']):<8} {s['accepted']}/{s['rejected']:<16} {s['distinct_policy_hypotheses']:<9} {'n/a' if gain is None else f'{gain:+.3f}%'}", flush=True)
        if args.cross_check:
            artifact["fresh_seed_check"] = cross_check(artifact["cases"], store, profiles, args.horizon_minutes)
        artifact["status"] = "completed"
        artifact["completed_at"] = now()
        store.put("evaluation_results", artifact["suite_id"], dict(artifact, kind="synthetic_scenario_suite"))
    except Exception as exc:
        artifact.update(status="failed", error_type=type(exc).__name__)
        save()
        raise
    save()
    print(f"Actual evidence saved to {args.output}", flush=True)


if __name__ == "__main__":
    main()
