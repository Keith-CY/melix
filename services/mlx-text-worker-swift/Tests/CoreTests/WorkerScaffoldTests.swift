import XCTest
import GRPCCore
import MelixWorkerProtocol
#if canImport(MLX)
import MLX
#endif
#if canImport(MLXLMCommon)
import MLXLMCommon
#endif
#if canImport(MLXLLM)
import MLXLLM
#endif
#if canImport(Tokenizers)
import Tokenizers
#endif
@testable import MelixTextWorkerCore

@available(macOS 15.0, *)
final class WorkerScaffoldTests: XCTestCase {
    func testConfigurationDefaultsPreferDedicatedWorkerIdentity() {
        let configuration = WorkerConfiguration()

        XCTAssertEqual(configuration.workerID, "swift-text-worker-001")
        XCTAssertEqual(configuration.socketPath, "/var/run/melix/swift-text-worker.sock")
        XCTAssertEqual(configuration.backendMode, "swift")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-text-worker/dev")
        XCTAssertEqual(configuration.cacheRootPath, ".runtime/swift-text-worker-cache")
    }

    func testConfigurationReadsEnvironmentOverrides() {
        let configuration = WorkerConfiguration.fromEnvironment([
            "MELIX_SWIFT_TEXT_WORKER_ID": "swift-text-worker-dev",
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift-text-worker.sock",
            "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "swift-experimental",
            "MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION": "melix-swift-text-worker/test",
            "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": "/tmp/melix-swift-text-worker-metrics.json",
            "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": "/tmp/melix-swift-text-worker-cache",
        ])

        XCTAssertEqual(configuration.workerID, "swift-text-worker-dev")
        XCTAssertEqual(configuration.socketPath, "/tmp/melix-swift-text-worker.sock")
        XCTAssertEqual(configuration.backendMode, "swift-experimental")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-text-worker/test")
        XCTAssertEqual(configuration.metricsExportPath, "/tmp/melix-swift-text-worker-metrics.json")
        XCTAssertEqual(configuration.cacheRootPath, "/tmp/melix-swift-text-worker-cache")
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

    func testAbortRegistryExposesHandleStateBeforeAndAfterAbort() {
        let abortRegistry = AbortRegistry()
        let handle = abortRegistry.register("req-handle")

        XCTAssertFalse(handle.isAborted)
        XCTAssertNotNil(abortRegistry.handle(for: "req-handle"))
        XCTAssertTrue(abortRegistry.abort("req-handle"))
        XCTAssertTrue(handle.isAborted)
        XCTAssertNil(abortRegistry.handle(for: "req-handle"))
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

    func testMetricsStoreExportsCountersWhenConfigured() throws {
        let exportURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        let metrics = MetricsStore(exportPath: exportURL.path)
        metrics.set("swift_text.decode_ttft_ms", value: 24)

        let data = try Data(contentsOf: exportURL)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let values = try XCTUnwrap(payload["values"] as? [String: Int])

        XCTAssertEqual(values["swift_text.decode_ttft_ms"], 24)
    }

    func testHandshakeReturnsExpectedRuntimeMetadata() async throws {
        let services = makeServices()
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"

        let response = try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(response.capabilities.cache.kvQuantProfiles, ["q4", "q8"])
        XCTAssertFalse(response.capabilities.execution.supportsContinuousBatching)
        XCTAssertFalse(response.capabilities.execution.supportsSpeculativeDecoding)
        XCTAssertEqual(
            response.capabilities.ext.map { $0.name },
            ["engine_family", "accelerated_prefill", "active_kv_quantized"]
        )
    }

    func testRuntimeStatsAndModelListReflectEmptyWorkerState() async throws {
        let services = makeServices()

        let stats = try await withTestServerContextRPCCancellationHandle { handle in
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

        let models = try await withTestServerContextRPCCancellationHandle { handle in
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

    func testAutoSwiftMLXBackendUsesDirectoryLoaderForExistingPath() async throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let backend = AutoSwiftMLXBackend(
            directoryLoader: { directoryURL in
                LoadedTextModel(storage: ["directory": directoryURL.path], residentBytesHint: 1)
            },
            identifierLoader: { _, _ in
                XCTFail("identifier loader should not be used for an existing directory path")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        spec.modelPath = tempDirectory.path

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual((loaded.storage as? [String: String])?["directory"], tempDirectory.path)
    }

    func testAutoSwiftMLXBackendUsesIdentifierLoaderForRemoteModelSources() async throws {
        let backend = AutoSwiftMLXBackend(
            directoryLoader: { _ in
                XCTFail("directory loader should not be used for remote model identifiers")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            },
            identifierLoader: { modelSource, revision in
                LoadedTextModel(
                    storage: ["model_source": modelSource, "revision": revision],
                    residentBytesHint: 2
                )
            }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        spec.modelPath = "mlx-community/melix-dev-text-4bit"
        spec.revision = "dev-branch"

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual((loaded.storage as? [String: String])?["model_source"], "mlx-community/melix-dev-text-4bit")
        XCTAssertEqual((loaded.storage as? [String: String])?["revision"], "dev-branch")
    }

    func testAutoSwiftMLXBackendGenerateEventsUsesPreparedGenerationFactory() async throws {
        let backend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 4,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.yield(.chunk("Hello"))
                        continuation.yield(.chunk(" world"))
                        continuation.yield(.summary(
                            TextGenerationSummary(
                                promptTokens: 4,
                                completionTokens: 2,
                                tokensPerSecond: 42
                            )
                        ))
                        continuation.finish()
                    }
                )
            }
        )

        let stream = try await backend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("hello")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: stream)

        XCTAssertEqual(events.count, 4)
        XCTAssertEqual(renderedPromptTokens(from: events), 4)
        XCTAssertEqual(renderedTokenChunks(from: events), ["Hello", " world"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 2)
    }

    func testAutoSwiftMLXBackendGenerateEventsFallsBackToObservedCompletionCount() async throws {
        let backend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 2,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.yield(.chunk("A"))
                        continuation.yield(.chunk("B"))
                        continuation.finish()
                    }
                )
            }
        )

