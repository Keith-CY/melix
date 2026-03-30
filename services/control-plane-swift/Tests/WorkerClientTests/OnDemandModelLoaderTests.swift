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
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 4_096)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 8_192)
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

        #expect(await workerClient.loadRequestCount == 0)
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
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "memory_budget_exceeded",
            errorMessage: "Projected resident memory would exceed the process budget."
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
        #expect(model.residency.transitionReason == "lazy_text_load_memory_budget_exceeded")
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
        errorMessage: String = ""
    ) {
        loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = ok
        loadResponse.modelHandle = handle
        loadResponse.estimatedResidentBytes = estimatedResidentBytes
        loadResponse.residency.state = ok ? .warm : .failed
        loadResponse.error.code = errorCode
        loadResponse.error.message = errorMessage
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
