import Foundation
import MelixWorkerProtocol

public enum ControlPlaneChatExecutionError: Error, Equatable {
    case unavailable
    case unavailableReason(String)
    case requestFailed(code: String, message: String)
}

extension ControlPlaneChatExecutionError: CustomStringConvertible {
    public var description: String {
        switch self {
        case .unavailable:
            return "unavailable"
        case .unavailableReason(let reason):
            let trimmed = reason.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? "unavailable" : trimmed
        case .requestFailed(_, let message):
            let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? "unavailable" : trimmed
        }
    }
}

public struct ControlPlaneChatRequest: Sendable, Equatable {
    public struct Message: Sendable, Equatable {
        public struct ToolCall: Sendable, Equatable {
            public let callID: String
            public let type: String
            public let toolName: String
            public let argumentsJSON: String

            public init(
                callID: String,
                type: String = "function",
                toolName: String,
                argumentsJSON: String
            ) {
                self.callID = callID
                self.type = type
                self.toolName = toolName
                self.argumentsJSON = argumentsJSON
            }
        }

        public let role: String
        public let content: String
        public let name: String?
        public let toolCalls: [ToolCall]
        public let toolCallID: String?

        public init(
            role: String,
            content: String,
            name: String? = nil,
            toolCalls: [ToolCall] = [],
            toolCallID: String? = nil
        ) {
            self.role = role
            self.content = content
            self.name = name
            self.toolCalls = toolCalls
            self.toolCallID = toolCallID
        }
    }

    public struct ToolDefinition: Sendable, Equatable {
        public let name: String
        public let description: String
        public let parametersJSON: String

        public init(
            name: String,
            description: String = "",
            parametersJSON: String
        ) {
            self.name = name
            self.description = description
            self.parametersJSON = parametersJSON
        }
    }

    public struct RemoteTarget: Sendable, Equatable {
        public let serverID: String
        public let providerKind: String
        public let baseURL: String
        public let apiKey: String
        public let modelID: String
        public let timeoutSeconds: UInt32
        public let rateLimitPerMinute: UInt32

        public init(
            serverID: String,
            providerKind: String,
            baseURL: String,
            apiKey: String,
            modelID: String,
            timeoutSeconds: UInt32 = 60,
            rateLimitPerMinute: UInt32 = 0
        ) {
            self.serverID = serverID
            self.providerKind = providerKind
            self.baseURL = baseURL
            self.apiKey = apiKey
            self.modelID = modelID
            self.timeoutSeconds = timeoutSeconds
            self.rateLimitPerMinute = rateLimitPerMinute
        }
    }

    public let modelID: String
    public let serverSessionID: String
    public let messages: [Message]
    public let tools: [ToolDefinition]
    public let toolChoice: String?
    public let parallelToolCalls: Bool
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let chatTemplateKwargs: ChatTemplateRequestConfiguration?
    public let resumeRequestID: String?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let remoteTarget: RemoteTarget?

    public init(
        modelID: String,
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        messages: [Message],
        tools: [ToolDefinition] = [],
        toolChoice: String? = nil,
        parallelToolCalls: Bool = false,
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        chatTemplateKwargs: ChatTemplateRequestConfiguration? = nil,
        resumeRequestID: String? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        remoteTarget: RemoteTarget? = nil
    ) {
        self.modelID = modelID
        let normalizedServerSessionID = serverSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.serverSessionID = normalizedServerSessionID.isEmpty
            ? ServerSessionRuntimeStore.defaultServerSessionID
            : normalizedServerSessionID
        self.messages = messages
        self.tools = tools
        self.toolChoice = toolChoice
        self.parallelToolCalls = parallelToolCalls
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        self.chatTemplateKwargs = chatTemplateKwargs
        self.resumeRequestID = resumeRequestID
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.remoteTarget = remoteTarget
    }
}

public enum ControlPlaneChatCancellationDisposition: String, Sendable, Equatable {
    case accepted
    case alreadyTerminal
    case notFound
    case unavailable
}

public struct ControlPlaneChatCancellationReceipt: Sendable, Equatable {
    public let requestID: String
    public let disposition: ControlPlaneChatCancellationDisposition

    public init(
        requestID: String,
        disposition: ControlPlaneChatCancellationDisposition
    ) {
        self.requestID = requestID
        self.disposition = disposition
    }
}

actor ControlPlaneChatCancellationController {
    private enum State {
        case active
        case cancellationRequested
        case terminal
    }

    private var cancellationAction: (@Sendable () -> Void)?
    private var state: State = .active

    func install(_ action: @escaping @Sendable () -> Void) {
        switch state {
        case .active:
            cancellationAction = action
        case .cancellationRequested:
            action()
        case .terminal:
            break
        }
    }

    func cancel(requestID: String) -> ControlPlaneChatCancellationReceipt {
        switch state {
        case .active:
            break
        case .cancellationRequested:
            return ControlPlaneChatCancellationReceipt(
                requestID: requestID,
                disposition: .accepted
            )
        case .terminal:
            return ControlPlaneChatCancellationReceipt(
                requestID: requestID,
                disposition: .alreadyTerminal
            )
        }
        state = .cancellationRequested
        cancellationAction?()
        cancellationAction = nil
        return ControlPlaneChatCancellationReceipt(
            requestID: requestID,
            disposition: .accepted
        )
    }

    func markTerminal() {
        state = .terminal
        cancellationAction = nil
    }
}

