import Foundation
import MelixControlPlaneProtocol

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
    private let translator: ChatRequestTranslator
    private let sseWriter: SSEStreamWriter
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(
        modelCatalog: ModelCatalog,
        requestCoordinator: RequestCoordinator,
        translator: ChatRequestTranslator = ChatRequestTranslator(),
        sseWriter: SSEStreamWriter = SSEStreamWriter()
    ) {
        self.modelCatalog = modelCatalog
        self.requestCoordinator = requestCoordinator
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
        case (.post, "/v1/chat/completions"):
            return try await handleChatCompletions(request)
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

    private func handleChatCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let chatRequest = try decoder.decode(OpenAIChatCompletionsRequest.self, from: request.body)
        guard chatRequest.stream ?? true else {
            return jsonResponse(
                statusCode: 400,
                payload: ["error": ["code": "stream_required", "message": "Phase 0 only supports stream=true."]]
            )
        }
        guard let modelHandle = await modelCatalog.dispatchHandle(for: chatRequest.model) else {
            return jsonResponse(
                statusCode: 409,
                payload: ["error": ["code": "model_not_ready", "message": "Requested model is not loaded."]]
            )
        }

        let translated = try translator.translate(chatRequest, modelHandle: modelHandle)
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
            modelID: execution.modelID
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
