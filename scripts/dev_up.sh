#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${MELIX_RUNTIME_DIR:-/tmp/melix-phase0}"
SOCKET_PATH="${MELIX_WORKER_SOCKET_PATH:-$RUNTIME_DIR/worker.sock}"
HTTP_PORT="${MELIX_HTTP_PORT:-11434}"
BACKEND_MODE="${MELIX_BACKEND_MODE:-deterministic}"
UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uv-cache}"
SWIFT_HOME="${MELIX_SWIFT_HOME:-$ROOT/.swift-home}"
CLANG_MODULE_CACHE_PATH="${MELIX_CLANG_MODULE_CACHE_PATH:-$ROOT/.build/ModuleCache.noindex}"

mkdir -p "$RUNTIME_DIR" "$UV_CACHE_DIR" "$SWIFT_HOME" "$CLANG_MODULE_CACHE_PATH"

if [[ -f "$RUNTIME_DIR/worker.pid" ]] || [[ -f "$RUNTIME_DIR/control-plane.pid" ]]; then
  echo "Melix runtime metadata already exists in $RUNTIME_DIR. Run scripts/dev_down.sh first." >&2
  exit 1
fi

rm -f "$SOCKET_PATH"

PYTHONPATH="$ROOT:$ROOT/services/mlx-worker-python" \
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv run --project "$ROOT/services/mlx-worker-python" \
python -m worker.bootstrap \
  --socket-path "$SOCKET_PATH" \
  --backend-mode "$BACKEND_MODE" \
  >"$RUNTIME_DIR/worker.log" 2>&1 &
WORKER_PID=$!
echo "$WORKER_PID" >"$RUNTIME_DIR/worker.pid"

MELIX_HTTP_PORT="$HTTP_PORT" \
MELIX_WORKER_SOCKET_PATH="$SOCKET_PATH" \
MELIX_REPO_ROOT="$ROOT" \
HOME="$SWIFT_HOME" \
CLANG_MODULE_CACHE_PATH="$CLANG_MODULE_CACHE_PATH" \
swift run --package-path "$ROOT/services/control-plane-swift" melix-control-plane \
  >"$RUNTIME_DIR/control-plane.log" 2>&1 &
CONTROL_PLANE_PID=$!
echo "$CONTROL_PLANE_PID" >"$RUNTIME_DIR/control-plane.pid"

cat >"$RUNTIME_DIR/env.sh" <<EOF
export MELIX_RUNTIME_DIR="$RUNTIME_DIR"
export MELIX_WORKER_SOCKET_PATH="$SOCKET_PATH"
export MELIX_HTTP_PORT="$HTTP_PORT"
export MELIX_BACKEND_MODE="$BACKEND_MODE"
EOF

READY=0
for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$HTTP_PORT/v1/models" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "$READY" -ne 1 ]]; then
  echo "Melix did not become ready. See $RUNTIME_DIR/control-plane.log and $RUNTIME_DIR/worker.log." >&2
  exit 1
fi

echo "Melix phase-0 stack is ready."
echo "HTTP: http://127.0.0.1:$HTTP_PORT"
echo "Worker socket: $SOCKET_PATH"
echo "Runtime env file: $RUNTIME_DIR/env.sh"
