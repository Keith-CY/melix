import Foundation
import GRPCCore
import MelixWorkerProtocol

struct FilteredTextOutputState {
    var assistantText = ""
    var reasoningText = ""
    var eventCount = 0
    var sawFirstToken = false
}

func writeFilteredTextOutput(
    _ output: HarmonyChannelOutputFilter.Output,
    response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>,
    requestID: String,
    executionKind: String,
    seq: inout UInt64,
    state: inout FilteredTextOutputState,
    metrics: MetricsStore,
    ttftMetricName: String,
    startedAt: Date,
    decorateEvent: (inout Melix_Worker_V1_ExecuteEvent) -> Void = { _ in }
) async throws {
    if !output.reasoningText.isEmpty {
        state.reasoningText += output.reasoningText

        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = executionKind
        event.seq = seq
        seq += 1
        decorateEvent(&event)

        var payload = Melix_Worker_V1_ReasoningDelta()
        payload.text = output.reasoningText
        event.reasoningDelta = payload
        try await response.write(event)
        state.eventCount += 1
    }

    guard !output.visibleText.isEmpty else {
        return
    }

    if !state.sawFirstToken {
        state.sawFirstToken = true
        metrics.recordMilliseconds(
            ttftMetricName,
            value: filteredOutputElapsedMilliseconds(since: startedAt)
        )
    }

    state.assistantText += output.visibleText

    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = executionKind
    event.seq = seq
    seq += 1
    decorateEvent(&event)

    var payload = Melix_Worker_V1_TokenDelta()
    payload.text = output.visibleText
    event.tokenDelta = payload
    try await response.write(event)
    state.eventCount += 1
}

private func filteredOutputElapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}
