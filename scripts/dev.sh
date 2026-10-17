#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
if [ ! -x .venv/bin/python ]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
npm run build --prefix frontend
export PYTHONPATH=backend
.venv/bin/python -m app.cli init-db
.venv/bin/python -m app.cli seed-demo
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --no-access-log
