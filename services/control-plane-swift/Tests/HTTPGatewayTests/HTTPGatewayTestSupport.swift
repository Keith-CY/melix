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
    text: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
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
    argumentsJSONFragment: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.toolCallDelta = Melix_Worker_V1_ToolCallDelta()
    event.toolCallDelta.callID = callID
    event.toolCallDelta.toolName = toolName
    event.toolCallDelta.argumentsJsonFragment = argumentsJSONFragment
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
    message: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.error = Melix_Worker_V1_ErrorEvent()
    event.error.error.code = code
    event.error.error.message = message
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
