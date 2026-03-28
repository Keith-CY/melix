import Foundation
import MelixWorkerProtocol

public enum ControlPlaneChatExecutionError: Error, Equatable {
    case unavailable
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

    public let modelID: String
    public let messages: [Message]
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?

    public init(
        modelID: String,
        messages: [Message],
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil
    ) {
        self.modelID = modelID
        self.messages = messages
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
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

    public init(
        requestID: String,
        modelID: String,
        stream: AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.stream = stream
    }
}
