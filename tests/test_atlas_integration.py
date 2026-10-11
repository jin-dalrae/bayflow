"""Opt-in acceptance proof using the official driver and actual organizer sandbox."""

import json
from pathlib import Path
import pytest
from backend.app.store import Store
from backend.app.main import seed_store
from backend.app.evolution import evolve


@pytest.mark.atlas
def test_real_atlas_recursive_harness_read_after_write(request):
    if not request.config.getoption("--atlas"):
        pytest.skip("Explicit --atlas flag required for external sandbox writes")
    store = Store()
    store.ensure()
    seed_store(store)
    result = evolve(store, seed=42, iterations=2, use_llm=False)
    for decision in result["decisions"]:
        mutation_id = decision["mutation_id"]
        proposal = store.get("mutation_proposals", mutation_id)
        evaluation = store.get("evaluation_results", mutation_id)
        deployment = store.get("deployment_decisions", mutation_id)
        assert proposal["accepted"] == evaluation["accepted"] == deployment["accepted"]
        assert evaluation["before"] == decision["before"]
        assert evaluation["after"] == decision["after"]
    for run_id in result["run_ids"].values():
        run = store.get("simulation_runs", run_id)
        assert run["status"] == "completed"
        assert run["accounting"]["conserved"]
        assert (
            len(store.list("simulation_frames", {"run_id": run_id}, limit=10000))
            == run["frame_count"]
        )
        assert (
            len(store.list("agent_traces", {"run_id": run_id}, limit=10000))
            == run["trace_count"]
        )
    status = store.status()
    assert status["connected"] and status["verified_read_write"]
    artifact = {k: v for k, v in result.items() if k != "replay"}
    artifact["database_verification"] = status
    path = Path("output/atlas-verification.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2))
