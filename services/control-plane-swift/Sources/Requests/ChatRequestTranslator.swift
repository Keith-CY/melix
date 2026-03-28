import Foundation
import MelixWorkerProtocol

public enum ChatRequestTranslationError: Error, Equatable {
    case unsupportedContent
}

public enum TextEndpointKind: String, Sendable, Codable, Equatable {
    case chatCompletions = "chat.completions"
    case completions = "completions"
    case responses = "responses"
    case messages = "messages"
}

public enum TextWorkflowKind: String, Sendable, Codable, Equatable {
    case interactive = "interactive"
    case toolFollowup = "tool_followup"
    case backgroundAnalysis = "background_analysis"
}

public struct NormalizedTextMessage: Sendable, Codable, Equatable {
    public let role: String
    public let content: String

    public init(role: String, content: String) {
        self.role = role
        self.content = content
    }
}

public struct NormalizedTextRequest: Sendable, Codable, Equatable {
    public let endpoint: TextEndpointKind
    public let model: String
    public let messages: [NormalizedTextMessage]
    public let stream: Bool
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?

    public init(
        endpoint: TextEndpointKind,
        model: String,
        messages: [NormalizedTextMessage],
        stream: Bool,
        temperature: Double?,
        topP: Double?,
        maxTokens: UInt32?,
        sessionID: String?,
        branchID: String?,
        parentRequestID: String?,
        restoreSnapshotID: String?,
        saveBoundarySnapshot: Bool?,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil
    ) {
        self.endpoint = endpoint
        self.model = model
        self.messages = messages
        self.stream = stream
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
    }
}

public struct ShapedTextRequest: Sendable, Equatable {
    public let endpoint: TextEndpointKind
    public let model: String
    public let messages: [NormalizedTextMessage]
    public let stream: Bool
    public let temperature: Double
    public let topP: Double
    public let maxTokens: UInt32
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?
    public let latencyClass: String
    public let lane: String
    public let priority: Int32
    public let latencySensitive: Bool
    public let admissionPolicy: String
    public let cachePolicy: String?
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
    public struct Message: Codable, Sendable, Equatable {
        public let role: String
        public let content: String

        public init(role: String, content: String) {
            self.role = role
            self.content = content
        }
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
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?

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
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
    }

    public init(
        model: String,
        messages: [Message],
        stream: Bool? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil
    ) {
        self.model = model
        self.messages = messages
        self.stream = stream
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
    }
}

public struct OpenAICompletionsRequest: Codable, Sendable {
    public let model: String
    public let prompt: String
    public let stream: Bool?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?

    enum CodingKeys: String, CodingKey {
        case model
        case prompt
        case stream
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
    }

    public init(
        model: String,
        prompt: String,
        stream: Bool? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil
    ) {
        self.model = model
        self.prompt = prompt
        self.stream = stream
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
    }
}

public struct OpenAIResponsesRequest: Codable, Sendable {
    public struct Message: Codable, Sendable, Equatable {
        public let role: String
        public let content: String

        public init(role: String, content: String) {
            self.role = role
            self.content = content
        }
    }

    public enum Input: Sendable, Codable, Equatable {
        case text(String)
        case messages([Message])

        public init(from decoder: Decoder) throws {
            let singleValue = try decoder.singleValueContainer()
            if let text = try? singleValue.decode(String.self) {
                self = .text(text)
                return
            }
            self = .messages(try singleValue.decode([Message].self))
        }

        public func encode(to encoder: Encoder) throws {
            var singleValue = encoder.singleValueContainer()
            switch self {
            case let .text(text):
                try singleValue.encode(text)
            case let .messages(messages):
                try singleValue.encode(messages)
            }
        }
    }

    public let model: String
    public let input: Input
    public let instructions: String?
    public let stream: Bool?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?

    enum CodingKeys: String, CodingKey {
        case model
        case input
        case instructions
        case stream
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
    }

    public init(
        model: String,
        input: Input,
        instructions: String? = nil,
        stream: Bool? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil
    ) {
        self.model = model
        self.input = input
        self.instructions = instructions
        self.stream = stream
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
    }
}

public struct MelixMessagesRequest: Codable, Sendable {
    public struct Message: Codable, Sendable, Equatable {
        public let role: String
        public let content: String

        public init(role: String, content: String) {
            self.role = role
            self.content = content
        }
    }

    public let model: String
    public let messages: [Message]
    public let system: String?
    public let stream: Bool?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?

    enum CodingKeys: String, CodingKey {
        case model
        case messages
        case system
        case stream
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
    }

