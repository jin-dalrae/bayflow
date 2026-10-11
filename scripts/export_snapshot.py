"""Export read-only API responses from Atlas so the frontend can be hosted as static files.

Usage: .venv/bin/python scripts/export_snapshot.py [--operation demo/autonomous-city-v3-atlas.json]
Writes frontend/public/snapshot/*.json (gitignored). Build with VITE_STATIC=1 to read them.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402
from backend.app.main import app  # noqa: E402

OUT = ROOT / "frontend" / "public" / "snapshot"
HORIZONS = (180, 720, 1440)


def key(path):
    """Must match snapshotKey in frontend/src/snapshot.ts."""
    path = re.sub(r"[?&]offline=true", "", path).lstrip("/")
    return re.sub(r"[^A-Za-z0-9_-]", "_", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", default="demo/autonomous-city-v3-atlas.json",
                        help="Completed operation artifact to show as the latest run")
    args = parser.parse_args()
    client = TestClient(app)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    def save(path, data=None):
        if data is None:
            response = client.get(path)
            response.raise_for_status()
            data = response.json()
        (OUT / f"{key(path)}.json").write_text(json.dumps(data, separators=(",", ":")))
        return data

    status = save("/database/status")
    if not status.get("connected"):
        raise SystemExit("Atlas is not connected; refusing to publish an empty snapshot.")
    scenarios = save("/scenarios")
    scenarios = scenarios if isinstance(scenarios, list) else scenarios.get("scenarios", [])
    for path in ("/harness/proposals", "/harness/versions", "/harness/evaluations"):
        save(path)
    history = save("/operations/history")
    for scenario in (s.get("id") for s in scenarios):
        save(f"/harness/current?scenario={scenario}")
        save(f"/harness/versions?scenario={scenario}")
        for horizon in HORIZONS:
            save(f"/network?scenario={scenario}&horizon_minutes={horizon}")
        latest = [e for e in history if e.get("scenario") == scenario and e.get("observed_run_id")]
        if latest:
            save(f"/simulation/{latest[-1]['observed_run_id']}")

    operation = json.loads((ROOT / args.operation).read_text())
    if operation.get("persistence") != "atlas":
        raise SystemExit("The operation artifact was not persisted in Atlas.")
    operation["replay"] = save(f"/simulation/{operation['run_ids']['evolved']}")
    for decision in operation.get("decisions", []):
        seed_run = (decision.get("per_seed") or [{}])[0].get("after_run_id")
        if seed_run:
            save(f"/simulation/{seed_run}")
    save(f"/snapshot-operation?scenario={operation['scenario']}", operation)
    save("/snapshot-meta", {"exported_at": datetime.now(timezone.utc).isoformat(),
                            "operation": args.operation})
    files = list(OUT.glob("*.json"))
    print(f"{len(files)} files, {sum(f.stat().st_size for f in files) / 1e6:.1f} MB in {OUT}")


if __name__ == "__main__":
    main()
