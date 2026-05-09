import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("On-Demand Model Loader")
struct OnDemandModelLoaderTests {
    @Test("ready handles are reused and ttl-expired residents are evicted first")
    func readyHandlesAreReusedAndTTLExpiredResidentsAreEvictedFirst() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 100_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(
                    id: "melix-old-text",
                    state: .modelWarm,
                    ttlSeconds: 60
                ),
                makeTextModel(
                    id: "melix-dev-text",
                    state: .modelWarm
                ),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(
            id: "melix-old-text",
            dispatchHandle: "melix-old-text::swift",
            reason: "seed_load"
        )
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::swift",
            reason: "seed_load"
        )
        clock.nowUnixMs += 61_000

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setUnloadResponse(ok: true)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let oldModel = try #require(await catalog.model(id: "melix-old-text"))
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-text::swift")
        #expect(oldModel.state == .modelUnloaded)
        #expect(await workerClient.unloadHandles == ["melix-old-text::swift"])
        #expect(metrics.values["control_plane.model_eviction_plan_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_ttl_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_success_count"] == 1)
    }

    @Test("discovered text models lazy-load with runtime resident bytes and explicit memory budgets")
    func discoveredTextModelsLazyLoadWithRuntimeResidentBytesAndExplicitMemoryBudgets() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 4_096
        )
        await workerClient.setRuntimeResidentBytes(8_192)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore,
            memoryBudgetBytes: 65_536
        )

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-text::swift")
        #expect(model.state == .modelWarm)
        #expect(model.residency.transitionReason == "lazy_text_load")
        #expect(loadRequest.memoryBudgetBytes == 65_536)
        #expect(loadRequest.pinOnLoad == false)
        #expect(loadRequest.diskStreamingMode == .diskStreamingDisabled)
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 4_096)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 8_192)
    }

    @Test("discovered text models lazy-load with configured default memory budgets")
    func discoveredTextModelsLazyLoadWithConfiguredDefaultMemoryBudgets() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.memoryBudgetBytes = 32_768
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 4_096
        )

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        #expect(loadRequest.memoryBudgetBytes == 32_768)
    }

    @Test("canonical python text compatibility metadata routes to the python compatibility worker")
    func canonicalPythonTextCompatibilityMetadataRoutesToPythonCompatibilityWorker() async throws {
        var model = makeTextModel(id: "registry-text", state: .modelDiscovered)
        model.routeClass = .unspecified
        model.settings.ext["melix.capability.route_kind"] = "python_text_compatibility"
        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        await swiftClient.setLoadResponse(
            ok: true,
            handle: "registry-text::swift",
            estimatedResidentBytes: 4_096
        )
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "registry-text::python",
            estimatedResidentBytes: 8_192
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "registry-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        #expect(handle == "registry-text::python")
        #expect(await pythonClient.loadRequestCount == 1)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("text-capable VLM models lazy-load through the Python VLM route")
    func textCapableVLMModelsLazyLoadThroughThePythonVLMRoute() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devVLMModel()])
        let swiftClient = LoaderTestingWorkerClient()
        await swiftClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-vlm::swift",
            estimatedResidentBytes: 4_096
        )
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-vlm::python",
            estimatedResidentBytes: 8_192
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-vlm",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let loadRequest = try #require(await pythonClient.lastLoadModelRequest)
        #expect(handle == "melix-dev-vlm::python")
        #expect(loadRequest.model.modelKind == "vlm")
        #expect(loadRequest.model.ext["melix.capability.route_kind"] == "python_vlm")
        #expect(await pythonClient.loadRequestCount == 1)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("VLM text loading falls back to ext when structured capability fields are empty")
    func vlmTextLoadingFallsBackToExtWhenStructuredCapabilityFieldsAreEmpty() async throws {
        var model = ModelCatalog.devVLMModel()
        model.modelID = "melix-dev-vlm-ext-only"
        model.supportedModalities = []
        model.supportedTasks = []
        model.settings.ext["melix.capability.supported_modalities"] = "text,image"
        model.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        model.settings.ext["melix.model_path"] = "/tmp/melix-dev-vlm-ext-only"

        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-vlm-ext-only::python",
            estimatedResidentBytes: 4_096
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-vlm-ext-only",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        #expect(handle == "melix-dev-vlm-ext-only::python")
        #expect(await pythonClient.loadRequestCount == 1)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("lazy load falls back to estimated resident bytes when runtime stats are unavailable")
    func lazyLoadFallsBackToEstimatedResidentBytesWhenRuntimeStatsAreUnavailable() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 12_288
        )
        await workerClient.setRuntimeStatsFailure(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let metrics = await metricsStore.snapshot()
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 12_288)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 12_288)
    }

    @Test("missing or non-text models return model-not-ready without contacting workers")
    func missingOrNonTextModelsReturnModelNotReadyWithoutContactingWorkers() async throws {
        let workerClient = LoaderTestingWorkerClient()
        let registry = WorkerRegistry(defaultTextClient: workerClient)
        let missingCatalog = ModelCatalog(seedModels: [])
        let nonTextCatalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        let imageCatalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        let metricsStore = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: missingCatalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-embed",
                modelCatalog: nonTextCatalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-image",
                modelCatalog: imageCatalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        #expect(await workerClient.loadRequestCount == 0)
    }

    @Test("VLM text loading honors structured capability fields before ext fallbacks")
    func vlmTextLoadingHonorsStructuredCapabilityFieldsBeforeExtFallbacks() async throws {
        var imageOnlyVLM = ModelCatalog.devVLMModel()
        imageOnlyVLM.modelID = "melix-dev-vlm-image-only"
        imageOnlyVLM.supportedModalities = ["image"]
        imageOnlyVLM.supportedTasks = ["vlm", "generate"]
        imageOnlyVLM.settings.ext["melix.capability.supported_modalities"] = "text,image"
        imageOnlyVLM.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        imageOnlyVLM.settings.ext["melix.model_path"] = "/tmp/melix-dev-vlm-image-only"

        var noGenerateVLM = ModelCatalog.devVLMModel()
        noGenerateVLM.modelID = "melix-dev-vlm-no-generate"
        noGenerateVLM.supportedModalities = ["text", "image"]
        noGenerateVLM.supportedTasks = ["vlm"]
        noGenerateVLM.settings.ext["melix.capability.supported_modalities"] = "text,image"
        noGenerateVLM.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        noGenerateVLM.settings.ext["melix.model_path"] = "/tmp/melix-dev-vlm-no-generate"

        let catalog = ModelCatalog(seedModels: [imageOnlyVLM, noGenerateVLM])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "unexpected-vlm::python",
            estimatedResidentBytes: 4_096
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-vlm-image-only",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }
        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-vlm-no-generate",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        #expect(await pythonClient.loadRequestCount == 0)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("worker unavailability and failed lazy loads record failed model state")
    func workerUnavailabilityAndFailedLazyLoadsRecordFailedModelState() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let unavailableMetrics = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: nil,
                metricsStore: unavailableMetrics
            )
        }

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_failed")
    }

    @Test("failed lazy loads preserve explicit worker error codes in transition reasons")
    func failedLazyLoadsPreserveExplicitWorkerErrorCodesInTransitionReasons() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        let metricsStore = MetricsStore()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "memory_budget_exceeded",
            errorMessage: "Projected resident memory would exceed the process budget.",
            errorDetails: [
                "budget_bytes": "32768",
                "headroom_bytes": "2048",
                "required_bytes": "34816",
            ]
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedMemoryError = Melix_Worker_V1_ErrorStatus()
        expectedMemoryError.code = "memory_budget_exceeded"
        expectedMemoryError.message = "Projected resident memory would exceed the process budget."
        expectedMemoryError.details = [
            "budget_bytes": "32768",
            "headroom_bytes": "2048",
            "required_bytes": "34816",
        ]
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedMemoryError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        let metrics = await metricsStore.snapshot()
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_memory_budget_exceeded")
        #expect(model.residency.memoryBudgetBytes == 32_768)
        #expect(model.residency.memoryHeadroomBytes == 2_048)
        #expect(model.residency.requiredBytes == 34_816)
        #expect(metrics.values["control_plane.text_load_memory_budget_rejection_count"] == 1)
        #expect(metrics.values["control_plane.text_load_last_budget_bytes"] == 32_768)
        #expect(metrics.values["control_plane.text_load_last_headroom_bytes"] == 2_048)
        #expect(metrics.values["control_plane.text_load_last_required_bytes"] == 34_816)
    }

    @Test("failed lazy loads forward disk-streaming mode and preserve explicit worker rejection codes")
    func failedLazyLoadsForwardDiskStreamingModeAndPreserveExplicitWorkerRejectionCodes() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.diskStreamingMode = .diskStreamingPreferDisk
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "disk_streaming_unsupported",
            errorMessage: "The selected runtime does not support disk-streaming mode."
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedDiskStreamingError = Melix_Worker_V1_ErrorStatus()
        expectedDiskStreamingError.code = "disk_streaming_unsupported"
        expectedDiskStreamingError.message = "The selected runtime does not support disk-streaming mode."
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedDiskStreamingError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        let failedModel = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(loadRequest.diskStreamingMode == .diskStreamingPreferDisk)
        #expect(failedModel.state == .modelFailed)
        #expect(failedModel.residency.transitionReason == "lazy_text_load_disk_streaming_unsupported")
    }

    @Test("failed lazy loads sanitize non-identifier worker error codes in transition reasons")
    func failedLazyLoadsSanitizeNonIdentifierWorkerErrorCodesInTransitionReasons() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "memory-budget.exceeded",
            errorMessage: "Projected resident memory would exceed the process budget."
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedSanitizedError = Melix_Worker_V1_ErrorStatus()
        expectedSanitizedError.code = "memory-budget.exceeded"
        expectedSanitizedError.message = "Projected resident memory would exceed the process budget."
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedSanitizedError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_memory_budget_exceeded")
    }

    @Test("eviction falls back to local unloads and records pinned protection when no routing client is available")
    func evictionFallsBackToLocalUnloadsAndRecordsPinnedProtectionWhenNoRoutingClientIsAvailable() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 300_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "ttl-text", state: .modelWarm, ttlSeconds: 60),
                makePinnedTextModel(id: "pinned-text"),
                ModelCatalog.devTextModel(),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(id: "ttl-text", dispatchHandle: "ttl-text::swift", reason: "seed_load")
        _ = await catalog.recordLoadSucceeded(
            id: "pinned-text",
            dispatchHandle: "pinned-text::swift",
            pinRequested: true,
            reason: "seed_load"
        )
        clock.nowUnixMs += 61_000

        let metricsStore = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: nil,
                metricsStore: metricsStore
            )
        }

        let evicted = try #require(await catalog.model(id: "ttl-text"))
        let protected = try #require(await catalog.model(id: "pinned-text"))
        let metrics = await metricsStore.snapshot()

        #expect(evicted.state == .modelUnloaded)
        #expect(protected.state == .modelPinned)
        #expect(metrics.values["control_plane.model_eviction_plan_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_pinned_protected_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_last_pinned_protected_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_success_count"] == 1)
    }

    @Test("eviction records lru and failure metrics for unsuccessful worker unloads")
    func evictionRecordsLruAndFailureMetricsForUnsuccessfulWorkerUnloads() async throws {
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "lru-text", state: .modelWarm),
                ModelCatalog.devTextModel(),
            ]
        )
        _ = await catalog.recordLoadSucceeded(id: "lru-text", dispatchHandle: "lru-text::swift", reason: "seed_load")

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 2_048
        )
        await workerClient.setUnloadResponse(ok: false)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let lruModel = try #require(await catalog.model(id: "lru-text"))
        let metrics = await metricsStore.snapshot()

        #expect(lruModel.state == .modelFailed)
        #expect(metrics.values["control_plane.model_eviction_lru_same_capability_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_failure_count"] == 1)
    }

    @Test("eviction records thrown unload failures and exposes the fallback metric bucket")
    func evictionRecordsThrownUnloadFailuresAndExposesTheFallbackMetricBucket() async throws {
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "throw-text", state: .modelWarm),
                ModelCatalog.devTextModel(),
            ]
        )
        _ = await catalog.recordLoadSucceeded(id: "throw-text", dispatchHandle: "throw-text::swift", reason: "seed_load")

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 2_048
        )
        await workerClient.setUnloadFailure(WorkerClientError.unavailable)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let failed = try #require(await catalog.model(id: "throw-text"))
        let metrics = await metricsStore.snapshot()

        #expect(failed.state == .modelFailed)
        #expect(metrics.values["control_plane.model_eviction_failure_count"] == 1)
        #expect(OnDemandModelLoader.evictionMetricKey(for: "custom_reason") == "control_plane.model_eviction_other_count")
    }
}

