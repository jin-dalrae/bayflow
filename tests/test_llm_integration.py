import json
from pathlib import Path
import pytest
from backend.app.models import HarnessConfig
from backend.app.simulator import simulate
from backend.app.planner import propose


@pytest.mark.llm
def test_real_model_architecture_proposal(request):
    if not request.config.getoption("--llm"):
        pytest.skip("Explicit --llm flag required for model token use")
    current = HarnessConfig()
    proposal, planner = propose(current, simulate(current), use_llm=True)
    assert planner["kind"] == "llm", planner
    path = Path("output/model-verification.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps({"proposal": proposal.model_dump(), "planner": planner}, indent=2)
    )
