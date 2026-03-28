import Foundation
import GRPCCore
import MelixWorkerProtocol

struct WorkerServices: Sendable {
    let configuration: WorkerConfiguration
    let registry: WorkerRuntimeRegistry
    let abortRegistry: AbortRegistry
    let metrics: MetricsStore
    let runtime: RuntimeRPCService
    let inference: InferenceRPCService
    let cache: CacheRPCService
    let maintenance: MaintenanceRPCService

    init(
        configuration: WorkerConfiguration,
        registry: WorkerRuntimeRegistry,
        abortRegistry: AbortRegistry,
        metrics: MetricsStore
    ) {
        self.configuration = configuration
        self.registry = registry
        self.abortRegistry = abortRegistry
        self.metrics = metrics
        self.runtime = RuntimeRPCService(configuration: configuration, registry: registry, metrics: metrics)
        self.inference = InferenceRPCService(
            configuration: configuration,
            registry: registry,
            abortRegistry: abortRegistry,
            metrics: metrics
        )
        self.cache = CacheRPCService(registry: registry, metrics: metrics)
        self.maintenance = MaintenanceRPCService(metrics: metrics)
    }

    var registrableServices: [any RegistrableRPCService] {
        [runtime, inference, cache, maintenance]
    }
}

final class RuntimeRPCService: Melix_Worker_V1_RuntimeService.SimpleServiceProtocol, @unchecked Sendable {
    let configuration: WorkerConfiguration

    private let registry: WorkerRuntimeRegistry
    private let metrics: MetricsStore

    init(
        configuration: WorkerConfiguration,
        registry: WorkerRuntimeRegistry,
        metrics: MetricsStore
    ) {
        self.configuration = configuration
        self.registry = registry
        self.metrics = metrics
    }

