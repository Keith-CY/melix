import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
}

public enum HTTPBody: Sendable {
    case data(Data)
    case stream(AsyncThrowingStream<Data, Error>)
}

public struct HTTPRequest: Sendable {
    public let method: HTTPMethod
    public let path: String
    public let headers: [String: String]
    public let body: Data

    public init(
        method: HTTPMethod,
        path: String,
        headers: [String: String],
        body: Data
    ) {
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
    }
}

public struct HTTPResponse: Sendable {
    public let statusCode: Int
    public let headers: [String: String]
    public let body: HTTPBody

    public init(
        statusCode: Int,
        headers: [String: String],
        body: HTTPBody
    ) {
        self.statusCode = statusCode
        self.headers = headers
        self.body = body
    }
}

public struct OpenAIHandler: Sendable {
    private let modelCatalog: ModelCatalog
    private let requestCoordinator: RequestCoordinator
    private let workerRegistry: WorkerRegistry?
    private let metricsStore: MetricsStore
    private let cacheMetadataStore: CacheMetadataStore?
    private let translator: ChatRequestTranslator
    private let sseWriter: SSEStreamWriter
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(
        modelCatalog: ModelCatalog,
        requestCoordinator: RequestCoordinator,
        workerRegistry: WorkerRegistry? = nil,
        metricsStore: MetricsStore = MetricsStore(),
        cacheMetadataStore: CacheMetadataStore? = nil,
        translator: ChatRequestTranslator = ChatRequestTranslator(),
        sseWriter: SSEStreamWriter = SSEStreamWriter()
    ) {
        self.modelCatalog = modelCatalog
        self.requestCoordinator = requestCoordinator
        self.workerRegistry = workerRegistry
        self.metricsStore = metricsStore
        self.cacheMetadataStore = cacheMetadataStore
        self.translator = translator
        self.sseWriter = sseWriter
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
    }

    public func handle(_ request: HTTPRequest) async throws -> HTTPResponse {
        switch (request.method, request.path) {
        case (.get, "/v1/models"):
            return try await handleModels()
        case (.get, "/health"):
            return try await handleHealth()
        case (.get, "/v1/cache/stats"):
            return try await handleCacheStats()
        case (.post, "/v1/chat/completions"):
            return try await handleChatCompletions(request)
        case (.post, "/v1/completions"):
            return try await handleCompletions(request)
        case (.post, "/v1/responses"):
            return try await handleResponses(request)
        case (.post, "/v1/messages"):
            return try await handleMessages(request)
        case (.post, "/v1/embeddings"):
            return try await handleEmbeddings(request)
        case (.post, "/v1/rerank"):
            return try await handleRerank(request)
        default:
            return jsonResponse(
                statusCode: 404,
                payload: ["error": ["code": "not_found", "message": "Unknown route."]]
            )
        }
    }

