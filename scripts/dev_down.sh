#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${MELIX_RUNTIME_DIR:-$ROOT/.runtime/phase1}"
PYTHON_SOCKET_PATH="${MELIX_WORKER_SOCKET_PATH:-$RUNTIME_DIR/python-worker.sock}"
SWIFT_TEXT_WORKER_SOCKET_PATH="${MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH:-$RUNTIME_DIR/swift-text-worker.sock}"

stop_pid_file() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "-$pid" >/dev/null 2>&1 || kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 40); do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        break
      fi
      sleep 0.25
    done
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "-$pid" >/dev/null 2>&1 || kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  fi

  rm -f "$pid_file"
}

stop_pid_file "$RUNTIME_DIR/control-plane.pid"
stop_pid_file "$RUNTIME_DIR/python-worker.pid"
stop_pid_file "$RUNTIME_DIR/swift-text-worker.pid"

rm -f "$PYTHON_SOCKET_PATH" "$SWIFT_TEXT_WORKER_SOCKET_PATH" "$RUNTIME_DIR/env.sh"

if [[ -d "$RUNTIME_DIR" ]]; then
  rmdir "$RUNTIME_DIR" 2>/dev/null || true
fi

echo "Melix phase-1 stack is stopped."