        let stream = try await backend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("fallback")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: stream)

        XCTAssertEqual(renderedSummary(from: events)?.promptTokens, 2)
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 2)
    }

    func testAutoSwiftMLXBackendGenerateEventsStopsOnAbortSkipsEmptyChunksAndSurfacesThrownErrors() async throws {
        let abortingBackend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 3,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.yield(.chunk(""))
                        continuation.yield(.chunk("ignored"))
                        continuation.finish()
                    }
                )
            }
        )

        let abortedStream = try await abortingBackend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("abort")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { true }
        )
        let abortedEvents = try await collectTextGenerationEvents(from: abortedStream)
        XCTAssertEqual(abortedEvents.count, 2)
        XCTAssertEqual(renderedPromptTokens(from: abortedEvents), 3)
        XCTAssertEqual(renderedSummary(from: abortedEvents)?.completionTokens, 0)

        enum ExpectedFailure: Error {
            case boom
        }

        let throwingBackend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 1,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.finish(throwing: ExpectedFailure.boom)
                    }
                )
            }
        )

        let failingStream = try await throwingBackend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("throw")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )

        do {
            _ = try await collectTextGenerationEvents(from: failingStream)
            XCTFail("expected runtime stream failure")
        } catch {
            XCTAssertTrue(error is ExpectedFailure)
        }
    }

    func testAutoSwiftMLXBackendDecodeRejectsUnsupportedSpeculativeModeWithoutFallback() async {
        let backend = AutoSwiftMLXBackend()
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .speculativeDecode
        acceleration.allowBaselineFallback = false

        await XCTAssertThrowsErrorAsync(
            try await backend.decodeEvents(
                model: LoadedTextModel(storage: ["kind": "fake"]),
                context: TextPrefillContext(storage: [:], promptTokens: 1),
                sampling: Melix_Worker_V1_SamplingConfig(),
                maxOutputTokens: 2,
                decodeStepSize: 1,
                prefillToken: "",
                acceleration: acceleration,
                shouldAbort: { false }
            )
        )
    }

    func testAutoSwiftMLXBackendDefaultPreparedGenerationFactoryRejectsNonMLXContainers() async {
        let backend = AutoSwiftMLXBackend()

        await XCTAssertThrowsErrorAsync(
            try await backend.generateEvents(
                model: LoadedTextModel(storage: ["kind": "not-a-container"]),
                messages: [makeUserMessage("default factory")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
    }

    #if canImport(MLX) && canImport(MLXLMCommon) && canImport(MLXLLM) && canImport(Tokenizers)
    func testAutoSwiftMLXBackendDefaultPreparedGenerationFactoryUsesLiveModelContainerBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let stream = try await backend.generateEvents(
                    model: LoadedTextModel(
                        storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge live path")],
                    sampling: sampling,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        XCTAssertEqual(renderedPromptTokens(from: events), promptTokens.count)
        XCTAssertFalse(renderedTokenChunks(from: events).joined().isEmpty)

        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.promptTokens, promptTokens.count)
        XCTAssertGreaterThan(summary.completionTokens, 0)
        XCTAssertNotNil(summary.tokensPerSecond)
    }

    func testAutoSwiftMLXBackendPrefillUsesLiveModelContainerBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                try await backend.prefill(
                    model: LoadedTextModel(
                        storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge prefill live path")],
                    prefillStepSize: 32,
                    resumeHint: "live-prefill",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
            }
        }

        XCTAssertEqual(result.promptTokens, promptTokens.count)
        XCTAssertEqual(result.context.promptTokens, promptTokens.count)
    }

    func testAutoSwiftMLXBackendPrefillAppliesAcceleratedPrefillPolicyForLiveBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .acceleratedPrefill
        acceleration.prefillHint = "json-schema"

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                try await backend.prefill(
                    model: LoadedTextModel(
                        storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("{\"kind\":\"object\"}")],
                    prefillStepSize: 4,
                    resumeHint: "live-accelerated-prefill",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
            }
        }

        XCTAssertEqual(result.appliedAcceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(result.appliedAcceleration.prefillHint, "json-schema")
        XCTAssertGreaterThan(result.acceleratedPrefillGainPct, 0)
        XCTAssertEqual(result.activeKVQuantizationRatio, 0)
    }

    func testAutoSwiftMLXBackendPrefillNormalizesActiveKVProfileForLiveBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                try await backend.prefill(
                    model: LoadedTextModel(
                        storage: makeQuantizableLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("quantized live prefill")],
                    prefillStepSize: 4,
                    resumeHint: "live-active-kv",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
            }
        }

        XCTAssertEqual(result.appliedAcceleration.mode, .activeKvQuantized)
        XCTAssertEqual(result.appliedAcceleration.activeKvQuantProfile, "q4")
        XCTAssertEqual(result.activeKVQuantizationRatio, 25)
    }

    func testAutoSwiftMLXBackendDecodeUsesLiveModelContainerBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge decode live path")],
                    prefillStepSize: 32,
                    resumeHint: "live-decode",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        XCTAssertFalse(renderedTokenChunks(from: events).joined().isEmpty)
        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.promptTokens, promptTokens.count)
        XCTAssertGreaterThan(summary.completionTokens, 0)
        XCTAssertNotNil(summary.tokensPerSecond)
    }
    #endif

    func testChatMessageConversionFlattensTextAndRejectsUnsupportedParts() throws {
        let converted = try convertChatMessages([
            makeUserMessage("line one", extraText: "line two"),
            makeSystemMessage("system prompt"),
        ])

        XCTAssertEqual(converted.count, 2)
        XCTAssertEqual(converted[0].content, "line one\nline two")
        XCTAssertEqual(converted[1].content, "system prompt")

        var invalid = Melix_Worker_V1_ChatMessage()
        invalid.role = "user"
        var imagePart = Melix_Worker_V1_MessagePart()
        imagePart.imageUri = "file:///tmp/test.png"
        invalid.parts = [imagePart]

        XCTAssertThrowsError(try convertChatMessages([invalid]))
    }

    func testChatMessageConversionCoversAssistantToolEmptyAndUnsupportedRoles() throws {
        let assistant = try convertChatMessages([makeRoleMessage("assistant", text: "draft")])
        XCTAssertEqual(assistant.first?.content, "draft")

        let tool = try convertChatMessages([makeRoleMessage("tool", text: "tool output")])
        XCTAssertEqual(tool.first?.content, "tool output")

        let emptyRole = try convertChatMessages([makeRoleMessage("", text: "fallback user")])
        XCTAssertEqual(emptyRole.first?.content, "fallback user")

        XCTAssertThrowsError(try convertChatMessages([]))
        XCTAssertThrowsError(try convertChatMessages([makeRoleMessage("critic", text: "unsupported")]))
    }

    func testFlattenTextContentSkipsUnsetParts() throws {
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var textPart = Melix_Worker_V1_MessagePart()
        textPart.text = "hello"
        let emptyPart = Melix_Worker_V1_MessagePart()
        message.parts = [textPart, emptyPart]

        XCTAssertEqual(try flattenTextContent(from: message), "hello")
    }

    func testGenerateParameterMappingUsesPhaseOneDefaults() {
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0.7
        sampling.topP = 0.95
        sampling.maxOutputTokens = 64
        sampling.frequencyPenalty = 0.5
        sampling.presencePenalty = 0.2

        let parameters = makeGenerateParameters(from: sampling)

        XCTAssertEqual(parameters.temperature, 0.7)
        XCTAssertEqual(parameters.topP, 0.95)
        XCTAssertEqual(parameters.maxTokens, 64)
        XCTAssertEqual(parameters.repetitionPenalty, 0.5)
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

    func testTextRuntimeForwardsGenerateEventsAndDefaultGenerateThrowsUnavailable() async throws {
        let runtime = TextRuntime(backend: FakeRuntimeBackend(generatedChunks: ["swift"]))
        let generated = try await runtime.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("go")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: generated)
        XCTAssertEqual(renderedTokenChunks(from: events), ["swift"])

        let unavailableRuntime = TextRuntime(backend: DefaultUnloadBackend())
        let unavailableModel = try await unavailableRuntime.loadModel(spec: Melix_Worker_V1_ModelSpec())
        await XCTAssertThrowsErrorAsync(
            try await unavailableRuntime.generateEvents(
                model: unavailableModel.model,
                messages: [makeUserMessage("go")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
    }

    func testTextRuntimeForwardsPrefillAndDefaultPrefillThrowsUnavailable() async throws {
        let runtime = TextRuntime(backend: FakeRuntimeBackend())
        let loaded = try await runtime.loadModel(spec: Melix_Worker_V1_ModelSpec())
        let result = try await runtime.prefill(
            model: loaded.model,
            messages: [makeUserMessage("prefill runtime")],
            prefillStepSize: 8,
            resumeHint: "runtime-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        XCTAssertEqual(result.promptTokens, 1)
        XCTAssertEqual(result.context.promptTokens, 1)
        XCTAssertEqual((result.context.storage as? [String: String])?["resume_hint"], "runtime-resume")
        XCTAssertEqual((result.context.storage as? [String: String])?["prefill_step_size"], "8")

        let unavailableRuntime = TextRuntime(backend: DefaultUnloadBackend())
        let unavailableModel = try await unavailableRuntime.loadModel(spec: Melix_Worker_V1_ModelSpec())

        await XCTAssertThrowsErrorAsync(
            try await unavailableRuntime.prefill(
                model: unavailableModel.model,
                messages: [makeUserMessage("go")],
                prefillStepSize: 4,
                resumeHint: "unavailable",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { false }
            )
        )
    }

    func testTextRuntimeForwardsDecodeAndDefaultDecodeThrowsUnavailable() async throws {
        let runtime = TextRuntime(backend: FakeRuntimeBackend(decodedChunks: ["decode", " path"]))
        let loaded = try await runtime.loadModel(spec: Melix_Worker_V1_ModelSpec())
        let prefill = try await runtime.prefill(
            model: loaded.model,
            messages: [makeUserMessage("decode runtime")],
            prefillStepSize: 8,
            resumeHint: "decode-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let decoded = try await runtime.decodeEvents(
            model: loaded.model,
            context: prefill.context,
            sampling: Melix_Worker_V1_SamplingConfig(),
            maxOutputTokens: 8,
            decodeStepSize: 1,
            prefillToken: "",
            acceleration: acceleration,
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: decoded)
        XCTAssertEqual(renderedTokenChunks(from: events), ["decode", " path"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 2)

        let unavailableRuntime = TextRuntime(backend: DefaultUnloadBackend())
        let unavailableModel = try await unavailableRuntime.loadModel(spec: Melix_Worker_V1_ModelSpec())

        await XCTAssertThrowsErrorAsync(
            try await unavailableRuntime.decodeEvents(
                model: unavailableModel.model,
                context: TextPrefillContext(storage: [:], promptTokens: 1),
                sampling: Melix_Worker_V1_SamplingConfig(),
                maxOutputTokens: 4,
                decodeStepSize: 1,
                prefillToken: "",
                acceleration: acceleration,
                shouldAbort: { false }
            )
        )
    }

    func testDrainTransitionsRuntimeStateToDraining() async throws {
        let services = makeServices()

        _ = try await withTestServerContextRPCCancellationHandle { handle in
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

        let stats = try await withTestServerContextRPCCancellationHandle { handle in
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

    func testRuntimeRegistrySupportsLoadedModelLookupAndReadableErrors() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var request = Melix_Worker_V1_ModelSpec()
        request.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(request)
        let found = await registry.getLoadedModel(loaded.handle)
        let missing = await registry.getLoadedModel("missing")

        XCTAssertEqual(found?.handle, loaded.handle)
        XCTAssertNil(missing)
        XCTAssertEqual(WorkerRuntimeRegistryError.unknownModelHandle.errorDescription, "Unknown model handle.")
    }

    func testRuntimeRegistryTracksBusyStateAndGenerateEventsForLoadedModel() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend(generatedChunks: ["one", " two"]))
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        await registry.startRequest()
        let busyStats = await registry.runtimeStats()
        await registry.finishRequest()
        let idleStats = await registry.runtimeStats()

        let stream = try await registry.generateEvents(
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: stream)

        XCTAssertEqual(busyStats.workerState, "busy")
        XCTAssertEqual(idleStats.workerState, "idle")
        XCTAssertEqual(renderedTokenChunks(from: events), ["one", " two"])
        await XCTAssertThrowsErrorAsync(
            try await registry.generateEvents(
                modelHandle: "missing",
                messages: [makeUserMessage("registry")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
    }

    func testRuntimeRegistryStoresPrefillContextsForLoadedModel() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let result = try await registry.prefill(
            requestID: "req-prefill-registry",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry prefill")],
            prefillStepSize: 16,
            returnDecodeHandle: true,
            resumeHint: "registry-resume",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let stored = await registry.prefillContext(for: result.decodeHandle)
        let contextCount = await registry.prefillContextCount()
        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertFalse(result.decodeHandle.isEmpty)
        XCTAssertFalse(result.blockTableID.isEmpty)
        XCTAssertEqual(result.blockTable.scopeID, cacheResponse.snapshot.scopes.first?.scopeID)
        XCTAssertEqual(result.blockTable.blocks.count, 1)
        XCTAssertEqual(result.promptTokens, 1)
        XCTAssertEqual(contextCount, 1)
        XCTAssertEqual(stored?.modelHandle, loaded.handle)
        XCTAssertEqual(stored?.promptTokens, 1)
        XCTAssertEqual(stored?.requestID, "req-prefill-registry")
        XCTAssertEqual(stored?.blockTableID, result.blockTableID)
        XCTAssertEqual(cacheResponse.stats.blockCount, 1)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.first?.tokenLength, 1)
    }

    func testRuntimeRegistryPrefillReusesMatchingHotPrefixMetadata() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let first = try await registry.prefill(
            requestID: "req-prefill-reuse-1",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry cache reuse")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "reuse-1",
            acceleration: acceleration,
            shouldAbort: { false }
        )
        let second = try await registry.prefill(
            requestID: "req-prefill-reuse-2",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry cache reuse")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "reuse-2",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertEqual(first.blockTableID, second.blockTableID)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
        XCTAssertGreaterThan(cacheResponse.stats.l1HitRate, 0)
        XCTAssertGreaterThan(cacheResponse.stats.dedupRatio, 1)
    }

    func testRuntimeRegistryPrefillWithoutDecodeHandleDoesNotStoreContextAndUnloadClearsStoredContexts() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let withoutHandle = try await registry.prefill(
            requestID: "req-prefill-no-handle",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry prefill no handle")],
            prefillStepSize: 8,
            returnDecodeHandle: false,
            resumeHint: "no-handle",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertTrue(withoutHandle.decodeHandle.isEmpty)
        let countWithoutHandle = await registry.prefillContextCount()
        XCTAssertEqual(countWithoutHandle, 0)

        let withHandle = try await registry.prefill(
            requestID: "req-prefill-clear",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry prefill clear")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "clear",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertFalse(withHandle.decodeHandle.isEmpty)
        let countWithHandle = await registry.prefillContextCount()
        XCTAssertEqual(countWithHandle, 1)

        let unloaded = await registry.unloadModel(loaded.handle)
        let countAfterUnload = await registry.prefillContextCount()
        let storedAfterUnload = await registry.prefillContext(for: withHandle.decodeHandle)
        XCTAssertTrue(unloaded)
        XCTAssertEqual(countAfterUnload, 0)
        XCTAssertNil(storedAfterUnload)
    }

    func testRuntimeRegistryBeginDecodeConsumesStoredContextAndTracksActiveDecodeState() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline
        let prefill = try await registry.prefill(
            requestID: "req-prefill-begin-decode",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry decode")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "begin-decode",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let session = try await registry.beginDecode(decodeHandle: prefill.decodeHandle)
        let statsDuringDecode = await registry.runtimeStats()
        let storedAfterBegin = await registry.prefillContext(for: prefill.decodeHandle)
        await registry.finishDecode()
        let statsAfterDecode = await registry.runtimeStats()

        XCTAssertEqual(session.prefill.requestID, "req-prefill-begin-decode")
        XCTAssertEqual(session.loadedModel.handle, loaded.handle)
        XCTAssertEqual(statsDuringDecode.activeDecodes, 1)
        XCTAssertEqual(statsDuringDecode.activeRequests, 1)
        XCTAssertNil(storedAfterBegin)
        XCTAssertEqual(statsAfterDecode.activeDecodes, 0)
        XCTAssertEqual(statsAfterDecode.activeRequests, 0)

        await XCTAssertThrowsErrorAsync(
            try await registry.beginDecode(decodeHandle: "missing-decode")
        )
    }

    func testRuntimeLifecycleLoadAndUnloadTrackModelState() async throws {
        let backend = FakeRuntimeBackend()
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: backend,
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let listedResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let loadedStats = try await withTestServerContextRPCCancellationHandle { handle in
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

        let unloadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let postUnloadStats = try await withTestServerContextRPCCancellationHandle { handle in
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

        let failedLoad = try await withTestServerContextRPCCancellationHandle { handle in
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

        let missingUnload = try await withTestServerContextRPCCancellationHandle { handle in
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

        let embedResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let rerankResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let transcribeResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let speakResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.speak(
                request: Melix_Worker_V1_SpeakRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Speak.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let imageGenerateResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let imageEditResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        XCTAssertEqual(embedResponse.error.code, "unimplemented")
        XCTAssertEqual(rerankResponse.error.code, "unimplemented")
        XCTAssertEqual(transcribeResponse.error.code, "unimplemented")
        XCTAssertEqual(speakResponse.error.code, "unimplemented")
        XCTAssertEqual(imageGenerateResponse.error.code, "unimplemented")
        XCTAssertEqual(imageEditResponse.error.code, "unimplemented")
    }

    func testPrefillReturnsDecodeHandleAndMetricsForLoadedModel() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [100, 2_148]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-success"
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.prefillStepSize = 32
            request.resumeHint = "tool-follow-up"
            request.execution.acceleration.mode = .baseline
            request.messages = [makeUserMessage("prefill me")]

            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let stored = await services.registry.prefillContext(for: response.decodeHandle)
        let contextCount = await services.registry.prefillContextCount()
        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertFalse(response.decodeHandle.isEmpty)
        XCTAssertFalse(response.blockTableID.isEmpty)
        XCTAssertEqual(response.blockTable.blocks.count, 1)
        XCTAssertEqual(response.promptTokens, 1)
        XCTAssertEqual(response.lifecyclePhase, .executionPrefilling)
        XCTAssertEqual(response.admissionState, .admissionAdmitted)
        XCTAssertEqual(response.appliedAcceleration.mode, .baseline)
        XCTAssertEqual(contextCount, 1)
        XCTAssertEqual(stored?.modelHandle, loadResponse.modelHandle)
        XCTAssertEqual(stored?.promptTokens, 1)
        XCTAssertEqual(metrics["swift_text.prefill_context_count"], 1)
        XCTAssertEqual(metrics["swift_text.prefill_prompt_tokens"], 1)
        XCTAssertEqual(metrics["swift_text.accelerated_prefill_gain_pct"], 0)
        XCTAssertEqual(metrics["swift_text.active_kv_quantization_ratio"], 0)
        XCTAssertEqual(metrics["swift_text.cache_block_count"], 1)
        XCTAssertEqual(metrics["swift_text.cache_prefix_count"], 1)
        XCTAssertNotNil(metrics["swift_text.prefill_ms"])
    }

    func testPrefillReturnsAcceleratedPrefillMetricsAndStoredAppliedPolicy() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-accelerated"
            request.execution.modelHandle = loadResponse.modelHandle
            request.execution.acceleration.mode = .acceleratedPrefill
            request.execution.acceleration.prefillHint = "json-schema"
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("{\"kind\":\"structured\"}")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let stored = await services.registry.prefillContext(for: response.decodeHandle)
        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.appliedAcceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(response.appliedAcceleration.prefillHint, "json-schema")
        XCTAssertEqual(metrics["swift_text.accelerated_prefill_gain_pct"], 50)
        XCTAssertEqual(stored?.acceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(stored?.acceleration.prefillHint, "json-schema")
    }

    func testPrefillReturnsActiveKVQuantizationRatioAndNormalizedProfile() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-active-kv"
            request.execution.modelHandle = loadResponse.modelHandle
            request.execution.acceleration.mode = .activeKvQuantized
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("cache quantized")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let stored = await services.registry.prefillContext(for: response.decodeHandle)
        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.appliedAcceleration.mode, .activeKvQuantized)
        XCTAssertEqual(response.appliedAcceleration.activeKvQuantProfile, "q4")
        XCTAssertEqual(metrics["swift_text.active_kv_quantization_ratio"], 25)
        XCTAssertEqual(stored?.acceleration.mode, .activeKvQuantized)
        XCTAssertEqual(stored?.acceleration.activeKvQuantProfile, "q4")
    }

    func testPrefillSurfacesActivePrefillInRuntimeStatsWhileRunning() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(prefillDelayNanos: 150_000_000)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let task = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-prefill-busy"
                request.execution.modelHandle = loadResponse.modelHandle
                request.returnDecodeHandle = true
                request.messages = [makeUserMessage("slow prefill")]
                return try await services.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
        }

        try? await Task.sleep(nanoseconds: 30_000_000)

        let statsWhileBusy = try await withTestServerContextRPCCancellationHandle { handle in
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

        _ = try await task.value

        let statsAfter = try await withTestServerContextRPCCancellationHandle { handle in
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

        XCTAssertEqual(statsWhileBusy.stats.workerState, "busy")
        XCTAssertEqual(statsWhileBusy.stats.activeRequests, 1)
        XCTAssertEqual(statsWhileBusy.stats.activePrefills, 1)
        XCTAssertEqual(statsWhileBusy.stats.activeDecodes, 0)
        XCTAssertEqual(statsAfter.stats.activePrefills, 0)
    }

    func testPrefillReturnsNotFoundForUnknownModelHandle() async throws {
        let services = makeServices()

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-missing"
            request.execution.modelHandle = "missing-handle"
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("missing")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "not_found")
    }

    func testPrefillReturnsRuntimeErrorForBackendFailureWithoutRequestID() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(prefillError: FakeRuntimeBackendError.prefillFailed)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("prefill error")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "runtime_error")
        XCTAssertEqual(services.metrics.counters["swift_text.rpc_error_count"], 1)
        XCTAssertNotNil(services.metrics.counters["swift_text.prefill_ms"])
    }

    func testGenerateStreamsPrefillTokenUsageAndCompletedForLoadedModel() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [100, 2_148]
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-generate-success"
        request.execution.modelHandle = loadResponse.modelHandle
        request.returnUsage = true
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Say hello from Swift."
        message.parts = [part]
        request.messages = [message]

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertGreaterThanOrEqual(recorded.count, 3)
        XCTAssertEqual(recorded.first?.requestID, "req-generate-success")
        XCTAssertEqual(recorded.first?.executionKind, "generate")
        XCTAssertTrue(matches(recorded.first?.payload, .prefillStarted))
        XCTAssertTrue(recorded.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertTrue(recorded.contains(where: { matches($0.payload, .usageDelta) }))
        XCTAssertTrue(matches(recorded.last?.payload, .completed))
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        XCTAssertFalse(recorded.last?.completed.assistantText.isEmpty ?? true)
        XCTAssertEqual(services.metrics.counters["swift_text.stream_event_count"], recorded.count)
    }

    func testGenerateReturnsNotFoundErrorEventForUnknownModelHandle() async throws {
        let services = makeServices()
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-generate-missing"
        request.execution.modelHandle = "missing-model-handle"

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded[0].requestID, "req-generate-missing")
        XCTAssertEqual(recorded[0].executionKind, "generate")
        XCTAssertTrue(matches(recorded[0].payload, .error))
        XCTAssertEqual(recorded[0].error.error.code, "not_found")
    }

    func testAbortCancelsActiveGenerationAndReportsCancelledCompletion() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(
                generatedChunks: ["one", " two", " three", " four"],
                tokenDelayNanos: 40_000_000
            ),
            residentMemorySamples: [100, 2_148]
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var generateRequest = Melix_Worker_V1_GenerateRequest()
        generateRequest.execution.id.requestID = "req-generate-abort"
        generateRequest.execution.modelHandle = loadResponse.modelHandle
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Generate enough tokens to be cancellable."
        message.parts = [part]
        generateRequest.messages = [message]

        let generateTask = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.generate(
                    request: generateRequest,
                    response: RPCWriter(wrapping: writer),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
        }

        try await Task.sleep(nanoseconds: 20_000_000)

        let abortResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_AbortRequest()
            request.requestID = "req-generate-abort"
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

        _ = try await generateTask.value

        let recorded = await writer.snapshot()
        XCTAssertTrue(abortResponse.ok)
        XCTAssertTrue(abortResponse.found)
        XCTAssertGreaterThanOrEqual(recorded.count, 2)
        XCTAssertTrue(matches(recorded.last?.payload, .completed))
        XCTAssertEqual(recorded.last?.completed.finishReason, "cancelled")
        XCTAssertNotNil(services.metrics.counters["swift_text.abort_ms"])
    }

    func testDecodeStreamingRpcStreamsTokensAndCleansUpStoredContext() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(decodedChunks: ["decode", " result"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-decode-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("decode rpc")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertGreaterThanOrEqual(recorded.count, 4)
        XCTAssertEqual(recorded[0].decodeStarted.decodeHandle, prefillResponse.decodeHandle)
        XCTAssertEqual(recorded[0].executionKind, "decode")
        XCTAssertEqual(recorded[1].tokenDelta.text, "decode")
        XCTAssertEqual(recorded[2].tokenDelta.text, " result")
        XCTAssertEqual(recorded[3].usageDelta.completionTokens, 2)
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        let storedAfterDecode = await services.registry.prefillContext(for: prefillResponse.decodeHandle)
        XCTAssertNil(storedAfterDecode)
        XCTAssertEqual(services.metrics.counters["swift_text.decode_tokens_per_second"], 16)
    }

    func testDecodeStreamingRpcReturnsStructuredNotFoundForMissingDecodeHandle() async throws {
        let services = makeServices()
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-missing-decode"
        request.decodeHandle = "missing-decode"

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded[0].error.error.code, "not_found")
    }

    func testDecodeStreamingRpcFallsBackToStoredRequestIDAndHandlesSummaryOnlyDecode() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(decodedChunks: [])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-stored-decode"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("summary only decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded.count, 3)
        XCTAssertEqual(recorded[0].requestID, "req-stored-decode")
        XCTAssertGreaterThan(recorded[1].usageDelta.promptTokens, 0)
        XCTAssertEqual(recorded[1].usageDelta.completionTokens, 0)
        XCTAssertEqual(recorded[2].completed.assistantText, "")
        XCTAssertEqual(recorded[2].completed.finishReason, "stop")
        XCTAssertNotNil(services.metrics.counters["swift_text.decode_ttft_ms"])
    }

    func testDecodeStreamingRpcReturnsStructuredRuntimeErrorForBackendDecodeFailure() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(decodeError: FakeRuntimeBackendError.decodeFailed)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-runtime-error-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("runtime error decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-runtime-error"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded[0].error.error.code, "runtime_error")
    }

    func testDecodeStreamingRpcFallsBackToBaselineWhenSpeculativeDecodeAllowsFallback() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["fallback"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-fallback-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .speculativeDecode
        prefillRequest.execution.acceleration.allowBaselineFallback = true
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("fallback decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-fallback-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = true
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded.first?.decodeStarted.decodeHandle, prefillResponse.decodeHandle)
        XCTAssertEqual(recorded.first?.accelerationMode, .baseline)
        XCTAssertFalse(matches(recorded.first?.payload, .accelerationApplied))
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
    }

    func testDecodeStreamingRpcReturnsStructuredUnimplementedWhenSpeculativeDecodeCannotFallback() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["unused"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-no-fallback-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("no fallback decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-no-fallback-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded[0].error.error.code, "unimplemented")
    }

    func testDecodeStreamingRpcCanBeAbortedWithoutUsageTrailer() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(
                decodedChunks: ["decode", " cancel", " tail"],
                decodeDelayNanos: 40_000_000
            )
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-decode-cancel-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("cancel decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-decode-cancel"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.returnUsage = true

        let decodeTask = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
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
        }

        try await Task.sleep(nanoseconds: 60_000_000)
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var abortRequest = Melix_Worker_V1_AbortRequest()
            abortRequest.requestID = "req-decode-cancel"
            return try await services.inference.abort(
                request: abortRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        _ = try await decodeTask.value

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.last?.completed.finishReason, "cancelled")
        XCTAssertFalse(recorded.contains(where: { matches($0.payload, .usageDelta) }))
    }

    func testDecodeStreamingRpcSupportsDeterministicSpeculativeMetrics() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "deterministic",
            ],
            backend: DeterministicTextBackend(tokenDelayNanos: 1_000_000)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-spec-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .speculativeDecode
        prefillRequest.execution.acceleration.allowBaselineFallback = false
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("speculative decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-spec-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.mode, .speculativeDecode)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_acceptance_rate"], 66)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_rollback_rate"], 33)
    }

    func testDecodeStreamingRpcRecordsActiveKVQuantizationRatio() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["active", " kv"])
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-active-kv-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .activeKvQuantized
        prefillRequest.execution.acceleration.activeKvQuantProfile = "q8"
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("active kv decode")]

        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-active-kv-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
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
        XCTAssertTrue(matches(recorded.first?.payload, .accelerationApplied))
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.mode, .activeKvQuantized)
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.activeKvQuantProfile, "q8")
        XCTAssertEqual(services.metrics.counters["swift_text.active_kv_quantization_ratio"], 50)
    }

    func testCacheManagementRpcsExposeHotAndDiskTierMetadata() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let services = makeServices(
                environment: [
                    "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                    "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path,
                ],
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-cache-prefill"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("cache me")]

                return try await services.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let cacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

            var pinRequest = Melix_Worker_V1_PinPrefixRequest()
            pinRequest.prefix = try XCTUnwrap(cacheResponse.snapshot.hotPrefixes.first)
            let pinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.pinPrefix(
                    request: pinRequest,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.PinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var unpinRequest = Melix_Worker_V1_UnpinPrefixRequest()
            unpinRequest.prefix = pinRequest.prefix
            let unpinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.unpinPrefix(
                    request: unpinRequest,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.UnpinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-cache-prefill"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let postSaveCacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = saveResponse.snapshotID
                return try await services.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var purgeRequest = Melix_Worker_V1_PurgeCacheRequest()
            purgeRequest.scope = pinRequest.prefix.scope
            purgeRequest.includePinned = true
            let purgeResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.purgeCache(
                    request: purgeRequest,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.PurgeCache.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let postPurgeCacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

            XCTAssertTrue(prefillResponse.ok)
            XCTAssertEqual(cacheResponse.stats.blockCount, 1)
            XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
            XCTAssertGreaterThan(cacheResponse.stats.l2Bytes, 0)
            XCTAssertTrue(pinResponse.ok)
            XCTAssertTrue(unpinResponse.ok)
            XCTAssertTrue(saveResponse.ok)
            XCTAssertFalse(saveResponse.snapshotID.isEmpty)
            XCTAssertEqual(postSaveCacheResponse.stats.snapshotCount, 1)
            XCTAssertGreaterThan(postSaveCacheResponse.stats.quantizedBytes, 0)
            XCTAssertGreaterThan(postSaveCacheResponse.stats.compressionRatio, 1.0)
            XCTAssertTrue(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.snapshot.snapshotID, saveResponse.snapshotID)
            XCTAssertEqual(restoreResponse.blockTableID, prefillResponse.blockTableID)
            XCTAssertTrue(purgeResponse.ok)
            XCTAssertEqual(purgeResponse.purgedBlocks, 2)
            XCTAssertEqual(postPurgeCacheResponse.stats.blockCount, 0)
            XCTAssertEqual(postPurgeCacheResponse.snapshot.hotPrefixes.count, 0)
            XCTAssertEqual(postPurgeCacheResponse.stats.snapshotCount, 0)
        }
    }

    func testBoundarySnapshotRestoreSurvivesRegistryRestartOnDeterministicBackend() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]

            let initialServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await initialServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-restart-prefill"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("persist this prompt")]
                return try await initialServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-restart-prefill"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await initialServices.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(saveResponse.ok)

            let restartedServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let restartedLoadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await restartedServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
            XCTAssertTrue(restartedLoadResponse.ok)

            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = saveResponse.snapshotID
                return try await restartedServices.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
            try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_DecodeRequest()
                request.execution.id.requestID = "req-restart-decode"
                request.execution.modelHandle = restartedLoadResponse.modelHandle
                request.decodeHandle = restoreResponse.decodeHandle
                request.returnUsage = true
                try await restartedServices.inference.decode(
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

            let restoredCacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await restartedServices.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let recorded = await writer.snapshot()
            XCTAssertTrue(restoreResponse.ok)
            XCTAssertFalse(restoreResponse.decodeHandle.isEmpty)
            XCTAssertTrue(recorded.contains(where: { matches($0.payload, .tokenDelta) }))
            XCTAssertEqual(restoredCacheResponse.stats.snapshotCount, 1)
            XCTAssertGreaterThan(restoredCacheResponse.stats.l2Bytes, 0)
            XCTAssertEqual(restoredCacheResponse.stats.l2RestoreHitRate, 1.0, accuracy: 0.0001)
        }
    }

    func testPrefillCanRestoreBoundarySnapshotsFromCacheHints() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

            var initialPrefill = Melix_Worker_V1_PrefillRequest()
            initialPrefill.execution.id.requestID = "req-restore-source"
            initialPrefill.execution.modelHandle = loadResponse.modelHandle
            initialPrefill.execution.cacheHints.allowL2 = true
            initialPrefill.execution.cacheHints.persistL2 = true
            initialPrefill.returnDecodeHandle = true
            initialPrefill.messages = [makeUserMessage("persist this boundary")]
            let initialPrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: initialPrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-restore-source"
                request.decodeHandle = initialPrefillResponse.decodeHandle
                request.tokenBoundary = initialPrefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var restorePrefill = Melix_Worker_V1_PrefillRequest()
            restorePrefill.execution.id.requestID = "req-restore-target"
            restorePrefill.execution.modelHandle = loadResponse.modelHandle
            restorePrefill.execution.cacheHints.restoreSnapshotID = savedSnapshot.snapshotID
            restorePrefill.returnDecodeHandle = true
            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: restorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.restoredSnapshotID, savedSnapshot.snapshotID)
            XCTAssertEqual(restoreResponse.blockTableID, initialPrefillResponse.blockTableID)
            XCTAssertFalse(restoreResponse.decodeHandle.isEmpty)
            let restoredContext = await services.registry.prefillContext(for: restoreResponse.decodeHandle)
            XCTAssertEqual(restoredContext?.restoredSnapshotID, savedSnapshot.snapshotID)
        }
    }

    func testDecodeStreamingRpcEmitsRecoveryEventsForRestoredSnapshots() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: FakeRuntimeBackend(decodedChunks: ["resume", " ok"])
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

            var sourcePrefill = Melix_Worker_V1_PrefillRequest()
            sourcePrefill.execution.id.requestID = "req-recovery-source"
            sourcePrefill.execution.modelHandle = loadResponse.modelHandle
            sourcePrefill.execution.cacheHints.allowL2 = true
            sourcePrefill.execution.cacheHints.persistL2 = true
            sourcePrefill.returnDecodeHandle = true
            sourcePrefill.messages = [makeUserMessage("persist for recovery decode")]
            let sourcePrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: sourcePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-recovery-source"
                request.decodeHandle = sourcePrefillResponse.decodeHandle
                request.tokenBoundary = sourcePrefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var restorePrefill = Melix_Worker_V1_PrefillRequest()
            restorePrefill.execution.id.requestID = "req-recovery-decode"
            restorePrefill.execution.modelHandle = loadResponse.modelHandle
            restorePrefill.execution.cacheHints.restoreSnapshotID = savedSnapshot.snapshotID
            restorePrefill.returnDecodeHandle = true
            let restorePrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: restorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
            var decodeRequest = Melix_Worker_V1_DecodeRequest()
            decodeRequest.execution.id.requestID = "req-recovery-decode"
            decodeRequest.execution.modelHandle = loadResponse.modelHandle
            decodeRequest.execution.cacheHints.saveBoundarySnapshot = true
            decodeRequest.decodeHandle = restorePrefillResponse.decodeHandle
            decodeRequest.returnUsage = true

            try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.decode(
                    request: decodeRequest,
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
            let startedEvent = try XCTUnwrap(recorded.first(where: { !$0.decodeStarted.decodeHandle.isEmpty }))
            XCTAssertEqual(startedEvent.decodeStarted.decodeHandle, restorePrefillResponse.decodeHandle)
            let cacheDecisionEvent = try XCTUnwrap(recorded.first(where: { !$0.cacheDecision.restoredSnapshotID.isEmpty }))
            XCTAssertEqual(cacheDecisionEvent.cacheDecision.restoredSnapshotID, savedSnapshot.snapshotID)
            let snapshotEvent = try XCTUnwrap(recorded.first(where: { !$0.snapshotCreated.snapshotID.isEmpty }))
            XCTAssertFalse(snapshotEvent.snapshotCreated.snapshotID.isEmpty)
            XCTAssertGreaterThan(snapshotEvent.snapshotCreated.tokenBoundary, 0)
            XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
            XCTAssertNotNil(services.metrics.counters["swift_text.cache_snapshot_save_ms"])
        }
    }

    func testCacheManagementRpcsReturnStructuredErrorsForUnknownRefsAndUnloadedSnapshotModels() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            var unknownPrefix = Melix_Worker_V1_PrefixRef()
            unknownPrefix.prefixID = "missing-prefix"

            let pinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PinPrefixRequest()
                request.prefix = unknownPrefix
                return try await services.cache.pinPrefix(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.PinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let unpinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_UnpinPrefixRequest()
                request.prefix = unknownPrefix
                return try await services.cache.unpinPrefix(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.UnpinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveMissingResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "missing-request"
                request.decodeHandle = "missing-decode"
                request.tokenBoundary = 2
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restoreMissingResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = "missing-snapshot"
                return try await services.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let initialServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )
            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await initialServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-precondition-prefill"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.messages = [makeUserMessage("persist before failed precondition")]
                return try await initialServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-precondition-prefill"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await initialServices.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let unloadedServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )
            let failedPreconditionRestore = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = savedSnapshot.snapshotID
                return try await unloadedServices.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertFalse(pinResponse.ok)
            XCTAssertEqual(pinResponse.error.code, "not_found")
            XCTAssertFalse(unpinResponse.ok)
            XCTAssertEqual(unpinResponse.error.code, "not_found")
            XCTAssertFalse(saveMissingResponse.ok)
            XCTAssertEqual(saveMissingResponse.error.code, "not_found")
            XCTAssertFalse(restoreMissingResponse.ok)
            XCTAssertEqual(restoreMissingResponse.error.code, "not_found")
            XCTAssertFalse(failedPreconditionRestore.ok)
            XCTAssertEqual(failedPreconditionRestore.error.code, "failed_precondition")
            XCTAssertGreaterThanOrEqual(services.metrics.counters["swift_text.rpc_error_count"] ?? 0, 2)
        }
    }

    func testDiskCacheStoreSupportsPurgesRestoreMissesAndModelEviction() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let fileManager = FileManager.default
            try fileManager.createDirectory(
                at: cacheRoot.appendingPathComponent("prefixes", isDirectory: true),
                withIntermediateDirectories: true
            )
            try fileManager.createDirectory(
                at: cacheRoot.appendingPathComponent("snapshots", isDirectory: true),
                withIntermediateDirectories: true
            )
            try Data("not-json".utf8).write(
                to: cacheRoot.appendingPathComponent("prefixes/bad.json"),
                options: [.atomic]
            )
            try Data("still-not-json".utf8).write(
                to: cacheRoot.appendingPathComponent("snapshots/bad.json"),
                options: [.atomic]
            )

            let store = DiskCacheStore(rootPath: cacheRoot.path)
            let missingRestore = await store.restoreSnapshot(snapshotID: "missing-snapshot")
            let initialSummary = await store.summary()
            XCTAssertNil(missingRestore)
            XCTAssertEqual(initialSummary.l2RestoreHitRate, 0, accuracy: 0.0001)

            let scope = makeCacheScope(scopeID: "scope-alpha", modelID: "model-alpha")
            let cacheKey = makeCacheKey(scopeID: scope.scopeID, prefixSeed: "alpha-prefix", fingerprintSeed: "alpha-fingerprint")
            let pinnedPrefix = makePrefixRef(
                prefixID: "prefix-alpha",
                scope: scope,
                cacheKey: cacheKey,
                pinned: true
            )
            let blockTable = makeBlockTable(scopeID: scope.scopeID, cacheKey: cacheKey, blockIDs: ["a0", "a1"], bytes: [120, 80])
            await store.persistPrefix(
                prefix: pinnedPrefix,
                blockTableID: "table-alpha",
                blockTable: blockTable,
                quantizedBytes: 100
            )

            let model = makeModelSpec(modelID: "model-alpha")
            let snapshotRef = makeSnapshotRef(snapshotID: "snapshot-alpha")
            let messages = [makeUserMessage("alpha snapshot")]
            await store.saveSnapshot(
                snapshot: snapshotRef,
                model: model,
                messages: messages,
                resumeHint: "resume-alpha",
                acceleration: makeAccelerationPolicy(mode: .baseline),
                promptTokens: 4,
                blockTableID: "table-alpha",
                blockTable: blockTable,
                prefix: nil
            )

            let summaryAfterSave = await store.summary()
            XCTAssertEqual(summaryAfterSave.snapshotCount, 1)
            XCTAssertEqual(summaryAfterSave.scopes.first?.snapshotCount, 1)
            XCTAssertEqual(summaryAfterSave.quantizedBytes, 100)
            XCTAssertEqual(summaryAfterSave.unquantizedBytes, 200)

            let skippedPinned = await store.purge(scope: scope, cacheKey: cacheKey, includePinned: false)
            let afterSkippedPinned = await store.summary()
            XCTAssertEqual(skippedPinned, 0)
            XCTAssertEqual(afterSkippedPinned.l2Bytes, 100)

            let purgedPinned = await store.purge(scope: scope, cacheKey: cacheKey, includePinned: true)
            let afterPurgedPinned = await store.summary()
            XCTAssertEqual(purgedPinned, 2)
            XCTAssertEqual(afterPurgedPinned.snapshotCount, 0)
            XCTAssertEqual(afterPurgedPinned.l2Bytes, 0)

            let otherScope = makeCacheScope(scopeID: "scope-beta", modelID: "model-beta")
            let otherKey = makeCacheKey(scopeID: otherScope.scopeID, prefixSeed: "beta-prefix", fingerprintSeed: "beta-fingerprint")
            let otherPrefix = makePrefixRef(prefixID: "prefix-beta", scope: otherScope, cacheKey: otherKey)
            let otherTable = makeBlockTable(scopeID: otherScope.scopeID, cacheKey: otherKey, blockIDs: ["b0"], bytes: [64])
            let otherSnapshot = makeSnapshotRef(snapshotID: "snapshot-beta")
            await store.saveSnapshot(
                snapshot: otherSnapshot,
                model: makeModelSpec(modelID: "model-beta"),
                messages: [makeUserMessage("beta snapshot")],
                resumeHint: "resume-beta",
                acceleration: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "q4"),
                promptTokens: 3,
                blockTableID: "table-beta",
                blockTable: otherTable,
                prefix: otherPrefix
            )

            let restoredSnapshot = await store.restoreSnapshot(snapshotID: otherSnapshot.snapshotID)
            let restored = try XCTUnwrap(restoredSnapshot)
            XCTAssertEqual(restored.snapshot.snapshotID, otherSnapshot.snapshotID)
            XCTAssertEqual(restored.blockTableID, "table-beta")

            await store.purgeModel(modelID: "model-beta")
            let finalSummary = await store.summary()
            XCTAssertEqual(finalSummary.snapshotCount, 0)
            XCTAssertEqual(finalSummary.l2Bytes, 0)
            XCTAssertEqual(finalSummary.l2RestoreHitRate, 0.5, accuracy: 0.0001)
        }
    }

    func testDiskCacheQuantizationHelpersClampAndNormalizeProfiles() {
        let table = makeBlockTable(
            scopeID: "scope-quant",
            cacheKey: makeCacheKey(scopeID: "scope-quant", prefixSeed: "quant-prefix", fingerprintSeed: "quant-fingerprint"),
            blockIDs: ["q0", "q1"],
            bytes: [120, 80]
        )

        XCTAssertEqual(storageBoundaryQuantizedBytes(for: table, activeKVQuantizationRatio: 0), 100)
        XCTAssertEqual(storageBoundaryQuantizedBytes(for: table, activeKVQuantizationRatio: 150), 200)
        XCTAssertEqual(storageBoundaryQuantizedBytes(for: table, activeKVQuantizationRatio: 1), 2)

        XCTAssertEqual(activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .baseline)), 0)
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "q4")),
            25
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "q8")),
            50
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "custom")),
            50
        )
    }

    func testMaintenanceRpcsReturnStructuredUnimplemented() async throws {
        let services = makeServices()
        let convertWriter = RecordingRPCWriter<Melix_Worker_V1_ConvertModelEvent>()
        let benchWriter = RecordingRPCWriter<Melix_Worker_V1_RunBenchEvent>()

        try await withTestServerContextRPCCancellationHandle { handle in
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

        let infoResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let doctorResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        try await withTestServerContextRPCCancellationHandle { handle in
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

    func testDeterministicBackendModeBuildsARepeatableTextRuntime() async throws {
        let runtime = makeTextRuntime(for: WorkerConfiguration(backendMode: "deterministic"))

        XCTAssertEqual(runtime.runtimeName, "deterministic-text")

        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await runtime.loadModel(spec: spec)
        let events = try await collectTextGenerationEvents(
            from: try await runtime.generateEvents(
                model: loaded.model,
                messages: [makeUserMessage("hello deterministic swift")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(renderedPromptTokens(from: events), 3)
        XCTAssertEqual(renderedTokenChunks(from: events), ["Echo: ", "hello ", "deterministic ", "swift"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 4)
    }

    func testDeterministicBackendRendersEmptyPromptAndStopsWhenAborted() async throws {
        let runtime = makeTextRuntime(for: WorkerConfiguration(backendMode: "deterministic"))
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await runtime.loadModel(spec: spec)

        let emptyPromptEvents = try await collectTextGenerationEvents(
            from: try await runtime.generateEvents(
                model: loaded.model,
                messages: [makeUserMessage("   ")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
        XCTAssertEqual(renderedTokenChunks(from: emptyPromptEvents), ["Echo: ", "empty"])
        XCTAssertEqual(renderedSummary(from: emptyPromptEvents)?.completionTokens, 2)

        let abortedEvents = try await collectTextGenerationEvents(
            from: try await runtime.generateEvents(
                model: loaded.model,
                messages: [makeUserMessage("abort after one token")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { true }
            )
        )
        XCTAssertEqual(renderedTokenChunks(from: abortedEvents), [])
        XCTAssertEqual(renderedSummary(from: abortedEvents)?.completionTokens, 0)
    }

    func testDeterministicBackendPrefillCapturesPromptMetadataAndAbortBranch() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 0)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("hello deterministic swift", extraText: "again")],
            prefillStepSize: 16,
            resumeHint: "deterministic-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        let stored = try XCTUnwrap(result.context.storage as? [String: String])
        XCTAssertEqual(result.promptTokens, 4)
        XCTAssertEqual(result.context.promptTokens, 4)
        XCTAssertEqual(stored["prompt"], "hello deterministic swift\nagain")
        XCTAssertEqual(stored["resume_hint"], "deterministic-resume")
        XCTAssertEqual(stored["prefill_step_size"], "16")

        let aborted = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("hello deterministic swift", extraText: "again")],
            prefillStepSize: 16,
            resumeHint: "deterministic-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { true }
        )

        let abortedStored = try XCTUnwrap(aborted.context.storage as? [String: String])
        XCTAssertEqual(aborted.promptTokens, 4)
        XCTAssertNil(abortedStored["prefill_step_size"])
        XCTAssertEqual(abortedStored["resume_hint"], "deterministic-resume")
    }

    func testDeterministicBackendAcceleratedPrefillReportsGainAndHint() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 20_000_000)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .acceleratedPrefill
        acceleration.prefillHint = "json-schema"

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("{\"type\":\"object\",\"name\":\"alpha\"}", extraText: "{\"type\":\"object\",\"name\":\"beta\"}")],
            prefillStepSize: 16,
            resumeHint: "structured",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let stored = try XCTUnwrap(result.context.storage as? [String: String])
        XCTAssertEqual(result.appliedAcceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(result.appliedAcceleration.prefillHint, "json-schema")
        XCTAssertGreaterThan(result.acceleratedPrefillGainPct, 0)
        XCTAssertEqual(result.activeKVQuantizationRatio, 0)
        XCTAssertEqual(stored["prefill_hint"], "json-schema")
        XCTAssertEqual(stored["prefill_gain_pct"], String(result.acceleratedPrefillGainPct))
    }

    func testDeterministicBackendActiveKVPrefillReportsQuantizationRatio() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 0)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "q8"

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("quantized cache")],
            prefillStepSize: 8,
            resumeHint: "quantized",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let stored = try XCTUnwrap(result.context.storage as? [String: String])
        XCTAssertEqual(result.appliedAcceleration.mode, .activeKvQuantized)
        XCTAssertEqual(result.appliedAcceleration.activeKvQuantProfile, "q8")
        XCTAssertEqual(result.activeKVQuantizationRatio, 50)
        XCTAssertEqual(stored["active_kv_quant_profile"], "q8")
        XCTAssertEqual(stored["active_kv_quant_ratio"], "50")
    }

    func testAutoSwiftMLXBackendDefaultPrefillRejectsNonMLXContainers() async {
        let backend = AutoSwiftMLXBackend()

        do {
            _ = try await backend.prefill(
                model: LoadedTextModel(storage: ["kind": "not-a-container"]),
                messages: [makeUserMessage("default prefill factory")],
                prefillStepSize: 4,
                resumeHint: "prefill",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { false }
            )
            XCTFail("expected prefill to fail for non-MLX containers")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("Loaded model is not a Swift MLX model container"))
        }
    }

    func testWarmupAndShutdownReturnExpectedStructuredResponses() async throws {
        let services = makeServices()

        let warmupResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        let shutdownResponse = try await withTestServerContextRPCCancellationHandle { handle in
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

        XCTAssertFalse(warmupResponse.ok)
        XCTAssertEqual(warmupResponse.error.code, "unimplemented")
        XCTAssertTrue(shutdownResponse.ok)
    }
}

