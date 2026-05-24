import Foundation
import MelixControlPlaneProtocol
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

public struct HarmonyMessageMetadata: Sendable, Equatable {
    public let channel: String?
    public let recipient: String?
    public let contentType: String?

    public init(
        channel: String? = nil,
        recipient: String? = nil,
        contentType: String? = nil
    ) {
        self.channel = Self.normalize(channel)
        self.recipient = Self.normalize(recipient)
        self.contentType = Self.normalize(contentType)
    }

    public var isEmpty: Bool {
        channel == nil && recipient == nil && contentType == nil
    }

    private static func normalize(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

public struct NormalizedTextMessage: Sendable, Equatable {
    public let role: String
    public let name: String?
    public let parts: [Melix_Worker_V1_MessagePart]
    public let harmonyMetadata: HarmonyMessageMetadata?

    public init(
        role: String,
        name: String? = nil,
        content: String,
        harmonyMetadata: HarmonyMessageMetadata? = nil
    ) {
        self.role = role
        self.name = Self.normalize(name)
        var part = Melix_Worker_V1_MessagePart()
        part.text = content
        self.parts = [part]
        self.harmonyMetadata = harmonyMetadata?.isEmpty == false ? harmonyMetadata : nil
    }

    public init(
        role: String,
        name: String? = nil,
        parts: [Melix_Worker_V1_MessagePart],
        harmonyMetadata: HarmonyMessageMetadata? = nil
    ) {
        self.role = role
        self.name = Self.normalize(name)
        self.parts = parts
        self.harmonyMetadata = harmonyMetadata?.isEmpty == false ? harmonyMetadata : nil
    }

    public var content: String {
        parts
            .map(\.text)
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
    }

    private static func normalize(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

public struct NormalizedToolDefinition: Sendable, Equatable {
    public let name: String
    public let description: String
    public let jsonSchema: String

    public init(
        name: String,
        description: String? = nil,
        jsonSchema: String = "{}"
    ) {
        self.name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedDescription = description?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.description = trimmedDescription.flatMap { $0.isEmpty ? nil : $0 } ?? ""
        let trimmedSchema = jsonSchema.trimmingCharacters(in: .whitespacesAndNewlines)
        self.jsonSchema = trimmedSchema.isEmpty ? "{}" : trimmedSchema
    }
}

public struct NormalizedTextRequest: Sendable, Equatable {
    public let endpoint: TextEndpointKind
    public let model: String
    public let messages: [NormalizedTextMessage]
    public let stream: Bool
    public let includeUsage: Bool
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let maxCompletionTokens: UInt32?
    public let topK: UInt32?
    public let minP: Double?
    public let repeatPenalty: Double?
    public let presencePenalty: Double?
    public let seed: UInt32?
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
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let thinking: MelixMessagesThinkingConfig?
    public let structuredOutput: StructuredOutputConfiguration?
    public let toolParser: ToolParserSelection?
    public let tools: [NormalizedToolDefinition]
    public let toolChoice: String?
    public let chatTemplate: ChatTemplateSelection?

    public init(
        endpoint: TextEndpointKind,
        model: String,
        messages: [NormalizedTextMessage],
        stream: Bool,
        includeUsage: Bool = false,
        temperature: Double?,
        topP: Double?,
        maxTokens: UInt32?,
        maxCompletionTokens: UInt32? = nil,
        topK: UInt32? = nil,
        minP: Double? = nil,
        repeatPenalty: Double? = nil,
        presencePenalty: Double? = nil,
        seed: UInt32? = nil,
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
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        thinking: MelixMessagesThinkingConfig? = nil,
        structuredOutput: StructuredOutputConfiguration? = nil,
        toolParser: ToolParserSelection? = nil,
        tools: [NormalizedToolDefinition] = [],
        toolChoice: String? = nil,
        chatTemplate: ChatTemplateSelection? = nil
    ) {
        self.endpoint = endpoint
        self.model = model
        self.messages = messages
        self.stream = stream
        self.includeUsage = includeUsage
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.maxCompletionTokens = maxCompletionTokens
        self.topK = topK
        self.minP = minP
        self.repeatPenalty = repeatPenalty
        self.presencePenalty = presencePenalty
        self.seed = seed
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
        self.enableThinking = enableThinking
        let trimmedReasoningEffort = reasoningEffort?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.reasoningEffort = trimmedReasoningEffort?.isEmpty == false ? trimmedReasoningEffort : nil
        self.thinking = thinking
        self.structuredOutput = structuredOutput?.isEnabled == true ? structuredOutput : nil
        self.toolParser = toolParser
        self.tools = tools.filter { !$0.name.isEmpty }
        let trimmedToolChoice = toolChoice?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.toolChoice = trimmedToolChoice?.isEmpty == false ? trimmedToolChoice : nil
        self.chatTemplate = chatTemplate
    }
}

public extension NormalizedTextRequest {
    func replacingModel(_ model: String) -> NormalizedTextRequest {
        NormalizedTextRequest(
            endpoint: endpoint,
            model: model,
            messages: messages,
            stream: stream,
            includeUsage: includeUsage,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            maxCompletionTokens: maxCompletionTokens,
            topK: topK,
            minP: minP,
            repeatPenalty: repeatPenalty,
            presencePenalty: presencePenalty,
            seed: seed,
            sessionID: sessionID,
            branchID: branchID,
            parentRequestID: parentRequestID,
            restoreSnapshotID: restoreSnapshotID,
            saveBoundarySnapshot: saveBoundarySnapshot,
            presetID: presetID,
            workflow: workflow,
            workflowRunID: workflowRunID,
            workflowNodeID: workflowNodeID,
            stopSequences: stopSequences,
            userID: userID,
            enableThinking: enableThinking,
            reasoningEffort: reasoningEffort,
            thinking: thinking,
            structuredOutput: structuredOutput,
            toolParser: toolParser,
            tools: tools,
            toolChoice: toolChoice,
            chatTemplate: chatTemplate
        )
    }
}

public struct ShapedTextRequest: Sendable, Equatable {
    public let endpoint: TextEndpointKind
    public let model: String
    public let messages: [NormalizedTextMessage]
    public let stream: Bool
    public let includeUsage: Bool
    public let temperature: Double
    public let topP: Double
    public let maxTokens: UInt32
    public let requestedMaxTokens: UInt32?
    public let requestedMaxCompletionTokens: UInt32?
    public let outputCapSource: String
    public let topK: UInt32?
    public let minP: Double?
    public let repeatPenalty: Double?
    public let presencePenalty: Double?
    public let seed: UInt32?
    public let streamIntervalTokens: UInt32
    public let maxConcurrentRequests: UInt32
    public let concurrentProcessingEnabled: Bool
    public let prefillBatchSize: UInt32
    public let completionBatchSize: UInt32
    public let accelerationMode: Melix_Controlplane_V1_AccelerationMode
    public let accelerationProfile: String
    public let draftModelID: String
    public let numDraftTokens: UInt32
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
    public let requestedStopSequences: [String]
    public let stopSource: String
    public let userID: String?
    public let thinking: MelixMessagesThinkingConfig?
    public let reasoningMode: String
    public let reasoningSource: String
    public let reasoningEffort: String?
    public let reasoningAutoDetectModelFamily: String?
    public let reasoningContinuityRehydrated: Bool
    public let reasoningHistoryStripCount: Int
    public let rawToolCallHistoryStripCount: Int
    public let structuredOutput: StructuredOutputConfiguration?
    public let toolParser: ToolParserSelection?
    public let tools: [NormalizedToolDefinition]
    public let toolChoice: String?
    public let toolParserSuppressedReason: String?
    public let chatTemplate: ResolvedChatTemplatePolicy?
    public let ocrPolicy: ResolvedOCRExecutionPolicy?
    public let partialMode: String?
    public let assistantPrefill: AssistantPrefillSelection?
}

public struct AssistantPrefillSelection: Sendable, Equatable {
    public let messageIndex: Int
    public let messageName: String?

    public init(messageIndex: Int, messageName: String? = nil) {
        self.messageIndex = messageIndex
        self.messageName = messageName
    }
}

public struct TranslatedChatRequest: Sendable {
    public let requestID: String
    public let modelID: String
    public let responseModelID: String?
    public let workerRequest: Melix_Worker_V1_GenerateRequest
    public let stream: Bool

    public init(
        requestID: String,
        modelID: String,
        responseModelID: String? = nil,
        workerRequest: Melix_Worker_V1_GenerateRequest,
        stream: Bool
    ) {
        self.requestID = requestID
        self.modelID = modelID
        let trimmedResponseModelID = responseModelID?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.responseModelID = trimmedResponseModelID?.isEmpty == false ? trimmedResponseModelID : nil
        self.workerRequest = workerRequest
        self.stream = stream
    }
}

public struct OpenAIStreamOptions: Codable, Sendable, Equatable {
    public let includeUsage: Bool?

    enum CodingKeys: String, CodingKey {
        case includeUsage = "include_usage"
    }

    public init(includeUsage: Bool? = nil) {
        self.includeUsage = includeUsage
    }
}

public enum OpenAIChatToolChoice: Codable, Sendable, Equatable {
    case mode(String)
    case structured(StructuredJSONValue)

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let mode = try? container.decode(String.self) {
            self = .mode(mode)
            return
        }
        self = .structured(try container.decode(StructuredJSONValue.self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .mode(mode):
            try container.encode(mode)
        case let .structured(value):
            try container.encode(value)
        }
    }

    public var normalizedValue: String? {
        switch self {
        case let .mode(mode):
            let trimmed = mode.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        case let .structured(value):
            return try? value.canonicalJSONString()
        }
    }
}

public struct OpenAIChatTool: Codable, Sendable, Equatable {
    public struct FunctionDefinition: Codable, Sendable, Equatable {
        public let name: String
        public let description: String?
        public let parameters: StructuredJSONValue?

        public init(
            name: String,
            description: String? = nil,
            parameters: StructuredJSONValue? = nil
        ) {
            self.name = name
            self.description = description
            self.parameters = parameters
        }
    }

    public let type: String
    public let function: FunctionDefinition?

    public init(
        type: String,
        function: FunctionDefinition? = nil
    ) {
        self.type = type
        self.function = function
    }

    public func normalizedDefinition() throws -> NormalizedToolDefinition? {
        guard type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "function",
              let function
        else {
            return nil
        }
        let name = function.name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else {
            return nil
        }
        return NormalizedToolDefinition(
            name: name,
            description: function.description,
            jsonSchema: try function.parameters?.canonicalJSONString() ?? "{}"
        )
    }
}

public struct OpenAIChatCompletionsRequest: Codable, Sendable {
    public enum StopSequencesValue: Codable, Sendable, Equatable {
        case single(String)
        case many([String])

        public init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let value = try? container.decode(String.self) {
                self = .single(value)
                return
            }
            self = .many(try container.decode([String].self))
        }

        public func encode(to encoder: Encoder) throws {
            var container = encoder.singleValueContainer()
            switch self {
            case let .single(value):
                try container.encode(value)
            case let .many(values):
                try container.encode(values)
            }
        }

        var normalized: [String] {
            switch self {
            case let .single(value):
                return value.isEmpty ? [] : [value]
            case let .many(values):
                return values.filter { !$0.isEmpty }
            }
        }
    }

    public struct Message: Codable, Sendable, Equatable {
        public let role: String
        public let name: String?
        public let content: String
        public let contentParts: [OpenAIMultimodalContentPart]?

        enum CodingKeys: String, CodingKey {
            case role
            case name
            case content
        }

        public init(role: String, name: String? = nil, content: String) {
            self.role = role
            self.name = name
            self.content = content
            self.contentParts = nil
        }

        public init(role: String, name: String? = nil, contentParts: [OpenAIMultimodalContentPart]) {
            self.role = role
            self.name = name
            self.content = contentParts.compactMap(\.text).joined(separator: "\n")
            self.contentParts = contentParts
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            role = try container.decode(String.self, forKey: .role)
            name = try container.decodeIfPresent(String.self, forKey: .name)
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
            try container.encodeIfPresent(name, forKey: .name)
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
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let stream: Bool?
    public let streamOptions: OpenAIStreamOptions?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let maxCompletionTokens: UInt32?
    public let topK: UInt32?
    public let minP: Double?
    public let repeatPenalty: Double?
    public let presencePenalty: Double?
    public let seed: UInt32?
    public let resumeRequestID: String?
    public let stopSequences: [String]?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?
    public let responseFormat: StructuredOutputRequestFormat?
    public let toolParser: ToolParserRequestConfiguration?
    public let tools: [OpenAIChatTool]?
    public let toolChoice: OpenAIChatToolChoice?
    public let chatTemplateKwargs: ChatTemplateRequestConfiguration?

    enum CodingKeys: String, CodingKey {
        case model
        case messages
        case enableThinking = "enable_thinking"
        case reasoningEffort = "reasoning_effort"
        case stream
        case streamOptions = "stream_options"
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case maxCompletionTokens = "max_completion_tokens"
        case topK = "top_k"
        case minP = "min_p"
        case repeatPenalty = "repeat_penalty"
        case presencePenalty = "presence_penalty"
        case seed
        case resumeRequestID = "resume_request_id"
        case stop
        case stopSequences = "stop_sequences"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
        case responseFormat = "response_format"
        case toolParser = "tool_parser"
        case tools
        case toolChoice = "tool_choice"
        case chatTemplateKwargs = "chat_template_kwargs"
    }

    public init(
        model: String,
        messages: [Message],
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        stream: Bool? = nil,
        streamOptions: OpenAIStreamOptions? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        maxCompletionTokens: UInt32? = nil,
        topK: UInt32? = nil,
        minP: Double? = nil,
        repeatPenalty: Double? = nil,
        presencePenalty: Double? = nil,
        seed: UInt32? = nil,
        resumeRequestID: String? = nil,
        stopSequences: [String]? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil,
        responseFormat: StructuredOutputRequestFormat? = nil,
        toolParser: ToolParserRequestConfiguration? = nil,
        tools: [OpenAIChatTool]? = nil,
        toolChoice: OpenAIChatToolChoice? = nil,
        chatTemplateKwargs: ChatTemplateRequestConfiguration? = nil
    ) {
        self.model = model
        self.messages = messages
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        self.stream = stream
        self.streamOptions = streamOptions
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.maxCompletionTokens = maxCompletionTokens
        self.topK = topK
        self.minP = minP
        self.repeatPenalty = repeatPenalty
        self.presencePenalty = presencePenalty
        self.seed = seed
        self.resumeRequestID = resumeRequestID
        self.stopSequences = stopSequences
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
        self.responseFormat = responseFormat
        self.toolParser = toolParser
        self.tools = tools
        self.toolChoice = toolChoice
        self.chatTemplateKwargs = chatTemplateKwargs
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.model = try container.decode(String.self, forKey: .model)
        self.messages = try container.decode([Message].self, forKey: .messages)
        self.enableThinking = try container.decodeIfPresent(Bool.self, forKey: .enableThinking)
        self.reasoningEffort = try container.decodeIfPresent(String.self, forKey: .reasoningEffort)
        self.stream = try container.decodeIfPresent(Bool.self, forKey: .stream)
        self.streamOptions = try container.decodeIfPresent(OpenAIStreamOptions.self, forKey: .streamOptions)
        self.temperature = try container.decodeIfPresent(Double.self, forKey: .temperature)
        self.topP = try container.decodeIfPresent(Double.self, forKey: .topP)
        self.maxTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxTokens)
        self.maxCompletionTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxCompletionTokens)
        self.topK = try container.decodeIfPresent(UInt32.self, forKey: .topK)
        self.minP = try container.decodeIfPresent(Double.self, forKey: .minP)
        self.repeatPenalty = try container.decodeIfPresent(Double.self, forKey: .repeatPenalty)
        self.presencePenalty = try container.decodeIfPresent(Double.self, forKey: .presencePenalty)
        self.seed = try container.decodeIfPresent(UInt32.self, forKey: .seed)
        self.resumeRequestID = try container.decodeIfPresent(String.self, forKey: .resumeRequestID)
        self.stopSequences = try Self.decodeStopSequences(from: container)
        self.sessionID = try container.decodeIfPresent(String.self, forKey: .sessionID)
        self.branchID = try container.decodeIfPresent(String.self, forKey: .branchID)
        self.parentRequestID = try container.decodeIfPresent(String.self, forKey: .parentRequestID)
        self.restoreSnapshotID = try container.decodeIfPresent(String.self, forKey: .restoreSnapshotID)
        self.saveBoundarySnapshot = try container.decodeIfPresent(Bool.self, forKey: .saveBoundarySnapshot)
        self.presetID = try container.decodeIfPresent(String.self, forKey: .presetID)
        self.workflow = try container.decodeIfPresent(TextWorkflowKind.self, forKey: .workflow)
        self.workflowRunID = try container.decodeIfPresent(String.self, forKey: .workflowRunID)
        self.workflowNodeID = try container.decodeIfPresent(String.self, forKey: .workflowNodeID)
        self.responseFormat = try container.decodeIfPresent(StructuredOutputRequestFormat.self, forKey: .responseFormat)
        self.toolParser = try container.decodeIfPresent(ToolParserRequestConfiguration.self, forKey: .toolParser)
        self.tools = try container.decodeIfPresent([OpenAIChatTool].self, forKey: .tools)
        self.toolChoice = try container.decodeIfPresent(OpenAIChatToolChoice.self, forKey: .toolChoice)
        self.chatTemplateKwargs = try container.decodeIfPresent(ChatTemplateRequestConfiguration.self, forKey: .chatTemplateKwargs)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(model, forKey: .model)
        try container.encode(messages, forKey: .messages)
        try container.encodeIfPresent(enableThinking, forKey: .enableThinking)
        try container.encodeIfPresent(reasoningEffort, forKey: .reasoningEffort)
        try container.encodeIfPresent(stream, forKey: .stream)
        try container.encodeIfPresent(streamOptions, forKey: .streamOptions)
        try container.encodeIfPresent(temperature, forKey: .temperature)
        try container.encodeIfPresent(topP, forKey: .topP)
        try container.encodeIfPresent(maxTokens, forKey: .maxTokens)
        try container.encodeIfPresent(maxCompletionTokens, forKey: .maxCompletionTokens)
        try container.encodeIfPresent(topK, forKey: .topK)
        try container.encodeIfPresent(minP, forKey: .minP)
        try container.encodeIfPresent(repeatPenalty, forKey: .repeatPenalty)
        try container.encodeIfPresent(presencePenalty, forKey: .presencePenalty)
        try container.encodeIfPresent(seed, forKey: .seed)
        try container.encodeIfPresent(resumeRequestID, forKey: .resumeRequestID)
        try encodeStopSequences(into: &container)
        try container.encodeIfPresent(sessionID, forKey: .sessionID)
        try container.encodeIfPresent(branchID, forKey: .branchID)
        try container.encodeIfPresent(parentRequestID, forKey: .parentRequestID)
        try container.encodeIfPresent(restoreSnapshotID, forKey: .restoreSnapshotID)
        try container.encodeIfPresent(saveBoundarySnapshot, forKey: .saveBoundarySnapshot)
        try container.encodeIfPresent(presetID, forKey: .presetID)
        try container.encodeIfPresent(workflow, forKey: .workflow)
        try container.encodeIfPresent(workflowRunID, forKey: .workflowRunID)
        try container.encodeIfPresent(workflowNodeID, forKey: .workflowNodeID)
        try container.encodeIfPresent(responseFormat, forKey: .responseFormat)
        try container.encodeIfPresent(toolParser, forKey: .toolParser)
        try container.encodeIfPresent(tools, forKey: .tools)
        try container.encodeIfPresent(toolChoice, forKey: .toolChoice)
        try container.encodeIfPresent(chatTemplateKwargs, forKey: .chatTemplateKwargs)
    }

    public var structuredOutputConfiguration: StructuredOutputConfiguration? {
        get throws {
            try responseFormat?.resolvedConfiguration()
        }
    }

    public var toolParserSelection: ToolParserSelection? {
        get throws {
            try toolParser?.resolvedSelection()
        }
    }

    public var normalizedTools: [NormalizedToolDefinition] {
        get throws {
            try (tools ?? []).compactMap { try $0.normalizedDefinition() }
        }
    }

    public var normalizedToolChoice: String? {
        toolChoice?.normalizedValue
    }

    public var chatTemplateSelection: ChatTemplateSelection? {
        chatTemplateKwargs?.resolvedSelection()
    }

    static func decodeStopSequences(
        from container: KeyedDecodingContainer<CodingKeys>
    ) throws -> [String]? {
        if let stopValue = try container.decodeIfPresent(StopSequencesValue.self, forKey: .stop) {
            let normalized = stopValue.normalized
            return normalized.isEmpty ? nil : normalized
        }
        if let stopValue = try container.decodeIfPresent(StopSequencesValue.self, forKey: .stopSequences) {
            let normalized = stopValue.normalized
            return normalized.isEmpty ? nil : normalized
        }
        return nil
    }

    static func encodeStopSequences(
        _ stopSequences: [String]?,
        into container: inout KeyedEncodingContainer<CodingKeys>
    ) throws {
        guard let stopSequences, !stopSequences.isEmpty else {
            return
        }
        if stopSequences.count == 1, let stopSequence = stopSequences.first {
            try container.encode(StopSequencesValue.single(stopSequence), forKey: .stop)
            return
        }
        try container.encode(StopSequencesValue.many(stopSequences), forKey: .stop)
    }

    private func encodeStopSequences(
        into container: inout KeyedEncodingContainer<CodingKeys>
    ) throws {
        try Self.encodeStopSequences(stopSequences, into: &container)
    }
}

public struct OpenAICompletionsRequest: Codable, Sendable {
    private typealias StopSequencesValue = OpenAIChatCompletionsRequest.StopSequencesValue

    public let model: String
    public let prompt: String
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let stream: Bool?
    public let streamOptions: OpenAIStreamOptions?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let maxCompletionTokens: UInt32?
    public let topK: UInt32?
    public let minP: Double?
    public let repeatPenalty: Double?
    public let presencePenalty: Double?
    public let seed: UInt32?
    public let stopSequences: [String]?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?
    public let responseFormat: StructuredOutputRequestFormat?
    public let toolParser: ToolParserRequestConfiguration?
    public let chatTemplateKwargs: ChatTemplateRequestConfiguration?

    enum CodingKeys: String, CodingKey {
        case model
        case prompt
        case enableThinking = "enable_thinking"
        case reasoningEffort = "reasoning_effort"
        case stream
        case streamOptions = "stream_options"
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case maxCompletionTokens = "max_completion_tokens"
        case topK = "top_k"
        case minP = "min_p"
        case repeatPenalty = "repeat_penalty"
        case presencePenalty = "presence_penalty"
        case seed
        case stop
        case stopSequences = "stop_sequences"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
        case responseFormat = "response_format"
        case toolParser = "tool_parser"
        case chatTemplateKwargs = "chat_template_kwargs"
    }

    public init(
        model: String,
        prompt: String,
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        stream: Bool? = nil,
        streamOptions: OpenAIStreamOptions? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        maxCompletionTokens: UInt32? = nil,
        topK: UInt32? = nil,
        minP: Double? = nil,
        repeatPenalty: Double? = nil,
        presencePenalty: Double? = nil,
        seed: UInt32? = nil,
        stopSequences: [String]? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil,
        responseFormat: StructuredOutputRequestFormat? = nil,
        toolParser: ToolParserRequestConfiguration? = nil,
        chatTemplateKwargs: ChatTemplateRequestConfiguration? = nil
    ) {
        self.model = model
        self.prompt = prompt
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        self.stream = stream
        self.streamOptions = streamOptions
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.maxCompletionTokens = maxCompletionTokens
        self.topK = topK
        self.minP = minP
        self.repeatPenalty = repeatPenalty
        self.presencePenalty = presencePenalty
        self.seed = seed
        self.stopSequences = stopSequences
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
        self.responseFormat = responseFormat
        self.toolParser = toolParser
        self.chatTemplateKwargs = chatTemplateKwargs
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.model = try container.decode(String.self, forKey: .model)
        self.prompt = try container.decode(String.self, forKey: .prompt)
        self.enableThinking = try container.decodeIfPresent(Bool.self, forKey: .enableThinking)
        self.reasoningEffort = try container.decodeIfPresent(String.self, forKey: .reasoningEffort)
        self.stream = try container.decodeIfPresent(Bool.self, forKey: .stream)
        self.streamOptions = try container.decodeIfPresent(OpenAIStreamOptions.self, forKey: .streamOptions)
        self.temperature = try container.decodeIfPresent(Double.self, forKey: .temperature)
        self.topP = try container.decodeIfPresent(Double.self, forKey: .topP)
        self.maxTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxTokens)
        self.maxCompletionTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxCompletionTokens)
        self.topK = try container.decodeIfPresent(UInt32.self, forKey: .topK)
        self.minP = try container.decodeIfPresent(Double.self, forKey: .minP)
        self.repeatPenalty = try container.decodeIfPresent(Double.self, forKey: .repeatPenalty)
        self.presencePenalty = try container.decodeIfPresent(Double.self, forKey: .presencePenalty)
        self.seed = try container.decodeIfPresent(UInt32.self, forKey: .seed)
        self.stopSequences = try Self.decodeStopSequences(from: container)
        self.sessionID = try container.decodeIfPresent(String.self, forKey: .sessionID)
        self.branchID = try container.decodeIfPresent(String.self, forKey: .branchID)
        self.parentRequestID = try container.decodeIfPresent(String.self, forKey: .parentRequestID)
        self.restoreSnapshotID = try container.decodeIfPresent(String.self, forKey: .restoreSnapshotID)
        self.saveBoundarySnapshot = try container.decodeIfPresent(Bool.self, forKey: .saveBoundarySnapshot)
        self.presetID = try container.decodeIfPresent(String.self, forKey: .presetID)
        self.workflow = try container.decodeIfPresent(TextWorkflowKind.self, forKey: .workflow)
        self.workflowRunID = try container.decodeIfPresent(String.self, forKey: .workflowRunID)
        self.workflowNodeID = try container.decodeIfPresent(String.self, forKey: .workflowNodeID)
        self.responseFormat = try container.decodeIfPresent(StructuredOutputRequestFormat.self, forKey: .responseFormat)
        self.toolParser = try container.decodeIfPresent(ToolParserRequestConfiguration.self, forKey: .toolParser)
        self.chatTemplateKwargs = try container.decodeIfPresent(ChatTemplateRequestConfiguration.self, forKey: .chatTemplateKwargs)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(model, forKey: .model)
        try container.encode(prompt, forKey: .prompt)
        try container.encodeIfPresent(enableThinking, forKey: .enableThinking)
        try container.encodeIfPresent(reasoningEffort, forKey: .reasoningEffort)
        try container.encodeIfPresent(stream, forKey: .stream)
        try container.encodeIfPresent(streamOptions, forKey: .streamOptions)
        try container.encodeIfPresent(temperature, forKey: .temperature)
        try container.encodeIfPresent(topP, forKey: .topP)
        try container.encodeIfPresent(maxTokens, forKey: .maxTokens)
        try container.encodeIfPresent(maxCompletionTokens, forKey: .maxCompletionTokens)
        try container.encodeIfPresent(topK, forKey: .topK)
        try container.encodeIfPresent(minP, forKey: .minP)
        try container.encodeIfPresent(repeatPenalty, forKey: .repeatPenalty)
        try container.encodeIfPresent(presencePenalty, forKey: .presencePenalty)
        try container.encodeIfPresent(seed, forKey: .seed)
        try Self.encodeStopSequences(stopSequences, into: &container)
        try container.encodeIfPresent(sessionID, forKey: .sessionID)
        try container.encodeIfPresent(branchID, forKey: .branchID)
        try container.encodeIfPresent(parentRequestID, forKey: .parentRequestID)
        try container.encodeIfPresent(restoreSnapshotID, forKey: .restoreSnapshotID)
        try container.encodeIfPresent(saveBoundarySnapshot, forKey: .saveBoundarySnapshot)
        try container.encodeIfPresent(presetID, forKey: .presetID)
        try container.encodeIfPresent(workflow, forKey: .workflow)
        try container.encodeIfPresent(workflowRunID, forKey: .workflowRunID)
        try container.encodeIfPresent(workflowNodeID, forKey: .workflowNodeID)
        try container.encodeIfPresent(responseFormat, forKey: .responseFormat)
        try container.encodeIfPresent(toolParser, forKey: .toolParser)
        try container.encodeIfPresent(chatTemplateKwargs, forKey: .chatTemplateKwargs)
    }

    private static func decodeStopSequences(
        from container: KeyedDecodingContainer<CodingKeys>
    ) throws -> [String]? {
        if let stopValue = try container.decodeIfPresent(StopSequencesValue.self, forKey: .stop) {
            let normalized = stopValue.normalized
            return normalized.isEmpty ? nil : normalized
        }
        if let stopValue = try container.decodeIfPresent(StopSequencesValue.self, forKey: .stopSequences) {
            let normalized = stopValue.normalized
            return normalized.isEmpty ? nil : normalized
        }
        return nil
    }

    private static func encodeStopSequences(
        _ stopSequences: [String]?,
        into container: inout KeyedEncodingContainer<CodingKeys>
    ) throws {
        guard let stopSequences, !stopSequences.isEmpty else {
            return
        }
        if stopSequences.count == 1, let stopSequence = stopSequences.first {
            try container.encode(StopSequencesValue.single(stopSequence), forKey: .stop)
            return
        }
        try container.encode(StopSequencesValue.many(stopSequences), forKey: .stop)
    }

    public var structuredOutputConfiguration: StructuredOutputConfiguration? {
        get throws {
            try responseFormat?.resolvedConfiguration()
        }
    }

    public var toolParserSelection: ToolParserSelection? {
        get throws {
            try toolParser?.resolvedSelection()
        }
    }

    public var chatTemplateSelection: ChatTemplateSelection? {
        chatTemplateKwargs?.resolvedSelection()
    }
}

public struct OpenAIResponsesRequest: Codable, Sendable {
    private typealias StopSequencesValue = OpenAIChatCompletionsRequest.StopSequencesValue

