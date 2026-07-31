#!/usr/bin/env bash

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

coverage_root="${repo_root}/.runtime/backend-model-identity-coverage"
python_coverage="${coverage_root}/python-coverage.json"
diff_from="${MELIX_BACKEND_IDENTITY_COVERAGE_DIFF_FROM:-HEAD}"
mkdir -p "${coverage_root}" "${repo_root}/.uv-cache"

PYTHONPATH="${repo_root}:${repo_root}/services/mlx-worker-python" \
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --frozen --project services/mlx-worker-python coverage run \
  --data-file "${coverage_root}/.coverage" \
  -m pytest -q \
  services/mlx-worker-python/tests/test_backend_model_identity.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_backend_model_identity_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

PYTHONPATH="${repo_root}:${repo_root}/services/mlx-worker-python" \
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --frozen --project services/mlx-worker-python coverage json \
  --data-file "${coverage_root}/.coverage" \
  -o "${python_coverage}"

python3 scripts/changed_scope_coverage.py \
  --coverage-json "${python_coverage}" \
  services/mlx-worker-python/worker/grpc_server.py \
  services/mlx-worker-python/worker/registry.py \
  services/mlx-worker-python/tests/test_backend_model_identity.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/backend_model_identity_probe.py

CLANG_MODULE_CACHE_PATH="${repo_root}/.build/ModuleCache.noindex/backend-model-identity-control" \
xcrun swift test \
  --package-path services/control-plane-swift \
  --enable-code-coverage \
  --skip SiblingFileAdvisoryLockTests

control_bin_dir="$(xcrun swift build --package-path services/control-plane-swift --show-bin-path)"
UV_CACHE_DIR="${repo_root}/.uv-cache" uv run --python 3.12 python \
  scripts/swift_changed_line_coverage.py \
  --binary "${control_bin_dir}/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests" \
  --profdata "${control_bin_dir}/codecov/default.profdata" \
  --diff-from "${diff_from}" \
  services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift \
  services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift \
  services/control-plane-swift/Sources/Requests/RequestCoordinator.swift \
  services/control-plane-swift/Sources/WorkerClient/BackendModelIdentityStamping.swift \
  services/control-plane-swift/Sources/WorkerClient/BackendRouteRecoveryCoordinator.swift \
  services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift \
  services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift \
  services/control-plane-swift/Sources/WorkerClient/SwiftTextWorkerClient.swift \
  services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift \
  services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift

CLANG_MODULE_CACHE_PATH="${repo_root}/.build/ModuleCache.noindex/backend-model-identity-text-worker" \
xcrun swift test \
  --package-path services/mlx-text-worker-swift \
  --enable-code-coverage

text_worker_bin_dir="$(xcrun swift build --package-path services/mlx-text-worker-swift --show-bin-path)"
UV_CACHE_DIR="${repo_root}/.uv-cache" uv run --python 3.12 python \
  scripts/swift_changed_line_coverage.py \
  --binary "${text_worker_bin_dir}/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests" \
  --profdata "${text_worker_bin_dir}/codecov/default.profdata" \
  --diff-from "${diff_from}" \
  services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift \
  services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift
