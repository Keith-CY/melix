#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${MELIX_RUNTIME_DIR:-$ROOT/.runtime/phase1}"
RUNTIME_DIR="$(python3 - "$RUNTIME_DIR" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve())
PY
)"
PYTHON_SOCKET_PATH="${MELIX_WORKER_SOCKET_PATH:-$RUNTIME_DIR/python-worker.sock}"
SWIFT_TEXT_WORKER_SOCKET_PATH="${MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH:-$RUNTIME_DIR/swift-text-worker.sock}"
CONTROL_PLANE_METRICS_PATH="${MELIX_CONTROL_PLANE_METRICS_PATH:-$RUNTIME_DIR/control-plane-metrics.json}"
SWIFT_TEXT_WORKER_METRICS_PATH="${MELIX_SWIFT_TEXT_WORKER_METRICS_PATH:-$RUNTIME_DIR/swift-text-worker-metrics.json}"

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

rm -f \
  "$PYTHON_SOCKET_PATH" \
  "$SWIFT_TEXT_WORKER_SOCKET_PATH" \
  "$CONTROL_PLANE_METRICS_PATH" \
  "$SWIFT_TEXT_WORKER_METRICS_PATH" \
  "$RUNTIME_DIR/env.sh"

if [[ -d "$RUNTIME_DIR" ]]; then
  rmdir "$RUNTIME_DIR" 2>/dev/null || true
fi

echo "Melix local stack is stopped."
