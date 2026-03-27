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
            var assistantText = ""
            var eventCount = 0
            var sawFirstToken = false
            var tokensPerSecond: Double?

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
                    try await response.write(event)
                    eventCount += 1
                case .token(let text):
                    if !sawFirstToken {
                        sawFirstToken = true
                        metrics.recordMilliseconds(
                            "swift_text.ttft_ms",
                            value: elapsedMilliseconds(since: startedAt)
                        )
                    }

                    assistantText.append(text)
                    completionTokens += 1

                    var event = Melix_Worker_V1_ExecuteEvent()
                    event.requestID = requestID
                    event.executionKind = "generate"
                    event.seq = seq
                    seq += 1

                    var payload = Melix_Worker_V1_TokenDelta()
                    payload.text = text
                    event.tokenDelta = payload
                    try await response.write(event)
                    eventCount += 1
                case .summary(let summary):
                    promptTokens = max(promptTokens, summary.promptTokens)
                    completionTokens = max(completionTokens, summary.completionTokens)
                    tokensPerSecond = summary.tokensPerSecond
                }
            }

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
                try await response.write(event)
                eventCount += 1
            }

            var completed = Melix_Worker_V1_Completed()
            completed.finishReason = abortHandle.isAborted ? "cancelled" : "stop"
            completed.assistantText = assistantText

            var completedEvent = Melix_Worker_V1_ExecuteEvent()
            completedEvent.requestID = requestID
            completedEvent.executionKind = "generate"
            completedEvent.seq = seq
            completedEvent.completed = completed
            try await response.write(completedEvent)
            eventCount += 1

            if !sawFirstToken {
                metrics.recordMilliseconds(
                    "swift_text.ttft_ms",
                    value: elapsedMilliseconds(since: startedAt)
                )
            }
            metrics.recordMilliseconds("swift_text.generate_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.stream_event_count", value: eventCount)

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
