#!/usr/bin/env bash
# Starts PlantDoctor at http://127.0.0.1:8000  (builds the web app first if needed)
set -e
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ] && command -v npm >/dev/null; then (cd frontend && npm ci && npm run build); fi
( sleep 4; xdg-open http://127.0.0.1:8000 >/dev/null 2>&1 ) &
exec .venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8000
