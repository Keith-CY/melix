import Foundation
import GRPCCore
import MelixWorkerProtocol

struct TextDecodeEngine: Sendable {
    let registry: WorkerRuntimeRegistry
    let abortRegistry: AbortRegistry
    let metrics: MetricsStore

    func runDecode(
        request: Melix_Worker_V1_DecodeRequest,
        response: GRPCCore.RPCWriter<Melix_Worker_V1_ExecuteEvent>
    ) async throws {
        let startedAt = Date()
        let lane = request.execution.scheduling.lane.isEmpty
            ? "text.decode.interactive"
            : request.execution.scheduling.lane

        do {
            let session = try await registry.beginDecode(decodeHandle: request.decodeHandle)
            let requestID = effectiveRequestID(request: request, storedRequestID: session.prefill.requestID)
            let abortHandle = requestID.isEmpty ? nil : abortRegistry.register(requestID)

            defer {
                if !requestID.isEmpty {
                    abortRegistry.remove(requestID)
                }
                Task { await registry.finishDecode() }
            }

            let acceleration = try resolveDecodeAcceleration(
                requested: request.execution.acceleration,
                stored: session.prefill.acceleration,
                supportsSpeculative: await registry.supportsSpeculativeDecoding()
            )

            var sampling = request.sampling
            if request.maxOutputTokens > 0 {
                sampling.maxOutputTokens = request.maxOutputTokens
            }

            let runtimeStream = try await registry.decodeEvents(
                session: session,
                sampling: sampling,
                maxOutputTokens: request.maxOutputTokens,
                decodeStepSize: request.decodeStepSize,
                prefillToken: request.prefillToken,
                acceleration: acceleration,
                shouldAbort: { abortHandle?.isAborted ?? false }
            )

            var seq: UInt64 = 1
            var completionTokens = 0
            var assistantText = ""
            var eventCount = 0
            var sawFirstToken = false
            var tokensPerSecond: Double?
            var speculativeAccepted: Int?
            var speculativeRejected: Int?

            if acceleration.mode != .baseline {
                var accelerationEvent = Melix_Worker_V1_ExecuteEvent()
                accelerationEvent.requestID = requestID
                accelerationEvent.executionKind = "decode"
                accelerationEvent.seq = seq
                accelerationEvent.phase = .executionDecoding
                accelerationEvent.admissionState = .admissionAdmitted
                accelerationEvent.lane = lane
                accelerationEvent.accelerationMode = acceleration.mode

                var payload = Melix_Worker_V1_AccelerationApplied()
                payload.policy = acceleration
                accelerationEvent.accelerationApplied = payload
                try await response.write(accelerationEvent)
                seq += 1
                eventCount += 1
            }

            var startedEvent = Melix_Worker_V1_ExecuteEvent()
            startedEvent.requestID = requestID
            startedEvent.executionKind = "decode"
            startedEvent.seq = seq
            startedEvent.phase = .executionDecoding
            startedEvent.admissionState = .admissionAdmitted
            startedEvent.lane = lane
            startedEvent.accelerationMode = acceleration.mode

            var payload = Melix_Worker_V1_DecodeStarted()
            payload.decodeHandle = request.decodeHandle
            payload.maxOutputTokens = request.maxOutputTokens
            payload.resumedFromPrefill = true
            startedEvent.decodeStarted = payload
            try await response.write(startedEvent)
            seq += 1
            eventCount += 1

            if !session.prefill.restoredSnapshotID.isEmpty {
                var cacheDecisionEvent = Melix_Worker_V1_ExecuteEvent()
                cacheDecisionEvent.requestID = requestID
                cacheDecisionEvent.executionKind = "decode"
                cacheDecisionEvent.seq = seq
                cacheDecisionEvent.phase = .executionDecoding
                cacheDecisionEvent.admissionState = .admissionAdmitted
                cacheDecisionEvent.lane = lane
                cacheDecisionEvent.accelerationMode = acceleration.mode

                var cacheDecision = Melix_Worker_V1_CacheDecision()
                cacheDecision.blockTableID = session.prefill.blockTableID
                cacheDecision.restoredSnapshotID = session.prefill.restoredSnapshotID
                cacheDecision.persistedToL2 = true
                cacheDecisionEvent.cacheDecision = cacheDecision
                try await response.write(cacheDecisionEvent)
                seq += 1
                eventCount += 1
            }

            for try await runtimeEvent in runtimeStream {
                switch runtimeEvent {
                case .prefillStarted:
                    continue
                case .token(let text):
                    if !sawFirstToken {
                        sawFirstToken = true
                        metrics.recordMilliseconds(
                            "swift_text.decode_ttft_ms",
                            value: elapsedMilliseconds(since: startedAt)
                        )
                    }

                    assistantText.append(text)

                    var event = Melix_Worker_V1_ExecuteEvent()
                    event.requestID = requestID
                    event.executionKind = "decode"
                    event.seq = seq
                    event.phase = .executionDecoding
                    event.admissionState = .admissionAdmitted
                    event.lane = lane
                    event.accelerationMode = acceleration.mode

                    var tokenDelta = Melix_Worker_V1_TokenDelta()
                    tokenDelta.text = text
                    event.tokenDelta = tokenDelta
                    try await response.write(event)
                    seq += 1
                    eventCount += 1
                case .summary(let summary):
                    completionTokens = summary.completionTokens
                    tokensPerSecond = summary.tokensPerSecond
                    speculativeAccepted = summary.speculativeAcceptedTokens
                    speculativeRejected = summary.speculativeRejectedTokens
                }
            }

            if request.returnUsage && !(abortHandle?.isAborted ?? false) {
                var event = Melix_Worker_V1_ExecuteEvent()
                event.requestID = requestID
                event.executionKind = "decode"
                event.seq = seq
                event.phase = .executionDecoding
                event.admissionState = .admissionAdmitted
                event.lane = lane
                event.accelerationMode = acceleration.mode

                var usage = Melix_Worker_V1_UsageDelta()
                usage.promptTokens = UInt32(max(0, session.prefill.promptTokens))
                usage.completionTokens = UInt32(max(0, completionTokens))
                event.usageDelta = usage
                try await response.write(event)
                seq += 1
                eventCount += 1
            }

            if request.execution.cacheHints.saveBoundarySnapshot && !(abortHandle?.isAborted ?? false) {
                let snapshotStartedAt = Date()
                let boundary = UInt32(max(0, session.prefill.promptTokens + completionTokens))
                let snapshot = await registry.saveBoundarySnapshot(
                    requestID: requestID,
                    session: session,
                    tokenBoundary: boundary
                )

                var snapshotEvent = Melix_Worker_V1_ExecuteEvent()
                snapshotEvent.requestID = requestID
                snapshotEvent.executionKind = "decode"
                snapshotEvent.seq = seq
                snapshotEvent.phase = .executionDecoding
                snapshotEvent.admissionState = .admissionAdmitted
                snapshotEvent.lane = lane
                snapshotEvent.accelerationMode = acceleration.mode

                var snapshotCreated = Melix_Worker_V1_BoundarySnapshotCreated()
                snapshotCreated.snapshotID = snapshot.snapshotID
                snapshotCreated.tokenBoundary = boundary
                snapshotEvent.snapshotCreated = snapshotCreated
                try await response.write(snapshotEvent)
                seq += 1
                eventCount += 1

                metrics.recordMilliseconds(
                    "swift_text.cache_snapshot_save_ms",
                    value: elapsedMilliseconds(since: snapshotStartedAt)
                )
            }

            var completed = Melix_Worker_V1_Completed()
            completed.finishReason = (abortHandle?.isAborted ?? false) ? "cancelled" : "stop"
            completed.assistantText = assistantText

            var completedEvent = Melix_Worker_V1_ExecuteEvent()
            completedEvent.requestID = requestID
            completedEvent.executionKind = "decode"
            completedEvent.seq = seq
            completedEvent.phase = (abortHandle?.isAborted ?? false) ? .executionAborted : .executionCompleted
            completedEvent.admissionState = .admissionAdmitted
            completedEvent.lane = lane
            completedEvent.accelerationMode = acceleration.mode
            completedEvent.completed = completed
            try await response.write(completedEvent)
            eventCount += 1

            if !sawFirstToken {
                metrics.recordMilliseconds(
                    "swift_text.decode_ttft_ms",
                    value: elapsedMilliseconds(since: startedAt)
                )
            }
            metrics.recordMilliseconds("swift_text.decode_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.decode_stream_event_count", value: eventCount)
            metrics.set(
                "swift_text.decode_tokens_per_second",
                value: max(0, Int((tokensPerSecond ?? 0).rounded()))
            )
            metrics.set(
                "swift_text.active_kv_quantization_ratio",
                value: activeKVQuantizationRatioPercent(for: acceleration)
            )
            recordSpeculativeMetrics(
                accepted: speculativeAccepted,
                rejected: speculativeRejected
            )
        } catch let error as WorkerRuntimeRegistryError where error == .unknownDecodeHandle {
            metrics.increment("swift_text.rpc_error_count")
            try await response.write(makeDecodeErrorExecuteEvent(
                requestID: request.execution.id.requestID,
                seq: 1,
                code: "not_found",
                message: "Unknown decode handle."
            ))
        } catch let error as WorkerRuntimeRegistryError where error == .unknownModelHandle {
            metrics.increment("swift_text.rpc_error_count")
            try await response.write(makeDecodeErrorExecuteEvent(
                requestID: request.execution.id.requestID,
                seq: 1,
                code: "not_found",
                message: "Unknown model handle."
            ))
        } catch let error as DecodeAccelerationError {
            metrics.increment("swift_text.rpc_error_count")
            try await response.write(makeDecodeErrorExecuteEvent(
                requestID: request.execution.id.requestID,
                seq: 1,
                code: "unimplemented",
                message: error.message
            ))
        } catch {
            metrics.increment("swift_text.rpc_error_count")
            try await response.write(makeDecodeErrorExecuteEvent(
                requestID: request.execution.id.requestID,
                seq: 1,
                code: "runtime_error",
                message: error.localizedDescription
            ))
        }
    }

