#!/usr/bin/env bash

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

coverage_root="${repo_root}/.runtime/paged-kv-cache-coverage"
diff_from="${MELIX_PAGED_KV_COVERAGE_DIFF_FROM:-origin/main}"
mkdir -p "${coverage_root}" "${repo_root}/.uv-cache"

PYTHONPATH="${repo_root}:${repo_root}/services/mlx-worker-python" \
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --frozen --project services/mlx-worker-python pytest -q \
  tests/test_paged_kv_cache_probe.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

HOME="${repo_root}/.swift-home/paged-kv-cache-coverage" \
CLANG_MODULE_CACHE_PATH="${repo_root}/.build/ModuleCache.noindex/paged-kv-cache-coverage" \
xcrun swift test \
  --package-path services/mlx-text-worker-swift \
  --enable-code-coverage \
  --filter WorkerScaffoldTests

bin_dir="$(xcrun swift build --package-path services/mlx-text-worker-swift --show-bin-path)"
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --python 3.12 python3 scripts/swift_changed_line_coverage.py \
  --binary "${bin_dir}/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests" \
  --profdata "${bin_dir}/codecov/default.profdata" \
  --diff-from "${diff_from}" \
  services/mlx-text-worker-swift/Sources/Core/Runtime/PagedKVCache.swift \
  services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift \
  services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift \
  services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift \
  services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift \
  services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift
