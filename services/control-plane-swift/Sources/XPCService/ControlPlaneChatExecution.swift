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
        public let role: String
        public let content: String

        public init(role: String, content: String) {
            self.role = role
            self.content = content
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
    public let messages: [Message]
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
        messages: [Message],
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
        self.messages = messages
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
    case usage(promptTokens: UInt32, completionTokens: UInt32)
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
                completionTokens: usageDelta.completionTokens
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

    public init(
        requestID: String,
        modelID: String,
        stream: AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>,
        lifecycle: AsyncStream<ConnectionLifecycleEvent> = AsyncStream { continuation in
            continuation.finish()
        }
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.stream = stream
        self.lifecycle = lifecycle
    }
}
