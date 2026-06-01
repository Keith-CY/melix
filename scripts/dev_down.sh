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
ENV_PATH="$RUNTIME_DIR/env.sh"
if [[ -f "$ENV_PATH" ]]; then
  # Reuse the recorded runtime contract so callers only need MELIX_RUNTIME_DIR
  # to stop instances that were started with automatic short socket paths.
  # shellcheck source=/dev/null
  source "$ENV_PATH"
fi
SERVICE_INSTANCE_NAME="${MELIX_SERVICE_INSTANCE_NAME:-}"
SOCKET_DIR="${MELIX_SOCKET_DIR:-/tmp}"
default_socket_path() {
  python3 - "$ROOT" "$SOCKET_DIR" "$SERVICE_INSTANCE_NAME" "$1" <<'PY'
import hashlib
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
socket_dir = Path(sys.argv[2]).expanduser().resolve()
instance = sys.argv[3].strip().lower() or "phase1"
role = sys.argv[4]
normalized = re.sub(r"[^a-z0-9-]+", "-", instance).strip("-") or "default"
if len(normalized) > 32:
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    normalized = f"{normalized[:23].rstrip('-')}-{digest}"
repo_hash = hashlib.sha1(str(repo_root).encode("utf-8")).hexdigest()[:10]
print(socket_dir / f"melix-{normalized}-{repo_hash}-{role}.sock")
PY
}
PYTHON_SOCKET_PATH="${MELIX_WORKER_SOCKET_PATH:-$(default_socket_path python)}"
SWIFT_TEXT_WORKER_SOCKET_PATH="${MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH:-$(default_socket_path swift)}"
SWIFT_VISION_WORKER_SOCKET_PATH="${MELIX_SWIFT_VISION_WORKER_SOCKET_PATH:-$(default_socket_path swift-vision)}"
CONTROL_PLANE_METRICS_PATH="${MELIX_CONTROL_PLANE_METRICS_PATH:-$RUNTIME_DIR/control-plane-metrics.json}"
SWIFT_TEXT_WORKER_METRICS_PATH="${MELIX_SWIFT_TEXT_WORKER_METRICS_PATH:-$RUNTIME_DIR/swift-text-worker-metrics.json}"
SWIFT_VISION_WORKER_METRICS_PATH="${MELIX_SWIFT_VISION_WORKER_METRICS_PATH:-$RUNTIME_DIR/swift-vision-worker-metrics.json}"
PYTHON_WORKER_METRICS_PATH="${MELIX_PYTHON_WORKER_METRICS_PATH:-$RUNTIME_DIR/python-worker-metrics.json}"

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

stop_pid_file "$RUNTIME_DIR/menubar.pid"
stop_pid_file "$RUNTIME_DIR/control-plane.pid"
stop_pid_file "$RUNTIME_DIR/python-worker.pid"
stop_pid_file "$RUNTIME_DIR/swift-vision-worker.pid"
stop_pid_file "$RUNTIME_DIR/swift-text-worker.pid"

rm -f \
  "$PYTHON_SOCKET_PATH" \
  "$SWIFT_TEXT_WORKER_SOCKET_PATH" \
  "$SWIFT_VISION_WORKER_SOCKET_PATH" \
  "$CONTROL_PLANE_METRICS_PATH" \
  "$SWIFT_TEXT_WORKER_METRICS_PATH" \
  "$SWIFT_VISION_WORKER_METRICS_PATH" \
  "$PYTHON_WORKER_METRICS_PATH" \
  "$RUNTIME_DIR/env.sh"

if [[ -d "$RUNTIME_DIR" ]]; then
  rmdir "$RUNTIME_DIR" 2>/dev/null || true
fi

echo "Melix local stack is stopped."