    private func handleModels() async throws -> HTTPResponse {
        let models = await modelCatalog.listModels().map { model in
            OpenAIModelDescriptor(
                id: model.modelID,
                object: "model",
                ownedBy: "melix",
                melixState: model.state.melixString
            )
        }

        let response = OpenAIModelsResponse(object: "list", data: models)
        let data = try encoder.encode(response)
        return HTTPResponse(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func handleHealth() async throws -> HTTPResponse {
        let startedAt = Date()
        let routes = await healthRoutes()
        let models = await modelCatalog.listModels()
        let readyCount = models.filter { $0.state == .modelWarm || $0.state == .modelPinned }.count
        let status = routes.values.allSatisfy { $0 } ? "ok" : "degraded"
        let response = HealthResponse(
            status: status,
            routes: routes,
            modelsReady: readyCount,
            modelsTotal: models.count
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "operator.health_latency_ms"
        )
        let data = try encoder.encode(response)
        return HTTPResponse(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func handleCacheStats() async throws -> HTTPResponse {
        let startedAt = Date()
        let summary = if let cacheMetadataStore {
            await cacheMetadataStore.cacheSummary()
        } else {
            CacheMetadataStore.emptySummary()
        }
        let response = CacheStatsResponse(
            l1Bytes: summary.l1Bytes,
            l2Bytes: summary.l2Bytes,
            l1HitRate: summary.l1HitRate,
            l2HitRate: summary.l2HitRate,
            checkpointCount: summary.checkpointCount,
            blockCount: summary.blockCount,
            quantizedBytes: summary.quantizedBytes,
            compressionRatio: summary.compressionRatio,
            l2RestoreHitRate: summary.l2RestoreHitRate
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "operator.cache_stats_latency_ms"
        )
        let data = try encoder.encode(response)
        return HTTPResponse(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func handleChatCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let chatRequest = try decoder.decode(OpenAIChatCompletionsRequest.self, from: request.body)
        let normalized = translator.normalize(chatRequest)
        do {
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(
                translated: translated,
                shape: .chatCompletions
            )
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let completionsRequest = try decoder.decode(OpenAICompletionsRequest.self, from: request.body)
        let normalized = translator.normalize(completionsRequest)
        do {
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(
                translated: translated,
                shape: .completions
            )
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleResponses(_ request: HTTPRequest) async throws -> HTTPResponse {
        let responsesRequest = try decoder.decode(OpenAIResponsesRequest.self, from: request.body)
        let normalized = translator.normalize(responsesRequest)
        do {
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(
                translated: translated,
                shape: .responses
            )
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleMessages(_ request: HTTPRequest) async throws -> HTTPResponse {
        let messagesRequest = try decoder.decode(MelixMessagesRequest.self, from: request.body)
        let normalized = translator.normalize(messagesRequest)
        do {
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(
                translated: translated,
                shape: .messages
            )
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleEmbeddings(_ request: HTTPRequest) async throws -> HTTPResponse {
        let embeddingsRequest = try decoder.decode(OpenAIEmbeddingsRequest.self, from: request.body)
        let inputs = embeddingsRequest.normalizedInputs

        guard let modelHandle = await modelCatalog.dispatchHandle(for: embeddingsRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: embeddingsRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }

        var workerRequest = Melix_Worker_V1_EmbedRequest()
        workerRequest.id.requestID = UUID().uuidString
        workerRequest.modelHandle = modelHandle
        workerRequest.inputs = inputs

        let startedAt = Date()
        do {
            let response = try await inferenceClient.embed(request: workerRequest)
            if !response.error.code.isEmpty {
                return workerErrorResponse(response.error)
            }

            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
            await metricsStore.set(elapsedMs, forKey: "embeddings.request_latency_ms")
            await metricsStore.set(Double(inputs.count) / max(elapsedMs / 1000, 0.001), forKey: "embeddings.items_per_second")

            let payload = OpenAIEmbeddingsResponse(
                object: "list",
                data: response.embeddings.enumerated().map { index, embedding in
                    OpenAIEmbeddingDatum(object: "embedding", embedding: embedding.values, index: index)
                },
                model: embeddingsRequest.model,
                usage: OpenAIEmbeddingsUsage(
                    promptTokens: estimatedTokenCount(for: inputs),
                    totalTokens: estimatedTokenCount(for: inputs)
                )
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            return workerUnavailableResponse()
        }
    }

    private func handleRerank(_ request: HTTPRequest) async throws -> HTTPResponse {
        let rerankRequest = try decoder.decode(OpenAIRerankRequest.self, from: request.body)

        guard let modelHandle = await modelCatalog.dispatchHandle(for: rerankRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: rerankRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }

        var workerRequest = Melix_Worker_V1_RerankRequest()
        workerRequest.id.requestID = UUID().uuidString
        workerRequest.modelHandle = modelHandle
        workerRequest.query = rerankRequest.query
        workerRequest.documents = rerankRequest.documents
        workerRequest.topK = rerankRequest.topK

        let startedAt = Date()
        do {
            let response = try await inferenceClient.rerank(request: workerRequest)
            if !response.error.code.isEmpty {
                return workerErrorResponse(response.error)
            }

            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
            await metricsStore.set(elapsedMs, forKey: "rerank.request_latency_ms")
            await metricsStore.set(
                Double(rerankRequest.documents.count) / max(elapsedMs / 1000, 0.001),
                forKey: "rerank.documents_per_second"
            )

            let payload = OpenAIRerankResponse(
                object: "list",
                data: response.items.map { OpenAIRerankDatum(index: Int($0.index), score: $0.score) },
                model: rerankRequest.model,
                topK: Int(rerankRequest.topK)
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            return workerUnavailableResponse()
        }
    }

    private func translatedRequest(
        _ normalized: NormalizedTextRequest
    ) async throws -> TranslatedChatRequest {
        guard normalized.stream else {
            throw HTTPRequestHandlingError.streamRequired
        }
        guard let modelHandle = await modelCatalog.dispatchHandle(for: normalized.model) else {
            throw HTTPRequestHandlingError.modelNotReady
        }
        let shapingStartedAt = Date()
        let translated = try translator.translate(normalized, modelHandle: modelHandle)
        await recordShapingMetrics(for: translated, startedAt: shapingStartedAt)
        return translated
    }

    private func recordShapingMetrics(
        for translated: TranslatedChatRequest,
        startedAt: Date
    ) async {
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "http.shaping_ms"
        )
        if translated.workerRequest.execution.ext["melix.preset_id"] != nil {
            await metricsStore.increment("http.preset_shaped_count")
        }
        if translated.workerRequest.execution.ext["melix.workflow"] != nil {
            await metricsStore.increment("http.workflow_shaped_count")
        }
    }

    private func streamResponse(
        translated: TranslatedChatRequest,
        shape: SSEStreamWriter.StreamShape
    ) async throws -> HTTPResponse {
        let execution: CoordinatedChatExecution

        do {
            execution = try await requestCoordinator.startChatCompletion(translated)
        } catch let error as RequestCoordinatorError {
            return jsonResponse(statusCode: error.statusCode, payload: [
                "error": [
                    "code": error.errorCode,
                    "message": error.errorMessage,
                ],
            ])
        }

        let stream = sseWriter.encode(
            stream: execution.stream,
            requestID: execution.requestID,
            modelID: execution.modelID,
            shape: shape
        )

        return HTTPResponse(
            statusCode: 200,
            headers: [
                "content-type": "text/event-stream; charset=utf-8",
                "cache-control": "no-cache",
                "connection": "keep-alive",
            ],
            body: .stream(stream)
        )
    }

    private func jsonResponse(statusCode: Int, payload: [String: Any]) -> HTTPResponse {
        let data = (try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])) ?? Data("{}".utf8)
        return HTTPResponse(
            statusCode: statusCode,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func httpErrorResponse(for error: HTTPRequestHandlingError) -> HTTPResponse {
        switch error {
        case .streamRequired:
            return jsonResponse(
                statusCode: 400,
                payload: ["error": ["code": "stream_required", "message": "Phase 4 currently supports stream=true only."]]
            )
        case .modelNotReady:
            return jsonResponse(
                statusCode: 409,
                payload: ["error": ["code": "model_not_ready", "message": "Requested model is not loaded."]]
            )
        }
    }

    private func workerUnavailableResponse() -> HTTPResponse {
        jsonResponse(
            statusCode: 503,
            payload: ["error": ["code": "worker_unavailable", "message": "The worker cannot accept requests."]]
        )
    }

    private func workerErrorResponse(_ error: Melix_Worker_V1_ErrorStatus) -> HTTPResponse {
        let statusCode: Int
        switch error.code {
        case "invalid_argument":
            statusCode = 400
        case "not_found":
            statusCode = 404
        default:
            statusCode = 500
        }

        return jsonResponse(
            statusCode: statusCode,
            payload: ["error": ["code": error.code, "message": error.message]]
        )
    }

    private func healthRoutes() async -> [String: Bool] {
        let routes: [WorkerRouteKind] = [.swiftText, .pythonEmbedding, .pythonRerank, .pythonModelOperations]
        guard let workerRegistry else {
            return Dictionary(uniqueKeysWithValues: routes.map { ($0.rawValue, false) })
        }

        var values: [String: Bool] = [:]
        for route in routes {
            if let client = await workerRegistry.client(for: route) {
                values[route.rawValue] = await client.canDispatchRequests()
            } else {
                values[route.rawValue] = false
            }
        }
        return values
    }

    private func routedWorkerClient(
        forModelID modelID: String,
        workerRegistry: WorkerRegistry
    ) async -> (any WorkerRoutingClient)? {
        if let model = await modelCatalog.model(id: modelID),
           let route = await workerRegistry.route(for: model) {
            return await workerRegistry.client(for: route)
        }
        return await workerRegistry.client(forModelID: modelID)
    }

    private func estimatedTokenCount(for inputs: [String]) -> Int {
        let total = inputs.reduce(0) { partial, value in
            let count = value.split(whereSeparator: \.isWhitespace).count
            return partial + max(count, value.isEmpty ? 0 : 1)
        }
        return max(total, inputs.isEmpty ? 0 : 1)
    }
}

private enum HTTPRequestHandlingError: Error {
    case streamRequired
    case modelNotReady
}

private struct HealthResponse: Codable {
    let status: String
    let routes: [String: Bool]
    let modelsReady: Int
    let modelsTotal: Int

    enum CodingKeys: String, CodingKey {
        case status
        case routes
        case modelsReady = "models_ready"
        case modelsTotal = "models_total"
    }
}

private struct CacheStatsResponse: Codable {
    let l1Bytes: UInt64
    let l2Bytes: UInt64
    let l1HitRate: Double
    let l2HitRate: Double
    let checkpointCount: UInt64
    let blockCount: UInt64
    let quantizedBytes: UInt64
    let compressionRatio: Double
    let l2RestoreHitRate: Double

    enum CodingKeys: String, CodingKey {
        case l1Bytes = "l1_bytes"
        case l2Bytes = "l2_bytes"
        case l1HitRate = "l1_hit_rate"
        case l2HitRate = "l2_hit_rate"
        case checkpointCount = "checkpoint_count"
        case blockCount = "block_count"
        case quantizedBytes = "quantized_bytes"
        case compressionRatio = "compression_ratio"
        case l2RestoreHitRate = "l2_restore_hit_rate"
    }
}

private struct OpenAIEmbeddingsRequest: Codable {
    enum Input: Sendable, Codable {
        case text(String)
        case texts([String])

        init(from decoder: Decoder) throws {
            let singleValue = try decoder.singleValueContainer()
            if let text = try? singleValue.decode(String.self) {
                self = .text(text)
                return
            }
            self = .texts(try singleValue.decode([String].self))
        }

        func encode(to encoder: Encoder) throws {
            var singleValue = encoder.singleValueContainer()
            switch self {
            case let .text(text):
                try singleValue.encode(text)
            case let .texts(texts):
                try singleValue.encode(texts)
            }
        }
    }

    let model: String
    let input: Input

    var normalizedInputs: [String] {
        switch input {
        case let .text(text):
            return [text]
        case let .texts(texts):
            return texts
        }
    }
}

private struct OpenAIEmbeddingsResponse: Codable {
    let object: String
    let data: [OpenAIEmbeddingDatum]
    let model: String
    let usage: OpenAIEmbeddingsUsage
}

private struct OpenAIEmbeddingDatum: Codable {
    let object: String
    let embedding: [Float]
    let index: Int
}

private struct OpenAIEmbeddingsUsage: Codable {
    let promptTokens: Int
    let totalTokens: Int

    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case totalTokens = "total_tokens"
    }
}

private struct OpenAIRerankRequest: Codable {
    let model: String
    let query: String
    let documents: [String]
    let topK: UInt32

    enum CodingKeys: String, CodingKey {
        case model
        case query
        case documents
        case topK = "top_k"
    }
}

private struct OpenAIRerankResponse: Codable {
    let object: String
    let data: [OpenAIRerankDatum]
    let model: String
    let topK: Int

    enum CodingKeys: String, CodingKey {
        case object
        case data
        case model
        case topK = "top_k"
    }
}

private struct OpenAIRerankDatum: Codable {
    let index: Int
    let score: Float
}

private struct OpenAIModelsResponse: Codable {
    let object: String
    let data: [OpenAIModelDescriptor]
}

private struct OpenAIModelDescriptor: Codable {
    let id: String
    let object: String
    let ownedBy: String
    let melixState: String

    enum CodingKeys: String, CodingKey {
        case id
        case object
        case ownedBy = "owned_by"
        case melixState = "melix_state"
    }
}

private extension Melix_Controlplane_V1_ModelState {
    var melixString: String {
        switch self {
        case .modelWarm:
            return "warm"
        case .modelPinned:
            return "pinned"
        case .modelUnloaded:
            return "unloaded"
        case .modelLoading:
            return "loading"
        case .modelDiscovered:
            return "discovered"
        case .modelFailed:
            return "failed"
        case .modelEvicting:
            return "evicting"
        default:
            return "unknown"
        }
    }
}

private extension RequestCoordinatorError {
    var statusCode: Int {
        switch self {
        case .requestAlreadyActive:
            return 409
        case .workerUnavailable:
            return 503
        }
    }

    var errorCode: String {
        switch self {
        case .requestAlreadyActive:
            return "request_already_active"
        case .workerUnavailable:
            return "worker_unavailable"
        }
    }

    var errorMessage: String {
        switch self {
        case .requestAlreadyActive:
            return "A text generation request is already active."
        case .workerUnavailable:
            return "The worker cannot accept requests."
        }
    }
}
