#!/usr/bin/env bash
# Starts the PlantDoctor web app at http://127.0.0.1:8000
cd "$(dirname "$0")"
( sleep 3; xdg-open http://127.0.0.1:8000 >/dev/null 2>&1 ) &
exec .venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8000
