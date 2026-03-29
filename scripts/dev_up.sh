#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFER_BUILT=0

usage() {
  cat <<'EOF'
Usage: bash scripts/dev_up.sh [--prefer-built]

Options:
  --prefer-built  Start Swift processes from existing built executables under .build/debug when available.
                  This keeps the Python worker on uv run and fails fast if the required Swift binaries are missing.
EOF
}

parse_dev_up_args() {
  while (($# > 0)); do
    case "$1" in
      --prefer-built)
        PREFER_BUILT=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
}

resolve_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve())
PY
}

resolve_built_swift_product_binary() {
  local package_path="$1"
  local product_name="$2"
  local build_root="$ROOT/$package_path/.build"
  local candidate="$build_root/debug/$product_name"

  if [[ -x "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  while IFS= read -r candidate; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(find "$build_root" -path "*/debug/$product_name" -type f 2>/dev/null | sort)

  echo "Built Swift product is missing for '$product_name' under $build_root." >&2
  echo "Run \`make swift-test\` or \`swift build --package-path $ROOT/$package_path\` before using --prefer-built." >&2
  return 1
}

build_swift_launch_command() {
  local package_path="$1"
  local product_name="$2"

  if [[ "$PREFER_BUILT" -eq 1 ]]; then
    resolve_built_swift_product_binary "$package_path" "$product_name"
  else
    printf '%s\n' swift run --package-path "$ROOT/$package_path" "$product_name"
  fi
}

main() {
  parse_dev_up_args "$@"

  local runtime_dir="${MELIX_RUNTIME_DIR:-$ROOT/.runtime/phase1}"
  runtime_dir="$(resolve_path "$runtime_dir")"
  local python_socket_path="${MELIX_WORKER_SOCKET_PATH:-$runtime_dir/python-worker.sock}"
  local swift_text_worker_socket_path="${MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH:-$runtime_dir/swift-text-worker.sock}"
  local control_plane_metrics_path="${MELIX_CONTROL_PLANE_METRICS_PATH:-$runtime_dir/control-plane-metrics.json}"
  local swift_text_worker_metrics_path="${MELIX_SWIFT_TEXT_WORKER_METRICS_PATH:-$runtime_dir/swift-text-worker-metrics.json}"
  local python_worker_metrics_path="${MELIX_PYTHON_WORKER_METRICS_PATH:-$runtime_dir/python-worker-metrics.json}"
  local http_port="${MELIX_HTTP_PORT:-11434}"
  local python_backend_mode="${MELIX_BACKEND_MODE:-deterministic}"
  local swift_text_worker_backend_mode="${MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE:-deterministic}"
  local uv_cache_dir="${UV_CACHE_DIR:-$ROOT/.uv-cache}"
  local swift_home="${MELIX_SWIFT_HOME:-$ROOT/.swift-home}"
  local clang_module_cache_path="${MELIX_CLANG_MODULE_CACHE_PATH:-$ROOT/.build/ModuleCache.noindex}"

  mkdir -p "$runtime_dir" "$uv_cache_dir" "$swift_home" "$clang_module_cache_path"

  if [[ -f "$runtime_dir/swift-text-worker.pid" ]] || [[ -f "$runtime_dir/python-worker.pid" ]] || [[ -f "$runtime_dir/control-plane.pid" ]]; then
    echo "Melix runtime metadata already exists in $runtime_dir. Run scripts/dev_down.sh first." >&2
    exit 1
  fi

  rm -f "$python_socket_path" "$swift_text_worker_socket_path"
  rm -f "$control_plane_metrics_path" "$swift_text_worker_metrics_path" "$python_worker_metrics_path"

  local swift_text_worker_command_output
  swift_text_worker_command_output="$(build_swift_launch_command "services/mlx-text-worker-swift" "melix-text-worker-swift")"
  local -a swift_text_worker_command
  mapfile -t swift_text_worker_command <<<"$swift_text_worker_command_output"

  local swift_text_worker_startup_t0_ns
  swift_text_worker_startup_t0_ns="$(python3 -c 'import time; print(time.perf_counter_ns())')"

  local swift_text_worker_pid
  swift_text_worker_pid="$(
    python3 "$ROOT/scripts/spawn_background.py" \
      --cwd "$ROOT" \
      --log-path "$runtime_dir/swift-text-worker.log" \
      --env "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH=$swift_text_worker_socket_path" \
      --env "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=$swift_text_worker_backend_mode" \
      --env "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH=$swift_text_worker_metrics_path" \
      --env "MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS=$swift_text_worker_startup_t0_ns" \
      --env "MELIX_DEV_TEXT_MODEL_PATH=${MELIX_DEV_TEXT_MODEL_PATH:-}" \
      --env "HOME=$swift_home" \
      --env "CLANG_MODULE_CACHE_PATH=$clang_module_cache_path" \
      -- \
      "${swift_text_worker_command[@]}"
  )"
  echo "$swift_text_worker_pid" >"$runtime_dir/swift-text-worker.pid"

  PYTHONPATH="$ROOT:$ROOT/services/mlx-worker-python" \
  UV_CACHE_DIR="$uv_cache_dir" \
  uv run --project "$ROOT/services/mlx-worker-python" \
  python "$ROOT/scripts/wait_for_worker_ready.py" \
    --socket-path "$swift_text_worker_socket_path" \
    >"$runtime_dir/swift-text-worker.ready.log" 2>&1

  local python_worker_startup_t0_ns
  python_worker_startup_t0_ns="$(python3 -c 'import time; print(time.perf_counter_ns())')"

  local python_worker_pid
  python_worker_pid="$(
    python3 "$ROOT/scripts/spawn_background.py" \
      --cwd "$ROOT" \
      --log-path "$runtime_dir/python-worker.log" \
      --env "PYTHONPATH=$ROOT:$ROOT/services/mlx-worker-python" \
      --env "UV_CACHE_DIR=$uv_cache_dir" \
      --env "MELIX_PYTHON_WORKER_METRICS_PATH=$python_worker_metrics_path" \
      --env "MELIX_PYTHON_WORKER_STARTUP_T0_NS=$python_worker_startup_t0_ns" \
      -- \
      uv run --project "$ROOT/services/mlx-worker-python" \
        python -m worker.bootstrap \
        --socket-path "$python_socket_path" \
        --backend-mode "$python_backend_mode"
  )"
  echo "$python_worker_pid" >"$runtime_dir/python-worker.pid"

  PYTHONPATH="$ROOT:$ROOT/services/mlx-worker-python" \
  UV_CACHE_DIR="$uv_cache_dir" \
  uv run --project "$ROOT/services/mlx-worker-python" \
  python "$ROOT/scripts/wait_for_worker_ready.py" \
    --socket-path "$python_socket_path" \
    >"$runtime_dir/python-worker.ready.log" 2>&1

  local control_plane_command_output
  control_plane_command_output="$(build_swift_launch_command "services/control-plane-swift" "melix-control-plane")"
  local -a control_plane_command
  mapfile -t control_plane_command <<<"$control_plane_command_output"

  local control_plane_pid
  control_plane_pid="$(
    python3 "$ROOT/scripts/spawn_background.py" \
      --cwd "$ROOT" \
      --log-path "$runtime_dir/control-plane.log" \
      --env "MELIX_HTTP_PORT=$http_port" \
      --env "MELIX_WORKER_SOCKET_PATH=$python_socket_path" \
      --env "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH=$swift_text_worker_socket_path" \
      --env "MELIX_REPO_ROOT=$ROOT" \
      --env "MELIX_CONTROL_PLANE_METRICS_PATH=$control_plane_metrics_path" \
      --env "HOME=$swift_home" \
      --env "CLANG_MODULE_CACHE_PATH=$clang_module_cache_path" \
      -- \
      "${control_plane_command[@]}"
  )"
  echo "$control_plane_pid" >"$runtime_dir/control-plane.pid"

  cat >"$runtime_dir/env.sh" <<EOF
