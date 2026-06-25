#!/bin/bash
# Double-clickable macOS launcher for the annotation server.
cd "$(dirname "$0")/backend"
if [ ! -x .venv/bin/uvicorn ]; then
  echo "Not installed yet — run ./install_mac.sh first."
  read -r -p "Press Enter to close."
  exit 1
fi
PORT="${PORT:-8000}"
echo "Starting GraphMind on http://localhost:$PORT (Ctrl+C to stop)"
(sleep 2 && open "http://localhost:$PORT") &
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
