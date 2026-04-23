import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Control Plane Chat Execution")
struct ControlPlaneChatExecutionTests {
    @Test("chat request preserves optional tuning fields")
    func chatRequestPreservesOptionalTuningFields() {
        let request = ControlPlaneChatRequest(
            modelID: "melix-dev-text",
            messages: [
                .init(role: "user", content: "Hello"),
                .init(role: "assistant", content: "World"),
            ],
            resumeRequestID: "req-resume-42",
            temperature: 0.2,
            topP: 0.8,
            maxTokens: 256
        )

        #expect(request.modelID == "melix-dev-text")
        #expect(request.messages == [
            .init(role: "user", content: "Hello"),
            .init(role: "assistant", content: "World"),
        ])
        #expect(request.resumeRequestID == "req-resume-42")
        #expect(request.temperature == 0.2)
        #expect(request.topP == 0.8)
        #expect(request.maxTokens == 256)
    }

    @Test("chat execution errors preserve user-facing diagnostics")
    func chatExecutionErrorsPreserveUserFacingDiagnostics() {
        #expect(String(describing: ControlPlaneChatExecutionError.unavailable) == "unavailable")
        #expect(
            String(describing: ControlPlaneChatExecutionError.unavailableReason("chat_unavailable: lazy text load failed")) ==
                "chat_unavailable: lazy text load failed"
        )
        #expect(String(describing: ControlPlaneChatExecutionError.unavailableReason("  ")) == "unavailable")
    }

    @Test("execute-event mapping covers all supported chat payloads")
    func executeEventMappingCoversAllSupportedChatPayloads() {
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeQueuedExecuteEvent()) ==
                .queued(lane: "text.decode.interactive", queuePosition: 2, backpressure: 0.25)
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeAdmittedExecuteEvent()) ==
                .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 4.5)
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makePrefillStartedExecuteEvent()) ==
                .prefillStarted(inputTokens: 128)
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeDecodeStartedExecuteEvent()) ==
                .decodeStarted(decodeHandle: "decode-42", maxOutputTokens: 256)
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeTokenExecuteEvent()) ==
                .tokenDelta("Assistant")
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeReasoningExecuteEvent()) ==
                .reasoningDelta("Reasoning")
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeToolExecuteEvent()) ==
                .toolCallDelta(
                    callID: "tool-1",
                    toolName: "search",
                    argumentsFragment: #"{"q":"melix"}"#
                )
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeUsageExecuteEvent()) ==
                .usage(promptTokens: 21, completionTokens: 34)
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeCompletedExecuteEvent()) ==
                .completed(finishReason: "stop", assistantText: "Assistant", reasoningText: "Reasoning")
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeErrorExecuteEvent()) ==
                .failed(code: "runtime_error", message: "worker failed")
        )
        #expect(
            ControlPlaneChatStreamEvent(executeEvent: makeHeartbeatExecuteEvent()) ==
                .heartbeat
        )
    }

    @Test("unsupported execute-event payloads are ignored")
    func unsupportedExecuteEventPayloadsAreIgnored() {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.seq = 7

        #expect(ControlPlaneChatStreamEvent(executeEvent: event) == nil)
    }

    @Test("chat execution preserves stream identity and payloads")
    func chatExecutionPreservesStreamIdentityAndPayloads() async throws {
        let execution = ControlPlaneChatExecution(
            requestID: "chat-request-42",
            modelID: "melix-dev-text",
            stream: AsyncThrowingStream { continuation in
                continuation.yield(.queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0))
                continuation.yield(.completed(finishReason: "stop", assistantText: "Assistant", reasoningText: "Reasoning"))
                continuation.finish()
            }
        )

        var observed: [ControlPlaneChatStreamEvent] = []
        for try await event in execution.stream {
            observed.append(event)
        }

        #expect(execution.requestID == "chat-request-42")
        #expect(execution.modelID == "melix-dev-text")
        #expect(observed == [
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .completed(finishReason: "stop", assistantText: "Assistant", reasoningText: "Reasoning"),
        ])
    }

    @Test("chat execution can surface lifecycle events alongside stream payloads")
    func chatExecutionCanSurfaceLifecycleEventsAlongsideStreamPayloads() async throws {
        let execution = ControlPlaneChatExecution(
            requestID: "chat-request-lifecycle",
            modelID: "melix-dev-text",
            stream: AsyncThrowingStream { continuation in
                continuation.finish()
            },
            lifecycle: AsyncStream { continuation in
                continuation.yield(.active)
                continuation.yield(.disconnectGraceStarted(timeoutMs: 50))
                continuation.yield(.resumed(recoveryLatencyMs: 12))
                continuation.finish()
            }
        )

        var lifecycle: [ConnectionLifecycleEvent] = []
        for await event in execution.lifecycle {
            lifecycle.append(event)
        }

        #expect(lifecycle == [
            .active,
            .disconnectGraceStarted(timeoutMs: 50),
            .resumed(recoveryLatencyMs: 12),
        ])
    }
}

private func makeQueuedExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.queued = Melix_Worker_V1_Queued()
    event.queued.lane = "text.decode.interactive"
    event.queued.queuePosition = 2
    event.queued.backpressure = 0.25
    return event
}

private func makeAdmittedExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.admitted = Melix_Worker_V1_Admitted()
    event.admitted.lane = "text.decode.interactive"
    event.admitted.workerID = "swift-text-worker"
    event.admitted.queueDelayMs = 4.5
    return event
}

private func makePrefillStartedExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.prefillStarted = Melix_Worker_V1_PrefillStarted()
    event.prefillStarted.inputTokens = 128
    return event
}

private func makeDecodeStartedExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.decodeStarted = Melix_Worker_V1_DecodeStarted()
    event.decodeStarted.decodeHandle = "decode-42"
    event.decodeStarted.maxOutputTokens = 256
    return event
}

private func makeTokenExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = "Assistant"
    return event
}

private func makeReasoningExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.reasoningDelta = Melix_Worker_V1_ReasoningDelta()
    event.reasoningDelta.text = "Reasoning"
    return event
}

private func makeToolExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.toolCallDelta = Melix_Worker_V1_ToolCallDelta()
    event.toolCallDelta.callID = "tool-1"
    event.toolCallDelta.toolName = "search"
    event.toolCallDelta.argumentsJsonFragment = #"{"q":"melix"}"#
    return event
}

private func makeUsageExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.usageDelta = Melix_Worker_V1_UsageDelta()
    event.usageDelta.promptTokens = 21
    event.usageDelta.completionTokens = 34
    return event
}

private func makeCompletedExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = "stop"
    event.completed.assistantText = "Assistant"
    event.completed.reasoningText = "Reasoning"
    return event
}

private func makeErrorExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.error = Melix_Worker_V1_ErrorEvent()
    event.error.error.code = "runtime_error"
    event.error.error.message = "worker failed"
    return event
}

private func makeHeartbeatExecuteEvent() -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.heartbeat = Melix_Worker_V1_Heartbeat()
    return event
}
