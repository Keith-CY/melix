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

public struct NormalizedTextMessage: Sendable, Equatable {
    public let role: String
    public let parts: [Melix_Worker_V1_MessagePart]

    public init(role: String, content: String) {
        self.role = role
        var part = Melix_Worker_V1_MessagePart()
        part.text = content
        self.parts = [part]
    }

    public init(role: String, parts: [Melix_Worker_V1_MessagePart]) {
        self.role = role
        self.parts = parts
    }

    public var content: String {
        parts
            .map(\.text)
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
    }
}

public struct NormalizedTextRequest: Sendable, Equatable {
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
    public let stopSequences: [String]
    public let userID: String?
    public let thinking: MelixMessagesThinkingConfig?

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
        workflowNodeID: String? = nil,
        stopSequences: [String] = [],
        userID: String? = nil,
        thinking: MelixMessagesThinkingConfig? = nil
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
        self.stopSequences = stopSequences
        self.userID = userID
        self.thinking = thinking
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
    public let stopSequences: [String]
    public let userID: String?
    public let thinking: MelixMessagesThinkingConfig?
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
        public let contentParts: [OpenAIMultimodalContentPart]?

        enum CodingKeys: String, CodingKey {
            case role
            case content
        }

        public init(role: String, content: String) {
            self.role = role
            self.content = content
            self.contentParts = nil
        }

        public init(role: String, contentParts: [OpenAIMultimodalContentPart]) {
            self.role = role
            self.content = contentParts.compactMap(\.text).joined(separator: "\n")
            self.contentParts = contentParts
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            role = try container.decode(String.self, forKey: .role)
            if let text = try? container.decode(String.self, forKey: .content) {
                content = text
                contentParts = nil
            } else {
                let parts = try container.decode([OpenAIMultimodalContentPart].self, forKey: .content)
                content = parts.compactMap(\.text).joined(separator: "\n")
                contentParts = parts
            }
        }

        public func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(role, forKey: .role)
            if let contentParts {
                try container.encode(contentParts, forKey: .content)
            } else {
                try container.encode(content, forKey: .content)
            }
        }

        public var hasMultimodalContent: Bool {
            contentParts != nil
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

public struct MelixMessagesContentBlock: Codable, Sendable, Equatable {
    public enum Kind: String, Codable, Sendable, Equatable {
        case text
        case thinking
    }

    public let type: Kind
    public let text: String?
    public let thinking: String?

    public init(
        type: Kind,
        text: String? = nil,
        thinking: String? = nil
    ) {
        self.type = type
        self.text = text
        self.thinking = thinking
    }

    public var normalizedText: String {
        switch type {
        case .text:
            return text ?? ""
        case .thinking:
            return thinking ?? ""
        }
    }
}

public enum MelixMessagesContentValue: Codable, Sendable, Equatable {
    case text(String)
    case blocks([MelixMessagesContentBlock])

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self) {
            self = .text(text)
            return
        }
        self = .blocks(try container.decode([MelixMessagesContentBlock].self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .text(let text):
            try container.encode(text)
        case .blocks(let blocks):
            try container.encode(blocks)
        }
    }

    public var flattenedText: String {
        switch self {
        case .text(let text):
            return text
        case .blocks(let blocks):
            return blocks
                .map(\.normalizedText)
                .filter { !$0.isEmpty }
                .joined(separator: "\n")
        }
    }

    public var blocks: [MelixMessagesContentBlock]? {
        switch self {
        case .text:
            return nil
        case .blocks(let blocks):
            return blocks
        }
    }
}

public struct MelixMessagesThinkingConfig: Codable, Sendable, Equatable {
    public let type: String
    public let budgetTokens: UInt32?

    enum CodingKeys: String, CodingKey {
        case type
        case budgetTokens = "budget_tokens"
    }

    public init(
        type: String,
        budgetTokens: UInt32? = nil
    ) {
        self.type = type
        self.budgetTokens = budgetTokens
    }

    public var isEnabled: Bool {
        type != "disabled"
    }
}

public struct MelixMessagesMetadata: Codable, Sendable, Equatable {
    public let userID: String?

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
    }

    public init(userID: String? = nil) {
        self.userID = userID
    }
}

public struct MelixMessagesRequest: Codable, Sendable {
    public struct Message: Codable, Sendable, Equatable {
        public let role: String
        private let rawContent: MelixMessagesContentValue

        enum CodingKeys: String, CodingKey {
            case role
            case content
        }

        public init(role: String, content: String) {
            self.role = role
            self.rawContent = .text(content)
        }

        public init(role: String, contentBlocks: [MelixMessagesContentBlock]) {
            self.role = role
            self.rawContent = .blocks(contentBlocks)
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.role = try container.decode(String.self, forKey: .role)
            self.rawContent = try container.decode(MelixMessagesContentValue.self, forKey: .content)
        }