    public struct TextOptions: Codable, Sendable, Equatable {
        public let format: StructuredOutputRequestFormat?

        public init(format: StructuredOutputRequestFormat? = nil) {
            self.format = format
        }
    }

    public struct Message: Codable, Sendable, Equatable {
        public let role: String
        public let name: String?
        public let content: String
        public let channel: String?
        public let recipient: String?
        public let contentType: String?

        enum CodingKeys: String, CodingKey {
            case role
            case name
            case content
            case channel
            case recipient
            case contentType = "content_type"
        }

        public init(
            role: String,
            name: String? = nil,
            content: String,
            channel: String? = nil,
            recipient: String? = nil,
            contentType: String? = nil
        ) {
            self.role = role
            self.name = name
            self.content = content
            self.channel = channel
            self.recipient = recipient
            self.contentType = contentType
        }

        public var harmonyMetadata: HarmonyMessageMetadata? {
            let metadata = HarmonyMessageMetadata(
                channel: channel,
                recipient: recipient,
                contentType: contentType
            )
            return metadata.isEmpty ? nil : metadata
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
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let instructions: String?
    public let stream: Bool?
    public let streamOptions: OpenAIStreamOptions?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let maxCompletionTokens: UInt32?
    public let topK: UInt32?
    public let minP: Double?
    public let repeatPenalty: Double?
    public let presencePenalty: Double?
    public let seed: UInt32?
    public let stopSequences: [String]?
    public let sessionID: String?
    public let branchID: String?
    public let parentRequestID: String?
    public let restoreSnapshotID: String?
    public let saveBoundarySnapshot: Bool?
    public let presetID: String?
    public let workflow: TextWorkflowKind?
    public let workflowRunID: String?
    public let workflowNodeID: String?
    public let text: TextOptions?
    public let toolParser: ToolParserRequestConfiguration?
    public let chatTemplateKwargs: ChatTemplateRequestConfiguration?

    enum CodingKeys: String, CodingKey {
        case model
        case input
        case enableThinking = "enable_thinking"
        case reasoningEffort = "reasoning_effort"
        case instructions
        case stream
        case streamOptions = "stream_options"
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case maxCompletionTokens = "max_completion_tokens"
        case topK = "top_k"
        case minP = "min_p"
        case repeatPenalty = "repeat_penalty"
        case presencePenalty = "presence_penalty"
        case seed
        case stop
        case stopSequences = "stop_sequences"
        case sessionID = "session_id"
        case branchID = "branch_id"
        case parentRequestID = "parent_request_id"
        case restoreSnapshotID = "restore_snapshot_id"
        case saveBoundarySnapshot = "save_boundary_snapshot"
        case presetID = "preset_id"
        case workflow
        case workflowRunID = "workflow_run_id"
        case workflowNodeID = "workflow_node_id"
        case text
        case toolParser = "tool_parser"
        case chatTemplateKwargs = "chat_template_kwargs"
    }

    public init(
        model: String,
        input: Input,
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        instructions: String? = nil,
        stream: Bool? = nil,
        streamOptions: OpenAIStreamOptions? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        maxCompletionTokens: UInt32? = nil,
        topK: UInt32? = nil,
        minP: Double? = nil,
        repeatPenalty: Double? = nil,
        presencePenalty: Double? = nil,
        seed: UInt32? = nil,
        stopSequences: [String]? = nil,
        sessionID: String? = nil,
        branchID: String? = nil,
        parentRequestID: String? = nil,
        restoreSnapshotID: String? = nil,
        saveBoundarySnapshot: Bool? = nil,
        presetID: String? = nil,
        workflow: TextWorkflowKind? = nil,
        workflowRunID: String? = nil,
        workflowNodeID: String? = nil,
        text: TextOptions? = nil,
        toolParser: ToolParserRequestConfiguration? = nil,
        chatTemplateKwargs: ChatTemplateRequestConfiguration? = nil
    ) {
        self.model = model
        self.input = input
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        self.instructions = instructions
        self.stream = stream
        self.streamOptions = streamOptions
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.maxCompletionTokens = maxCompletionTokens
        self.topK = topK
        self.minP = minP
        self.repeatPenalty = repeatPenalty
        self.presencePenalty = presencePenalty
        self.seed = seed
        self.stopSequences = stopSequences
        self.sessionID = sessionID
        self.branchID = branchID
        self.parentRequestID = parentRequestID
        self.restoreSnapshotID = restoreSnapshotID
        self.saveBoundarySnapshot = saveBoundarySnapshot
        self.presetID = presetID
        self.workflow = workflow
        self.workflowRunID = workflowRunID
        self.workflowNodeID = workflowNodeID
        self.text = text
        self.toolParser = toolParser
        self.chatTemplateKwargs = chatTemplateKwargs
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.model = try container.decode(String.self, forKey: .model)
        self.input = try container.decode(Input.self, forKey: .input)
        self.enableThinking = try container.decodeIfPresent(Bool.self, forKey: .enableThinking)
        self.reasoningEffort = try container.decodeIfPresent(String.self, forKey: .reasoningEffort)
        self.instructions = try container.decodeIfPresent(String.self, forKey: .instructions)
        self.stream = try container.decodeIfPresent(Bool.self, forKey: .stream)
        self.streamOptions = try container.decodeIfPresent(OpenAIStreamOptions.self, forKey: .streamOptions)
        self.temperature = try container.decodeIfPresent(Double.self, forKey: .temperature)
        self.topP = try container.decodeIfPresent(Double.self, forKey: .topP)
        self.maxTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxTokens)
        self.maxCompletionTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxCompletionTokens)
        self.topK = try container.decodeIfPresent(UInt32.self, forKey: .topK)
        self.minP = try container.decodeIfPresent(Double.self, forKey: .minP)
        self.repeatPenalty = try container.decodeIfPresent(Double.self, forKey: .repeatPenalty)
        self.presencePenalty = try container.decodeIfPresent(Double.self, forKey: .presencePenalty)
        self.seed = try container.decodeIfPresent(UInt32.self, forKey: .seed)
        self.stopSequences = try Self.decodeStopSequences(from: container)
        self.sessionID = try container.decodeIfPresent(String.self, forKey: .sessionID)
        self.branchID = try container.decodeIfPresent(String.self, forKey: .branchID)
        self.parentRequestID = try container.decodeIfPresent(String.self, forKey: .parentRequestID)
        self.restoreSnapshotID = try container.decodeIfPresent(String.self, forKey: .restoreSnapshotID)
        self.saveBoundarySnapshot = try container.decodeIfPresent(Bool.self, forKey: .saveBoundarySnapshot)
        self.presetID = try container.decodeIfPresent(String.self, forKey: .presetID)
        self.workflow = try container.decodeIfPresent(TextWorkflowKind.self, forKey: .workflow)
        self.workflowRunID = try container.decodeIfPresent(String.self, forKey: .workflowRunID)
        self.workflowNodeID = try container.decodeIfPresent(String.self, forKey: .workflowNodeID)
        self.text = try container.decodeIfPresent(TextOptions.self, forKey: .text)
        self.toolParser = try container.decodeIfPresent(ToolParserRequestConfiguration.self, forKey: .toolParser)
        self.chatTemplateKwargs = try container.decodeIfPresent(ChatTemplateRequestConfiguration.self, forKey: .chatTemplateKwargs)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(model, forKey: .model)
        try container.encode(input, forKey: .input)
        try container.encodeIfPresent(enableThinking, forKey: .enableThinking)
        try container.encodeIfPresent(reasoningEffort, forKey: .reasoningEffort)
        try container.encodeIfPresent(instructions, forKey: .instructions)
        try container.encodeIfPresent(stream, forKey: .stream)
        try container.encodeIfPresent(streamOptions, forKey: .streamOptions)
        try container.encodeIfPresent(temperature, forKey: .temperature)
        try container.encodeIfPresent(topP, forKey: .topP)
        try container.encodeIfPresent(maxTokens, forKey: .maxTokens)
        try container.encodeIfPresent(maxCompletionTokens, forKey: .maxCompletionTokens)
        try container.encodeIfPresent(topK, forKey: .topK)
        try container.encodeIfPresent(minP, forKey: .minP)
        try container.encodeIfPresent(repeatPenalty, forKey: .repeatPenalty)
        try container.encodeIfPresent(presencePenalty, forKey: .presencePenalty)
        try container.encodeIfPresent(seed, forKey: .seed)
        try Self.encodeStopSequences(stopSequences, into: &container)
        try container.encodeIfPresent(sessionID, forKey: .sessionID)
        try container.encodeIfPresent(branchID, forKey: .branchID)
        try container.encodeIfPresent(parentRequestID, forKey: .parentRequestID)
        try container.encodeIfPresent(restoreSnapshotID, forKey: .restoreSnapshotID)
        try container.encodeIfPresent(saveBoundarySnapshot, forKey: .saveBoundarySnapshot)
        try container.encodeIfPresent(presetID, forKey: .presetID)
        try container.encodeIfPresent(workflow, forKey: .workflow)
        try container.encodeIfPresent(workflowRunID, forKey: .workflowRunID)
        try container.encodeIfPresent(workflowNodeID, forKey: .workflowNodeID)
        try container.encodeIfPresent(text, forKey: .text)
        try container.encodeIfPresent(toolParser, forKey: .toolParser)
        try container.encodeIfPresent(chatTemplateKwargs, forKey: .chatTemplateKwargs)
    }

