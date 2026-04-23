#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="$ROOT/scripts/phase8_acceptance_bundle.py"
PROJECT_PATH="$ROOT/services/mlx-worker-python"
UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uv-cache}"
PYTHONPATH_VALUE="$ROOT:$ROOT/services/mlx-worker-python${PYTHONPATH:+:$PYTHONPATH}"

_python_supports_project() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1
}

_run_with_python() {
  local python_binary="$1"
  shift
  if ! _python_supports_project "$python_binary"; then
    printf 'Phase 8 acceptance requires Python 3.12+; rejected: %s\n' "$python_binary" >&2
    return 1
  fi
  PYTHONPATH="$PYTHONPATH_VALUE" exec "$python_binary" "$SCRIPT_PATH" "$@"
}

if [[ -n "${MELIX_PHASE8_ACCEPTANCE_PYTHON:-}" ]]; then
  _run_with_python "$MELIX_PHASE8_ACCEPTANCE_PYTHON" "$@"
fi

if command -v uv >/dev/null 2>&1; then
  PYTHONPATH="$PYTHONPATH_VALUE" UV_CACHE_DIR="$UV_CACHE_DIR" exec uv run \
    --project "$PROJECT_PATH" \
    --extra mlx \
    python "$SCRIPT_PATH" "$@"
fi

for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [[ -x "$candidate" ]] && _python_supports_project "$candidate"; then
    _run_with_python "$candidate" "$@"
  fi
done

candidate="$(command -v python3 || true)"
if [[ -n "$candidate" ]] && _python_supports_project "$candidate"; then
  _run_with_python "$candidate" "$@"
fi

cat >&2 <<'EOF'
Phase 8 acceptance could not find a usable Python runtime.
Install uv, set MELIX_PHASE8_ACCEPTANCE_PYTHON to Python 3.12+, or install a Python 3.12+ interpreter at /opt/homebrew/bin/python3.
EOF
exit 1