    private func recordSpeculativeMetrics(
        accepted: Int?,
        rejected: Int?
    ) {
        let accepted = max(0, accepted ?? 0)
        let rejected = max(0, rejected ?? 0)
        let total = max(accepted + rejected, 1)
        metrics.set("swift_text.speculative_acceptance_rate", value: (accepted * 100) / total)
        metrics.set("swift_text.speculative_rollback_rate", value: (rejected * 100) / total)
    }
}

private struct DecodeAccelerationError: LocalizedError {
    let message: String

    var errorDescription: String? {
        message
    }
}

private func resolveDecodeAcceleration(
    requested: Melix_Worker_V1_AccelerationPolicy,
    stored: Melix_Worker_V1_AccelerationPolicy,
    supportsSpeculative: Bool
) throws -> Melix_Worker_V1_AccelerationPolicy {
    var resolved = requested
    if resolved.mode == .unspecified {
        resolved = stored
    }
    if resolved.mode == .unspecified {
        resolved.mode = .baseline
    }

    if resolved.mode == .speculativeDecode && !supportsSpeculative {
        if resolved.allowBaselineFallback {
            resolved.mode = .baseline
        } else {
            throw DecodeAccelerationError(
                message: "Speculative decode is not available for the active Swift text backend."
            )
        }
    }

    return resolved
}

private func effectiveRequestID(
    request: Melix_Worker_V1_DecodeRequest,
    storedRequestID: String
) -> String {
    request.execution.id.requestID.isEmpty ? storedRequestID : request.execution.id.requestID
}

private func makeDecodeErrorExecuteEvent(
    requestID: String,
    seq: UInt64,
    code: String,
    message: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "decode"
    event.seq = seq
    event.phase = .executionFailed

    var errorEvent = Melix_Worker_V1_ErrorEvent()
    var status = Melix_Worker_V1_ErrorStatus()
    status.code = code
    status.message = message
    status.retriable = false
    errorEvent.error = status
    event.error = errorEvent
    return event
}

private func elapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}