private func makeTextModel(
    id: String,
    state: Melix_Controlplane_V1_ModelState,
    ttlSeconds: UInt32 = 0
) -> Melix_Controlplane_V1_ModelSummary {
    var model = ModelCatalog.devTextModel()
    model.modelID = id
    model.state = state
    model.settings.memoryPolicy = ttlSeconds > 0 ? .memoryResidencyTtl : .memoryResidencyEvictable
    model.settings.ttlSeconds = ttlSeconds
    switch state {
    case .modelDiscovered:
        model.residency.state = .discovered
    case .modelLoading:
        model.residency.state = .loading
    case .modelPinned:
        model.residency.state = .pinned
        model.pinned = true
    case .modelWarm:
        model.residency.state = .warm
    case .modelEvicting:
        model.residency.state = .evicting
    case .modelUnloaded:
        model.residency.state = .unloaded
    case .modelFailed:
        model.residency.state = .failed
    default:
        model.residency.state = .unspecified
    }
    return model
}

private func makePinnedTextModel(id: String) -> Melix_Controlplane_V1_ModelSummary {
    var model = makeTextModel(id: id, state: .modelPinned)
    model.settings.pinOnLoad = true
    model.settings.memoryPolicy = .memoryResidencyPinned
    model.pinned = true
    return model
}