        public func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(role, forKey: .role)
            try container.encode(rawContent, forKey: .content)
        }

        public var content: String {
            rawContent.flattenedText
        }

        public var contentBlocks: [MelixMessagesContentBlock]? {
            rawContent.blocks
        }
    }

    public let model: String
    public let messages: [Message]
    private let rawSystem: MelixMessagesContentValue?
    public let stream: Bool?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let stopSequences: [String]?
    public let metadata: MelixMessagesMetadata?
    public let thinking: MelixMessagesThinkingConfig?
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
        case stopSequences = "stop_sequences"
        case metadata
        case thinking
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
        systemBlocks: [MelixMessagesContentBlock]? = nil,
        stream: Bool? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        stopSequences: [String]? = nil,
        metadata: MelixMessagesMetadata? = nil,
        thinking: MelixMessagesThinkingConfig? = nil,
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
        if let systemBlocks {
            self.rawSystem = .blocks(systemBlocks)
        } else if let system {
            self.rawSystem = .text(system)
        } else {
            self.rawSystem = nil
        }
        self.stream = stream
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.stopSequences = stopSequences
        self.metadata = metadata
        self.thinking = thinking
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

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.model = try container.decode(String.self, forKey: .model)
        self.messages = try container.decode([Message].self, forKey: .messages)
        self.rawSystem = try container.decodeIfPresent(MelixMessagesContentValue.self, forKey: .system)
        self.stream = try container.decodeIfPresent(Bool.self, forKey: .stream)
        self.temperature = try container.decodeIfPresent(Double.self, forKey: .temperature)
        self.topP = try container.decodeIfPresent(Double.self, forKey: .topP)
        self.maxTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxTokens)
        self.stopSequences = try container.decodeIfPresent([String].self, forKey: .stopSequences)
        self.metadata = try container.decodeIfPresent(MelixMessagesMetadata.self, forKey: .metadata)
        self.thinking = try container.decodeIfPresent(MelixMessagesThinkingConfig.self, forKey: .thinking)
        self.sessionID = try container.decodeIfPresent(String.self, forKey: .sessionID)
        self.branchID = try container.decodeIfPresent(String.self, forKey: .branchID)
        self.parentRequestID = try container.decodeIfPresent(String.self, forKey: .parentRequestID)
        self.restoreSnapshotID = try container.decodeIfPresent(String.self, forKey: .restoreSnapshotID)
        self.saveBoundarySnapshot = try container.decodeIfPresent(Bool.self, forKey: .saveBoundarySnapshot)
        self.presetID = try container.decodeIfPresent(String.self, forKey: .presetID)
        self.workflow = try container.decodeIfPresent(TextWorkflowKind.self, forKey: .workflow)
        self.workflowRunID = try container.decodeIfPresent(String.self, forKey: .workflowRunID)
        self.workflowNodeID = try container.decodeIfPresent(String.self, forKey: .workflowNodeID)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(model, forKey: .model)
        try container.encode(messages, forKey: .messages)
        try container.encodeIfPresent(rawSystem, forKey: .system)
        try container.encodeIfPresent(stream, forKey: .stream)
        try container.encodeIfPresent(temperature, forKey: .temperature)
        try container.encodeIfPresent(topP, forKey: .topP)
        try container.encodeIfPresent(maxTokens, forKey: .maxTokens)
        try container.encodeIfPresent(stopSequences, forKey: .stopSequences)
        try container.encodeIfPresent(metadata, forKey: .metadata)
        try container.encodeIfPresent(thinking, forKey: .thinking)
        try container.encodeIfPresent(sessionID, forKey: .sessionID)
        try container.encodeIfPresent(branchID, forKey: .branchID)
        try container.encodeIfPresent(parentRequestID, forKey: .parentRequestID)
        try container.encodeIfPresent(restoreSnapshotID, forKey: .restoreSnapshotID)
        try container.encodeIfPresent(saveBoundarySnapshot, forKey: .saveBoundarySnapshot)
        try container.encodeIfPresent(presetID, forKey: .presetID)
        try container.encodeIfPresent(workflow, forKey: .workflow)
        try container.encodeIfPresent(workflowRunID, forKey: .workflowRunID)
        try container.encodeIfPresent(workflowNodeID, forKey: .workflowNodeID)
    }

    public var system: String? {
        guard let text = rawSystem?.flattenedText, !text.isEmpty else {
            return nil
        }
        return text
    }

    public var systemBlocks: [MelixMessagesContentBlock]? {
        rawSystem?.blocks
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
        makeNormalizedRequest(
            endpoint: .chatCompletions,
            model: request.model,
            messages: request.messages.map {
                NormalizedTextMessage(role: $0.role, content: $0.content)
            },
            stream: request.stream,
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

    public func normalizeMultimodalChat(
        _ request: OpenAIChatCompletionsRequest
    ) throws -> NormalizedTextRequest {
        let normalizer = MultimodalRequestNormalizer()
        let messages = try request.messages.map { message in
            if let contentParts = message.contentParts {
                let normalized = try normalizer.normalize(
                    OpenAIMultimodalMessage(role: message.role, content: contentParts)
                )
                return NormalizedTextMessage(role: normalized.role, parts: Array(normalized.parts))
            }
            return NormalizedTextMessage(role: message.role, content: message.content)
        }

        return makeNormalizedRequest(
            endpoint: .chatCompletions,
            model: request.model,
            messages: messages,
            stream: request.stream,
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
        makeNormalizedRequest(
            endpoint: .completions,
            model: request.model,
            messages: [
                NormalizedTextMessage(role: "user", content: request.prompt),
            ],
            stream: request.stream,
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

        return makeNormalizedRequest(
            endpoint: .responses,
            model: request.model,
            messages: messages,
            stream: request.stream,
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
        if let systemBlocks = request.systemBlocks {
            let systemParts = messageParts(from: systemBlocks)
            if !systemParts.isEmpty {
                messages.append(NormalizedTextMessage(role: "system", parts: systemParts))
            }
        } else if let system = request.system, !system.isEmpty {
            messages.append(NormalizedTextMessage(role: "system", content: system))
        }
        messages.append(
            contentsOf: request.messages.map { message in
                if let contentBlocks = message.contentBlocks {
                    return NormalizedTextMessage(role: message.role, parts: messageParts(from: contentBlocks))
                }
                return NormalizedTextMessage(role: message.role, content: message.content)
            }
        )

        return makeNormalizedRequest(
            endpoint: .messages,
            model: request.model,
            messages: messages,
            stream: request.stream,
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
            workflowNodeID: request.workflowNodeID,
            stopSequences: request.stopSequences,
            userID: request.metadata?.userID,
            thinking: request.thinking
        )
    }

    private func makeNormalizedRequest(
        endpoint: TextEndpointKind,
        model: String,
        messages: [NormalizedTextMessage],
        stream: Bool?,
        temperature: Double?,
        topP: Double?,
        maxTokens: UInt32?,
        sessionID: String?,
        branchID: String?,
        parentRequestID: String?,
        restoreSnapshotID: String?,
        saveBoundarySnapshot: Bool?,
        presetID: String?,
        workflow: TextWorkflowKind?,
        workflowRunID: String?,
        workflowNodeID: String?,
        stopSequences: [String]? = nil,
        userID: String? = nil,
        thinking: MelixMessagesThinkingConfig? = nil
    ) -> NormalizedTextRequest {
        NormalizedTextRequest(
            endpoint: endpoint,
            model: model,
            messages: messages,
            stream: stream ?? true,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            sessionID: sessionID,
            branchID: branchID,
            parentRequestID: parentRequestID,
            restoreSnapshotID: restoreSnapshotID,
            saveBoundarySnapshot: saveBoundarySnapshot,
            presetID: presetID,
            workflow: workflow,
            workflowRunID: workflowRunID,
            workflowNodeID: workflowNodeID,
            stopSequences: stopSequences ?? [],
            userID: userID,
            thinking: thinking
        )
    }

    private func messageParts(
        from blocks: [MelixMessagesContentBlock]
    ) -> [Melix_Worker_V1_MessagePart] {
        blocks.compactMap { block in
            let text = block.normalizedText
            guard !text.isEmpty else {
                return nil
            }
            var part = Melix_Worker_V1_MessagePart()
            part.text = text
            return part
        }
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
        if let userID = shapedRequest.userID, !userID.isEmpty {
            generateRequest.execution.ext["melix.messages.user_id"] = userID
        }
        if let thinking = shapedRequest.thinking, thinking.isEnabled {
            generateRequest.execution.reasoning = Melix_Worker_V1_ReasoningConfig()
            generateRequest.execution.reasoning.enabled = true
            generateRequest.execution.reasoning.separateStream = true
            generateRequest.execution.ext["melix.messages.thinking.type"] = thinking.type
            if let budgetTokens = thinking.budgetTokens {
                generateRequest.execution.ext["melix.messages.thinking.budget_tokens"] = String(budgetTokens)
            }
        }
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
        generateRequest.sampling.stop = shapedRequest.stopSequences
        generateRequest.stream = shapedRequest.stream
        generateRequest.returnUsage = true
        generateRequest.messages = shapedRequest.messages.map { message in
            var chatMessage = Melix_Worker_V1_ChatMessage()
            chatMessage.role = message.role
            chatMessage.parts = message.parts
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