export MELIX_RUNTIME_DIR="$runtime_dir"
export MELIX_WORKER_SOCKET_PATH="$python_socket_path"
export MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="$swift_text_worker_socket_path"
export MELIX_HTTP_PORT="$http_port"
export MELIX_BACKEND_MODE="$python_backend_mode"
export MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE="$swift_text_worker_backend_mode"
export MELIX_CONTROL_PLANE_METRICS_PATH="$control_plane_metrics_path"
export MELIX_SWIFT_TEXT_WORKER_METRICS_PATH="$swift_text_worker_metrics_path"
export MELIX_PYTHON_WORKER_METRICS_PATH="$python_worker_metrics_path"
EOF

  local ready=0
  for _ in $(seq 1 240); do
    if curl -fsS "http://127.0.0.1:$http_port/v1/models" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.5
  done

  if [[ "$ready" -ne 1 ]]; then
    echo "Melix did not become ready. See $runtime_dir/control-plane.log, $runtime_dir/swift-text-worker.log, and $runtime_dir/python-worker.log." >&2
    exit 1
  fi

  echo "Melix local stack is ready."
  echo "HTTP: http://127.0.0.1:$http_port"
  echo "Swift text worker socket: $swift_text_worker_socket_path"
  echo "Python compatibility worker socket: $python_socket_path"
  echo "Control plane metrics: $control_plane_metrics_path"
  echo "Swift text worker metrics: $swift_text_worker_metrics_path"
  echo "Python worker metrics: $python_worker_metrics_path"
  echo "Runtime env file: $runtime_dir/env.sh"

  if [[ "$PREFER_BUILT" -eq 1 ]]; then
    echo "Swift launch mode: prefer-built"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