@available(macOS 15.0, *)
private func withTestServerContextRPCCancellationHandle<Success>(
    _ operation: (ServerContext.RPCCancellationHandle) async throws -> Success
) async rethrows -> Success {
    // grpc-swift's generic task-local helper currently crashes under this XCTest package on the
    // active Xcode toolchain. The worker tests only need a concrete cancellation handle.
    try await operation(ServerContext.RPCCancellationHandle())
}

@available(macOS 15.0, *)
private func makeServices(
    environment: [String: String] = [:],
    backend: some TextRuntimeBackend = FakeRuntimeBackend(),
    residentMemorySamples: [UInt64] = [0, 0]
) -> WorkerServices {
    let configuration = WorkerConfiguration.fromEnvironment(environment)
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
    case prefillFailed
    case decodeFailed
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
    private let prefillError: Error?
    private let decodeError: Error?
    private let residentBytesHint: UInt64
    private let generatedChunks: [String]
    private let decodedChunks: [String]
    private let tokenDelayNanos: UInt64
    private let prefillDelayNanos: UInt64
    private let decodeDelayNanos: UInt64
    private let storage = FakeRuntimeBackendStorage()
    private let unloadedStorage = FakeRuntimeBackendUnloadStorage()

    init(
        loadError: Error? = nil,
        prefillError: Error? = nil,
        decodeError: Error? = nil,
        residentBytesHint: UInt64 = 0,
        generatedChunks: [String] = ["Hello", " from Swift"],
        decodedChunks: [String]? = nil,
        tokenDelayNanos: UInt64 = 0,
        prefillDelayNanos: UInt64 = 0,
        decodeDelayNanos: UInt64 = 0
    ) {
        self.loadError = loadError
        self.prefillError = prefillError
        self.decodeError = decodeError
        self.residentBytesHint = residentBytesHint
        self.generatedChunks = generatedChunks
        self.decodedChunks = decodedChunks ?? generatedChunks
        self.tokenDelayNanos = tokenDelayNanos
        self.prefillDelayNanos = prefillDelayNanos
        self.decodeDelayNanos = decodeDelayNanos
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

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        if let prefillError {
            throw prefillError
        }
        if prefillDelayNanos > 0 {
            try? await Task.sleep(nanoseconds: prefillDelayNanos)
        }

        let promptTokens = max(1, messages.count)
        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: [
                    "resume_hint": resumeHint,
                    "prefill_step_size": String(prefillStepSize),
                ],
                promptTokens: promptTokens
            ),
            promptTokens: promptTokens,
            appliedAcceleration: normalizedAccelerationPolicy(acceleration),
            acceleratedPrefillGainPct: acceleration.mode == .acceleratedPrefill ? 50 : 0,
            activeKVQuantizationRatio: activeKVQuantizationRatioPercent(for: acceleration)
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.yield(.prefillStarted(promptTokens: max(1, messages.count)))

            Task {
                var emitted = 0
                for chunk in generatedChunks {
                    if shouldAbort() {
                        break
                    }
                    if tokenDelayNanos > 0 {
                        try? await Task.sleep(nanoseconds: tokenDelayNanos)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    continuation.yield(.token(chunk))
                }

                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: max(1, messages.count),
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) * 10.0 : nil
                    )
                ))
                continuation.finish()
            }
        }
    }

    func decodeEvents(
        model: LoadedTextModel,
        context: TextPrefillContext,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        if let decodeError {
            throw decodeError
        }

        let chunks = maxOutputTokens > 0
            ? Array(decodedChunks.prefix(Int(maxOutputTokens)))
            : decodedChunks

        return AsyncThrowingStream { continuation in
            Task {
                var emitted = 0

                for chunk in chunks {
                    if shouldAbort() {
                        break
                    }
                    if decodeDelayNanos > 0 {
                        try? await Task.sleep(nanoseconds: decodeDelayNanos)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    continuation.yield(.token(chunk))
                }

                let speculativeAccepted = acceleration.mode == .speculativeDecode ? max(emitted - 1, 0) : nil
                let speculativeRejected = acceleration.mode == .speculativeDecode && emitted > 0 ? 1 : nil
                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: max(1, context.promptTokens),
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) * 8.0 : nil,
                        speculativeAcceptedTokens: speculativeAccepted,
                        speculativeRejectedTokens: speculativeRejected
                    )
                ))
                continuation.finish()
            }
        }
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

@available(macOS 15.0, *)
private func matches(
    _ payload: Melix_Worker_V1_ExecuteEvent.OneOf_Payload?,
    _ matcher: ExecuteEventPayloadMatcher
) -> Bool {
    guard let payload else {
        return false
    }

    switch (payload, matcher) {
    case (.prefillStarted, .prefillStarted),
         (.decodeStarted, .decodeStarted),
         (.accelerationApplied, .accelerationApplied),
         (.tokenDelta, .tokenDelta),
         (.usageDelta, .usageDelta),
         (.completed, .completed),
         (.error, .error):
        return true
    default:
        return false
    }
}

@available(macOS 15.0, *)
private enum ExecuteEventPayloadMatcher {
    case prefillStarted
    case decodeStarted
    case accelerationApplied
    case tokenDelta
    case usageDelta
    case completed
    case error
}

@available(macOS 15.0, *)
private func makeUserMessage(
    _ text: String,
    extraText: String? = nil
) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = "user"

    var parts: [Melix_Worker_V1_MessagePart] = []
    var firstPart = Melix_Worker_V1_MessagePart()
    firstPart.text = text
    parts.append(firstPart)

    if let extraText {
        var extraPart = Melix_Worker_V1_MessagePart()
        extraPart.text = extraText
        parts.append(extraPart)
    }

    message.parts = parts
    return message
}

@available(macOS 15.0, *)
private func makeSystemMessage(_ text: String) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = "system"

    var part = Melix_Worker_V1_MessagePart()
    part.text = text
    message.parts = [part]
    return message
}

@available(macOS 15.0, *)
private func makeRoleMessage(_ role: String, text: String) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = role

    var part = Melix_Worker_V1_MessagePart()
    part.text = text
    message.parts = [part]
    return message
}

@available(macOS 15.0, *)
private func makeCacheScope(scopeID: String, modelID: String) -> Melix_Worker_V1_CacheScope {
    var scope = Melix_Worker_V1_CacheScope()
    scope.scopeID = scopeID
    scope.modelID = modelID
    return scope
}

@available(macOS 15.0, *)
private func makeCacheKey(
    scopeID: String,
    prefixSeed: String,
    fingerprintSeed: String
) -> Melix_Worker_V1_CacheKey {
    var key = Melix_Worker_V1_CacheKey()
    key.scopeID = scopeID
    key.prefixHash = Data(prefixSeed.utf8)
    key.fingerprintHash = Data(fingerprintSeed.utf8)
    return key
}

@available(macOS 15.0, *)
private func makePrefixRef(
    prefixID: String,
    scope: Melix_Worker_V1_CacheScope,
    cacheKey: Melix_Worker_V1_CacheKey,
    pinned: Bool = false
) -> Melix_Worker_V1_PrefixRef {
    var prefix = Melix_Worker_V1_PrefixRef()
    prefix.prefixID = prefixID
    prefix.scope = scope
    prefix.cacheKey = cacheKey
    prefix.pinned = pinned
    prefix.tokenLength = 4
    return prefix
}

@available(macOS 15.0, *)
private func makeBlockTable(
    scopeID: String,
    cacheKey: Melix_Worker_V1_CacheKey,
    blockIDs: [String],
    bytes: [UInt64]
) -> Melix_Worker_V1_BlockTable {
    var table = Melix_Worker_V1_BlockTable()
    table.scopeID = scopeID
    table.cacheKey = cacheKey
    table.blocks = zip(blockIDs, bytes).enumerated().map { index, pair in
        var block = Melix_Worker_V1_BlockRef()
        block.blockID = pair.0
        block.tokenStart = Int32(index * 16)
        block.tokenEnd = Int32((index + 1) * 16)
        block.bytes = pair.1
        return block
    }
    return table
}

@available(macOS 15.0, *)
private func makeSnapshotRef(snapshotID: String) -> Melix_Worker_V1_SnapshotRef {
    var snapshot = Melix_Worker_V1_SnapshotRef()
    snapshot.snapshotID = snapshotID
    snapshot.requestID = "request-\(snapshotID)"
    snapshot.sessionID = "session-\(snapshotID)"
    snapshot.branchID = "branch-\(snapshotID)"
    snapshot.tokenBoundary = 4
    return snapshot
}

@available(macOS 15.0, *)
private func makeModelSpec(modelID: String) -> Melix_Worker_V1_ModelSpec {
    var model = Melix_Worker_V1_ModelSpec()
    model.modelID = modelID
    model.modelPath = modelID
    return model
}

@available(macOS 15.0, *)
private func makeAccelerationPolicy(
    mode: Melix_Worker_V1_AccelerationMode,
    activeKvQuantProfile: String = ""
) -> Melix_Worker_V1_AccelerationPolicy {
    var policy = Melix_Worker_V1_AccelerationPolicy()
    policy.mode = mode
    policy.activeKvQuantProfile = activeKvQuantProfile
    return policy
}

@available(macOS 15.0, *)
private func collectTextGenerationEvents(
    from stream: AsyncThrowingStream<TextGenerationEvent, Error>
) async throws -> [TextGenerationEvent] {
    var events: [TextGenerationEvent] = []
    for try await event in stream {
        events.append(event)
    }
    return events
}

@available(macOS 15.0, *)
private func renderedPromptTokens(from events: [TextGenerationEvent]) -> Int? {
    for event in events {
        if case .prefillStarted(let promptTokens) = event {
            return promptTokens
        }
    }
    return nil
}

@available(macOS 15.0, *)
private func renderedTokenChunks(from events: [TextGenerationEvent]) -> [String] {
    events.compactMap { event in
        guard case .token(let text) = event else {
            return nil
        }
        return text
    }
}

@available(macOS 15.0, *)
private func renderedSummary(from events: [TextGenerationEvent]) -> TextGenerationSummary? {
    for event in events {
        if case .summary(let summary) = event {
            return summary
        }
    }
    return nil
}

@available(macOS 15.0, *)
private func XCTAssertThrowsErrorAsync<T>(
    _ expression: @autoclosure () async throws -> T,
    _ message: @autoclosure () -> String = "",
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    do {
        _ = try await expression()
        XCTFail(message().isEmpty ? "Expected async expression to throw an error." : message(), file: file, line: line)
    } catch {
    }
}

#if canImport(MLX) && canImport(MLXLMCommon) && canImport(MLXLLM) && canImport(Tokenizers)
@available(macOS 15.0, *)
private func makeLiveSwiftMLXModelContainer(promptTokens: [Int]) -> ModelContainer {
    let vocabularySize = 32
    let configuration = LlamaConfiguration(
        hiddenSize: 64,
        hiddenLayers: 4,
        intermediateSize: 128,
        attentionHeads: 8,
        rmsNormEps: 0.00001,
        vocabularySize: vocabularySize,
        kvHeads: 4
    )
    let model = LlamaModel(configuration)
    eval(model)

    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/live-swift-mlx"),
        model: model,
        processor: DeterministicUserInputProcessor(promptTokens: promptTokens),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private func makeQuantizableLiveSwiftMLXModelContainer(promptTokens: [Int]) -> ModelContainer {
    let vocabularySize = 32
    let configuration = LlamaConfiguration(
        hiddenSize: 512,
        hiddenLayers: 1,
        intermediateSize: 1024,
        attentionHeads: 8,
        rmsNormEps: 0.00001,
        vocabularySize: vocabularySize,
        kvHeads: 4
    )
    let model = LlamaModel(configuration)
    eval(model)

    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/live-swift-mlx-quant"),
        model: model,
        processor: DeterministicUserInputProcessor(promptTokens: promptTokens),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private struct DeterministicUserInputProcessor: UserInputProcessor {
    let promptTokens: [Int]

    func prepare(input: UserInput) async throws -> LMInput {
        LMInput(tokens: MLXArray(promptTokens))
    }
}

@available(macOS 15.0, *)
private struct DeterministicTokenizer: Tokenizer {
    let vocabularySize: Int

    private var tokenLookup: [Int: String] {
        Dictionary(uniqueKeysWithValues: (0 ..< vocabularySize).map { ($0, "tok\($0)") })
    }

    func tokenize(text: String) -> [String] {
        text.split(separator: " ").map(String.init)
    }

    func encode(text: String) -> [Int] {
        encode(text: text, addSpecialTokens: true)
    }

    func encode(text: String, addSpecialTokens: Bool) -> [Int] {
        let tokens = tokenize(text: text)
        if tokens.isEmpty {
            return [1]
        }
        return tokens.enumerated().map { index, token in
            convertTokenToId(token) ?? max(1, (index % max(1, vocabularySize - 1)) + 1)
        }
    }

    func decode(tokens: [Int], skipSpecialTokens: Bool) -> String {
        tokens.compactMap { convertIdToToken($0) }.joined(separator: " ")
    }

    func convertTokenToId(_ token: String) -> Int? {
        if let explicit = Int(token.replacingOccurrences(of: "tok", with: "")) {
            return explicit % vocabularySize
        }
        return nil
    }

    func convertIdToToken(_ id: Int) -> String? {
        tokenLookup[id] ?? "tok\(id)"
    }

    var bosToken: String? { nil }
    var bosTokenId: Int? { nil }
    var eosToken: String? { nil }
    var eosTokenId: Int? { nil }
    var unknownToken: String? { nil }
    var unknownTokenId: Int? { nil }
    var hasChatTemplate: Bool { true }

    func applyChatTemplate(messages: [Tokenizers.Message]) throws -> [Int] {
        Array(1 ... max(1, messages.count + 1))
    }

    func applyChatTemplate(messages: [Tokenizers.Message], tools: [Tokenizers.ToolSpec]?) throws
        -> [Int]
    {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        tools: [Tokenizers.ToolSpec]?,
        additionalContext: [String: any Sendable]?
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        chatTemplate: Tokenizers.ChatTemplateArgument
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(messages: [Tokenizers.Message], chatTemplate: String) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        chatTemplate: Tokenizers.ChatTemplateArgument?,
        addGenerationPrompt: Bool,
        truncation: Bool,
        maxLength: Int?,
        tools: [Tokenizers.ToolSpec]?
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        chatTemplate: Tokenizers.ChatTemplateArgument?,
        addGenerationPrompt: Bool,
        truncation: Bool,
        maxLength: Int?,
        tools: [Tokenizers.ToolSpec]?,
        additionalContext: [String: any Sendable]?
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }
}

@available(macOS 15.0, *)
private func withTemporaryDefaultMetallib<T>(
    _ operation: () async throws -> T
) async throws -> T {
    let fileManager = FileManager.default
    guard let metallibURL = findLocalMLXMetallib() else {
        throw XCTSkip("No local mlx.metallib was found for the Swift MLX live-bridge test.")
    }

    let temporaryDirectory = fileManager.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fileManager.createDirectory(at: temporaryDirectory, withIntermediateDirectories: true)

    let defaultMetallibURL = temporaryDirectory.appendingPathComponent("default.metallib")
    try fileManager.createSymbolicLink(at: defaultMetallibURL, withDestinationURL: metallibURL)

    let originalDirectory = fileManager.currentDirectoryPath
    guard fileManager.changeCurrentDirectoryPath(temporaryDirectory.path) else {
        try? fileManager.removeItem(at: temporaryDirectory)
        throw RuntimeUnavailableError(message: "Failed to switch into the temporary MLX metallib directory.")
    }

    defer {
        _ = fileManager.changeCurrentDirectoryPath(originalDirectory)
        try? fileManager.removeItem(at: temporaryDirectory)
    }

    return try await operation()
}

@available(macOS 15.0, *)
private func withTemporaryCacheRoot<T>(
    _ operation: (URL) async throws -> T
) async throws -> T {
    let fileManager = FileManager.default
    let cacheRoot = fileManager.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fileManager.createDirectory(at: cacheRoot, withIntermediateDirectories: true)
    defer { try? fileManager.removeItem(at: cacheRoot) }
    return try await operation(cacheRoot)
}

@available(macOS 15.0, *)
private func findLocalMLXMetallib() -> URL? {
    let fileManager = FileManager.default
    let currentDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
    let candidateRoots = [
        currentDirectory,
        currentDirectory.deletingLastPathComponent(),
        currentDirectory.deletingLastPathComponent().deletingLastPathComponent(),
    ]

    let candidatePrefixes = [
        ".venv",
        ".uv-cache",
    ]

    for root in candidateRoots {
        for prefix in candidatePrefixes {
            let searchRoot = root.appendingPathComponent(prefix, isDirectory: true)
            guard fileManager.fileExists(atPath: searchRoot.path) else {
                continue
            }
            guard let enumerator = fileManager.enumerator(
                at: searchRoot,
                includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles]
            ) else {
                continue
            }

            for case let fileURL as URL in enumerator {
                guard fileURL.lastPathComponent == "mlx.metallib" else {
                    continue
                }
                return fileURL
            }
        }
    }

    return nil
}
#endif
