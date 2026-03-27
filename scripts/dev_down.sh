#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${MELIX_RUNTIME_DIR:-/tmp/melix-phase0}"
SOCKET_PATH="${MELIX_WORKER_SOCKET_PATH:-$RUNTIME_DIR/worker.sock}"

stop_pid_file() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 40); do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        break
      fi
      sleep 0.25
    done
  fi

  rm -f "$pid_file"
}

stop_pid_file "$RUNTIME_DIR/control-plane.pid"
stop_pid_file "$RUNTIME_DIR/worker.pid"

rm -f "$SOCKET_PATH" "$RUNTIME_DIR/env.sh"

if [[ -d "$RUNTIME_DIR" ]]; then
  rmdir "$RUNTIME_DIR" 2>/dev/null || true
fi

echo "Melix phase-0 stack is stopped."
