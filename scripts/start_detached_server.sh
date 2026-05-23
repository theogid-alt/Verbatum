#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT_DIR/data/verbatim/server_v2.log"
ERROR_LOG_FILE="$ROOT_DIR/data/verbatim/server_v2.err.log"
SCREEN_NAME="verbatim-server"

cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/data/verbatim"

if screen -list | grep -q "[.]$SCREEN_NAME[[:space:]]"; then
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

for _ in 1 2 3 4 5; do
  if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Started Verbatim v2 server in detached screen session: $SCREEN_NAME"
    echo "URL: http://127.0.0.1:8000"
    echo "Log: $LOG_FILE"
    echo "Error log: $ERROR_LOG_FILE"
    exit 0
  fi
  sleep 0.4
done

echo "Verbatim server did not start on port 8000."
echo "Error log: $ERROR_LOG_FILE"
tail -n 20 "$ERROR_LOG_FILE" || true
exit 1
