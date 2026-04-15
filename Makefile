ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
UV_CACHE_DIR := $(ROOT)/.uv-cache
SWIFT_HOME := $(ROOT)/.swift-home
CLANG_MODULE_CACHE_PATH := $(ROOT)/.build/ModuleCache.noindex
PROTOCOL_SWIFT_HOME := $(SWIFT_HOME)/protocol
TEXT_WORKER_SWIFT_HOME := $(SWIFT_HOME)/mlx-text-worker-swift
CONTROL_PLANE_SWIFT_HOME := $(SWIFT_HOME)/control-plane-swift
MENUBAR_SWIFT_HOME := $(SWIFT_HOME)/macos-menubar

PROTOCOL_MODULE_CACHE_PATH := $(CLANG_MODULE_CACHE_PATH)/protocol
TEXT_WORKER_MODULE_CACHE_PATH := $(CLANG_MODULE_CACHE_PATH)/mlx-text-worker-swift
CONTROL_PLANE_MODULE_CACHE_PATH := $(CLANG_MODULE_CACHE_PATH)/control-plane-swift
MENUBAR_MODULE_CACHE_PATH := $(CLANG_MODULE_CACHE_PATH)/macos-menubar

CONTROL_PLANE_TEST_FILTER_CONTROL := SnapshotStoreTests|BenchmarkExportBundleTests|ImageDefaultsStoreTests|SchedulerReadModelTests|ToolParserRegistryTests|GatewayConfigStoreTests|ChatTemplatePolicyTests|ImageJobReadModelTests|GatewayServingDefaultsStoreTests|MCPToolCatalogTests|ModelCatalogTests|MultimodalContractTests|ImageJobAdmissionControllerTests|StructuredOutputValidationTests|AudioAssetManagerTests|EventSubscriptionHubTests|CoreUtilityTests|ControlPlaneServiceTests|ControlPlaneChatExecutionTests|ControlPlaneServiceFastPathTests|TextEndpointContractTests
CONTROL_PLANE_TEST_FILTER_WORKER := PythonBridgeWorkerClientTests|SwiftTextWorkerClientTests|WorkerClientTests|WorkerRegistryTests|OnDemandModelLoaderTests
CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_A := \
	"HTTPGatewayTests.RequestCoordinatorTests/admittedRequestCancellationBeforeGenerateReturnsYieldsACancelledExecution()" \
	"HTTPGatewayTests.RequestCoordinatorTests/admittedTextRequestsRefreshModelRecencyForSameFamilyEvictionPlanning()" \
	"HTTPGatewayTests.RequestCoordinatorTests/cancelSucceedsWhenRequestTrackingExistsWithoutAnActiveWorker()" \
	"HTTPGatewayTests.RequestCoordinatorTests/cancellationRecordsPrefillAndDecodePhaseMetrics()" \
	"HTTPGatewayTests.RequestCoordinatorTests/cancellationTriggersWorkerAbort()" \
	"HTTPGatewayTests.RequestCoordinatorTests/cancellingUnknownRequestReturnsFalse()" \
	"HTTPGatewayTests.RequestCoordinatorTests/chunkedPrefillsEmitProgressEventsAndSchedulerMetricsForLongPrompts()" \
	"HTTPGatewayTests.RequestCoordinatorTests/coldSessionRequestsPreferBackgroundPrefillLanesBeforeReuseExists()" \
	"HTTPGatewayTests.RequestCoordinatorTests/disconnectGraceExpiryAbortsTheWorkerAndRecordsATerminalLifecycleFailure()" \
	"HTTPGatewayTests.RequestCoordinatorTests/disconnectGraceKeepsRequestResumeEligibleUntilANewConsumerAttaches()" \
	"HTTPGatewayTests.RequestCoordinatorTests/duplicateRequestIdentifiersAreRejectedWhileTracked()"
CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_B := \
	"HTTPGatewayTests.RequestCoordinatorTests/emptyModelIdentifiersAreRejectedBeforeDispatch()" \
	"HTTPGatewayTests.RequestCoordinatorTests/gatewayBatchingDefaultsCanDisableContinuousBatchAdmissions()" \
	"HTTPGatewayTests.RequestCoordinatorTests/gatewayBatchingDefaultsCanExpandContinuousBatchCapacity()" \
	"HTTPGatewayTests.RequestCoordinatorTests/gatewaySpeculativeDefaultsPopulateWorkerAccelerationWhenModelDefaultsAreUnspecified()" \
	"HTTPGatewayTests.RequestCoordinatorTests/generateFailuresPropagateWhenTheWorkerThrowsAGenericError()"
CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_C := \
	"HTTPGatewayTests.RequestCoordinatorTests/generateUnavailabilityIsSurfacedWithoutFallback()" \
	"HTTPGatewayTests.RequestCoordinatorTests/modelAccelerationDefaultsOverrideGatewaySpeculativeExecutionDefaults()" \
	"HTTPGatewayTests.RequestCoordinatorTests/multimodalVisionRequestsUseBackgroundLanes()" \
	"HTTPGatewayTests.RequestCoordinatorTests/ocrRequestsPublishVisionMetrics()" \
	"HTTPGatewayTests.RequestCoordinatorTests/partialRestorePlansRecordWalkBackMetricsAndMetadata()" \
	"HTTPGatewayTests.RequestCoordinatorTests/phaseAwareStreamEventsPreserveAccelerationMetadataAndTerminalAborts()"
CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_D := \
	"HTTPGatewayTests.RequestCoordinatorTests/phaseAwareTextRequestsJoinTheActiveContinuousBatchCohort()" \
	"HTTPGatewayTests.RequestCoordinatorTests/phaseAwareVLMRequestsPreserveToolParserMetadataAndStreamToolCallDeltas()" \
	"HTTPGatewayTests.RequestCoordinatorTests/queuedRequestCancellationSucceedsBeforeAWorkerIsBound()" \
	"HTTPGatewayTests.RequestCoordinatorTests/reasoningBudgetOverflowClipsCompletedReasoningOutputWithoutRequiringDeltas()" \
	"HTTPGatewayTests.RequestCoordinatorTests/reasoningBudgetOverflowTruncatesStreamedReasoningAndClosesTheRequestExplicitly()" \
	"HTTPGatewayTests.RequestCoordinatorTests/schedulerSnapshotsTrackCoordinatorLifecycle()" \
	"HTTPGatewayTests.RequestCoordinatorTests/secondRequestQueuesUntilTheActiveRequestReleasesAdmission()" \
	"HTTPGatewayTests.RequestCoordinatorTests/sessionFollowUpRequestsRestoreLatestBranchSnapshot()" \
	"HTTPGatewayTests.RequestCoordinatorTests/sessionTaggedRequestsHydrateSessionGraphRequestHeads()" \
	"HTTPGatewayTests.RequestCoordinatorTests/snapshotCreatedEventsHydrateBranchResumeMetadata()" \
	"HTTPGatewayTests.RequestCoordinatorTests/streamDisconnectHandlerRecordsDisconnectMetricsAndOpensAResumeGraceWindow()"
CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_E := \
	"HTTPGatewayTests.RequestCoordinatorTests/streamFailuresPropagateAndReleaseRequestTracking()" \
	"HTTPGatewayTests.RequestCoordinatorTests/swiftRouteFailureDoesNotFallBackToPythonTextExecution()" \
	"HTTPGatewayTests.RequestCoordinatorTests/textRequestsRouteToTheSwiftTextClientByDefault()" \
	"HTTPGatewayTests.RequestCoordinatorTests/textTTFTUnderMultimodalLoadIsRecordedSeparately()" \
	"HTTPGatewayTests.RequestCoordinatorTests/toolCallDeltasHydrateSessionGraphToolMetadata()" \
	"HTTPGatewayTests.RequestCoordinatorTests/videoBearingVLMRequestsPublishFramePolicyMetrics()" \
	"HTTPGatewayTests.RequestCoordinatorTests/videoBearingVLMRequestsStayDispatchableDuringIngressOnlyRollout()" \
	"HTTPGatewayTests.RequestCoordinatorTests/vlmRequestsPublishVisionMetrics()" \
	"HTTPGatewayTests.RequestCoordinatorTests/vlmRoutesUsePhaseAwarePrefillAndDecodeOnBackgroundLanes()" \
	"HTTPGatewayTests.RequestCoordinatorTests/warmFollowUpRequestsPreferHotPrefillLanesAndRefreshCacheObservability()" \
	"HTTPGatewayTests.RequestCoordinatorTests/workerStreamEventsAdvanceSchedulerProgressThroughPrefillAndDecode()" \
	"HTTPGatewayTests.RequestCoordinatorTests/workerUnavailableRequestsAreRejected()"
