import Foundation
import MelixWorkerProtocol

struct TextPrefillEngine: Sendable {
    let registry: WorkerRuntimeRegistry
    let abortRegistry: AbortRegistry
    let metrics: MetricsStore

    func runPrefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async -> Melix_Worker_V1_PrefillResponse {
        let requestID = request.execution.id.requestID
        let startedAt = Date()

        let abortHandle: AbortHandle?
        if requestID.isEmpty {
            abortHandle = nil
        } else {
            abortHandle = abortRegistry.register(requestID)
        }

        defer {
            if !requestID.isEmpty {
                abortRegistry.remove(requestID)
            }
        }

        do {
            let acceleration = resolvedAccelerationPolicy(from: request.execution.acceleration)
            let result = try await registry.prefill(
                requestID: requestID,
                modelHandle: request.execution.modelHandle,
                messages: request.messages,
                prefillStepSize: request.prefillStepSize,
                returnDecodeHandle: request.returnDecodeHandle,
                resumeHint: request.resumeHint,
                acceleration: acceleration,
                shouldAbort: { abortHandle?.isAborted ?? false }
            )

            metrics.recordMilliseconds("swift_text.prefill_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.prefill_prompt_tokens", value: Int(clamping: result.promptTokens))
            metrics.set("swift_text.prefill_context_count", value: await registry.prefillContextCount())
            metrics.set("swift_text.accelerated_prefill_gain_pct", value: result.acceleratedPrefillGainPct)
            metrics.set("swift_text.active_kv_quantization_ratio", value: result.activeKVQuantizationRatio)

            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = true
            response.decodeHandle = result.decodeHandle
            response.promptTokens = UInt32(max(0, result.promptTokens))
            response.lifecyclePhase = .executionPrefilling
            response.admissionState = .admissionAdmitted
            response.appliedAcceleration = result.appliedAcceleration
            return response
        } catch let error as WorkerRuntimeRegistryError where error == .unknownModelHandle {
            metrics.increment("swift_text.rpc_error_count")
            metrics.recordMilliseconds("swift_text.prefill_ms", value: elapsedMilliseconds(since: startedAt))

            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = false
            response.error = makePrefillErrorStatus(code: "not_found", message: "Unknown model handle.")
            return response
        } catch {
            metrics.increment("swift_text.rpc_error_count")
            metrics.recordMilliseconds("swift_text.prefill_ms", value: elapsedMilliseconds(since: startedAt))

            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = false
            response.error = makePrefillErrorStatus(code: "runtime_error", message: error.localizedDescription)
            return response
        }
    }
}

private func resolvedAccelerationPolicy(
    from policy: Melix_Worker_V1_AccelerationPolicy
) -> Melix_Worker_V1_AccelerationPolicy {
    normalizedAccelerationPolicy(policy)
}

private func elapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}

private func makePrefillErrorStatus(
    code: String,
    message: String
) -> Melix_Worker_V1_ErrorStatus {
    var status = Melix_Worker_V1_ErrorStatus()
    status.code = code
    status.message = message
    status.retriable = false
    return status
}
