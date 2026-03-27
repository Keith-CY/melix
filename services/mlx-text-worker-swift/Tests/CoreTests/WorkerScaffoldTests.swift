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

    func testConfigurationFallsBackToDefaultsForEmptyEnvironment() {
        let configuration = WorkerConfiguration.fromEnvironment([:])

        XCTAssertEqual(configuration, WorkerConfiguration())
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

    func testDevelopmentModelCatalogResolvesEnvironmentOverride() {
        let catalog = WorkerModelCatalog(environment: [
            "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
        ])

        let model = catalog.get("melix-dev-text")

        XCTAssertEqual(model?.modelID, "melix-dev-text")
        XCTAssertEqual(model?.modelPath, "mlx-community/melix-dev-text-4bit")
        XCTAssertEqual(model?.quantProfileID, "q4")
    }

    func testAutoSwiftMLXBackendUsesInjectedLoader() async throws {
        let backend = AutoSwiftMLXBackend(runtimeName: "fake-mlx-loader") { modelSource in
            ["model_source": modelSource]
        }
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        spec.modelPath = "mlx-community/melix-dev-text-4bit"

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual(backend.runtimeName, "fake-mlx-loader")
        XCTAssertEqual((loaded.storage as? [String: String])?["model_source"], "mlx-community/melix-dev-text-4bit")
    }

    func testAutoSwiftMLXBackendDefaultsToMLXRuntimeNameAndUsesModelIDFallback() async throws {
        let backend = AutoSwiftMLXBackend { modelSource in
            ["model_source": modelSource]
        }
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual(backend.runtimeName, "mlx-swift-lm")
        XCTAssertEqual((loaded.storage as? [String: String])?["model_source"], "melix-dev-text")
    }

    func testRuntimeUnavailableErrorReturnsMessageAsDescription() {
        let error = RuntimeUnavailableError(message: "mlx unavailable")

        XCTAssertEqual(error.errorDescription, "mlx unavailable")
    }

    func testTextRuntimeUsesResidentDeltaAndForwardsUnload() async throws {
        let backend = FakeRuntimeBackend(residentBytesHint: 2_048)
        let probe = ResidentMemoryProbe(samples: [100, 3_600])
        let runtime = TextRuntime(
            backend: backend,
            residentMemoryReader: { probe.next() }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"

        let loaded = try await runtime.loadModel(spec: spec)
        await runtime.unloadModel(loaded.model)
        let unloadedCount = await backend.unloadedModelCount()

        XCTAssertEqual(runtime.runtimeName, "fake-mlx-swift")
        XCTAssertEqual(loaded.estimatedResidentBytes, 3_500)
        XCTAssertEqual(unloadedCount, 1)
    }

    func testTextRuntimeDefaultResidentReaderAndDefaultUnloadPathAreSafe() async throws {
        let runtime = TextRuntime(backend: DefaultUnloadBackend())
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"

        let loaded = try await runtime.loadModel(spec: spec)
        await runtime.unloadModel(loaded.model)

        XCTAssertEqual(runtime.runtimeName, "default-unload-backend")
        XCTAssertGreaterThanOrEqual(loaded.estimatedResidentBytes, 0)
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

    func testRuntimeLifecycleLoadAndUnloadTrackModelState() async throws {
        let backend = FakeRuntimeBackend()
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: backend,
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.memoryBudgetBytes = 4_096
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let listedResponse = try await withServerContextRPCCancellationHandle { handle in
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

        let loadedStats = try await withServerContextRPCCancellationHandle { handle in
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

        let unloadResponse = try await withServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_UnloadModelRequest()
            request.modelHandle = loadResponse.modelHandle
            return try await services.runtime.unloadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.UnloadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let postUnloadStats = try await withServerContextRPCCancellationHandle { handle in
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

        XCTAssertTrue(loadResponse.ok)
        XCTAssertEqual(loadResponse.modelHandle, "melix-dev-text::1")
        XCTAssertEqual(loadResponse.estimatedResidentBytes, 4_096)
        XCTAssertEqual(listedResponse.modelHandles, ["melix-dev-text::1"])
        XCTAssertEqual(loadedStats.stats.residentBytes, 4_096)
        XCTAssertTrue(unloadResponse.ok)
        XCTAssertEqual(postUnloadStats.stats.residentBytes, 0)
        XCTAssertEqual(services.metrics.counters["swift_text.loaded_model_count"], 0)

        let loadedSpecs = await backend.loadedSpecs()
        XCTAssertEqual(loadedSpecs.map(\.modelPath), ["mlx-community/melix-dev-text-4bit"])
    }

    func testRuntimeLifecycleReportsLoadFailuresAndMissingHandles() async throws {
        let services = makeServices(
            backend: FakeRuntimeBackend(loadError: FakeRuntimeBackendError.loadFailed),
            residentMemorySamples: [1_000, 1_000]
        )

        let failedLoad = try await withServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let missingUnload = try await withServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_UnloadModelRequest()
            request.modelHandle = "missing-handle"
            return try await services.runtime.unloadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.UnloadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(failedLoad.ok)
        XCTAssertEqual(failedLoad.error.code, "load_failed")
        XCTAssertFalse(missingUnload.ok)
        XCTAssertEqual(missingUnload.error.code, "not_found")
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
private func makeServices(
    environment: [String: String] = [:],
    backend: some TextRuntimeBackend = FakeRuntimeBackend(),
    residentMemorySamples: [UInt64] = [0, 0]
) -> WorkerServices {
    let configuration = WorkerConfiguration()
    let metrics = MetricsStore()
    let abortRegistry = AbortRegistry()
    let catalog = WorkerModelCatalog(environment: environment)
    let probe = ResidentMemoryProbe(samples: residentMemorySamples)
    let runtime = TextRuntime(
        backend: backend,
        residentMemoryReader: { probe.next() }
    )
    let registry = WorkerRuntimeRegistry(
        configuration: configuration,
        modelCatalog: catalog,
        runtime: runtime
    )
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
private enum FakeRuntimeBackendError: Error {
    case loadFailed
}

@available(macOS 15.0, *)
private actor FakeRuntimeBackendStorage {
    private var specs: [Melix_Worker_V1_ModelSpec] = []

    func append(_ spec: Melix_Worker_V1_ModelSpec) {
        specs.append(spec)
    }

    func snapshot() -> [Melix_Worker_V1_ModelSpec] {
        specs
    }
}

@available(macOS 15.0, *)
private final class FakeRuntimeBackend: TextRuntimeBackend, @unchecked Sendable {
    let runtimeName: String = "fake-mlx-swift"

    private let loadError: Error?
    private let residentBytesHint: UInt64
    private let storage = FakeRuntimeBackendStorage()
    private let unloadedStorage = FakeRuntimeBackendUnloadStorage()

    init(loadError: Error? = nil, residentBytesHint: UInt64 = 0) {
        self.loadError = loadError
        self.residentBytesHint = residentBytesHint
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        await storage.append(spec)
        if let loadError {
            throw loadError
        }
        return LoadedTextModel(
            storage: ["model_id": spec.modelID, "model_path": spec.modelPath],
            residentBytesHint: residentBytesHint
        )
    }

    func unloadModel(_ model: LoadedTextModel) async {
        await unloadedStorage.increment()
    }

    func loadedSpecs() async -> [Melix_Worker_V1_ModelSpec] {
        await storage.snapshot()
    }

    func unloadedModelCount() async -> Int {
        await unloadedStorage.count()
    }
}

@available(macOS 15.0, *)
private struct DefaultUnloadBackend: TextRuntimeBackend {
    let runtimeName: String = "default-unload-backend"

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        LoadedTextModel(storage: ["model_id": spec.modelID], residentBytesHint: 1)
    }
}

@available(macOS 15.0, *)
private actor FakeRuntimeBackendUnloadStorage {
    private var value: Int = 0

    func increment() {
        value += 1
    }

    func count() -> Int {
        value
    }
}

@available(macOS 15.0, *)
private final class ResidentMemoryProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var samples: [UInt64]

    init(samples: [UInt64]) {
        self.samples = samples
    }

    func next() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        if samples.isEmpty {
            return 0
        }
        return samples.removeFirst()
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
