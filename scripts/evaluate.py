"""One-command end-to-end evolution and measured three-way comparison."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.store import Store
from backend.app.main import seed_store
from backend.app.evolution import evolve

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--offline",
    action="store_true",
    help="Explicit in-memory preview, not an eligible Atlas demo",
)
parser.add_argument(
    "--rule-based", action="store_true", help="Use labeled deterministic planner"
)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--iterations", type=int, default=2)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
store = Store(offline=args.offline)
if args.offline:
    print(
        "OFFLINE PREVIEW — no Atlas persistence; not hackathon eligible",
        file=sys.stderr,
    )
store.ensure()
seed_store(store)
result = evolve(
    store,
    args.seed,
    args.iterations,
    not args.rule_based,
    lambda stage: print(stage, file=sys.stderr),
)
summary = {k: v for k, v in result.items() if k not in ("replay",)}
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
