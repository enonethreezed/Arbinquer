#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/arbinquer.pid"
LOG_FILE="$ROOT_DIR/arbinquer.log"
PYTHON_BIN="${PYTHON_BIN:-python}"

start() {
  local running_pid
  running_pid="$(pgrep -f "${PYTHON_BIN} -m arbinquer.bot" | head -n 1 || true)"
  if [[ -n "$running_pid" ]]; then
    echo "Already running (pid $running_pid)"
    echo "$running_pid" >"$PID_FILE"
    exit 0
  fi

  if [[ -f "$PID_FILE" ]]; then
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Already running (pid $(cat "$PID_FILE"))"
      exit 0
    fi
  fi

  echo "Starting bot..."
  (cd "$ROOT_DIR" && PYTHONPATH="$ROOT_DIR/src" nohup "$PYTHON_BIN" -m arbinquer.bot >>"$LOG_FILE" 2>&1 & echo $! >"$PID_FILE")
  echo "Started (pid $(cat "$PID_FILE"))"
  exit 0
}

stop() {
  local running_pids
  running_pids="$(pgrep -f "${PYTHON_BIN} -m arbinquer.bot" || true)"
  if [[ -n "$running_pids" ]]; then
    echo "$running_pids" | while read -r pid; do
      if [[ -n "$pid" ]]; then
        kill "$pid" 2>/dev/null || true
      fi
    done
  fi

  if [[ ! -f "$PID_FILE" ]]; then
    echo "Not running (no pid file)"
    return 0
  fi

  PID="$(cat "$PID_FILE")"
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Not running (stale pid $PID)"
    rm -f "$PID_FILE"
    return 0
  fi

  echo "Stopping (pid $PID)..."
  kill "$PID"
  for _ in {1..30}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "Stopped"
      return 0
    fi
    sleep 1
  done

  echo "Force stopping (pid $PID)..."
  kill -9 "$PID"
  rm -f "$PID_FILE"
  echo "Stopped"
}

restart() {
  stop
  start
}

status() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Running (pid $(cat "$PID_FILE"))"
  else
    echo "Not running"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
