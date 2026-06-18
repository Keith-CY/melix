import Foundation
import Testing

import MelixControlPlaneProtocol
import MelixWorkerProtocol

func collectChunks(
    _ stream: AsyncThrowingStream<Data, Error>
) async throws -> String {
    var data = Data()
    for try await chunk in stream {
        data.append(chunk)
    }
    return try #require(String(data: data, encoding: .utf8))
}

func makeTokenEvent(
    requestID: String,
    seq: UInt64,
    text: String,
    tokenIDs: [UInt32] = [],
    tokenLogprobs: [Double] = []
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    event.tokenDelta.tokenIds = tokenIDs
    event.tokenDelta.tokenLogprobs = tokenLogprobs
    return event
}

func makeUsageEvent(
    requestID: String,
    seq: UInt64,
    promptTokens: UInt32,
    completionTokens: UInt32
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.usageDelta = Melix_Worker_V1_UsageDelta()
    event.usageDelta.promptTokens = promptTokens
    event.usageDelta.completionTokens = completionTokens
    return event
}

func makeReasoningEvent(
    requestID: String,
    seq: UInt64,
    text: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.reasoningDelta = Melix_Worker_V1_ReasoningDelta()
    event.reasoningDelta.text = text
    return event
}

func makeToolCallEvent(
    requestID: String,
    seq: UInt64,
    callID: String,
    toolName: String,
    argumentsJSONFragment: String,
    fragmentIndex: UInt32 = 1
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.toolCallDelta = Melix_Worker_V1_ToolCallDelta()
    event.toolCallDelta.callID = callID
    event.toolCallDelta.toolName = toolName
    event.toolCallDelta.argumentsJsonFragment = argumentsJSONFragment
    event.toolCallDelta.fragmentIndex = fragmentIndex
    return event
}

func makeAnnotationEvent(
    requestID: String,
    seq: UInt64,
    annotationID: String,
    kind: String,
    startOffset: UInt32,
    endOffset: UInt32,
    payloadJSON: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.annotationDelta = Melix_Worker_V1_AnnotationDelta()
    event.annotationDelta.annotationID = annotationID
    event.annotationDelta.kind = kind
    event.annotationDelta.startOffset = startOffset
    event.annotationDelta.endOffset = endOffset
    event.annotationDelta.payloadJson = payloadJSON
    return event
}

func makeToolResultEvent(
    requestID: String,
    seq: UInt64,
    callID: String,
    status: String,
    resultJSON: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.toolResultDelta = Melix_Worker_V1_ToolResultDelta()
    event.toolResultDelta.callID = callID
    event.toolResultDelta.status = status
    event.toolResultDelta.resultJson = resultJSON
    return event
}

func makeCompletedEvent(
    requestID: String,
    seq: UInt64,
    finishReason: String,
    assistantText: String,
    reasoningText: String = ""
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistantText
    event.completed.reasoningText = reasoningText
    return event
}

func makeHeartbeatEvent(
    requestID: String,
    seq: UInt64,
    unixMs: Int64
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.heartbeat = Melix_Worker_V1_Heartbeat()
    event.heartbeat.unixMs = unixMs
    return event
}

func makeErrorEvent(
    requestID: String,
    seq: UInt64,
    code: String,
    message: String,
    details: [String: String] = [:]
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.error = Melix_Worker_V1_ErrorEvent()
    event.error.error.code = code
    event.error.error.message = message
    event.error.error.details = details
    return event
}

func makeApplyGatewayAccessRequest(
    requestID: String = "req-server-apply-gateway-access",
    serverSessionID: String,
    mode: Melix_Controlplane_V1_GatewayAccessMode,
    sharedAccessEnabled: Bool,
    primaryKey: Melix_Controlplane_V1_GatewayAccessKeyRecord?
) -> Melix_Controlplane_V1_ControlPlaneRequest {
    var request = Melix_Controlplane_V1_ControlPlaneRequest()
    request.requestID = requestID
    request.targetID = serverSessionID
    request.commandType = "server.apply_gateway_access"
    request.server = Melix_Controlplane_V1_ServerCommand()
    request.server.applyGatewayAccess = Melix_Controlplane_V1_ApplyGatewayAccess()
    request.server.applyGatewayAccess.serverSessionID = serverSessionID
    request.server.applyGatewayAccess.mode = mode
    request.server.applyGatewayAccess.sharedAccessEnabled = sharedAccessEnabled
    if let primaryKey {
        request.server.applyGatewayAccess.primaryKey = primaryKey
    }
    return request
}

func makePrefillStartedEvent(
    requestID: String,
    seq: UInt64,
    inputTokens: UInt32
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.prefillStarted = Melix_Worker_V1_PrefillStarted()
    event.prefillStarted.inputTokens = inputTokens
    return event
}

func makePrefillProgressEvent(
    requestID: String,
    seq: UInt64,
    processedTokens: UInt32,
    totalTokens: UInt32
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.prefillProgress = Melix_Worker_V1_PrefillProgress()
    event.prefillProgress.processedTokens = processedTokens
    event.prefillProgress.totalTokens = totalTokens
    return event
}

struct SSERecord: Equatable {
    let event: String?
    let data: String
}

func parseSSERecords(_ payload: String) -> [SSERecord] {
    payload.components(separatedBy: "\n\n").compactMap { block in
        var eventName: String?
        var dataLines: [String] = []
        for line in block.split(separator: "\n", omittingEmptySubsequences: true) {
            if line.hasPrefix("event: ") {
                eventName = String(line.dropFirst("event: ".count))
            } else if line.hasPrefix("data: ") {
                dataLines.append(String(line.dropFirst("data: ".count)))
            }
        }
        guard !dataLines.isEmpty else {
            return nil
        }
        return SSERecord(event: eventName, data: dataLines.joined(separator: "\n"))
    }
}
