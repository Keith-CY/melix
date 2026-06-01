import Foundation
import GRPCCore
import MelixWorkerProtocol

struct TextGenerationEngine: Sendable {
    let registry: WorkerRuntimeRegistry
    let abortRegistry: AbortRegistry
    let metrics: MetricsStore

    func runGenerate(
        request: Melix_Worker_V1_GenerateRequest,
        response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>
    ) async throws {
        let requestID = request.execution.id.requestID
        let startedAt = Date()

        let abortHandle = abortRegistry.register(requestID)
        await registry.startRequest()
        defer {
            abortRegistry.remove(requestID)
            Task { await registry.finishRequest() }
        }

        do {
            let runtimeStream = try await registry.generateEvents(
                modelHandle: request.execution.modelHandle,
                messages: request.messages,
                sampling: request.sampling,
                shouldAbort: { abortHandle.isAborted }
            )

            var seq: UInt64 = 1
            var promptTokens = 0
            var completionTokens = 0
            var outputState = FilteredTextOutputState()
            var tokensPerSecond: Double?
            var outputFilter = HarmonyChannelOutputFilter()
            var harmonyFilterTotalMicros = 0
            var harmonyFilterCallCount = 0
            var grpcWriteTotalMicros = 0
            var grpcWriteCallCount = 0

            func writeOutput(_ output: HarmonyChannelOutputFilter.Output) async throws {
                let writeSummary = try await writeFilteredTextOutput(
                    output,
                    response: response,
                    requestID: requestID,
                    executionKind: "generate",
                    seq: &seq,
                    state: &outputState,
                    metrics: metrics,
                    ttftMetricName: "swift_text.ttft_ms",
                    startedAt: startedAt
                )
                grpcWriteTotalMicros += writeSummary.grpcWriteTotalMicros
                grpcWriteCallCount += writeSummary.grpcWriteCallCount
            }

            func writeEvent(_ event: Melix_Worker_V1_ExecuteEvent) async throws {
                let writeStartedAt = Date()
                try await response.write(event)
                grpcWriteTotalMicros += elapsedMicroseconds(since: writeStartedAt)
                grpcWriteCallCount += 1
            }

            func acceptFilteredOutput(_ text: String) -> HarmonyChannelOutputFilter.Output {
                let filterStartedAt = Date()
                let output = outputFilter.accept(text)
                harmonyFilterTotalMicros += elapsedMicroseconds(since: filterStartedAt)
                harmonyFilterCallCount += 1
                return output
            }

            func finishFilteredOutput() -> HarmonyChannelOutputFilter.Output {
                let filterStartedAt = Date()
                let output = outputFilter.finish()
                harmonyFilterTotalMicros += elapsedMicroseconds(since: filterStartedAt)
                harmonyFilterCallCount += 1
                return output
            }

            for try await runtimeEvent in runtimeStream {
                switch runtimeEvent {
                case .prefillStarted(let inputTokens):
                    promptTokens = inputTokens
                    var event = Melix_Worker_V1_ExecuteEvent()
                    event.requestID = requestID
                    event.executionKind = "generate"
                    event.seq = seq
                    seq += 1

                    var payload = Melix_Worker_V1_PrefillStarted()
                    payload.inputTokens = UInt32(max(0, inputTokens))
                    event.prefillStarted = payload
                    try await writeEvent(event)
                    outputState.eventCount += 1
                case .token(let text):
                    completionTokens += 1
                    let filtered = acceptFilteredOutput(text)
                    try await writeOutput(filtered)
                case .summary(let summary):
                    promptTokens = max(promptTokens, summary.promptTokens)
                    completionTokens = max(completionTokens, summary.completionTokens)
                    tokensPerSecond = summary.tokensPerSecond
                }
            }

            let finalFiltered = finishFilteredOutput()
            try await writeOutput(finalFiltered)

            if request.returnUsage && !abortHandle.isAborted {
                var event = Melix_Worker_V1_ExecuteEvent()
                event.requestID = requestID
                event.executionKind = "generate"
                event.seq = seq
                seq += 1

                var payload = Melix_Worker_V1_UsageDelta()
                payload.promptTokens = UInt32(max(0, promptTokens))
                payload.completionTokens = UInt32(max(0, completionTokens))
                event.usageDelta = payload
                try await writeEvent(event)
                outputState.eventCount += 1
            }

            var completed = Melix_Worker_V1_Completed()
            completed.finishReason = abortHandle.isAborted ? "cancelled" : "stop"
            completed.assistantText = outputState.assistantText
            completed.reasoningText = outputState.reasoningText

            var completedEvent = Melix_Worker_V1_ExecuteEvent()
            completedEvent.requestID = requestID
            completedEvent.executionKind = "generate"
            completedEvent.seq = seq
            completedEvent.completed = completed
            try await writeEvent(completedEvent)
            outputState.eventCount += 1

            metrics.addMicrosecondTiming(
                prefix: "swift_text.generate_harmony_filter",
                totalMicros: harmonyFilterTotalMicros,
                callCount: harmonyFilterCallCount
            )
            metrics.addMicrosecondTiming(
                prefix: "swift_text.generate_grpc_write",
                totalMicros: grpcWriteTotalMicros,
                callCount: grpcWriteCallCount
            )
            if !outputState.sawFirstToken {
                metrics.recordMilliseconds(
                    "swift_text.ttft_ms",
                    value: elapsedMilliseconds(since: startedAt)
                )
            }
            metrics.recordMilliseconds("swift_text.generate_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.stream_event_count", value: outputState.eventCount)

            if let tokensPerSecond {
                metrics.set(
                    "swift_text.tokens_per_second",
                    value: max(0, Int(tokensPerSecond.rounded()))
                )
            } else {
                metrics.set("swift_text.tokens_per_second", value: 0)
            }
        } catch let error as WorkerRuntimeRegistryError where error == .unknownModelHandle {
            metrics.increment("swift_text.rpc_error_count")
            try await response.write(makeGenerateErrorExecuteEvent(
                requestID: requestID,
                executionKind: "generate",
                seq: 1,
                code: "not_found",
                message: "Unknown model handle."
            ))
        } catch {
            metrics.increment("swift_text.rpc_error_count")
            try await response.write(makeGenerateErrorExecuteEvent(
                requestID: requestID,
                executionKind: "generate",
                seq: 1,
                code: "runtime_error",
                message: error.localizedDescription
            ))
        }
    }
}

private func makeGenerateErrorExecuteEvent(
    requestID: String,
    executionKind: String,
    seq: UInt64,
    code: String,
    message: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = executionKind
    event.seq = seq

    var errorStatus = Melix_Worker_V1_ErrorStatus()
    errorStatus.code = code
    errorStatus.message = message
    errorStatus.retriable = false

    var errorEvent = Melix_Worker_V1_ErrorEvent()
    errorEvent.error = errorStatus
    event.error = errorEvent
    return event
}

private func elapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}

private func elapsedMicroseconds(since startedAt: Date) -> Int {
    max(1, Int(Date().timeIntervalSince(startedAt) * 1_000_000.0))
}
