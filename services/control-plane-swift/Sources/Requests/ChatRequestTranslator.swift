import Foundation
import MelixWorkerProtocol

public enum ChatRequestTranslationError: Error, Equatable {
    case unsupportedContent
}

public struct TranslatedChatRequest: Sendable {
    public let requestID: String
    public let modelID: String
    public let workerRequest: Melix_Worker_V1_GenerateRequest
    public let stream: Bool

    public init(
        requestID: String,
        modelID: String,
        workerRequest: Melix_Worker_V1_GenerateRequest,
        stream: Bool
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.workerRequest = workerRequest
        self.stream = stream
    }
}

public struct OpenAIChatCompletionsRequest: Codable, Sendable {
    public struct Message: Codable, Sendable {
        public let role: String
        public let content: String
    }

    public let model: String
    public let messages: [Message]
    public let stream: Bool?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?

    enum CodingKeys: String, CodingKey {
        case model
        case messages
        case stream
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
    }
}

public struct ChatRequestTranslator: Sendable {
    private let requestIDGenerator: @Sendable () -> String

    public init(
        requestIDGenerator: @escaping @Sendable () -> String = { UUID().uuidString }
    ) {
        self.requestIDGenerator = requestIDGenerator
    }

    public func translate(
        _ request: OpenAIChatCompletionsRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        let requestID = requestIDGenerator()

        var generateRequest = Melix_Worker_V1_GenerateRequest()
        generateRequest.execution = Melix_Worker_V1_ExecutionMetadata()
        generateRequest.execution.id = Melix_Worker_V1_RequestIdentity()
        generateRequest.execution.id.requestID = requestID
        generateRequest.execution.id.latencyClass = "interactive"
        generateRequest.execution.id.sessionID = request.sessionID ?? ""
        generateRequest.execution.id.branchID = request.branchID ?? ""
        generateRequest.execution.id.parentRequestID = request.parentRequestID ?? ""
        generateRequest.execution.modelHandle = modelHandle
        generateRequest.execution.scheduling = Melix_Worker_V1_SchedulingHints()
        generateRequest.execution.scheduling.lane = "text.decode.interactive"
        generateRequest.execution.scheduling.priority = 100
        generateRequest.execution.scheduling.latencySensitive = true
        generateRequest.execution.cacheHints = Melix_Worker_V1_CacheHints()
        if !(request.sessionID ?? "").isEmpty {
            generateRequest.execution.cacheHints.allowL1 = true
            generateRequest.execution.cacheHints.allowL2 = true
            generateRequest.execution.cacheHints.persistL2 = true
            generateRequest.execution.cacheHints.preferHotPrefix = true
            generateRequest.execution.id.branchID = request.branchID ?? "branch-main"
        }
        generateRequest.execution.cacheHints.restoreSnapshotID = request.restoreSnapshotID ?? ""
        generateRequest.execution.cacheHints.saveBoundarySnapshot = request.saveBoundarySnapshot
            ?? !(request.sessionID ?? "").isEmpty
        generateRequest.sampling = Melix_Worker_V1_SamplingConfig()
        generateRequest.sampling.temperature = Float(request.temperature ?? 0.7)
        generateRequest.sampling.topP = Float(request.topP ?? 1.0)
        generateRequest.sampling.maxOutputTokens = request.maxTokens ?? 256
        generateRequest.stream = request.stream ?? true
        generateRequest.returnUsage = true
        generateRequest.messages = request.messages.map { message in
            var chatMessage = Melix_Worker_V1_ChatMessage()
            chatMessage.role = message.role
            var part = Melix_Worker_V1_MessagePart()
            part.text = message.content
            chatMessage.parts = [part]
            return chatMessage
        }

        return TranslatedChatRequest(
            requestID: requestID,
            modelID: request.model,
            workerRequest: generateRequest,
            stream: generateRequest.stream
        )
    }
}
