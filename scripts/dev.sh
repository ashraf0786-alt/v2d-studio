#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
[ -f .env ] && source .env
set +a

echo "==> Backend dependencies"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt

echo "==> Frontend dependencies"
[ -d frontend/node_modules ] || (cd frontend && npm install --no-audit --no-fund)

if [ ! -f frontend/dist/index.html ]; then
  echo "==> Building frontend"
  (cd frontend && NODE_OPTIONS=--max-old-space-size=4096 npm run build)
fi

echo "==> Starting API at http://localhost:8000 (serves the built UI)"
exec .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