CONTROL_PLANE_TEST_FILTER_OPENAI := OpenAIHandlerTests
CONTROL_PLANE_TEST_FILTER_HTTP_REST := RichOutputSanitizerTests|PersistentAuthSessionStoreTests|ProtocolCompatibilityMatrixTests|ConnectionLifecyclePolicyTests|SSEStreamWriterTests

.PHONY: bootstrap proto proto-check swift-build-integration-prereqs swift-test py-test integration-test package-smoke swift-coverage py-coverage coverage phase1-metrics phase2-metrics phase5-metrics phase6-metrics phase7-metrics phase8-acceptance phase8-real-e2e phase8-install-smoke phase8-release-gate phase8-metrics phase17-metrics

PHASE1_METRICS_ARGS ?=
PHASE2_METRICS_ARGS ?=
PHASE17_METRICS_ARGS ?=
PHASE8_ACCEPTANCE_ARGS ?=
PHASE8_REAL_E2E_ARGS ?=
PHASE8_INSTALL_SMOKE_ARGS ?=
PHASE8_RELEASE_GATE_ARGS ?=
PHASE8_METRICS_ARGS ?=

bootstrap:
	mkdir -p "$(UV_CACHE_DIR)" "$(SWIFT_HOME)" "$(CLANG_MODULE_CACHE_PATH)"
	UV_CACHE_DIR="$(UV_CACHE_DIR)" uv sync --project services/mlx-worker-python --extra mlx

proto:
	./scripts/proto_gen.sh

proto-check: proto
	git diff --exit-code -- packages/protocol/descriptors packages/protocol/python packages/protocol/swift

swift-build-integration-prereqs:
	/bin/zsh -lc 'set -e; \
	mkdir -p "$(TEXT_WORKER_SWIFT_HOME)" "$(CONTROL_PLANE_SWIFT_HOME)"; \
	mkdir -p "$(TEXT_WORKER_MODULE_CACHE_PATH)" "$(CONTROL_PLANE_MODULE_CACHE_PATH)"; \
	HOME="$(TEXT_WORKER_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(TEXT_WORKER_MODULE_CACHE_PATH)" xcrun swift build --package-path services/mlx-text-worker-swift --product melix-text-worker-swift --disable-automatic-resolution; \
	HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift build --package-path services/control-plane-swift --product melix-control-plane --disable-automatic-resolution'

swift-test:
	/bin/zsh -lc 'set -e; \
	mkdir -p "$(PROTOCOL_SWIFT_HOME)" "$(TEXT_WORKER_SWIFT_HOME)" "$(CONTROL_PLANE_SWIFT_HOME)" "$(MENUBAR_SWIFT_HOME)"; \
	mkdir -p "$(PROTOCOL_MODULE_CACHE_PATH)" "$(TEXT_WORKER_MODULE_CACHE_PATH)" "$(CONTROL_PLANE_MODULE_CACHE_PATH)" "$(MENUBAR_MODULE_CACHE_PATH)"; \
	HOME="$(PROTOCOL_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(PROTOCOL_MODULE_CACHE_PATH)" xcrun swift test --package-path packages/protocol/swift; \
	HOME="$(TEXT_WORKER_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(TEXT_WORKER_MODULE_CACHE_PATH)" xcrun swift test --package-path services/mlx-text-worker-swift; \
	HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift test --no-parallel --package-path services/control-plane-swift --filter "$(CONTROL_PLANE_TEST_FILTER_CONTROL)"; \
	for specifier in $(CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_A) $(CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_B) $(CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_C) $(CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_D) $(CONTROL_PLANE_REQUEST_COORDINATOR_SPECIFIERS_E); do \
		HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift test --no-parallel --package-path services/control-plane-swift --filter "$$specifier"; \
	done; \
	HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift test --no-parallel --package-path services/control-plane-swift --filter "$(CONTROL_PLANE_TEST_FILTER_OPENAI)"; \
	HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift test --no-parallel --package-path services/control-plane-swift --filter "$(CONTROL_PLANE_TEST_FILTER_HTTP_REST)"; \
	HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift test --no-parallel --package-path services/control-plane-swift --filter "$(CONTROL_PLANE_TEST_FILTER_WORKER)"; \
	HOME="$(MENUBAR_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(MENUBAR_MODULE_CACHE_PATH)" xcrun swift test --package-path apps/macos-menubar'

