#!/usr/bin/env bash

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

coverage_root="${repo_root}/.runtime/backend-model-identity-coverage"
python_coverage="${coverage_root}/python-coverage.json"
diff_from="${MELIX_BACKEND_IDENTITY_COVERAGE_DIFF_FROM:-HEAD}"
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

  local coverage_output
  local coverage_status
  if coverage_output="$("$@" 2>&1)"; then
    coverage_status=0
  else
    coverage_status=$?
  fi
  printf '%s\n' "${coverage_output}"

  if (( coverage_status == 0 )); then
    return 0
  fi
  if [[ "${scope_mode}" != "unfiltered" ]]; then
    while IFS= read -r coverage_line; do
      if [[ "${coverage_line}" == $'TOTAL\t100.00%\t0/0' ]]; then
        return 0
      fi
    done <<< "${coverage_output}"
  fi
  return "${coverage_status}"
}

PYTHONPATH="${repo_root}:${repo_root}/services/mlx-worker-python" \
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --frozen --project services/mlx-worker-python coverage run \
  --data-file "${coverage_root}/.coverage" \
  -m pytest -q \
  services/mlx-worker-python/tests/test_backend_model_identity.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_backend_model_identity_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_engine_generate_usage_token_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

PYTHONPATH="${repo_root}:${repo_root}/services/mlx-worker-python" \
UV_CACHE_DIR="${repo_root}/.uv-cache" \
uv run --frozen --project services/mlx-worker-python coverage json \
  --data-file "${coverage_root}/.coverage" \
  -o "${python_coverage}"

UV_CACHE_DIR="${repo_root}/.uv-cache" run_changed_line_coverage \
  "${coverage_scope_mode}" \
  uv run --python 3.12 python \
    scripts/python_changed_line_coverage.py \
    --coverage-json "${python_coverage}" \
    --diff-from "${diff_from}" \
    services/mlx-worker-python/worker/engine/engine_core.py \
    services/mlx-worker-python/worker/grpc_server.py \
    services/mlx-worker-python/worker/registry.py \
    services/mlx-worker-python/tests/test_backend_model_identity.py \
    services/mlx-worker-python/tests/test_pr_scoped_performance.py \
    scripts/backend_model_identity_probe.py \
    scripts/engine_generate_usage_token_probe.py

control_identity_test_filters=(
  'BackendModelIdentityTests'
  'ControlPlaneServiceTests'
  'OpenAIHandlerTests'
  'SSEStreamWriterTests'
  'OnDemandModelLoaderTests'
  'PythonBridgeWorkerClientTests'
  'WorkerRegistryTests'
  'HTTPGatewayTests.RequestCoordinatorTests/configuredCatalogRequiresBackendBinding()'
  'HTTPGatewayTests.RequestCoordinatorTests/emptyBackendStreamRecoversBeforeResponse()'
  'HTTPGatewayTests.RequestCoordinatorTests/repeatedEmptyBackendStreamExhaustsRecovery()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendStreamWithoutTerminalIsPartial()'
  'HTTPGatewayTests.RequestCoordinatorTests/completedBackendStreamDropsTrailingEvents()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendStreamCreationWithoutSemanticOutputRemainsReplaySafe()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendAdmissionSuppressesLaterTransportReplay()'
  'HTTPGatewayTests.RequestCoordinatorTests/externalWorkerPreResponseFailureMatrix'
  'HTTPGatewayTests.RequestCoordinatorTests/reusedBackendEndpointRequiresReplacementIdentity()'
  'HTTPGatewayTests.RequestCoordinatorTests/repeatedIdentityMismatchEventsExhaustOneRetry()'
  'HTTPGatewayTests.RequestCoordinatorTests/identityMismatchEventAfterTokenOutputIsNeverReplayed()'
  'HTTPGatewayTests.RequestCoordinatorTests/identityMismatchRecoveryLoadFailureIsTypedAsExhausted()'
  'HTTPGatewayTests.RequestCoordinatorTests/transportRecoveryLoadFailureIsTypedAsExhausted()'
  'HTTPGatewayTests.RequestCoordinatorTests/concurrentIdentityMismatchDispatchesCoalesceOneFreshBinding()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendIdentityRecoveryProbeEmitsMeasuredControlPlaneEvidence()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendTransportFailureAfterTokenOutputIsTypedAndNeverReplayed()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendTransportFailureAfterCompletedToolOutputIsTypedAndNeverReplayed()'
  'HTTPGatewayTests.RequestCoordinatorTests/backendPreResponseRetryExhaustionReturnsAStableTypedFailure()'
)
control_profile_root="${coverage_root}/control-profiles"
control_merged_profile="${coverage_root}/control-merged.profdata"
control_profiles=()
mkdir -p "${control_profile_root}"