    public init(
        model: String,
        messages: [Message],
        system: String? = nil,
        stream: Bool? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil
    ) {
        self.model = model
        self.messages = messages
        self.system = system
        self.stream = stream
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
    }
}

public struct OpenAICompletionChunk: Codable, Sendable, Equatable {
    public struct Choice: Codable, Sendable, Equatable {
        public let index: Int
        public let text: String
        public let finishReason: String?

        enum CodingKeys: String, CodingKey {
            case index
            case text
            case finishReason = "finish_reason"
        }
    }

    public let id: String
    public let object: String
    public let model: String
    public let choices: [Choice]
}

public struct OpenAIResponseEvent: Codable, Sendable, Equatable {
    public let type: String
    public let responseID: String

    enum CodingKeys: String, CodingKey {
        case type
        case responseID = "response_id"
    }
}

public struct MelixMessagesEvent: Codable, Sendable, Equatable {
    public let type: String
    public let messageID: String

    enum CodingKeys: String, CodingKey {
        case type
        case messageID = "message_id"
    }
}

public struct ChatRequestTranslator: Sendable {
    private let requestIDGenerator: @Sendable () -> String
    private let requestShaper: TextRequestShaper

    public init(
        requestIDGenerator: @escaping @Sendable () -> String = { UUID().uuidString },
        requestShaper: TextRequestShaper = TextRequestShaper()
    ) {
        self.requestIDGenerator = requestIDGenerator
        self.requestShaper = requestShaper
    }

    public func normalize(
        _ request: OpenAIChatCompletionsRequest
    ) -> NormalizedTextRequest {
        NormalizedTextRequest(
            endpoint: .chatCompletions,
            model: request.model,
            messages: request.messages.map {
                NormalizedTextMessage(role: $0.role, content: $0.content)
            },
            stream: request.stream ?? true,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            sessionID: request.sessionID,
            branchID: request.branchID,
            parentRequestID: request.parentRequestID,
            restoreSnapshotID: request.restoreSnapshotID,
            saveBoundarySnapshot: request.saveBoundarySnapshot,
            presetID: request.presetID,
            workflow: request.workflow,
            workflowRunID: request.workflowRunID,
            workflowNodeID: request.workflowNodeID
        )
    }

    public func normalize(
        _ request: OpenAICompletionsRequest
    ) -> NormalizedTextRequest {
        NormalizedTextRequest(
            endpoint: .completions,
            model: request.model,
            messages: [
                NormalizedTextMessage(role: "user", content: request.prompt),
            ],
            stream: request.stream ?? true,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            sessionID: request.sessionID,
            branchID: request.branchID,
            parentRequestID: request.parentRequestID,
            restoreSnapshotID: request.restoreSnapshotID,
            saveBoundarySnapshot: request.saveBoundarySnapshot,
            presetID: request.presetID,
            workflow: request.workflow,
            workflowRunID: request.workflowRunID,
            workflowNodeID: request.workflowNodeID
        )
    }

    public func normalize(
        _ request: OpenAIResponsesRequest
    ) -> NormalizedTextRequest {
        var messages: [NormalizedTextMessage] = []
        if let instructions = request.instructions, !instructions.isEmpty {
            messages.append(NormalizedTextMessage(role: "system", content: instructions))
        }
        switch request.input {
        case let .text(text):
            messages.append(NormalizedTextMessage(role: "user", content: text))
        case let .messages(inputMessages):
            messages.append(
                contentsOf: inputMessages.map {
                    NormalizedTextMessage(role: $0.role, content: $0.content)
                }
            )
        }

        return NormalizedTextRequest(
            endpoint: .responses,
            model: request.model,
            messages: messages,
            stream: request.stream ?? true,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            sessionID: request.sessionID,
            branchID: request.branchID,
            parentRequestID: request.parentRequestID,
            restoreSnapshotID: request.restoreSnapshotID,
            saveBoundarySnapshot: request.saveBoundarySnapshot,
            presetID: request.presetID,
            workflow: request.workflow,
            workflowRunID: request.workflowRunID,
            workflowNodeID: request.workflowNodeID
        )
    }