py-test:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests -q

integration-test:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration -q

package-smoke:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_build_metadata.py services/mlx-worker-python/tests/test_packaging_targets.py services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py services/mlx-worker-python/tests/test_m8_packaging_target_smoke.py -q
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_packaging_target_smoke.py --json

swift-coverage:
	/bin/zsh -lc 'set -e; \
	mkdir -p "$(TEXT_WORKER_SWIFT_HOME)" "$(CONTROL_PLANE_SWIFT_HOME)" "$(MENUBAR_SWIFT_HOME)"; \
	mkdir -p "$(TEXT_WORKER_MODULE_CACHE_PATH)" "$(CONTROL_PLANE_MODULE_CACHE_PATH)" "$(MENUBAR_MODULE_CACHE_PATH)"; \
	HOME="$(TEXT_WORKER_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(TEXT_WORKER_MODULE_CACHE_PATH)" xcrun swift test --package-path services/mlx-text-worker-swift --enable-code-coverage; \
	HOME="$(CONTROL_PLANE_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CONTROL_PLANE_MODULE_CACHE_PATH)" xcrun swift test --package-path services/control-plane-swift --enable-code-coverage; \
	HOME="$(MENUBAR_SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(MENUBAR_MODULE_CACHE_PATH)" xcrun swift test --package-path apps/macos-menubar --enable-code-coverage'
	python3 scripts/swift_coverage_summary.py services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/MelixTextWorkerSwift.json /services/mlx-text-worker-swift/Sources/
	python3 scripts/swift_coverage_summary.py services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/MelixControlPlane.json /services/control-plane-swift/Sources/
	python3 scripts/swift_coverage_summary.py apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/MelixMacOSMenubar.json /apps/macos-menubar/Sources/

py-coverage:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx coverage run --source=services/mlx-worker-python/worker,phase8_runtime_probes,phase8_metrics_report,phase8_lora_cli_smoke,phase8_lora_window_smoke,m9_agent_export_smoke,m15_desktop_polish_smoke -m pytest services/mlx-worker-python/tests -q
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx coverage report --include='services/mlx-worker-python/worker/*,scripts/phase8_runtime_probes.py,scripts/phase8_metrics_report.py,scripts/phase8_lora_cli_smoke.py,scripts/phase8_lora_window_smoke.py,scripts/m9_agent_export_smoke.py,scripts/m15_desktop_polish_smoke.py'

coverage: swift-coverage py-coverage

phase1-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase1_metrics_report.py $(PHASE1_METRICS_ARGS)

phase2-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py $(PHASE2_METRICS_ARGS)

phase5-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase5_control_plane_metrics.py

phase6-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase6_metrics_report.py

phase7-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase7_metrics_report.py

phase8-acceptance:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_acceptance_bundle.py $(PHASE8_ACCEPTANCE_ARGS)

phase8-real-e2e:
	mkdir -p "$(UV_CACHE_DIR)"
	MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_phase8_cli_acceptance.py -q -k phase8_acceptance_bundle_real_small_model_profile_closes_real_lora_chain $(PHASE8_REAL_E2E_ARGS)

phase8-install-smoke:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_install_smoke.py $(PHASE8_INSTALL_SMOKE_ARGS)

phase8-release-gate:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_release_gate.py $(PHASE8_RELEASE_GATE_ARGS)

phase8-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_metrics_report.py $(PHASE8_METRICS_ARGS)

phase17-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/m17_speech_runtime_smoke.py $(PHASE17_METRICS_ARGS)
