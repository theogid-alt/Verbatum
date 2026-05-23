#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="gui/$(id -u)"
LABEL="com.verbatim.server"
SCREEN_NAME="verbatim-server"

if launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "Stopped Verbatim LaunchAgent $LABEL"
fi

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
  fi
done
