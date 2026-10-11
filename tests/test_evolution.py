from backend.app.evolution import evolve, current_config, promotion_gate, execute_run
from backend.app.models import HarnessConfig
from backend.app.store import Store
from backend.app.planner import MutationProposal
from pydantic import ValidationError
import pytest


def test_actual_recursive_loop_rejects_then_promotes_and_persists():
    store = Store(offline=True)
    result = evolve(store, seed=42, iterations=2, use_llm=False, scenario="event_surge")
    assert [d["accepted"] for d in result["decisions"]] == [False, True]
    assert result["current"]["version"] == "v3"
    assert current_config(store).version == "v3"
    assert (
        result["comparison"]["evolved"]["objective"]
        < result["comparison"]["fixed"]["objective"]
    )
    assert len(store.list("evaluation_results")) == 2
    assert len(store.list("deployment_decisions")) == 2
    assert len(store.list("mutation_proposals")) == 2
    assert store.get("harness_versions", "v2")["accepted"] is False
    assert result["decisions"][0]["candidate"] != result["decisions"][1]["candidate"]
    assert all(d["planner"]["kind"] == "rule_based" for d in result["decisions"])
    for run in store.list("simulation_runs"):
        assert run["accounting"]["conserved"]
        assert run["evaluator"] == result["evaluator"]


def test_bad_candidate_is_never_promoted(monkeypatch):
    from backend.app import evolution

    def no_change(current, run, use_llm, history):
        return MutationProposal(
            candidate=current,
            diagnosis="No structural failure resolved by this candidate.",
            rationale="Test a candidate with identical operational behavior.",
            expected_improvement="No predicted gain.",
            confidence=0.1,
        ), {"kind": "rule_based"}

    monkeypatch.setattr(evolution, "propose", no_change)
    store = Store(offline=True)
    result = evolve(store, iterations=1, use_llm=False, scenario="event_surge")
    assert not result["decisions"][0]["accepted"]
    assert current_config(store).version == "v1"
    assert store.get("harness_versions", "v2")["accepted"] is False


def test_fixed_safety_gate_rejects_capacity_or_feasibility_even_if_score_improves():
    before, after = {"objective": 0.5}, {"objective": 0.1}
    for violation in ("capacity_violations", "feasibility_violations"):
        result = promotion_gate(
            before, after, [{"metrics": {violation: 1}}], before, after
        )
        assert not result[0]
        assert "feasibility" in result[1]


def test_mutation_schema_cannot_edit_evaluator_or_execute_code():
    with pytest.raises(ValidationError):
        HarnessConfig(unsafe_python="print(1)", evaluator={"delay": 0})


def test_frame_and_run_retrieval_are_actual_written_documents():
    store = Store(offline=True)
    run = execute_run(store, HarnessConfig(), 101)
    saved = store.get("simulation_runs", run["run_id"])
    frames = store.list("simulation_frames", {"run_id": run["run_id"]}, limit=10000)
    traces = store.list("agent_traces", {"run_id": run["run_id"]}, limit=10000)
    assert saved["metrics"] == run["metrics"]
    assert len(frames) == len(run["frames"])
    assert len(traces) == len(run["traces"])
    assert store.status()["connected"] is False
    assert store.status()["eligible"] is False
