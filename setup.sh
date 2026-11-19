#!/usr/bin/env bash
# Re-creates the PlantDoctor environment from scratch (no sudo needed).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/pip ]; then
  python3 -m venv --without-pip .venv
  url=$(curl -s https://pypi.org/pypi/pip/json | python3 -c "import sys,json;print([u['url'] for u in json.load(sys.stdin)['urls'] if u['url'].endswith('.whl')][0])")
  curl -sL -o /tmp/pip.whl "$url" && .venv/bin/python /tmp/pip.whl/pip install --no-index /tmp/pip.whl
fi
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv/bin/pip install -r requirements.txt
echo "Environment ready. Train with: .venv/bin/python train.py   Run app with: ./run.sh"
