#!/usr/bin/env bash
# Start the Verdex planner at http://127.0.0.1:8000
#   ./run.sh            normal (fetches NASA data for new pins)
#   ./run.sh offline    cache only — use this on stage
set -e
cd "$(dirname "$0")"
VENV="${VERDEX_VENV:-$HOME/.venvs/verdex}"   # kept off the network drive: much faster
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating Python environment in $VENV (first run only)…"
  python3.11 -m venv "$VENV" 2>/dev/null || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt jsonschema "qrcode[pil]" anthropic
  "$VENV/bin/pip" install -q torch torchvision timm pillow || echo "(disease model disabled: torch install failed)"
fi
[ "$1" = "offline" ] && export VERDEX_OFFLINE=1
( sleep 2 && open "http://127.0.0.1:8000" 2>/dev/null || true ) &
exec "$VENV/bin/python" -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000
