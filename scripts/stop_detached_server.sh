#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCREEN_NAME="verbatim-server"

if screen -S "$SCREEN_NAME" -X quit >/dev/null 2>&1; then
  echo "Stopped Verbatim screen session $SCREEN_NAME"
else
  echo "Verbatim detached server was not running."
fi

LISTENER_PIDS="$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
for pid in $LISTENER_PIDS; do
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if [[ "$command" == *"$ROOT_DIR/.venv/bin/python"* && "$command" == *"uvicorn verbatim.server:create_app"* ]]; then
    kill "$pid" >/dev/null 2>&1 || true
    echo "Stopped orphaned Verbatim server process $pid"
  elif [[ -z "$command" ]]; then
    echo "Found listener on port 8000 but could not inspect process $pid. Re-run with elevated permissions if this is a stale Verbatim server."
  fi
done
