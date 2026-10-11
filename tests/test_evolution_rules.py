"""Typed architecture diffs, fixed paired gates, parallel isolation and memory audit."""

from backend.app import evolution
from backend.app.models import HarnessConfig
from backend.app.planner import MutationProposal
from backend.app.store import Store


def rule(threshold=0.9):
    return dict(
        id="bus_queue",
        description="Dispatch when bus queue exceeds safe threshold",
        signal="edge_queue_ratio",
        comparator=">=",
        threshold=threshold,
        scope_operators=["Muni Bus"],
        action="standby_dispatch",
        max_hold_minutes=0,
        priority=1,
        enabled=True,
    )


def test_benchmark_scope_isolates_champion_and_records_frozen_controls():
    store = Store(offline=True)
    first_scope = "suite:first:standard"
    second_scope = "suite:second:standard"
    assert evolution.current_config(store, scenario=first_scope).version == "v1"
    result = evolution.evolve(
        store, iterations=1, use_llm=False, scenario="event_surge",
        benchmark_scope=first_scope,
    )
    decision = result["decisions"][0]
    assert decision["benchmark_scope"] == first_scope
    assert decision["control_parameters"] == {}
    assert evolution.current_config(store, scenario=second_scope).version == "v1"
    assert store.get("mutation_proposals", decision["mutation_id"])["control_parameters"] == {}


def test_recursive_diff_policy_rule_add_change_remove_and_identity():
    original = HarnessConfig()
    edited = HarnessConfig.model_validate(
        dict(
            original.model_dump(),
            version="v2",
            planning_horizon_minutes=60,
            policy={**original.policy.model_dump(), "urgent_wait_minutes": 5},
            rules=[rule()],
        )
    )
    diff = evolution.config_diff(original, edited)
    paths = {item["path"] for item in diff}
    assert paths == {
        "planning_horizon_minutes",
        "policy.urgent_wait_minutes",
        "rules.bus_queue",
    }
    addition = next(item for item in diff if item["path"] == "rules.bus_queue")
    assert addition["operation"] == "add" and addition["before"] is None
    changed = edited.model_copy(
        update={"rules": [type(edited.rules[0]).model_validate(rule(0.75))]}
    )
    modification = evolution.config_diff(edited, changed)
    assert modification[0]["operation"] == "change"
    assert modification[0]["changes"][0]["path"] == "rules.bus_queue.threshold"
    removed = evolution.config_diff(edited, edited.model_copy(update={"rules": []}))
    assert removed[0]["operation"] == "remove" and removed[0]["after"] is None
    assert (
        evolution.config_diff(original, original.model_copy(update={"version": "v99"}))
        == []
    )


def test_three_of_five_gate_is_independent_of_aggregate_and_safety():
    before = {"objective": 0.5}
    after = {"objective": 0.4}
    runs = [
        {"metrics": {"capacity_violations": 0, "feasibility_violations": 0}}
        for _ in range(5)
    ]
    assert not evolution.promotion_gate(
        before, after, runs, before, after, seed_wins=2
    )[0]
    assert evolution.promotion_gate(before, after, runs, before, after, seed_wins=3)[0]
    bad = [{"metrics": {"capacity_violations": 1}}] + runs[1:]
    assert not evolution.promotion_gate(before, after, bad, before, after, seed_wins=5)[
        0
    ]
    assert not evolution.promotion_gate(
        before, after, runs, before, {"objective": 0.6}, seed_wins=5
    )[0]


def test_paired_distribution_reports_real_seed_spread():
    before = [
        {"seed": seed, "run_id": f"b{seed}", "metrics": {"objective": value}}
        for seed, value in zip(evolution.EVALUATION_SEEDS, [0.5, 0.4, 0.3, 0.2, 0.1])
    ]
    after = [
        {"seed": seed, "run_id": f"a{seed}", "metrics": {"objective": value}}
        for seed, value in zip(evolution.EVALUATION_SEEDS, [0.4, 0.3, 0.2, 0.25, 0.1])
    ]
    result = evolution.evaluation_distribution(before, after)
    assert result["seed_wins"] == 3
    assert result["seed_count"] == 5
    assert result["before_distribution"]["objective"]["mean"] == 0.3
    assert result["before_distribution"]["objective"]["stddev"] > 0
    assert [row["seed"] for row in result["per_seed"]] == list(
        evolution.EVALUATION_SEEDS
    )


def test_pure_parallel_workers_and_parent_persistence_keep_telemetry():
    store = Store(offline=True)
    config = HarnessConfig()
    specs = [
        dict(
            config=config.model_dump(),
            seed=seed,
            mode="fixed",
            scenario="event_surge",
            parameters={},
        )
        for seed in [42, 43]
    ]
    runs = evolution.parallel_runs(store, specs)
    assert [run["seed"] for run in runs] == [42, 43]
    assert len(store.list("simulation_runs")) == 2
    for run in runs:
        saved = store.get("simulation_runs", run["run_id"])
        assert saved["telemetry"]["simulation_runtime_seconds"] >= 0
        assert saved["metrics"] == run["metrics"]


def test_persisted_rule_diff_five_seeds_and_bounded_prior_lessons(monkeypatch):
    histories = []

    def propose(current, run, use_llm, history):
        histories.append(history)
        candidate = current.model_dump()
        candidate["rules"] = [rule(0.9 if not history else 0.8)]
        return MutationProposal(
            candidate=HarnessConfig.model_validate(candidate),
            diagnosis="Measured queues warrant a declarative dispatch policy test.",
            rationale="Test an explicit bus queue threshold within the same resource constraints.",
            expected_improvement="A falsifiable decrease in passenger waiting.",
            confidence=0.5,
        ), {"kind": "rule_based"}

    monkeypatch.setattr(evolution, "propose", propose)
    store = Store(offline=True)
    result = evolution.evolve(
        store, iterations=2, use_llm=False, scenario="event_surge"
    )
    assert result["evaluation_seeds"] == list(evolution.EVALUATION_SEEDS)
    assert len(set(result["evaluation_seeds"])) == 5
    assert 42 not in result["evaluation_seeds"]
    assert histories[0] == []
    assert len(histories[1]) == 1 and histories[1][0]["lesson"]
    assert histories[1][0]["reason"] and histories[1][0]["config_diff"]
    for decision in result["decisions"]:
        identifier = decision["mutation_id"]
        assert len(decision["per_seed"]) == 5
        assert any(
            item["path"] == "rules.bus_queue" for item in decision["config_diff"]
        )
        for collection in [
            "mutation_proposals",
            "evaluation_results",
            "deployment_decisions",
            "agent_memory",
        ]:
            document = store.get(collection, identifier)
            assert document["config_diff"] == decision["config_diff"]
        assert store.get("agent_memory", identifier)["lesson"][
            "measured_improvement_percent"
        ] == round(decision["improvement_percent"], 6)


def test_rule_telemetry_aggregates_actual_runs_without_inventing_firings():
    runs = [
        {
            "rule_telemetry": {
                "transfer_hold": {
                    "action": "hold_for_transfer",
                    "evaluations": 12,
                    "fired": 3,
                    "holds": 2,
                    "hold_minutes": 5,
                    "riders_affected": 17,
                }
            }
        },
        {
            "rule_telemetry": {
                "transfer_hold": {
                    "action": "hold_for_transfer",
                    "evaluations": 9,
                    "fired": 1,
                    "holds": 1,
                    "hold_minutes": 2,
                    "riders_affected": 8,
                },
                "inactive_rule": {
                    "action": "standby_dispatch",
                    "evaluations": 0,
                    "fired": 0,
                },
            }
        },
        {},
    ]
    summary = evolution.aggregate_rule_telemetry(runs)
    assert summary["transfer_hold"] == {
        "action": "hold_for_transfer",
        "evaluations": 21,
        "fired": 4,
        "dispatches": 0,
        "holds": 3,
        "hold_minutes": 7,
        "riders_affected": 25,
    }
    assert summary["inactive_rule"]["fired"] == 0
    assert evolution.aggregate_rule_telemetry([{}, {}]) == {}
