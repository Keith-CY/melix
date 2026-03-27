import XCTest
import GRPCCore
import MelixWorkerProtocol
@testable import MelixTextWorkerCore

@available(macOS 15.0, *)
final class WorkerScaffoldTests: XCTestCase {
    func testConfigurationDefaultsPreferDedicatedWorkerIdentity() {
        let configuration = WorkerConfiguration()

        XCTAssertEqual(configuration.workerID, "swift-text-worker-001")
        XCTAssertEqual(configuration.socketPath, "/var/run/melix/swift-text-worker.sock")
        XCTAssertEqual(configuration.backendMode, "swift")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-text-worker/dev")
    }

    func testConfigurationReadsEnvironmentOverrides() {
        let configuration = WorkerConfiguration.fromEnvironment([
            "MELIX_SWIFT_TEXT_WORKER_ID": "swift-text-worker-dev",
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift-text-worker.sock",
            "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "swift-experimental",
            "MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION": "melix-swift-text-worker/test"
        ])

        XCTAssertEqual(configuration.workerID, "swift-text-worker-dev")
        XCTAssertEqual(configuration.socketPath, "/tmp/melix-swift-text-worker.sock")
        XCTAssertEqual(configuration.backendMode, "swift-experimental")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-text-worker/test")
    }

    func testAbortRegistryTracksRequestLifecycle() {
        let abortRegistry = AbortRegistry()

        abortRegistry.register("req-1")
        XCTAssertTrue(abortRegistry.abort("req-1"))
        XCTAssertFalse(abortRegistry.abort("req-1"))

        abortRegistry.register("req-2")
        abortRegistry.remove("req-2")
        XCTAssertFalse(abortRegistry.abort("req-2"))
    }

    func testMetricsStoreTracksCountersAndTimings() {
        let metrics = MetricsStore()
        metrics.increment("swift_text.unimplemented_rpc_count")
        metrics.increment("swift_text.custom_counter", by: 3)
        metrics.recordMilliseconds("swift_text.runtime_stats_ms", value: 12)

        let counters = metrics.counters
        XCTAssertEqual(counters["swift_text.unimplemented_rpc_count"], 1)
        XCTAssertEqual(counters["swift_text.custom_counter"], 3)
        XCTAssertEqual(counters["swift_text.runtime_stats_ms"], 12)
    }

    func testHandshakeReturnsExpectedRuntimeMetadata() async throws {
        let services = makeServices()
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"

        let response = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.handshake(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Handshake.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(response.protocolVersion, "melix.worker.v1")
        XCTAssertEqual(response.runtimeVersion, "melix-swift-text-worker/dev")
        XCTAssertTrue(response.capabilities.cache.supportsPrefixCache)
        XCTAssertFalse(response.capabilities.execution.supportsContinuousBatching)
        XCTAssertFalse(response.capabilities.execution.supportsSpeculativeDecoding)
        XCTAssertEqual(response.capabilities.ext.map { $0.name }, ["engine_family"])
    }

    func testRuntimeStatsAndModelListReflectEmptyWorkerState() async throws {
        let services = makeServices()

        let stats = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let models = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.listLoadedModels(
                request: Melix_Worker_V1_ListLoadedModelsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.ListLoadedModels.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(stats.stats.workerState, "idle")
        XCTAssertEqual(stats.stats.activeRequests, 0)
        XCTAssertEqual(stats.stats.residentBytes, 0)
        XCTAssertTrue(models.modelHandles.isEmpty)
    }

    func testServicesExposeExpectedRegistrableRpcServices() {
        let services = makeServices()

        XCTAssertEqual(services.registrableServices.count, 4)
    }

    func testDrainTransitionsRuntimeStateToDraining() async throws {
        let services = makeServices()

        _ = try await withServerContextRPCCancellationHandle { handle in
            var response = Melix_Worker_V1_DrainResponse()
            var request = Melix_Worker_V1_DrainRequest()
            request.stopAcceptingNew = true
            response = try await services.runtime.drain(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Drain.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
            return response
        }

        let stats = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(stats.stats.workerState, "draining")
    }

    func testRuntimeLifecycleRpcsReturnExpectedResponses() async throws {
        let services = makeServices()

        let loadResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.loadModel(
                request: Melix_Worker_V1_LoadModelRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let unloadResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.unloadModel(
                request: Melix_Worker_V1_UnloadModelRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.UnloadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let warmupResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.warmupModel(
                request: Melix_Worker_V1_WarmupModelRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.WarmupModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let shutdownResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.runtime.shutdown(
                request: Melix_Worker_V1_ShutdownRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Shutdown.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(loadResponse.ok)
        XCTAssertEqual(loadResponse.error.code, "unimplemented")
        XCTAssertFalse(unloadResponse.ok)
        XCTAssertEqual(unloadResponse.error.code, "unimplemented")
        XCTAssertFalse(warmupResponse.ok)
        XCTAssertEqual(warmupResponse.error.code, "unimplemented")
        XCTAssertTrue(shutdownResponse.ok)
        XCTAssertEqual(services.metrics.counters["swift_text.unimplemented_rpc_count"], 3)
    }

    func testInferenceUnaryFallbackRpcsReturnStructuredUnimplemented() async throws {
        let services = makeServices()

        services.abortRegistry.register("req-present")

        let prefillResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: Melix_Worker_V1_PrefillRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let abortResponse = try await withServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_AbortRequest()
            request.requestID = "req-present"
            return try await services.inference.abort(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let missingAbortResponse = try await withServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_AbortRequest()
            request.requestID = "req-missing"
            return try await services.inference.abort(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let embedResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.embed(
                request: Melix_Worker_V1_EmbedRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Embed.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let rerankResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.rerank(
                request: Melix_Worker_V1_RerankRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Rerank.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let transcribeResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.transcribe(
                request: Melix_Worker_V1_TranscribeRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Transcribe.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let imageGenerateResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.imageGenerate(
                request: Melix_Worker_V1_ImageGenerateRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.ImageGenerate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let imageEditResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.imageEdit(
                request: Melix_Worker_V1_ImageEditRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.ImageEdit.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(prefillResponse.ok)
        XCTAssertEqual(prefillResponse.error.code, "unimplemented")
        XCTAssertTrue(abortResponse.ok)
        XCTAssertTrue(abortResponse.found)
        XCTAssertFalse(missingAbortResponse.ok)
        XCTAssertFalse(missingAbortResponse.found)
        XCTAssertEqual(embedResponse.error.code, "unimplemented")
        XCTAssertEqual(rerankResponse.error.code, "unimplemented")
        XCTAssertEqual(transcribeResponse.error.code, "unimplemented")
        XCTAssertEqual(imageGenerateResponse.error.code, "unimplemented")
        XCTAssertEqual(imageEditResponse.error.code, "unimplemented")
    }

    func testUnsupportedStreamingRpcsEmitStructuredUnimplementedEvent() async throws {
        let services = makeServices()
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-generate"

        try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.generate(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].requestID, "req-generate")
        XCTAssertEqual(recorded[0].executionKind, "generate")
        XCTAssertEqual(recorded[0].seq, 1)
        XCTAssertEqual(recorded[0].error.error.code, "unimplemented")
    }

    func testDecodeStreamingRpcEmitsStructuredUnimplementedEvent() async throws {
        let services = makeServices()
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-decode"

        try await withServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].requestID, "req-decode")
        XCTAssertEqual(recorded[0].executionKind, "decode")
        XCTAssertEqual(recorded[0].error.error.code, "unimplemented")
    }

    func testCacheManagementRpcsReturnStructuredUnimplemented() async throws {
        let services = makeServices()

        let cacheResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.cache.getCacheStats(
                request: Melix_Worker_V1_GetCacheStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let pinResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.cache.pinPrefix(
                request: Melix_Worker_V1_PinPrefixRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_CacheService.Method.PinPrefix.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let unpinResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.cache.unpinPrefix(
                request: Melix_Worker_V1_UnpinPrefixRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_CacheService.Method.UnpinPrefix.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let saveResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.cache.saveBoundarySnapshot(
                request: Melix_Worker_V1_SaveBoundarySnapshotRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let restoreResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.cache.restoreBoundarySnapshot(
                request: Melix_Worker_V1_RestoreBoundarySnapshotRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let purgeResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.cache.purgeCache(
                request: Melix_Worker_V1_PurgeCacheRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_CacheService.Method.PurgeCache.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(cacheResponse.stats.blockCount, 0)
        XCTAssertFalse(pinResponse.ok)
        XCTAssertEqual(pinResponse.error.code, "unimplemented")
        XCTAssertFalse(unpinResponse.ok)
        XCTAssertEqual(unpinResponse.error.code, "unimplemented")
        XCTAssertFalse(saveResponse.ok)
        XCTAssertEqual(saveResponse.error.code, "unimplemented")
        XCTAssertFalse(restoreResponse.ok)
        XCTAssertEqual(restoreResponse.error.code, "unimplemented")
        XCTAssertFalse(purgeResponse.ok)
        XCTAssertEqual(purgeResponse.error.code, "unimplemented")
    }

    func testMaintenanceRpcsReturnStructuredUnimplemented() async throws {
        let services = makeServices()
        let convertWriter = RecordingRPCWriter<Melix_Worker_V1_ConvertModelEvent>()
        let benchWriter = RecordingRPCWriter<Melix_Worker_V1_RunBenchEvent>()

        try await withServerContextRPCCancellationHandle { handle in
            try await services.maintenance.convertModel(
                request: Melix_Worker_V1_ConvertModelRequest(),
                response: RPCWriter(wrapping: convertWriter),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.ConvertModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let infoResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.maintenance.getModelInfo(
                request: Melix_Worker_V1_GetModelInfoRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.GetModelInfo.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let doctorResponse = try await withServerContextRPCCancellationHandle { handle in
            try await services.maintenance.runDoctor(
                request: Melix_Worker_V1_RunDoctorRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.RunDoctor.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        try await withServerContextRPCCancellationHandle { handle in
            try await services.maintenance.runBench(
                request: Melix_Worker_V1_RunBenchRequest(),
                response: RPCWriter(wrapping: benchWriter),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.RunBench.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let convertEvents = await convertWriter.snapshot()
        let benchEvents = await benchWriter.snapshot()

        XCTAssertEqual(convertEvents.count, 1)
        XCTAssertEqual(convertEvents[0].failed.error.code, "unimplemented")
        XCTAssertFalse(infoResponse.ok)
        XCTAssertEqual(infoResponse.error.code, "unimplemented")
        XCTAssertFalse(doctorResponse.ok)
        XCTAssertEqual(doctorResponse.error.code, "unimplemented")
        XCTAssertEqual(benchEvents.count, 1)
        XCTAssertEqual(benchEvents[0].failed.error.code, "unimplemented")
    }

    func testBootstrapBuildsServerWithDeterministicConfiguration() throws {
        let configuration = WorkerConfiguration()
        let bootstrap = try WorkerBootstrap.build(configuration: configuration)

        XCTAssertEqual(bootstrap.configuration.workerID, configuration.workerID)
        XCTAssertEqual(bootstrap.services.runtime.configuration.workerID, configuration.workerID)
        XCTAssertEqual(bootstrap.services.metrics.counters["swift_text.unimplemented_rpc_count"], 0)
    }
}

@available(macOS 15.0, *)
private func makeServices() -> WorkerServices {
    let configuration = WorkerConfiguration()
    let registry = WorkerRuntimeRegistry(configuration: configuration)
    let metrics = MetricsStore()
    let abortRegistry = AbortRegistry()
    return WorkerServices(
        configuration: configuration,
        registry: registry,
        abortRegistry: abortRegistry,
        metrics: metrics
    )
}

@available(macOS 15.0, *)
private actor RecordingRPCWriterStorage<Element: Sendable> {
    private var elements: [Element] = []

    func append(_ element: Element) {
        elements.append(element)
    }

    func append(contentsOf elements: some Sequence<Element>) {
        self.elements.append(contentsOf: elements)
    }

    func snapshot() -> [Element] {
        elements
    }
}

@available(macOS 15.0, *)
private final class RecordingRPCWriter<Element: Sendable>: RPCWriterProtocol, @unchecked Sendable {
    private let storage = RecordingRPCWriterStorage<Element>()

    func write(_ element: Element) async throws {
        await storage.append(element)
    }

    func write(contentsOf elements: some Sequence<Element>) async throws {
        let snapshot = Array(elements)
        await storage.append(contentsOf: snapshot)
    }

    func snapshot() async -> [Element] {
        await storage.snapshot()
    }
}
