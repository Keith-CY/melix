#!/usr/bin/env bash

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

coverage_root="${repo_root}/.runtime/paged-kv-cache-coverage"
diff_from="${MELIX_PAGED_KV_COVERAGE_DIFF_FROM:-origin/main}"
minimum_coverage_pct=95
mkdir -p "${coverage_root}" "${repo_root}/.uv-cache"

coverage_scope_mode="$(python3 - <<'PY'
import json
import os

raw = os.environ.get("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON", "").strip()
if not raw:
    print("unfiltered")
else:
    try:
        paths = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"invalid MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON: {exc}"
        ) from exc
    if not isinstance(paths, list):
        raise SystemExit("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON must be a JSON list")
    print("empty" if not paths else "filtered")
PY
)"

run_changed_line_coverage() {
  local scope_mode="$1"
  shift

  local output
  local status
  if output="$("$@" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  printf '%s\n' "${output}"

  if (( status == 0 )); then
    return 0
  fi
  if [[ "${scope_mode}" != "unfiltered" ]]; then
    while IFS= read -r coverage_line; do
      if [[ "${coverage_line}" == $'TOTAL\t100.00%\t0/0' ]]; then
        return 0
      fi
    done <<< "${output}"
  fi
  return "${status}"
}

PYTHONPATH="${repo_root}:${repo_root}/services/mlx-worker-python" \
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --frozen --project services/mlx-worker-python pytest -q \
  tests/test_paged_kv_cache_probe.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

MELIX_PAGED_KV_INSTRUMENTED_COVERAGE=1 \
HOME="${repo_root}/.swift-home/paged-kv-cache-coverage" \
CLANG_MODULE_CACHE_PATH="${repo_root}/.build/ModuleCache.noindex/paged-kv-cache-coverage" \
xcrun swift test \
  --package-path services/mlx-text-worker-swift \
  --enable-code-coverage \
  --filter WorkerScaffoldTests

bin_dir="$(xcrun swift build --package-path services/mlx-text-worker-swift --show-bin-path)"
if coverage_output="$({
  UV_CACHE_DIR="${repo_root}/.uv-cache" run_changed_line_coverage \
    "${coverage_scope_mode}" \
    uv run --python 3.12 python3 scripts/swift_changed_line_coverage.py \
    --binary "${bin_dir}/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests" \
    --profdata "${bin_dir}/codecov/default.profdata" \
    --diff-from "${diff_from}" \
    services/mlx-text-worker-swift/Sources/Core/Runtime/PagedKVCache.swift \
    services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift \
    services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift \
    services/mlx-text-worker-swift/Sources/Core/DiskCacheStore.swift \
    services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift \
    services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift \
    services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift
} 2>&1)"; then
  coverage_status=0
else
  coverage_status=$?
fi
printf '%s\n' "${coverage_output}"
if (( coverage_status != 0 )); then
  exit "${coverage_status}"
fi

awk -F '\t' -v minimum="${minimum_coverage_pct}" '
  $1 == "TOTAL" {
    gsub(/%/, "", $2)
    found = 1
    if (($2 + 0) < minimum) {
      printf "Paged KV changed-line coverage %.2f%% is below %.2f%%.\n", $2, minimum > "/dev/stderr"
      exit 1
    }
  }
  END {
    if (!found) {
      print "Paged KV changed-line coverage output is missing TOTAL." > "/dev/stderr"
      exit 1
    }
  }
' <<< "${coverage_output}"