public enum ControlPlaneChatStreamEvent: Sendable, Equatable {
    case queued(lane: String, queuePosition: UInt32, backpressure: Double)
    case admitted(lane: String, workerID: String, queueDelayMs: Double)
    case prefillStarted(inputTokens: UInt32)
    case decodeStarted(decodeHandle: String, maxOutputTokens: UInt32)
    case tokenDelta(String)
    case reasoningDelta(String)
    case toolCallDelta(callID: String, toolName: String, argumentsFragment: String)
    case annotationDelta(annotationID: String, kind: String, startOffset: UInt32, endOffset: UInt32, payloadJSON: String)
    case toolResultDelta(callID: String, status: String, resultJSON: String)
    case usage(
        promptTokens: UInt32,
        completionTokens: UInt32,
        cachedPromptTokens: UInt32,
        mediaFeatureCacheHits: UInt64,
        mediaFeatureCacheMisses: UInt64,
        mediaFeatureEncoderCallsSaved: UInt64,
        mediaFeatureWorkSavedBytes: UInt64
    )
    case completed(finishReason: String, assistantText: String, reasoningText: String)
    case failed(code: String, message: String)
    case heartbeat

    init?(executeEvent: Melix_Worker_V1_ExecuteEvent) {
        switch executeEvent.payload {
        case .queued(let queued):
            self = .queued(
                lane: queued.lane,
                queuePosition: queued.queuePosition,
                backpressure: queued.backpressure
            )
        case .admitted(let admitted):
            self = .admitted(
                lane: admitted.lane,
                workerID: admitted.workerID,
                queueDelayMs: admitted.queueDelayMs
            )
        case .prefillStarted(let prefillStarted):
            self = .prefillStarted(inputTokens: prefillStarted.inputTokens)
        case .decodeStarted(let decodeStarted):
            self = .decodeStarted(
                decodeHandle: decodeStarted.decodeHandle,
                maxOutputTokens: decodeStarted.maxOutputTokens
            )
        case .tokenDelta(let tokenDelta):
            self = .tokenDelta(tokenDelta.text)
        case .reasoningDelta(let reasoningDelta):
            self = .reasoningDelta(reasoningDelta.text)
        case .toolCallDelta(let toolCallDelta):
            self = .toolCallDelta(
                callID: toolCallDelta.callID,
                toolName: toolCallDelta.toolName,
                argumentsFragment: toolCallDelta.argumentsJsonFragment
            )
        case .annotationDelta(let annotationDelta):
            self = .annotationDelta(
                annotationID: annotationDelta.annotationID,
                kind: annotationDelta.kind,
                startOffset: annotationDelta.startOffset,
                endOffset: annotationDelta.endOffset,
                payloadJSON: annotationDelta.payloadJson
            )
        case .toolResultDelta(let toolResultDelta):
            self = .toolResultDelta(
                callID: toolResultDelta.callID,
                status: toolResultDelta.status,
                resultJSON: toolResultDelta.resultJson
            )
        case .usageDelta(let usageDelta):
            self = .usage(
                promptTokens: usageDelta.promptTokens,
                completionTokens: usageDelta.completionTokens,
                cachedPromptTokens: usageDelta.cachedPromptTokens,
                mediaFeatureCacheHits: usageDelta.mediaFeatureCacheHits,
                mediaFeatureCacheMisses: usageDelta.mediaFeatureCacheMisses,
                mediaFeatureEncoderCallsSaved: usageDelta.mediaFeatureEncoderCallsSaved,
                mediaFeatureWorkSavedBytes: usageDelta.mediaFeatureWorkSavedBytes
            )
        case .completed(let completed):
            self = .completed(
                finishReason: completed.finishReason,
                assistantText: completed.assistantText,
                reasoningText: completed.reasoningText
            )
        case .error(let errorEvent):
            self = .failed(
                code: errorEvent.error.code,
                message: errorEvent.error.message
            )
        case .heartbeat:
            self = .heartbeat
        default:
            return nil
        }
    }
}

public struct ControlPlaneChatExecution: Sendable {
    public let requestID: String
    public let modelID: String
    public let stream: AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>
    public let lifecycle: AsyncStream<ConnectionLifecycleEvent>
    public let cancel: @Sendable () async -> ControlPlaneChatCancellationReceipt

    public init(
        requestID: String,
        modelID: String,
        stream: AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>,
        lifecycle: AsyncStream<ConnectionLifecycleEvent> = AsyncStream { continuation in
            continuation.finish()
        },
        cancel: (@Sendable () async -> ControlPlaneChatCancellationReceipt)? = nil
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.stream = stream
        self.lifecycle = lifecycle
        self.cancel = cancel ?? {
            ControlPlaneChatCancellationReceipt(
                requestID: requestID,
                disposition: .unavailable
            )
        }
    }
}
