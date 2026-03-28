#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${MELIX_RUNTIME_DIR:-$ROOT/.runtime/phase1}"
PYTHON_SOCKET_PATH="${MELIX_WORKER_SOCKET_PATH:-$RUNTIME_DIR/python-worker.sock}"
SWIFT_TEXT_WORKER_SOCKET_PATH="${MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH:-$RUNTIME_DIR/swift-text-worker.sock}"
HTTP_PORT="${MELIX_HTTP_PORT:-11434}"
PYTHON_BACKEND_MODE="${MELIX_BACKEND_MODE:-deterministic}"
SWIFT_TEXT_WORKER_BACKEND_MODE="${MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE:-deterministic}"
UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uv-cache}"
SWIFT_HOME="${MELIX_SWIFT_HOME:-$ROOT/.swift-home}"
CLANG_MODULE_CACHE_PATH="${MELIX_CLANG_MODULE_CACHE_PATH:-$ROOT/.build/ModuleCache.noindex}"

mkdir -p "$RUNTIME_DIR" "$UV_CACHE_DIR" "$SWIFT_HOME" "$CLANG_MODULE_CACHE_PATH"

if [[ -f "$RUNTIME_DIR/swift-text-worker.pid" ]] || [[ -f "$RUNTIME_DIR/python-worker.pid" ]] || [[ -f "$RUNTIME_DIR/control-plane.pid" ]]; then
  echo "Melix runtime metadata already exists in $RUNTIME_DIR. Run scripts/dev_down.sh first." >&2
  exit 1
fi

rm -f "$PYTHON_SOCKET_PATH" "$SWIFT_TEXT_WORKER_SOCKET_PATH"

SWIFT_TEXT_WORKER_PID="$(
  python3 "$ROOT/scripts/spawn_background.py" \
    --cwd "$ROOT" \
    --log-path "$RUNTIME_DIR/swift-text-worker.log" \
    --env "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH=$SWIFT_TEXT_WORKER_SOCKET_PATH" \
    --env "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=$SWIFT_TEXT_WORKER_BACKEND_MODE" \
    --env "MELIX_DEV_TEXT_MODEL_PATH=${MELIX_DEV_TEXT_MODEL_PATH:-}" \
    --env "HOME=$SWIFT_HOME" \
    --env "CLANG_MODULE_CACHE_PATH=$CLANG_MODULE_CACHE_PATH" \
    -- \
    swift run --package-path "$ROOT/services/mlx-text-worker-swift" melix-text-worker-swift
)"
echo "$SWIFT_TEXT_WORKER_PID" >"$RUNTIME_DIR/swift-text-worker.pid"

PYTHONPATH="$ROOT:$ROOT/services/mlx-worker-python" \
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv run --project "$ROOT/services/mlx-worker-python" \
python "$ROOT/scripts/wait_for_worker_ready.py" \
  --socket-path "$SWIFT_TEXT_WORKER_SOCKET_PATH" \
  >"$RUNTIME_DIR/swift-text-worker.ready.log" 2>&1

PYTHON_WORKER_PID="$(
  python3 "$ROOT/scripts/spawn_background.py" \
    --cwd "$ROOT" \
    --log-path "$RUNTIME_DIR/python-worker.log" \
    --env "PYTHONPATH=$ROOT:$ROOT/services/mlx-worker-python" \
    --env "UV_CACHE_DIR=$UV_CACHE_DIR" \
    -- \
    uv run --project "$ROOT/services/mlx-worker-python" \
      python -m worker.bootstrap \
      --socket-path "$PYTHON_SOCKET_PATH" \
      --backend-mode "$PYTHON_BACKEND_MODE"
)"
echo "$PYTHON_WORKER_PID" >"$RUNTIME_DIR/python-worker.pid"

PYTHONPATH="$ROOT:$ROOT/services/mlx-worker-python" \
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv run --project "$ROOT/services/mlx-worker-python" \
python "$ROOT/scripts/wait_for_worker_ready.py" \
  --socket-path "$PYTHON_SOCKET_PATH" \
  >"$RUNTIME_DIR/python-worker.ready.log" 2>&1

CONTROL_PLANE_PID="$(
  python3 "$ROOT/scripts/spawn_background.py" \
    --cwd "$ROOT" \
    --log-path "$RUNTIME_DIR/control-plane.log" \
    --env "MELIX_HTTP_PORT=$HTTP_PORT" \
    --env "MELIX_WORKER_SOCKET_PATH=$PYTHON_SOCKET_PATH" \
    --env "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH=$SWIFT_TEXT_WORKER_SOCKET_PATH" \
    --env "MELIX_REPO_ROOT=$ROOT" \
    --env "HOME=$SWIFT_HOME" \
    --env "CLANG_MODULE_CACHE_PATH=$CLANG_MODULE_CACHE_PATH" \
    -- \
    swift run --package-path "$ROOT/services/control-plane-swift" melix-control-plane
)"
echo "$CONTROL_PLANE_PID" >"$RUNTIME_DIR/control-plane.pid"

cat >"$RUNTIME_DIR/env.sh" <<EOF
export MELIX_RUNTIME_DIR="$RUNTIME_DIR"
export MELIX_WORKER_SOCKET_PATH="$PYTHON_SOCKET_PATH"
export MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="$SWIFT_TEXT_WORKER_SOCKET_PATH"
export MELIX_HTTP_PORT="$HTTP_PORT"
export MELIX_BACKEND_MODE="$PYTHON_BACKEND_MODE"
export MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE="$SWIFT_TEXT_WORKER_BACKEND_MODE"
EOF

READY=0
for _ in $(seq 1 240); do
  if curl -fsS "http://127.0.0.1:$HTTP_PORT/v1/models" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "$READY" -ne 1 ]]; then
  echo "Melix did not become ready. See $RUNTIME_DIR/control-plane.log, $RUNTIME_DIR/swift-text-worker.log, and $RUNTIME_DIR/python-worker.log." >&2
  exit 1
fi

echo "Melix phase-1 stack is ready."
echo "HTTP: http://127.0.0.1:$HTTP_PORT"
echo "Swift text worker socket: $SWIFT_TEXT_WORKER_SOCKET_PATH"
echo "Python compatibility worker socket: $PYTHON_SOCKET_PATH"
echo "Runtime env file: $RUNTIME_DIR/env.sh"
