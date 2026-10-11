#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi
echo 'Verifying organizer MongoDB Atlas Sandbox (credentials are never printed)…'
if ! .venv/bin/python scripts/verify_atlas.py; then
  echo 'Atlas verification failed. Official runs stay disabled; you may explicitly enable offline preview in the UI.'
fi
echo 'Starting BayFlow API at http://127.0.0.1:8000 and web UI at http://127.0.0.1:5175'
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
bayflow_backend_pid=$!
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5175) &
bayflow_frontend_pid=$!
trap 'kill "$bayflow_backend_pid" "$bayflow_frontend_pid" 2>/dev/null || true' EXIT INT TERM
wait
