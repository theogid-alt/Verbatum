#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT_DIR/data/verbatim/server.log"
ERROR_LOG_FILE="$ROOT_DIR/data/verbatim/server.err.log"
DOMAIN="gui/$(id -u)"
LABEL="com.verbatim.server"
SCREEN_NAME="verbatim-server"

cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/data/verbatim"

launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true

SCREEN_LIST="$(screen -list || true)"
if printf "%s\n" "$SCREEN_LIST" | grep -q "[.]$SCREEN_NAME[[:space:]]"; then
  echo "Verbatim server screen session already running: $SCREEN_NAME"
  echo "URL: http://127.0.0.1:8000"
  echo "Log: $LOG_FILE"
  echo "Error log: $ERROR_LOG_FILE"
  exit 0
fi

touch "$LOG_FILE" "$ERROR_LOG_FILE"

screen -dmS "$SCREEN_NAME" bash -lc "
  cd '$ROOT_DIR'
  export PYTHONPATH='$ROOT_DIR/src'
  export PYTHONUNBUFFERED=1
  exec '$ROOT_DIR/.venv/bin/python' -m uvicorn verbatim.server:create_app --factory --host 127.0.0.1 --port 8000 >>'$LOG_FILE' 2>>'$ERROR_LOG_FILE'
"

echo "Started Verbatim server in detached screen session: $SCREEN_NAME"
echo "URL: http://127.0.0.1:8000"
echo "Log: $LOG_FILE"
echo "Error log: $ERROR_LOG_FILE"