    private static func decodeStopSequences(
        from container: KeyedDecodingContainer<CodingKeys>
    ) throws -> [String]? {
        if let stopValue = try container.decodeIfPresent(StopSequencesValue.self, forKey: .stop) {
            let normalized = stopValue.normalized
            return normalized.isEmpty ? nil : normalized
        }
        if let stopValue = try container.decodeIfPresent(StopSequencesValue.self, forKey: .stopSequences) {
            let normalized = stopValue.normalized
            return normalized.isEmpty ? nil : normalized
        }
        return nil
    }

    private static func encodeStopSequences(
        _ stopSequences: [String]?,
        into container: inout KeyedEncodingContainer<CodingKeys>
    ) throws {
        guard let stopSequences, !stopSequences.isEmpty else {
            return
        }
        if stopSequences.count == 1, let stopSequence = stopSequences.first {
            try container.encode(StopSequencesValue.single(stopSequence), forKey: .stop)
            return
        }
        try container.encode(StopSequencesValue.many(stopSequences), forKey: .stop)
    }

    public var structuredOutputConfiguration: StructuredOutputConfiguration? {
        get throws {
            try text?.format?.resolvedConfiguration()
        }
    }

    public var toolParserSelection: ToolParserSelection? {
        get throws {
            try toolParser?.resolvedSelection()
        }
    }