control_profile_index=0
for control_filter in "${control_identity_test_filters[@]}"; do
  CLANG_MODULE_CACHE_PATH="${repo_root}/.build/ModuleCache.noindex/backend-model-identity-control" \
  xcrun swift test \
    --no-parallel \
    --package-path services/control-plane-swift \
    --enable-code-coverage \
    --filter "${control_filter}"

  control_bin_dir="$(xcrun swift build --package-path services/control-plane-swift --show-bin-path)"
  printf -v control_profile '%s/control-%02d.profdata' \
    "${control_profile_root}" "${control_profile_index}"
  cp "${control_bin_dir}/codecov/default.profdata" "${control_profile}"
  control_profiles+=("${control_profile}")
  control_profile_index=$((control_profile_index + 1))
done

xcrun llvm-profdata merge -sparse \
  "${control_profiles[@]}" \
  -o "${control_merged_profile}"

UV_CACHE_DIR="${repo_root}/.uv-cache" run_changed_line_coverage \
  "${coverage_scope_mode}" \
  uv run --python 3.12 python \
    scripts/swift_changed_line_coverage.py \
    --binary "${control_bin_dir}/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests" \
    --profdata "${control_merged_profile}" \
    --diff-from "${diff_from}" \
    services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift \
    services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift \
    services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift \
    services/control-plane-swift/Sources/Requests/RequestCoordinator.swift \
    services/control-plane-swift/Sources/WorkerClient/BackendModelIdentityStamping.swift \
    services/control-plane-swift/Sources/WorkerClient/BackendRouteRecoveryCoordinator.swift \
    services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift \
    services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift \
    services/control-plane-swift/Sources/WorkerClient/SwiftTextWorkerClient.swift \
    services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift \
    services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift \
    services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift

text_worker_identity_tests='WorkerScaffoldTests/(testBackendIdentity|testBoundarySnapshotRestoreSurvivesRestartAndPreservesExecutionMetadata|testCompleteBackendIdentity|testConfigurationDefaultsPreferDedicatedWorkerIdentity|testDecodeRejectsUnownedOrCrossResidencyPrefillContext|testGenerateReturnsRetriableIdentityMismatch|testHandshakeReturnsExpectedRuntimeMetadata|testLoadedIdentityUsesResolvedSwiftModelAndAdapterInsteadOfClaimedLoadIdentity|testPrefillCanRestoreBoundarySnapshotsFromCacheHints|testPrefillReturnsDecodeHandleAndMetricsForLoadedModel|testPrefillReturnsRetriableIdentityMismatch|testRuntimeRegistryAllowsUnloadWhileAnotherModelIsActive|testRuntimeRegistryCompletesPendingForcedUnloadForSharedResidency|testRuntimeRegistryDefersTargetUnloadUntilItsLastRequestFinishes|testRuntimeRegistryPromotesReusedResidencyToPinnedWithoutReloading|testRuntimeRegistryWaitsForForceUnloadBeforeReloadingSameResidency|testRuntimeUnloadComparesBackendIdentityAtomically|testSwiftTextModelFamilyIDRequiresGemmaIdentityMetadata|testVisionHandshakeReturnsVisionWorkerFamilyMetadata|testVisionPayloadReceiptIsWrittenAsynchronously|testWorkerRuntimeRegistryErrorExposesPrefillGuardMetadataAndMappings|testWorkerServiceRejectsStaleLoadEpochBeforeRuntimeWork)'

CLANG_MODULE_CACHE_PATH="${repo_root}/.build/ModuleCache.noindex/backend-model-identity-text-worker" \
xcrun swift test \
  --no-parallel \
  --package-path services/mlx-text-worker-swift \
  --enable-code-coverage \
  --filter "${text_worker_identity_tests}"

text_worker_bin_dir="$(xcrun swift build --package-path services/mlx-text-worker-swift --show-bin-path)"
UV_CACHE_DIR="${repo_root}/.uv-cache" run_changed_line_coverage \
  "${coverage_scope_mode}" \
  uv run --python 3.12 python \
    scripts/swift_changed_line_coverage.py \
    --binary "${text_worker_bin_dir}/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests" \
    --profdata "${text_worker_bin_dir}/codecov/default.profdata" \
    --diff-from "${diff_from}" \
    services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift \
    services/mlx-text-worker-swift/Sources/Core/Inference/TextGenerationEngine.swift \
    services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift \
    services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift \
    services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift
