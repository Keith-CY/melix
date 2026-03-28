import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix
import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Swift Text Worker Client")
struct SwiftTextWorkerClientTests {
    @Test("handshake responses drive dispatch availability")
    func handshakeResponsesDriveDispatchAvailability() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)

        #expect(await client.canDispatchRequests())
    }

    @Test("load model returns the worker handle from the runner")
    func loadModelReturnsWorkerHandle() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())

        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        await runner.setLoadModelResponse(response)

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)
        let loaded = try await client.loadModel(request: makeLoadModelRequest())

        #expect(loaded.ok)
        #expect(loaded.modelHandle == "melix-dev-text::swift")
    }

    @Test("runtime and cache stats forward unary responses from the runner")
    func runtimeAndCacheStatsForwardUnaryResponsesFromTheRunner() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())

        var runtimeResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
        runtimeResponse.stats.residentBytes = 8_192
        runtimeResponse.stats.l1CacheBytes = 2_048
        await runner.setRuntimeStatsResponse(runtimeResponse)

        var cacheResponse = Melix_Worker_V1_GetCacheStatsResponse()
        cacheResponse.stats.l1Bytes = 2_048
        cacheResponse.stats.l2Bytes = 4_096
        cacheResponse.stats.l1HitRate = 0.5
        await runner.setCacheStatsResponse(cacheResponse)

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)
        let runtimeStats = try await client.runtimeStats()
        let cacheStats = try await client.cacheStats()

        #expect(runtimeStats.stats.residentBytes == 8_192)
        #expect(runtimeStats.stats.l1CacheBytes == 2_048)
        #expect(cacheStats.stats.l1Bytes == 2_048)
        #expect(cacheStats.stats.l2Bytes == 4_096)
        #expect(cacheStats.stats.l1HitRate == 0.5)
    }

    @Test("generate forwards streamed execute events from the runner")
    func generateForwardsStreamedExecuteEventsFromTheRunner() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())
        await runner.setGenerateEvents([
            makeTokenEvent(requestID: "req-swift", seq: 1, text: "Hi"),
            makeCompletedEvent(requestID: "req-swift", seq: 2, finishReason: "stop", assistantText: "Hi"),
        ])

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)
        let stream = try await client.generate(request: makeGenerateRequest(requestID: "req-swift"))
        let events = try await collect(stream)

        #expect(events.count == 2)
        #expect(events[0].tokenDelta.text == "Hi")
        #expect(events[1].completed.finishReason == "stop")
    }

    @Test("prefill forwards unary responses from the runner")
    func prefillForwardsUnaryResponsesFromTheRunner() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())

        var prefillResponse = Melix_Worker_V1_PrefillResponse()
        prefillResponse.ok = true
        prefillResponse.decodeHandle = "melix-dev-text::decode::prefill"
        prefillResponse.restoredSnapshotID = "snapshot-prefill"
        prefillResponse.appliedAcceleration.mode = .baseline
        await runner.setPrefillResponse(prefillResponse)

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)
        let response = try await client.prefill(request: makePrefillRequest(requestID: "req-prefill"))

        #expect(response.ok)
        #expect(response.decodeHandle == "melix-dev-text::decode::prefill")
        #expect(response.restoredSnapshotID == "snapshot-prefill")
    }

    @Test("decode forwards streamed execute events from the runner")
    func decodeForwardsStreamedExecuteEventsFromTheRunner() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())
        await runner.setDecodeEvents([
            makeTokenEvent(requestID: "req-decode", seq: 1, text: "De"),
            makeCompletedEvent(requestID: "req-decode", seq: 2, finishReason: "stop", assistantText: "Decode"),
        ])

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)
        let stream = try await client.decode(request: makeDecodeRequest(requestID: "req-decode"))
        let events = try await collect(stream)

        #expect(events.count == 2)
        #expect(events[0].tokenDelta.text == "De")
        #expect(events[1].completed.assistantText == "Decode")
    }

    @Test("abort returns the found bit from the runner response")
    func abortReturnsFoundBitFromTheRunnerResponse() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.setHandshakeResponse(makeHandshakeResponse())

        var response = Melix_Worker_V1_AbortResponse()
        response.ok = true
        response.found = true
        await runner.setAbortResponse(response)

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)
        let aborted = try await client.abort(requestID: "req-abort")

        #expect(aborted)
    }

    @Test("client treats runner failures as unavailable")
    func clientTreatsRunnerFailuresAsUnavailable() async throws {
        let runner = ScriptedSwiftTextWorkerRunner()
        await runner.failHandshake()
        await runner.failGenerate()

        let client = SwiftTextWorkerClient(socketPath: "/tmp/melix-swift-test.sock", runner: runner)

        #expect(!(await client.canDispatchRequests()))

        do {
            let stream = try await client.generate(request: makeGenerateRequest(requestID: "req-unavailable"))
            _ = try await collect(stream)
            Issue.record("Expected generate to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("grpc runner bridges phase 1 worker RPCs over a unix domain socket")
    func grpcRunnerBridgesPhase1WorkerRPCsOverAUnixDomainSocket() async throws {
        let fixture = try await LiveSwiftWorkerFixture.start(
            handshakeResponse: makeHandshakeResponse(),
            loadModelResponse: {
                var response = Melix_Worker_V1_LoadModelResponse()
                response.ok = true
                response.modelHandle = "melix-dev-text::swift-live"
                return response
            }(),
            prefillResponse: {
                var response = Melix_Worker_V1_PrefillResponse()
                response.ok = true
                response.decodeHandle = "melix-dev-text::decode::live"
                response.appliedAcceleration.mode = .baseline
                return response
            }(),
            runtimeStatsResponse: {
                var response = Melix_Worker_V1_GetRuntimeStatsResponse()
                response.stats.residentBytes = 8_192
                return response
            }(),
            cacheStatsResponse: {
                var response = Melix_Worker_V1_GetCacheStatsResponse()
                response.stats.l1Bytes = 2_048
                response.stats.l2Bytes = 4_096
                return response
            }(),
            generateEvents: [
                makeTokenEvent(requestID: "req-live", seq: 1, text: "Hel"),
                makeCompletedEvent(requestID: "req-live", seq: 2, finishReason: "stop", assistantText: "Hel"),
            ],
            decodeEvents: [
                makeTokenEvent(requestID: "req-live-decode", seq: 1, text: "Dec"),
                makeCompletedEvent(requestID: "req-live-decode", seq: 2, finishReason: "stop", assistantText: "Decode"),
            ],
            abortFound: true
        )
        defer { Task { await fixture.stop() } }

        let client = SwiftTextWorkerClient(socketPath: fixture.socketPath)

        #expect(await client.canDispatchRequests())

        let loadResponse = try await client.loadModel(request: makeLoadModelRequest())
        #expect(loadResponse.modelHandle == "melix-dev-text::swift-live")

        let runtimeStats = try await client.runtimeStats()
        #expect(runtimeStats.stats.residentBytes == 8_192)

        let cacheStats = try await client.cacheStats()
        #expect(cacheStats.stats.l1Bytes == 2_048)
        #expect(cacheStats.stats.l2Bytes == 4_096)

        let stream = try await client.generate(request: makeGenerateRequest(requestID: "req-live"))
        let events = try await collect(stream)
        #expect(events.count == 2)
        #expect(events[0].tokenDelta.text == "Hel")
        #expect(events[1].completed.assistantText == "Hel")

        let prefill = try await client.prefill(request: makePrefillRequest(requestID: "req-live-prefill"))
        #expect(prefill.ok)
        #expect(prefill.decodeHandle == "melix-dev-text::decode::live")

        let decode = try await client.decode(request: makeDecodeRequest(requestID: "req-live-decode"))
        let decodeEvents = try await collect(decode)
        #expect(decodeEvents.count == 2)
        #expect(decodeEvents[0].tokenDelta.text == "Dec")
        #expect(decodeEvents[1].completed.assistantText == "Decode")

        let aborted = try await client.abort(requestID: "req-live")
        #expect(aborted)
    }
}

private actor ScriptedSwiftTextWorkerRunner: SwiftTextWorkerRPCRunning {
    private var handshakeResponse: Melix_Worker_V1_HandshakeResponse?
    private var loadModelResponse: Melix_Worker_V1_LoadModelResponse?
    private var runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse?
    private var cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse?
    private var generateEvents: [Melix_Worker_V1_ExecuteEvent] = []
    private var prefillResponse: Melix_Worker_V1_PrefillResponse?
    private var decodeEvents: [Melix_Worker_V1_ExecuteEvent] = []
    private var abortResponse: Melix_Worker_V1_AbortResponse?
    private var failHandshakeFlag = false
    private var failGenerateFlag = false

    func setHandshakeResponse(_ response: Melix_Worker_V1_HandshakeResponse) {
        handshakeResponse = response
    }

    func setLoadModelResponse(_ response: Melix_Worker_V1_LoadModelResponse) {
        loadModelResponse = response
    }

    func setRuntimeStatsResponse(_ response: Melix_Worker_V1_GetRuntimeStatsResponse) {
        runtimeStatsResponse = response
    }

    func setCacheStatsResponse(_ response: Melix_Worker_V1_GetCacheStatsResponse) {
        cacheStatsResponse = response
    }

    func setGenerateEvents(_ events: [Melix_Worker_V1_ExecuteEvent]) {
        generateEvents = events
    }

    func setPrefillResponse(_ response: Melix_Worker_V1_PrefillResponse) {
        prefillResponse = response
    }

    func setDecodeEvents(_ events: [Melix_Worker_V1_ExecuteEvent]) {
        decodeEvents = events
    }

    func setAbortResponse(_ response: Melix_Worker_V1_AbortResponse) {
        abortResponse = response
    }

    func failHandshake() {
        failHandshakeFlag = true
    }

    func failGenerate() {
        failGenerateFlag = true
    }

    func handshake(
        socketPath: String,
        request: Melix_Worker_V1_HandshakeRequest
    ) async throws -> Melix_Worker_V1_HandshakeResponse {
        if failHandshakeFlag {
            throw WorkerClientError.unavailable
        }
        return handshakeResponse ?? makeHandshakeResponse()
    }

    func loadModel(
        socketPath: String,
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadModelResponse ?? {
            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = true
            response.modelHandle = "melix-dev-text::swift"
            return response
        }()
    }

    func runtimeStats(
        socketPath: String,
        request: Melix_Worker_V1_GetRuntimeStatsRequest
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        runtimeStatsResponse ?? Melix_Worker_V1_GetRuntimeStatsResponse()
    }

    func cacheStats(
        socketPath: String,
        request: Melix_Worker_V1_GetCacheStatsRequest
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        cacheStatsResponse ?? Melix_Worker_V1_GetCacheStatsResponse()
    }

    func generate(
        socketPath: String,
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        if failGenerateFlag {
            throw WorkerClientError.unavailable
        }

        let events = generateEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func prefill(
        socketPath: String,
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        prefillResponse ?? {
            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = true
            response.appliedAcceleration.mode = .baseline
            return response
        }()
    }

    func decode(
        socketPath: String,
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        let events = decodeEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func abort(
        socketPath: String,
        request: Melix_Worker_V1_AbortRequest
    ) async throws -> Melix_Worker_V1_AbortResponse {
        abortResponse ?? {
            var response = Melix_Worker_V1_AbortResponse()
            response.ok = true
            response.found = true
            return response
        }()
    }
}

private actor LiveSwiftWorkerFixture {
    let socketPath: String
    private let server: GRPCServer<HTTP2ServerTransport.Posix>
    private let serveTask: Task<Void, Error>

    private init(
        socketPath: String,
        server: GRPCServer<HTTP2ServerTransport.Posix>,
        serveTask: Task<Void, Error>
    ) {
        self.socketPath = socketPath
        self.server = server
        self.serveTask = serveTask
    }

    static func start(
        handshakeResponse: Melix_Worker_V1_HandshakeResponse,
        loadModelResponse: Melix_Worker_V1_LoadModelResponse,
        prefillResponse: Melix_Worker_V1_PrefillResponse,
        runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse,
        cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse,
        generateEvents: [Melix_Worker_V1_ExecuteEvent],
        decodeEvents: [Melix_Worker_V1_ExecuteEvent],
        abortFound: Bool
    ) async throws -> LiveSwiftWorkerFixture {
        let socketPath = "/tmp/melix-swift-\(UUID().uuidString.prefix(8)).sock"
        try? FileManager.default.removeItem(atPath: socketPath)

        let runtime = TestRuntimeService(
            handshakeResponse: handshakeResponse,
            loadModelResponse: loadModelResponse,
            runtimeStatsResponse: runtimeStatsResponse
        )
        let inference = TestInferenceService(
            prefillResponse: prefillResponse,
            generateEvents: generateEvents,
            decodeEvents: decodeEvents,
            abortFound: abortFound
        )
        let cache = TestCacheService(cacheStatsResponse: cacheStatsResponse)

        let server = GRPCServer(
            transport: .http2NIOPosix(
                address: .unixDomainSocket(path: socketPath),
                transportSecurity: .plaintext
            ),
            services: [runtime, inference, cache]
        )
        let serveTask = Task {
            try await server.serve()
        }
        _ = try await server.listeningAddress

        return LiveSwiftWorkerFixture(
            socketPath: socketPath,
            server: server,
            serveTask: serveTask
        )
    }

    func stop() async {
        server.beginGracefulShutdown()
        _ = try? await serveTask.value
        try? FileManager.default.removeItem(atPath: socketPath)
    }
}

private final class TestRuntimeService: Melix_Worker_V1_RuntimeService.SimpleServiceProtocol, @unchecked Sendable {
    private let handshakeResponse: Melix_Worker_V1_HandshakeResponse
    private let loadModelResponse: Melix_Worker_V1_LoadModelResponse
    private let runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse

    init(
        handshakeResponse: Melix_Worker_V1_HandshakeResponse,
        loadModelResponse: Melix_Worker_V1_LoadModelResponse,
        runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse
    ) {
        self.handshakeResponse = handshakeResponse
        self.loadModelResponse = loadModelResponse
        self.runtimeStatsResponse = runtimeStatsResponse
    }

    func handshake(
        request: Melix_Worker_V1_HandshakeRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_HandshakeResponse {
        handshakeResponse
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadModelResponse
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        Melix_Worker_V1_UnloadModelResponse()
    }

    func warmupModel(
        request: Melix_Worker_V1_WarmupModelRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_WarmupModelResponse {
        Melix_Worker_V1_WarmupModelResponse()
    }

    func getRuntimeStats(
        request: Melix_Worker_V1_GetRuntimeStatsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        runtimeStatsResponse
    }

    func listLoadedModels(
        request: Melix_Worker_V1_ListLoadedModelsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ListLoadedModelsResponse {
        Melix_Worker_V1_ListLoadedModelsResponse()
    }

    func drain(
        request: Melix_Worker_V1_DrainRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_DrainResponse {
        var response = Melix_Worker_V1_DrainResponse()
        response.ok = true
        return response
    }

    func shutdown(
        request: Melix_Worker_V1_ShutdownRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ShutdownResponse {
        var response = Melix_Worker_V1_ShutdownResponse()
        response.ok = true
        return response
    }
}

private final class TestCacheService: Melix_Worker_V1_CacheService.SimpleServiceProtocol, @unchecked Sendable {
    private let cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse

    init(cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse) {
        self.cacheStatsResponse = cacheStatsResponse
    }

    func getCacheStats(
        request: Melix_Worker_V1_GetCacheStatsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        cacheStatsResponse
    }

    func pinPrefix(
        request: Melix_Worker_V1_PinPrefixRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_PinPrefixResponse {
        Melix_Worker_V1_PinPrefixResponse()
    }

    func unpinPrefix(
        request: Melix_Worker_V1_UnpinPrefixRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_UnpinPrefixResponse {
        Melix_Worker_V1_UnpinPrefixResponse()
    }

    func saveBoundarySnapshot(
        request: Melix_Worker_V1_SaveBoundarySnapshotRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_SaveBoundarySnapshotResponse {
        Melix_Worker_V1_SaveBoundarySnapshotResponse()
    }

    func restoreBoundarySnapshot(
        request: Melix_Worker_V1_RestoreBoundarySnapshotRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_RestoreBoundarySnapshotResponse {
        Melix_Worker_V1_RestoreBoundarySnapshotResponse()
    }

    func purgeCache(
        request: Melix_Worker_V1_PurgeCacheRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_PurgeCacheResponse {
        Melix_Worker_V1_PurgeCacheResponse()
    }
}

private final class TestInferenceService: Melix_Worker_V1_InferenceService.SimpleServiceProtocol, @unchecked Sendable {
    private let prefillResponse: Melix_Worker_V1_PrefillResponse
    private let generateEvents: [Melix_Worker_V1_ExecuteEvent]
    private let decodeEvents: [Melix_Worker_V1_ExecuteEvent]
    private let abortFound: Bool

    init(
        prefillResponse: Melix_Worker_V1_PrefillResponse,
        generateEvents: [Melix_Worker_V1_ExecuteEvent],
        decodeEvents: [Melix_Worker_V1_ExecuteEvent],
        abortFound: Bool
    ) {
        self.prefillResponse = prefillResponse
        self.generateEvents = generateEvents
        self.decodeEvents = decodeEvents
        self.abortFound = abortFound
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest,
        response: RPCWriter<Melix_Worker_V1_ExecuteEvent>,
        context: ServerContext
    ) async throws {
        for event in generateEvents {
            try await response.write(event)
        }
    }

    func prefill(
        request: Melix_Worker_V1_PrefillRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        prefillResponse
    }

    func decode(
        request: Melix_Worker_V1_DecodeRequest,
        response: RPCWriter<Melix_Worker_V1_ExecuteEvent>,
        context: ServerContext
    ) async throws {
        for event in decodeEvents {
            try await response.write(event)
        }
    }

    func abort(
        request: Melix_Worker_V1_AbortRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_AbortResponse {
        var response = Melix_Worker_V1_AbortResponse()
        response.ok = abortFound
        response.found = abortFound
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        Melix_Worker_V1_ImageGenerateResponse()
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        Melix_Worker_V1_ImageEditResponse()
    }
}

private func makeHandshakeResponse() -> Melix_Worker_V1_HandshakeResponse {
    var response = Melix_Worker_V1_HandshakeResponse()
    response.protocolVersion = "melix.worker.v1"
    response.runtimeVersion = "melix-swift-text-worker/test"
    return response
}

private func makeLoadModelRequest() -> Melix_Worker_V1_LoadModelRequest {
    var request = Melix_Worker_V1_LoadModelRequest()
    request.model = makeDevModel()
    request.pinOnLoad = true
    return request
}

private func makeGenerateRequest(requestID: String) -> Melix_Worker_V1_GenerateRequest {
    var request = Melix_Worker_V1_GenerateRequest()
    request.execution.id.requestID = requestID
    request.execution.modelHandle = "melix-dev-text::swift"
    return request
}

private func makePrefillRequest(requestID: String) -> Melix_Worker_V1_PrefillRequest {
    var request = Melix_Worker_V1_PrefillRequest()
    request.execution.id.requestID = requestID
    request.execution.modelHandle = "melix-dev-text::swift"
    request.returnDecodeHandle = true
    return request
}

private func makeDecodeRequest(requestID: String) -> Melix_Worker_V1_DecodeRequest {
    var request = Melix_Worker_V1_DecodeRequest()
    request.execution.id.requestID = requestID
    request.execution.modelHandle = "melix-dev-text::swift"
    request.decodeHandle = "melix-dev-text::decode::live"
    return request
}

private func makeDevModel() -> Melix_Worker_V1_ModelSpec {
    var model = Melix_Worker_V1_ModelSpec()
    model.modelID = "melix-dev-text"
    model.modelPath = "models/melix-dev-text"
    model.modelKind = "text"
    model.revision = "dev"
    model.tokenizerHash = "tok-dev"
    model.quantProfileID = "q4"
    model.parserMode = "text"
    model.reasoningMode = "off"
    model.maxContext = 8192
    return model
}

private func makeTokenEvent(
    requestID: String,
    seq: UInt64,
    text: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeCompletedEvent(
    requestID: String,
    seq: UInt64,
    finishReason: String,
    assistantText: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistantText
    return event
}

private func collect<T: Sendable>(_ stream: AsyncThrowingStream<T, Error>) async throws -> [T] {
    var values: [T] = []
    for try await value in stream {
        values.append(value)
    }
    return values
}