    func handshake(
        request: Melix_Worker_V1_HandshakeRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_HandshakeResponse {
        metrics.recordMilliseconds("swift_text.handshake_ms", value: 0)

        var response = Melix_Worker_V1_HandshakeResponse()
        response.protocolVersion = request.protocolVersion
        response.runtimeVersion = configuration.runtimeVersion
        response.capabilities = await registry.capabilities()
        return response
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        let startedAt = Date()

        do {
            let loaded = try await registry.loadModel(request.model)
            metrics.recordMilliseconds("swift_text.load_model_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.peak_resident_bytes", value: Int(clamping: loaded.estimatedResidentBytes))
            metrics.set("swift_text.loaded_model_count", value: await registry.loadedModelCount())

            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = true
            response.modelHandle = loaded.handle
            response.estimatedResidentBytes = loaded.estimatedResidentBytes
            response.resolvedCapabilities = await registry.capabilities()
            return response
        } catch {
            metrics.increment("swift_text.rpc_error_count")
            metrics.recordMilliseconds("swift_text.load_model_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.loaded_model_count", value: await registry.loadedModelCount())

            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = false
            response.error = makeErrorStatus(code: "load_failed", message: error.localizedDescription)
            response.resolvedCapabilities = await registry.capabilities()
            return response
        }
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        let startedAt = Date()
        let found = await registry.unloadModel(request.modelHandle)
        metrics.recordMilliseconds("swift_text.unload_model_ms", value: elapsedMilliseconds(since: startedAt))
        metrics.set("swift_text.loaded_model_count", value: await registry.loadedModelCount())

        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = found
        if !found {
            response.error = makeErrorStatus(code: "not_found", message: "Unknown model handle.")
        }
        return response
    }

    func warmupModel(
        request: Melix_Worker_V1_WarmupModelRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_WarmupModelResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_WarmupModelResponse()
        response.ok = false
        response.error = makeUnimplementedStatus("WarmupModel is deferred until P1-M4.")
        return response
    }

    func getRuntimeStats(
        request: Melix_Worker_V1_GetRuntimeStatsRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        metrics.recordMilliseconds("swift_text.runtime_stats_ms", value: 0)

        var response = Melix_Worker_V1_GetRuntimeStatsResponse()
        response.stats = await registry.runtimeStats()
        return response
    }

    func listLoadedModels(
        request: Melix_Worker_V1_ListLoadedModelsRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_ListLoadedModelsResponse {
        var response = Melix_Worker_V1_ListLoadedModelsResponse()
        response.modelHandles = await registry.listLoadedModels()
        return response
    }

    func drain(
        request: Melix_Worker_V1_DrainRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_DrainResponse {
        await registry.setDraining(request.stopAcceptingNew)

        var response = Melix_Worker_V1_DrainResponse()
        response.ok = true
        return response
    }

    func shutdown(
        request: Melix_Worker_V1_ShutdownRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_ShutdownResponse {
        var response = Melix_Worker_V1_ShutdownResponse()
        response.ok = true
        return response
    }
}

final class InferenceRPCService: Melix_Worker_V1_InferenceService.SimpleServiceProtocol, @unchecked Sendable {
    let configuration: WorkerConfiguration

    private let registry: WorkerRuntimeRegistry
    private let abortRegistry: AbortRegistry
    private let metrics: MetricsStore
    private let generationEngine: TextGenerationEngine
    private let prefillEngine: TextPrefillEngine
    private let decodeEngine: TextDecodeEngine

    init(
        configuration: WorkerConfiguration,
        registry: WorkerRuntimeRegistry,
        abortRegistry: AbortRegistry,
        metrics: MetricsStore
    ) {
        self.configuration = configuration
        self.registry = registry
        self.abortRegistry = abortRegistry
        self.metrics = metrics
        self.generationEngine = TextGenerationEngine(registry: registry, abortRegistry: abortRegistry, metrics: metrics)
        self.prefillEngine = TextPrefillEngine(registry: registry, abortRegistry: abortRegistry, metrics: metrics)
        self.decodeEngine = TextDecodeEngine(registry: registry, abortRegistry: abortRegistry, metrics: metrics)
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest,
        response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>,
        context: GRPCCore.ServerContext
    ) async throws {
        try await generationEngine.runGenerate(request: request, response: response)
    }

    func prefill(
        request: Melix_Worker_V1_PrefillRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        await prefillEngine.runPrefill(request: request)
    }

    func decode(
        request: Melix_Worker_V1_DecodeRequest,
        response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>,
        context: GRPCCore.ServerContext
    ) async throws {
        try await decodeEngine.runDecode(request: request, response: response)
    }

    func abort(
        request: Melix_Worker_V1_AbortRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_AbortResponse {
        let startedAt = Date()
        let found = abortRegistry.abort(request.requestID)
        metrics.recordMilliseconds("swift_text.abort_ms", value: elapsedMilliseconds(since: startedAt))

        var response = Melix_Worker_V1_AbortResponse()
        response.ok = found
        response.found = found
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_EmbedResponse()
        response.error = makeUnimplementedStatus("Embed is handled by the Python worker family.")
        return response
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_RerankResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_RerankResponse()
        response.error = makeUnimplementedStatus("Rerank is handled by the Python worker family.")
        return response
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_TranscribeResponse()
        response.error = makeUnimplementedStatus("Transcribe is handled by the Python worker family.")
        return response
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_ImageGenerateResponse()
        response.error = makeUnimplementedStatus("ImageGenerate is handled by the Python worker family.")
        return response
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_ImageEditResponse()
        response.error = makeUnimplementedStatus("ImageEdit is handled by the Python worker family.")
        return response
    }
}

final class CacheRPCService: Melix_Worker_V1_CacheService.SimpleServiceProtocol, @unchecked Sendable {
    private let registry: WorkerRuntimeRegistry
    private let metrics: MetricsStore

    init(registry: WorkerRuntimeRegistry, metrics: MetricsStore) {
        self.registry = registry
        self.metrics = metrics
    }

    func getCacheStats(
        request: Melix_Worker_V1_GetCacheStatsRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        let response = await registry.cacheStatsResponse()
        metrics.set("swift_text.cache_l1_bytes", value: Int(clamping: response.stats.l1Bytes))
        metrics.set("swift_text.cache_block_count", value: Int(clamping: response.stats.blockCount))
        metrics.set("swift_text.cache_prefix_count", value: response.snapshot.hotPrefixes.count)
        metrics.set(
            "swift_text.cache_pinned_prefix_count",
            value: Int(clamping: response.stats.pinnedPrefixCount)
        )
        metrics.set(
            "swift_text.cache_l1_hit_rate",
            value: Int((response.stats.l1HitRate * 100.0).rounded())
        )
        metrics.set(
            "swift_text.cache_block_reuse_ratio",
            value: Int((response.stats.dedupRatio * 100.0).rounded())
        )
        return response
    }

    func pinPrefix(
        request: Melix_Worker_V1_PinPrefixRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_PinPrefixResponse {
        var response = Melix_Worker_V1_PinPrefixResponse()
        response.ok = await registry.pinPrefix(request.prefix)
        if !response.ok {
            response.error = makeErrorStatus(code: "not_found", message: "Unknown prefix reference.")
        }
        return response
    }

    func unpinPrefix(
        request: Melix_Worker_V1_UnpinPrefixRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_UnpinPrefixResponse {
        var response = Melix_Worker_V1_UnpinPrefixResponse()
        response.ok = await registry.unpinPrefix(request.prefix)
        if !response.ok {
            response.error = makeErrorStatus(code: "not_found", message: "Unknown prefix reference.")
        }
        return response
    }

    func saveBoundarySnapshot(
        request: Melix_Worker_V1_SaveBoundarySnapshotRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_SaveBoundarySnapshotResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_SaveBoundarySnapshotResponse()
        response.ok = false
        response.error = makeUnimplementedStatus("SaveBoundarySnapshot is deferred until Phase 3.")
        return response
    }

    func restoreBoundarySnapshot(
        request: Melix_Worker_V1_RestoreBoundarySnapshotRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_RestoreBoundarySnapshotResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_RestoreBoundarySnapshotResponse()
        response.ok = false
        response.error = makeUnimplementedStatus("RestoreBoundarySnapshot is deferred until Phase 3.")
        return response
    }

    func purgeCache(
        request: Melix_Worker_V1_PurgeCacheRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_PurgeCacheResponse {
        var response = Melix_Worker_V1_PurgeCacheResponse()
        response.ok = true
        response.purgedBlocks = await registry.purgeCache(
            scope: request.scope,
            cacheKey: request.cacheKey,
            includePinned: request.includePinned
        )
        return response
    }
}

final class MaintenanceRPCService: Melix_Worker_V1_MaintenanceService.SimpleServiceProtocol, @unchecked Sendable {
    private let metrics: MetricsStore

    init(metrics: MetricsStore) {
        self.metrics = metrics
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest,
        response: GRPCCore.RPCWriter<Melix_Worker_V1_ConvertModelEvent>,
        context: GRPCCore.ServerContext
    ) async throws {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var event = Melix_Worker_V1_ConvertModelEvent()
        var failed = Melix_Worker_V1_ConvertFailed()
        failed.error = makeUnimplementedStatus("ConvertModel is handled by the Python worker family.")
        event.failed = failed
        try await response.write(event)
    }

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_GetModelInfoResponse()
        response.ok = false
        response.error = makeUnimplementedStatus("GetModelInfo is handled by the Python worker family.")
        return response
    }

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest,
        context: GRPCCore.ServerContext
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var response = Melix_Worker_V1_RunDoctorResponse()
        response.ok = false
        response.error = makeUnimplementedStatus("RunDoctor is handled by the Python worker family.")
        return response
    }

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest,
        response: GRPCCore.RPCWriter<Melix_Worker_V1_RunBenchEvent>,
        context: GRPCCore.ServerContext
    ) async throws {
        metrics.increment("swift_text.unimplemented_rpc_count")

        var event = Melix_Worker_V1_RunBenchEvent()
        var failed = Melix_Worker_V1_BenchFailed()
        failed.error = makeUnimplementedStatus("RunBench is handled by the Python worker family.")
        event.failed = failed
        try await response.write(event)
    }
}

private func makeUnimplementedStatus(_ message: String) -> Melix_Worker_V1_ErrorStatus {
    makeErrorStatus(code: "unimplemented", message: message)
}

private func makeErrorStatus(
    code: String,
    message: String
) -> Melix_Worker_V1_ErrorStatus {
    var status = Melix_Worker_V1_ErrorStatus()
    status.code = code
    status.message = message
    status.retriable = false
    return status
}

private func makeUnimplementedExecuteEvent(
    requestID: String,
    executionKind: String,
    message: String
) -> Melix_Worker_V1_ExecuteEvent {
    makeErrorExecuteEvent(
        requestID: requestID,
        executionKind: executionKind,
        seq: 1,
        code: "unimplemented",
        message: message
    )
}

private func makeErrorExecuteEvent(
    requestID: String,
    executionKind: String,
    seq: UInt64,
    code: String,
    message: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = executionKind
    event.seq = seq

    var errorEvent = Melix_Worker_V1_ErrorEvent()
    errorEvent.error = makeErrorStatus(code: code, message: message)
    event.error = errorEvent
    return event
}

private func elapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}