    public var chatTemplateSelection: ChatTemplateSelection? {
        chatTemplateKwargs?.resolvedSelection()
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
        normalizedType != "disabled"
    }

    public var normalizedType: String {
        let normalized = type
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        return normalized.isEmpty ? "enabled" : normalized
    }

    public var reasoningMode: String {
        switch normalizedType {
        case "disabled":
            "off"
        case "adaptive":
            "adaptive"
        default:
            "enabled"
        }
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
        public let name: String?
        private let rawContent: MelixMessagesContentValue

        enum CodingKeys: String, CodingKey {
            case role
            case name
            case content
        }

        public init(role: String, name: String? = nil, content: String) {
            self.role = role
            self.name = name
            self.rawContent = .text(content)
        }

        public init(role: String, name: String? = nil, contentBlocks: [MelixMessagesContentBlock]) {
            self.role = role
            self.name = name
            self.rawContent = .blocks(contentBlocks)
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.role = try container.decode(String.self, forKey: .role)
            self.name = try container.decodeIfPresent(String.self, forKey: .name)
            self.rawContent = try container.decode(MelixMessagesContentValue.self, forKey: .content)
        }

        public func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(role, forKey: .role)
            try container.encodeIfPresent(name, forKey: .name)
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
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    private let rawSystem: MelixMessagesContentValue?
    public let stream: Bool?
    public let streamOptions: OpenAIStreamOptions?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let maxCompletionTokens: UInt32?
    public let topK: UInt32?
    public let minP: Double?
    public let repeatPenalty: Double?
    public let presencePenalty: Double?
    public let seed: UInt32?
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
    public let responseFormat: StructuredOutputRequestFormat?
    public let toolParser: ToolParserRequestConfiguration?
    public let chatTemplateKwargs: ChatTemplateRequestConfiguration?

    enum CodingKeys: String, CodingKey {
        case model
        case messages
        case enableThinking = "enable_thinking"
        case reasoningEffort = "reasoning_effort"
        case system
        case stream
        case streamOptions = "stream_options"
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case maxCompletionTokens = "max_completion_tokens"
        case topK = "top_k"
        case minP = "min_p"
        case repeatPenalty = "repeat_penalty"
        case presencePenalty = "presence_penalty"
        case seed
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
        case responseFormat = "response_format"
        case toolParser = "tool_parser"
        case chatTemplateKwargs = "chat_template_kwargs"
    }

    public init(
        model: String,
        messages: [Message],
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        system: String? = nil,
        systemBlocks: [MelixMessagesContentBlock]? = nil,
        stream: Bool? = nil,
        streamOptions: OpenAIStreamOptions? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        maxCompletionTokens: UInt32? = nil,
        topK: UInt32? = nil,
        minP: Double? = nil,
        repeatPenalty: Double? = nil,
        presencePenalty: Double? = nil,
        seed: UInt32? = nil,
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
        workflowNodeID: String? = nil,
        responseFormat: StructuredOutputRequestFormat? = nil,
        toolParser: ToolParserRequestConfiguration? = nil,
        chatTemplateKwargs: ChatTemplateRequestConfiguration? = nil
    ) {
        self.model = model
        self.messages = messages
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        if let systemBlocks {
            self.rawSystem = .blocks(systemBlocks)
        } else if let system {
            self.rawSystem = .text(system)
        } else {
            self.rawSystem = nil
        }
        self.stream = stream
        self.streamOptions = streamOptions
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.maxCompletionTokens = maxCompletionTokens
        self.topK = topK
        self.minP = minP
        self.repeatPenalty = repeatPenalty
        self.presencePenalty = presencePenalty
        self.seed = seed
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
        self.responseFormat = responseFormat
        self.toolParser = toolParser
        self.chatTemplateKwargs = chatTemplateKwargs
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.model = try container.decode(String.self, forKey: .model)
        self.messages = try container.decode([Message].self, forKey: .messages)
        self.enableThinking = try container.decodeIfPresent(Bool.self, forKey: .enableThinking)
        self.reasoningEffort = try container.decodeIfPresent(String.self, forKey: .reasoningEffort)
        self.rawSystem = try container.decodeIfPresent(MelixMessagesContentValue.self, forKey: .system)
        self.stream = try container.decodeIfPresent(Bool.self, forKey: .stream)
        self.streamOptions = try container.decodeIfPresent(OpenAIStreamOptions.self, forKey: .streamOptions)
        self.temperature = try container.decodeIfPresent(Double.self, forKey: .temperature)
        self.topP = try container.decodeIfPresent(Double.self, forKey: .topP)
        self.maxTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxTokens)
        self.maxCompletionTokens = try container.decodeIfPresent(UInt32.self, forKey: .maxCompletionTokens)
        self.topK = try container.decodeIfPresent(UInt32.self, forKey: .topK)
        self.minP = try container.decodeIfPresent(Double.self, forKey: .minP)
        self.repeatPenalty = try container.decodeIfPresent(Double.self, forKey: .repeatPenalty)
        self.presencePenalty = try container.decodeIfPresent(Double.self, forKey: .presencePenalty)
        self.seed = try container.decodeIfPresent(UInt32.self, forKey: .seed)
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
        self.responseFormat = try container.decodeIfPresent(StructuredOutputRequestFormat.self, forKey: .responseFormat)
        self.toolParser = try container.decodeIfPresent(ToolParserRequestConfiguration.self, forKey: .toolParser)
        self.chatTemplateKwargs = try container.decodeIfPresent(ChatTemplateRequestConfiguration.self, forKey: .chatTemplateKwargs)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(model, forKey: .model)
        try container.encode(messages, forKey: .messages)
        try container.encodeIfPresent(enableThinking, forKey: .enableThinking)
        try container.encodeIfPresent(reasoningEffort, forKey: .reasoningEffort)
        try container.encodeIfPresent(rawSystem, forKey: .system)
        try container.encodeIfPresent(stream, forKey: .stream)
        try container.encodeIfPresent(streamOptions, forKey: .streamOptions)
        try container.encodeIfPresent(temperature, forKey: .temperature)
        try container.encodeIfPresent(topP, forKey: .topP)
        try container.encodeIfPresent(maxTokens, forKey: .maxTokens)
        try container.encodeIfPresent(maxCompletionTokens, forKey: .maxCompletionTokens)
        try container.encodeIfPresent(topK, forKey: .topK)
        try container.encodeIfPresent(minP, forKey: .minP)
        try container.encodeIfPresent(repeatPenalty, forKey: .repeatPenalty)
        try container.encodeIfPresent(presencePenalty, forKey: .presencePenalty)
        try container.encodeIfPresent(seed, forKey: .seed)
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
        try container.encodeIfPresent(responseFormat, forKey: .responseFormat)
        try container.encodeIfPresent(toolParser, forKey: .toolParser)
        try container.encodeIfPresent(chatTemplateKwargs, forKey: .chatTemplateKwargs)
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

    public var structuredOutputConfiguration: StructuredOutputConfiguration? {
        get throws {
            try responseFormat?.resolvedConfiguration()
        }
    }

    public var toolParserSelection: ToolParserSelection? {
        get throws {
            try toolParser?.resolvedSelection()
        }
    }

    public var chatTemplateSelection: ChatTemplateSelection? {
        chatTemplateKwargs?.resolvedSelection()
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
    ) throws -> NormalizedTextRequest {
        makeNormalizedRequest(
            endpoint: .chatCompletions,
            model: request.model,
            messages: request.messages.map {
                NormalizedTextMessage(role: $0.role, name: $0.name, content: $0.content)
            },
            stream: request.stream,
            includeUsage: request.streamOptions?.includeUsage,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            maxCompletionTokens: request.maxCompletionTokens,
            topK: request.topK,
            minP: request.minP,
            repeatPenalty: request.repeatPenalty,
            presencePenalty: request.presencePenalty,
            seed: request.seed,
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
            enableThinking: request.enableThinking,
            reasoningEffort: request.reasoningEffort,
            structuredOutput: try request.structuredOutputConfiguration,
            toolParser: try request.toolParserSelection,
            tools: try request.normalizedTools,
            toolChoice: request.normalizedToolChoice,
            chatTemplate: request.chatTemplateSelection
        )
    }

    public func normalizeMultimodalChat(
        _ request: OpenAIChatCompletionsRequest
    ) throws -> NormalizedTextRequest {
        let normalizer = MultimodalRequestNormalizer()
        let messages = try request.messages.map { message in
            if let contentParts = message.contentParts {
                let normalized = try normalizer.normalize(
                    OpenAIMultimodalMessage(role: message.role, name: message.name, content: contentParts)
                )
                return NormalizedTextMessage(role: normalized.role, name: normalized.name, parts: Array(normalized.parts))
            }
            return NormalizedTextMessage(role: message.role, name: message.name, content: message.content)
        }

        return makeNormalizedRequest(
            endpoint: .chatCompletions,
            model: request.model,
            messages: messages,
            stream: request.stream,
            includeUsage: request.streamOptions?.includeUsage,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            maxCompletionTokens: request.maxCompletionTokens,
            topK: request.topK,
            minP: request.minP,
            repeatPenalty: request.repeatPenalty,
            presencePenalty: request.presencePenalty,
            seed: request.seed,
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
            enableThinking: request.enableThinking,
            reasoningEffort: request.reasoningEffort,
            structuredOutput: try request.structuredOutputConfiguration,
            toolParser: try request.toolParserSelection,
            tools: try request.normalizedTools,
            toolChoice: request.normalizedToolChoice,
            chatTemplate: request.chatTemplateSelection
        )
    }

    public func normalize(
        _ request: OpenAICompletionsRequest
    ) throws -> NormalizedTextRequest {
        makeNormalizedRequest(
            endpoint: .completions,
            model: request.model,
            messages: [
                NormalizedTextMessage(role: "user", content: request.prompt),
            ],
            stream: request.stream,
            includeUsage: request.streamOptions?.includeUsage,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            maxCompletionTokens: request.maxCompletionTokens,
            topK: request.topK,
            minP: request.minP,
            repeatPenalty: request.repeatPenalty,
            presencePenalty: request.presencePenalty,
            seed: request.seed,
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
            enableThinking: request.enableThinking,
            reasoningEffort: request.reasoningEffort,
            structuredOutput: try request.structuredOutputConfiguration,
            toolParser: try request.toolParserSelection,
            chatTemplate: request.chatTemplateSelection
        )
    }

    public func normalize(
        _ request: OpenAIResponsesRequest
    ) throws -> NormalizedTextRequest {
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
                    NormalizedTextMessage(
                        role: $0.role,
                        name: $0.name,
                        content: $0.content,
                        harmonyMetadata: $0.harmonyMetadata
                    )
                }
            )
        }