private actor LoaderTestingWorkerClient: WorkerRoutingClient, RuntimeIntrospectingWorkerClientProtocol {
    private var loadResponse = Melix_Worker_V1_LoadModelResponse()
    private var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
    private var loadFailure: Error?
    private var unloadFailure: Error?
    private var runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
    private var runtimeStatsFailure: Error?

    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?
    private(set) var unloadHandles: [String] = []
    private(set) var loadRequestCount = 0

    func setLoadResponse(
        ok: Bool,
        handle: String,
        estimatedResidentBytes: UInt64,
        errorCode: String = "",
        errorMessage: String = "",
        errorDetails: [String: String] = [:]
    ) {
        loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = ok
        loadResponse.modelHandle = handle
        loadResponse.estimatedResidentBytes = estimatedResidentBytes
        loadResponse.residency.state = ok ? .warm : .failed
        loadResponse.error.code = errorCode
        loadResponse.error.message = errorMessage
        loadResponse.error.details = errorDetails
    }

    func setUnloadResponse(ok: Bool) {
        unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = ok
    }

    func setLoadFailure(_ error: Error?) {
        loadFailure = error
    }

    func setUnloadFailure(_ error: Error?) {
        unloadFailure = error
    }

    func setRuntimeResidentBytes(_ residentBytes: UInt64) {
        runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
        runtimeStatsResponse.stats.residentBytes = residentBytes
    }

    func setRuntimeStatsFailure(_ error: Error?) {
        runtimeStatsFailure = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadRequestCount += 1
        lastLoadModelRequest = request
        if let loadFailure {
            throw loadFailure
        }
        return loadResponse
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadHandles.append(request.modelHandle)
        if let unloadFailure {
            throw unloadFailure
        }
        return unloadResponse
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        if let runtimeStatsFailure {
            throw runtimeStatsFailure
        }
        return runtimeStatsResponse
    }
}
