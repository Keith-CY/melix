import Foundation
import GRPCCore
import MelixWorkerProtocol

struct FilteredTextOutputState {
    var assistantText = ""
    var reasoningText = ""
    var eventCount = 0
    var sawFirstToken = false
    var pendingVisibleText = ""
    var pendingVisibleFragmentCount = 0
}

struct FilteredTextOutputWriteSummary {
    var grpcWriteTotalMicros = 0
    var grpcWriteCallCount = 0

    mutating func record(_ elapsedMicros: Int) {
        grpcWriteTotalMicros += max(1, elapsedMicros)
        grpcWriteCallCount += 1
    }

    mutating func merge(_ other: FilteredTextOutputWriteSummary) {
        grpcWriteTotalMicros += other.grpcWriteTotalMicros
        grpcWriteCallCount += other.grpcWriteCallCount
    }
}

struct FilteredTextOutputCadencePolicy: Sendable, Equatable {
    var coalesceVisibleDeltas: Bool
    var maxBufferedVisibleFragments: Int
    var maxBufferedVisibleCharacters: Int

    static let immediate = FilteredTextOutputCadencePolicy(
        coalesceVisibleDeltas: false,
        maxBufferedVisibleFragments: 1,
        maxBufferedVisibleCharacters: 0
    )

    static let gemmaDecodeDefault = FilteredTextOutputCadencePolicy(
        coalesceVisibleDeltas: true,
        maxBufferedVisibleFragments: 4,
        maxBufferedVisibleCharacters: 96
    )

    var shouldBufferVisibleDeltas: Bool {
        coalesceVisibleDeltas
            && maxBufferedVisibleFragments > 1
            && maxBufferedVisibleCharacters > 0
    }

    func shouldFlush(fragmentCount: Int, characterCount: Int) -> Bool {
        fragmentCount >= maxBufferedVisibleFragments
            || characterCount >= maxBufferedVisibleCharacters
    }
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
    cadencePolicy: FilteredTextOutputCadencePolicy = .immediate,
    decorateEvent: (inout Melix_Worker_V1_ExecuteEvent) -> Void = { _ in }
) async throws -> FilteredTextOutputWriteSummary {
    var summary = FilteredTextOutputWriteSummary()
    if !output.reasoningText.isEmpty {
        summary.merge(try await flushPendingFilteredTextOutput(
            response: response,
            requestID: requestID,
            executionKind: executionKind,
            seq: &seq,
            state: &state,
            decorateEvent: decorateEvent
        ))
        state.reasoningText += output.reasoningText

        summary.record(try await writeReasoningDelta(
            output.reasoningText,
            response: response,
            requestID: requestID,
            executionKind: executionKind,
            seq: &seq,
            decorateEvent: decorateEvent
        ))
        state.eventCount += 1
    }

    guard !output.visibleText.isEmpty else {
        return summary
    }

    let isFirstVisibleToken = !state.sawFirstToken
    if isFirstVisibleToken {
        state.sawFirstToken = true
        metrics.recordMilliseconds(
            ttftMetricName,
            value: filteredOutputElapsedMilliseconds(since: startedAt)
        )
    }

    state.assistantText += output.visibleText
    if cadencePolicy.shouldBufferVisibleDeltas, !isFirstVisibleToken {
        state.pendingVisibleText += output.visibleText
        state.pendingVisibleFragmentCount += 1
        if cadencePolicy.shouldFlush(
            fragmentCount: state.pendingVisibleFragmentCount,
            characterCount: state.pendingVisibleText.count
        ) {
            summary.merge(try await flushPendingFilteredTextOutput(
                response: response,
                requestID: requestID,
                executionKind: executionKind,
                seq: &seq,
                state: &state,
                decorateEvent: decorateEvent
            ))
        }
        return summary
    }

    summary.record(try await writeVisibleTextDelta(
        output.visibleText,
        response: response,
        requestID: requestID,
        executionKind: executionKind,
        seq: &seq,
        decorateEvent: decorateEvent
    ))
    state.eventCount += 1
    return summary
}

func flushPendingFilteredTextOutput(
    response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>,
    requestID: String,
    executionKind: String,
    seq: inout UInt64,
    state: inout FilteredTextOutputState,
    decorateEvent: (inout Melix_Worker_V1_ExecuteEvent) -> Void = { _ in }
) async throws -> FilteredTextOutputWriteSummary {
    var summary = FilteredTextOutputWriteSummary()
    guard !state.pendingVisibleText.isEmpty else {
        return summary
    }
    let text = state.pendingVisibleText
    state.pendingVisibleText.removeAll(keepingCapacity: true)
    state.pendingVisibleFragmentCount = 0
    summary.record(try await writeVisibleTextDelta(
        text,
        response: response,
        requestID: requestID,
        executionKind: executionKind,
        seq: &seq,
        decorateEvent: decorateEvent
    ))
    state.eventCount += 1
    return summary
}

private func writeReasoningDelta(
    _ text: String,
    response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>,
    requestID: String,
    executionKind: String,
    seq: inout UInt64,
    decorateEvent: (inout Melix_Worker_V1_ExecuteEvent) -> Void
) async throws -> Int {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = executionKind
    event.seq = seq
    seq += 1
    decorateEvent(&event)

    var payload = Melix_Worker_V1_ReasoningDelta()
    payload.text = text
    event.reasoningDelta = payload
    let writeStartedAt = Date()
    try await response.write(event)
    return filteredOutputElapsedMicros(since: writeStartedAt)
}

private func writeVisibleTextDelta(
    _ text: String,
    response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>,
    requestID: String,
    executionKind: String,
    seq: inout UInt64,
    decorateEvent: (inout Melix_Worker_V1_ExecuteEvent) -> Void
) async throws -> Int {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = executionKind
    event.seq = seq
    seq += 1
    decorateEvent(&event)

    var payload = Melix_Worker_V1_TokenDelta()
    payload.text = text
    event.tokenDelta = payload
    let writeStartedAt = Date()
    try await response.write(event)
    return filteredOutputElapsedMicros(since: writeStartedAt)
}

private func filteredOutputElapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}

private func filteredOutputElapsedMicros(since startedAt: Date) -> Int {
    max(1, Int(Date().timeIntervalSince(startedAt) * 1_000_000.0))
}