        return makeNormalizedRequest(
            endpoint: .responses,
            model: request.model,
            messages: messages,
            stream: request.stream,
            includeUsage: request.streamOptions?.includeUsage,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            maxCompletionTokens: request.maxCompletionTokens,
            topK: request.topK,
            minP: request.minP,
            repeatPenalty: request.repeatPenalty,
            presencePenalty: request.presencePenalty,
            seed: request.seed,
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
            enableThinking: request.enableThinking,
            reasoningEffort: request.reasoningEffort,
            structuredOutput: try request.structuredOutputConfiguration,
            toolParser: try request.toolParserSelection,
            chatTemplate: request.chatTemplateSelection
        )
    }

    public func normalize(
        _ request: MelixMessagesRequest
    ) throws -> NormalizedTextRequest {
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
                    return NormalizedTextMessage(role: message.role, name: message.name, parts: messageParts(from: contentBlocks))
                }
                return NormalizedTextMessage(role: message.role, name: message.name, content: message.content)
            }
        )

        return makeNormalizedRequest(
            endpoint: .messages,
            model: request.model,
            messages: messages,
            stream: request.stream,
            includeUsage: request.streamOptions?.includeUsage,
            temperature: request.temperature,
            topP: request.topP,
            maxTokens: request.maxTokens,
            maxCompletionTokens: request.maxCompletionTokens,
            topK: request.topK,
            minP: request.minP,
            repeatPenalty: request.repeatPenalty,
            presencePenalty: request.presencePenalty,
            seed: request.seed,
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
            enableThinking: request.enableThinking,
            reasoningEffort: request.reasoningEffort,
            thinking: request.thinking,
            structuredOutput: try request.structuredOutputConfiguration,
            toolParser: try request.toolParserSelection,
            chatTemplate: request.chatTemplateSelection
        )
    }

    private func makeNormalizedRequest(
        endpoint: TextEndpointKind,
        model: String,
        messages: [NormalizedTextMessage],
        stream: Bool?,
        includeUsage: Bool? = nil,
        temperature: Double?,
        topP: Double?,
        maxTokens: UInt32?,
        maxCompletionTokens: UInt32? = nil,
        topK: UInt32? = nil,
        minP: Double? = nil,
        repeatPenalty: Double? = nil,
        presencePenalty: Double? = nil,
        seed: UInt32? = nil,
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
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        thinking: MelixMessagesThinkingConfig? = nil,
        structuredOutput: StructuredOutputConfiguration? = nil,
        toolParser: ToolParserSelection? = nil,
        tools: [NormalizedToolDefinition] = [],
        toolChoice: String? = nil,
        chatTemplate: ChatTemplateSelection? = nil
    ) -> NormalizedTextRequest {
        NormalizedTextRequest(
            endpoint: endpoint,
            model: model,
            messages: messages,
            stream: stream ?? (endpoint != .chatCompletions),
            includeUsage: includeUsage ?? false,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            maxCompletionTokens: maxCompletionTokens,
            topK: topK,
            minP: minP,
            repeatPenalty: repeatPenalty,
            presencePenalty: presencePenalty,
            seed: seed,
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
            enableThinking: enableThinking,
            reasoningEffort: reasoningEffort,
            thinking: thinking,
            structuredOutput: structuredOutput,
            toolParser: toolParser,
            tools: tools,
            toolChoice: toolChoice,
            chatTemplate: chatTemplate
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
        try translate(try normalize(request), modelHandle: modelHandle, modelToolParser: nil)
    }

    public func translate(
        _ request: OpenAICompletionsRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(try normalize(request), modelHandle: modelHandle, modelToolParser: nil)
    }

    public func translate(
        _ request: OpenAIResponsesRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(try normalize(request), modelHandle: modelHandle, modelToolParser: nil)
    }

    public func translate(
        _ request: MelixMessagesRequest,
        modelHandle: String
    ) throws -> TranslatedChatRequest {
        try translate(try normalize(request), modelHandle: modelHandle, modelToolParser: nil)
    }

    public func translate(
        _ normalizedRequest: NormalizedTextRequest,
        modelHandle: String,
        modelToolParser: ToolParserSelection? = nil,
        modelChatTemplatePolicy: ModelChatTemplatePolicy? = nil,
        modelOCRPolicy: OCRExecutionPolicy? = nil,
        modelSamplingPolicy: ModelSamplingPolicy? = nil,
        gatewayServingDefaults: GatewayServingDefaultsPolicy? = nil,
        mcpToolCatalog: MCPToolCatalog = .empty
    ) throws -> TranslatedChatRequest {
        let requestID = requestIDGenerator()
        let shapedRequest = requestShaper.shape(
            normalizedRequest,
            modelToolParser: modelToolParser,
            modelChatTemplatePolicy: modelChatTemplatePolicy,
            modelOCRPolicy: modelOCRPolicy,
            modelSamplingPolicy: modelSamplingPolicy,
            gatewayServingDefaults: gatewayServingDefaults,
            mcpToolCatalog: mcpToolCatalog
        )

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
        generateRequest.execution.ext["melix.reasoning.mode"] = shapedRequest.reasoningMode
        generateRequest.execution.ext["melix.reasoning.source"] = shapedRequest.reasoningSource
        generateRequest.execution.ext["melix.reasoning.mode_source"] = shapedRequest.reasoningSource
        if let reasoningEffort = shapedRequest.reasoningEffort {
            generateRequest.execution.ext["melix.reasoning.effort"] = reasoningEffort
        }
        if let autoDetectFamily = shapedRequest.reasoningAutoDetectModelFamily {
            generateRequest.execution.ext["melix.reasoning.auto_detect_model_family"] = autoDetectFamily
        }
        generateRequest.execution.ext["melix.reasoning.continuity_rehydrated"] =
            shapedRequest.reasoningContinuityRehydrated ? "true" : "false"
        generateRequest.execution.ext["melix.reasoning.history_strip_count"] =
            String(shapedRequest.reasoningHistoryStripCount)
        generateRequest.execution.ext["melix.tool_call_history_strip_count"] =
            String(shapedRequest.rawToolCallHistoryStripCount)
        generateRequest.execution.reasoning = Melix_Worker_V1_ReasoningConfig()
        generateRequest.execution.reasoning.mode = shapedRequest.reasoningMode
        generateRequest.execution.reasoning.modeSource = shapedRequest.reasoningSource
        generateRequest.execution.reasoning.effort = shapedRequest.reasoningEffort ?? ""
        generateRequest.execution.reasoning.autoDetectModelFamily =
            shapedRequest.reasoningAutoDetectModelFamily ?? ""
        generateRequest.execution.reasoning.continuityRehydrated = shapedRequest.reasoningContinuityRehydrated
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
        if let structuredOutput = shapedRequest.structuredOutput, structuredOutput.isEnabled {
            generateRequest.execution.ext["melix.structured_output.mode"] = structuredOutput.mode.rawValue
            generateRequest.execution.acceleration.prefillHint = structuredOutput.prefillHint
            if let schemaName = structuredOutput.schemaName {
                generateRequest.execution.ext["melix.structured_output.schema_name"] = schemaName
            }
            if let schemaJSONString = structuredOutput.schemaJSONString {
                generateRequest.execution.ext["melix.structured_output.schema_json"] = schemaJSONString
            }
            if structuredOutput.mode == .jsonSchema {
                generateRequest.execution.ext["melix.structured_output.strict"] = structuredOutput.strict ? "true" : "false"
            }
        }
        if let toolParser = shapedRequest.toolParser, toolParser.isExplicit {
            generateRequest.execution.ext["melix.tool_parser.mode"] = toolParser.mode.rawValue
            generateRequest.execution.ext["melix.tool_parser.source"] = toolParser.source
            if !toolParser.namespaces.isEmpty {
                generateRequest.execution.ext["melix.tool_parser.namespaces"] = toolParser.namespaces.joined(separator: ",")
            }
            if let fallbackMode = toolParser.fallbackMode {
                generateRequest.execution.ext["melix.tool_parser.fallback_mode"] = fallbackMode.rawValue
            }
            if !toolParser.mcpSourceIDs.isEmpty {
                generateRequest.execution.ext["melix.mcp.source_ids"] = toolParser.mcpSourceIDs.joined(separator: ",")
            }
        }
        if !shapedRequest.tools.isEmpty {
            generateRequest.execution.toolConfig = Self.workerToolConfig(
                tools: shapedRequest.tools,
                toolChoice: shapedRequest.toolChoice,
                toolParser: shapedRequest.toolParser
            )
            generateRequest.execution.ext["melix.tool_config.source"] = "openai_chat_tools"
            generateRequest.execution.ext["melix.tool_config.tool_count"] = String(shapedRequest.tools.count)
        }
        if let toolParserSuppressedReason = shapedRequest.toolParserSuppressedReason {
            generateRequest.execution.ext["melix.tool_parser.suppressed_reason"] = toolParserSuppressedReason
        }
        if let chatTemplate = shapedRequest.chatTemplate,
           let effectiveJSONString = chatTemplate.effectiveJSONString {
            generateRequest.execution.ext["melix.chat_template_kwargs.source"] = chatTemplate.source
            generateRequest.execution.ext["melix.chat_template_kwargs.effective_json"] = effectiveJSONString
            if let modelJSONString = chatTemplate.modelJSONString {
                generateRequest.execution.ext["melix.chat_template_kwargs.model_json"] = modelJSONString
            }
            if let requestJSONString = chatTemplate.requestJSONString {
                generateRequest.execution.ext["melix.chat_template_kwargs.request_json"] = requestJSONString
            }
            if let forcedJSONString = chatTemplate.forcedJSONString {
                generateRequest.execution.ext["melix.chat_template_kwargs.forced_json"] = forcedJSONString
            }
            if !chatTemplate.forcedKeys.isEmpty {
                generateRequest.execution.ext["melix.chat_template_kwargs.forced_keys"] = chatTemplate.forcedKeys.joined(separator: ",")
            }
        }
        if let ocrPolicy = shapedRequest.ocrPolicy {
            generateRequest.execution.ext["melix.ocr.prompt_profile_id"] = ocrPolicy.promptProfileID
            generateRequest.execution.ext["melix.ocr.prompt_template"] = ocrPolicy.promptTemplate
            generateRequest.execution.ext["melix.ocr.auto_prompt"] = ocrPolicy.autoPrompt
            generateRequest.execution.ext["melix.ocr.prompt_source"] = ocrPolicy.promptSource
            generateRequest.execution.ext["melix.ocr.sampling_profile_id"] = ocrPolicy.samplingProfileID
            generateRequest.execution.ext["melix.ocr.sampling_source"] = ocrPolicy.samplingSource
            if !ocrPolicy.stopSequences.isEmpty {
                generateRequest.execution.ext["melix.ocr.stop_sequences"] = ocrPolicy.stopSequences.joined(separator: ",")
            }
        }
        if let partialMode = shapedRequest.partialMode {
            generateRequest.execution.ext["melix.partial_mode"] = partialMode
        }
        if let assistantPrefill = shapedRequest.assistantPrefill {
            generateRequest.execution.ext["melix.assistant_prefill"] = "true"
            generateRequest.execution.ext["melix.assistant_prefill.message_index"] = String(assistantPrefill.messageIndex)
            if let messageName = assistantPrefill.messageName {
                generateRequest.execution.ext["melix.assistant_prefill.name"] = messageName
            }
        }
        var hasHarmonyMetadata = false
        for (index, message) in shapedRequest.messages.enumerated() {
            guard let harmonyMetadata = message.harmonyMetadata else {
                continue
            }
            hasHarmonyMetadata = true
            generateRequest.execution.ext["melix.harmony.message.\(index).role"] = message.role
            if let channel = harmonyMetadata.channel {
                generateRequest.execution.ext["melix.harmony.message.\(index).channel"] = channel
            }
            if let recipient = harmonyMetadata.recipient {
                generateRequest.execution.ext["melix.harmony.message.\(index).recipient"] = recipient
            }
            if let contentType = harmonyMetadata.contentType {
                generateRequest.execution.ext["melix.harmony.message.\(index).content_type"] = contentType
            }
        }
        if hasHarmonyMetadata {
            generateRequest.execution.ext["melix.harmony"] = "true"
        }
        if let thinking = shapedRequest.thinking, thinking.isEnabled {
            generateRequest.execution.reasoning.enabled = true
            generateRequest.execution.reasoning.separateStream = true
            generateRequest.execution.ext["melix.messages.thinking.type"] = thinking.normalizedType
            if let budgetTokens = thinking.budgetTokens {
                generateRequest.execution.ext["melix.messages.thinking.budget_tokens"] = String(budgetTokens)
                generateRequest.execution.ext["melix.reasoning.budget_tokens"] = String(budgetTokens)
                generateRequest.execution.ext["melix.reasoning.enforcement"] = "control-plane"
                generateRequest.execution.ext["melix.reasoning.overflow_behavior"] = "close_stream"
            }
        }
        generateRequest.execution.scope = Melix_Worker_V1_CacheScope()
        generateRequest.execution.scope.modelID = shapedRequest.model
        generateRequest.execution.scope.parserMode = shapedRequest.toolParser?.mode.rawValue ?? ""
        generateRequest.execution.scope.reasoningMode = shapedRequest.reasoningMode
        generateRequest.execution.scope.reasoningEffort = shapedRequest.reasoningEffort ?? ""
        generateRequest.execution.scope.toolParserMode = shapedRequest.toolParser?.mode.rawValue ?? ""
        generateRequest.execution.scope.structuredOutputMode = shapedRequest.structuredOutput?.mode.rawValue ?? ""
        let chatTemplateKwargsHash = cacheScopeHash(shapedRequest.chatTemplate?.effectiveJSONString)
        generateRequest.execution.scope.chatTemplateKwargsHash = chatTemplateKwargsHash
        generateRequest.execution.scope.reasoningContinuityPresent = shapedRequest.reasoningContinuityRehydrated
        // CacheScope is the canonical worker cache partition. The matching ext
        // keys are a compatibility mirror for older evidence/report readers.
        generateRequest.execution.ext["melix.cache.fingerprint.reasoning_mode"] = shapedRequest.reasoningMode
        generateRequest.execution.ext["melix.cache.fingerprint.reasoning_effort"] = shapedRequest.reasoningEffort ?? ""
        generateRequest.execution.ext["melix.cache.fingerprint.parser_mode"] = shapedRequest.toolParser?.mode.rawValue ?? ""
        generateRequest.execution.ext["melix.cache.fingerprint.structured_output_mode"] =
            shapedRequest.structuredOutput?.mode.rawValue ?? ""
        generateRequest.execution.ext["melix.cache.fingerprint.chat_template_kwargs"] =
            chatTemplateKwargsHash
        generateRequest.execution.ext["melix.cache.fingerprint.reasoning_continuity_present"] =
            shapedRequest.reasoningContinuityRehydrated ? "true" : "false"
        let compatibilityPolicyReceipt = TextCompatibilityPolicyReceipt(shapedRequest: shapedRequest)
        generateRequest.execution.ext.merge(
            compatibilityPolicyReceipt.extFields,
            uniquingKeysWith: { _, new in new }
        )
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
        if let topK = shapedRequest.topK {
            generateRequest.sampling.topK = topK
        }
        if let presencePenalty = shapedRequest.presencePenalty {
            generateRequest.sampling.presencePenalty = Float(presencePenalty)
        }
        if let seed = shapedRequest.seed {
            generateRequest.sampling.seed = seed
        }
        generateRequest.sampling.maxOutputTokens = shapedRequest.maxTokens
        generateRequest.sampling.stop = shapedRequest.stopSequences
        generateRequest.stream = shapedRequest.stream
        generateRequest.returnUsage = shapedRequest.includeUsage
        addGenerationReceipt(to: &generateRequest, shapedRequest: shapedRequest)
        generateRequest.execution.ext["melix.stream.include_usage"] = shapedRequest.includeUsage ? "true" : "false"
        generateRequest.execution.ext["melix.stream.interval_tokens"] = String(shapedRequest.streamIntervalTokens)
        generateRequest.execution.ext["melix.gateway.max_concurrent_requests"] = String(shapedRequest.maxConcurrentRequests)
        generateRequest.execution.ext["melix.gateway.max_concurrent_sequences"] = String(shapedRequest.maxConcurrentRequests)
        generateRequest.execution.ext["melix.gateway.concurrent_processing"] = shapedRequest.concurrentProcessingEnabled ? "true" : "false"
        generateRequest.execution.ext["melix.gateway.prefill_batch_size"] = String(shapedRequest.prefillBatchSize)
        generateRequest.execution.ext["melix.gateway.completion_batch_size"] = String(shapedRequest.completionBatchSize)
        generateRequest.execution.ext["melix.gateway.acceleration_mode"] = gatewayAccelerationModeRawValue(shapedRequest.accelerationMode)
        generateRequest.execution.ext["melix.gateway.acceleration_profile"] = shapedRequest.accelerationProfile
        generateRequest.execution.ext["melix.gateway.num_draft_tokens"] = String(shapedRequest.numDraftTokens)
        if !shapedRequest.draftModelID.isEmpty {
            generateRequest.execution.ext["melix.gateway.draft_model_id"] = shapedRequest.draftModelID
        }
        generateRequest.messages = shapedRequest.messages.map { message in
            var chatMessage = Melix_Worker_V1_ChatMessage()
            chatMessage.role = message.role
            chatMessage.name = message.name ?? ""
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

    private func addGenerationReceipt(
        to request: inout Melix_Worker_V1_GenerateRequest,
        shapedRequest: ShapedTextRequest
    ) {
        let extPrefix = "melix.generation."
        request.execution.ext["\(extPrefix)max_tokens_requested"] = stringValue(shapedRequest.requestedMaxTokens)
        request.execution.ext["\(extPrefix)max_tokens_effective"] = String(shapedRequest.maxTokens)
        request.execution.ext["\(extPrefix)max_completion_tokens_requested"] =
            stringValue(shapedRequest.requestedMaxCompletionTokens)
        request.execution.ext["\(extPrefix)max_completion_tokens_effective"] = String(shapedRequest.maxTokens)
        request.execution.ext["\(extPrefix)output_cap_source"] = shapedRequest.outputCapSource
        request.execution.ext["\(extPrefix)bounds_rejection_reason"] = ""
        request.execution.ext["\(extPrefix)stop_requested"] = stopReceiptValue(shapedRequest.requestedStopSequences)
        request.execution.ext["\(extPrefix)stop_effective"] = stopReceiptValue(shapedRequest.stopSequences)
        request.execution.ext["\(extPrefix)stop_source"] = shapedRequest.stopSource
        request.execution.ext["\(extPrefix)temperature"] = stringValue(shapedRequest.temperature)
        request.execution.ext["\(extPrefix)top_p"] = stringValue(shapedRequest.topP)
        request.execution.ext["\(extPrefix)top_k"] = stringValue(shapedRequest.topK)
        request.execution.ext["\(extPrefix)min_p"] = stringValue(shapedRequest.minP)
        request.execution.ext["\(extPrefix)repeat_penalty"] = stringValue(shapedRequest.repeatPenalty)
        request.execution.ext["\(extPrefix)presence_penalty"] = stringValue(shapedRequest.presencePenalty)
        request.execution.ext["\(extPrefix)seed"] = stringValue(shapedRequest.seed)
    }

    private func stopReceiptValue(_ stopSequences: [String]) -> String {
        if stopSequences.isEmpty {
            return ""
        }
        if stopSequences.count == 1, let stop = stopSequences.first {
            return stop
        }
        let encoded = (try? JSONSerialization.data(withJSONObject: stopSequences))
            .flatMap { String(data: $0, encoding: .utf8) }
        return encoded ?? stopSequences.joined(separator: ",")
    }

    private func stringValue<T>(_ value: T?) -> String {
        value.map { "\($0)" } ?? ""
    }

    private func stringValue(_ value: Double) -> String {
        String(format: "%g", value)
    }

    private static func workerToolConfig(
        tools: [NormalizedToolDefinition],
        toolChoice: String?,
        toolParser: ToolParserSelection?
    ) -> Melix_Worker_V1_ToolConfig {
        var config = Melix_Worker_V1_ToolConfig()
        config.schemaFormat = "openai_chat_tools"
        config.schemaVersion = "2024-06"
        config.toolsetVersion = "1"
        config.parser = toolParser?.mode.rawValue ?? ""
        config.parserContractVersion = "melix.tool-parser.v1"
        config.toolChoice = toolChoice ?? ""
        config.tools = tools.map { tool in
            var definition = Melix_Worker_V1_ToolDefinition()
            definition.name = tool.name
            definition.description_p = tool.description
            definition.jsonSchema = tool.jsonSchema
            return definition
        }
        return config
    }
}

private func gatewayAccelerationModeRawValue(
    _ mode: Melix_Controlplane_V1_AccelerationMode
) -> String {
    switch mode {
    case .speculativeDecode:
        return "speculative_decode"
    default:
        return "baseline"
    }
}
