"""Verify real official-driver Atlas ping and read/write without printing credentials."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.store import Store
from backend.app.main import seed_store

store = Store()
status = store.status()
print(json.dumps(status, indent=2))
if not status['connected']:
    sys.exit(1)
seed_store(store)
print(json.dumps(store.status(), indent=2))
