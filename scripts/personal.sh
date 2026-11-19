#!/usr/bin/env bash
# Personal-use launcher: loads .env, sets up the owner account, starts everything.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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

echo "==> Setting up owner account"
PYTHONPATH=backend .venv/bin/python backend/setup_owner.py

echo "==> Starting V2D Studio at http://localhost:8000"
echo "    Login: ${OWNER_EMAILS:-owner@example.com} / ${OWNER_PASSWORD:-password123}"
exec .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