    public func normalize(
        _ request: MelixMessagesRequest
    ) -> NormalizedTextRequest {
        var messages: [NormalizedTextMessage] = []
        if let system = request.system, !system.isEmpty {
            messages.append(NormalizedTextMessage(role: "system", content: system))
        }
        messages.append(
            contentsOf: request.messages.map {
                NormalizedTextMessage(role: $0.role, content: $0.content)
            }
        )

        return NormalizedTextRequest(
            endpoint: .messages,
            model: request.model,
            messages: messages,
            stream: request.stream ?? true,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            sessionID: request.sessionID,
            branchID: request.branchID,
            parentRequestID: request.parentRequestID,
            restoreSnapshotID: request.restoreSnapshotID,
            saveBoundarySnapshot: request.saveBoundarySnapshot,
            presetID: request.presetID,
            workflow: request.workflow,
            workflowRunID: request.workflowRunID,
            workflowNodeID: request.workflowNodeID
        )
    }

    public func shape(_ normalizedRequest: NormalizedTextRequest) -> ShapedTextRequest {
        requestShaper.shape(normalizedRequest)
    }

    public func translate(
        _ request: OpenAIChatCompletionsRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(normalize(request), modelHandle: modelHandle)
    }

    public func translate(
        _ request: OpenAICompletionsRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(normalize(request), modelHandle: modelHandle)
    }

    public func translate(
        _ request: OpenAIResponsesRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(normalize(request), modelHandle: modelHandle)
    }

    public func translate(
        _ request: MelixMessagesRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(normalize(request), modelHandle: modelHandle)
    }

    public func translate(
        _ normalizedRequest: NormalizedTextRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        let requestID = requestIDGenerator()
        let shapedRequest = shape(normalizedRequest)

        var generateRequest = Melix_Worker_V1_GenerateRequest()
        generateRequest.execution = Melix_Worker_V1_ExecutionMetadata()
        generateRequest.execution.id = Melix_Worker_V1_RequestIdentity()
        generateRequest.execution.id.requestID = requestID
        generateRequest.execution.id.latencyClass = shapedRequest.latencyClass
        generateRequest.execution.id.sessionID = shapedRequest.sessionID ?? ""
        generateRequest.execution.id.branchID = shapedRequest.branchID ?? ""
        generateRequest.execution.id.parentRequestID = shapedRequest.parentRequestID ?? ""
        generateRequest.execution.id.workflowRunID = shapedRequest.workflowRunID ?? ""
        generateRequest.execution.id.workflowNodeID = shapedRequest.workflowNodeID ?? ""
        generateRequest.execution.modelHandle = modelHandle
        generateRequest.execution.scheduling = Melix_Worker_V1_SchedulingHints()
        generateRequest.execution.scheduling.lane = shapedRequest.lane
        generateRequest.execution.scheduling.priority = shapedRequest.priority
        generateRequest.execution.scheduling.latencySensitive = shapedRequest.latencySensitive
        generateRequest.execution.scheduling.admissionPolicy = shapedRequest.admissionPolicy
        generateRequest.execution.cacheHints = Melix_Worker_V1_CacheHints()
        generateRequest.execution.cacheHints.cachePolicy = shapedRequest.cachePolicy ?? ""
        if let presetID = shapedRequest.presetID {
            generateRequest.execution.ext["melix.preset_id"] = presetID
        }
        if let workflow = shapedRequest.workflow {
            generateRequest.execution.ext["melix.workflow"] = workflow.rawValue
        }
        generateRequest.execution.ext["melix.endpoint"] = shapedRequest.endpoint.rawValue
        if !(shapedRequest.sessionID ?? "").isEmpty {
            generateRequest.execution.cacheHints.allowL1 = true
            generateRequest.execution.cacheHints.allowL2 = true
            generateRequest.execution.cacheHints.persistL2 = true
            generateRequest.execution.cacheHints.preferHotPrefix = true
        }
        generateRequest.execution.cacheHints.restoreSnapshotID = shapedRequest.restoreSnapshotID ?? ""
        generateRequest.execution.cacheHints.saveBoundarySnapshot = shapedRequest.saveBoundarySnapshot
        generateRequest.sampling = Melix_Worker_V1_SamplingConfig()
        generateRequest.sampling.temperature = Float(shapedRequest.temperature)
        generateRequest.sampling.topP = Float(shapedRequest.topP)
        generateRequest.sampling.maxOutputTokens = shapedRequest.maxTokens
        generateRequest.stream = shapedRequest.stream
        generateRequest.returnUsage = true
        generateRequest.messages = shapedRequest.messages.map { message in
            var chatMessage = Melix_Worker_V1_ChatMessage()
            chatMessage.role = message.role
            var part = Melix_Worker_V1_MessagePart()
            part.text = message.content
            chatMessage.parts = [part]
            return chatMessage
        }

        return TranslatedChatRequest(
            requestID: requestID,
            modelID: shapedRequest.model,
            workerRequest: generateRequest,
            stream: generateRequest.stream
        )
    }
}
