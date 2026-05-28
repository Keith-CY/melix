import Foundation
import GRPCCore
import MelixWorkerProtocol

struct TextDecodeEngine: Sendable {
    let registry: WorkerRuntimeRegistry
    let abortRegistry: AbortRegistry
    let metrics: MetricsStore
    let batchCoordinator: TextDecodeBatchCoordinator?

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

            var sampling = request.sampling
            if request.maxOutputTokens > 0 {
                sampling.maxOutputTokens = request.maxOutputTokens
            }

            let accelerationResolution = try await resolveDecodeAcceleration(
                requested: request.execution.acceleration,
                stored: session.prefill.acceleration,
                sampling: sampling,
                supportsSpeculative: await registry.supportsSpeculativeDecoding(),
                requiresLoadedDraftModel: await registry.requiresLoadedDraftModelForSpeculativeDecoding(),
                draftModelReadiness: { draftModelID in
                    await registry.speculativeDraftModelReadiness(
                        id: draftModelID,
                        excludingModelHandle: session.loadedModel.handle,
                        targetSpec: session.loadedModel.spec
                    )
                }
            )
            let acceleration = accelerationResolution.policy
            recordSpeculativeRequestMetrics(accelerationResolution)

            let shouldAbort: @Sendable () -> Bool = { abortHandle?.isAborted ?? false }
            let runtimeStream = try await resolveRuntimeStream(
                request: request,
                requestID: requestID,
                lane: lane,
                session: session,
                sampling: sampling,
                acceleration: acceleration,
                shouldAbort: shouldAbort
            )

            var seq: UInt64 = 1
            var completionTokens = 0
            var outputState = FilteredTextOutputState()
            var tokensPerSecond: Double?
            var decodeBatchSize = 1
            var modelEvalBatchSize = 1
            var decodeLoopIterations = 1
            var perBatchOutputTokenCount: Int?
            var perBatchOutputTokensPerSecond: Double?
            var speculativeAccepted: Int?
            var speculativeRejected: Int?
            var speculativeFallbackCount: Int?
            var speculativeDraftProposeMillis: Int?
            var speculativeTargetVerifyMillis: Int?
            var dflashEnabled = false
            var dflashBlockSize: Int?
            var dflashRollbackCount: Int?
            var dflashTargetHiddenLayers: Int?
            var activeKVProbe: ActiveKVProbeSummary?

            func writeOutput(_ output: HarmonyChannelOutputFilter.Output) async throws {
                try await writeFilteredTextOutput(
                    output,
                    response: response,
                    requestID: requestID,
                    executionKind: "decode",
                    seq: &seq,
                    state: &outputState,
                    metrics: metrics,
                    ttftMetricName: "swift_text.decode_ttft_ms",
                    startedAt: startedAt,
                    decorateEvent: { event in
                        event.phase = .executionDecoding
                        event.admissionState = .admissionAdmitted
                        event.lane = lane
                        event.accelerationMode = acceleration.mode
                    }
                )
            }

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
                outputState.eventCount += 1
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
            outputState.eventCount += 1

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
                outputState.eventCount += 1
            }

            var outputFilter = HarmonyChannelOutputFilter()
            for try await runtimeEvent in runtimeStream {
                switch runtimeEvent {
                case .prefillStarted:
                    continue
                case .token(let text):
                    completionTokens += 1
                    let filtered = outputFilter.accept(text)
                    try await writeOutput(filtered)
                case .summary(let summary):
                    completionTokens = max(completionTokens, summary.completionTokens)
                    tokensPerSecond = summary.tokensPerSecond
                    decodeBatchSize = max(decodeBatchSize, summary.decodeBatchSize ?? 1)
                    modelEvalBatchSize = max(modelEvalBatchSize, summary.modelEvalBatchSize ?? 1)
                    decodeLoopIterations = max(decodeLoopIterations, summary.decodeLoopIterations ?? 1)
                    if let value = summary.perBatchOutputTokenCount {
                        perBatchOutputTokenCount = max(perBatchOutputTokenCount ?? 0, value)
                    }
                    if let value = summary.perBatchOutputTokensPerSecond {
                        perBatchOutputTokensPerSecond = value
                    }
                    speculativeAccepted = summary.speculativeAcceptedTokens
                    speculativeRejected = summary.speculativeRejectedTokens
                    speculativeFallbackCount = summary.speculativeFallbackCount
                    speculativeDraftProposeMillis = summary.speculativeDraftProposeMillis
                    speculativeTargetVerifyMillis = summary.speculativeTargetVerifyMillis
                    dflashEnabled = summary.dflashEnabled
                    dflashBlockSize = summary.dflashBlockSize
                    dflashRollbackCount = summary.dflashRollbackCount
                    dflashTargetHiddenLayers = summary.dflashTargetHiddenLayers
                    activeKVProbe = summary.activeKVProbe
                }
            }

            let finalFiltered = outputFilter.finish()
            try await writeOutput(finalFiltered)

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
                outputState.eventCount += 1
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
                outputState.eventCount += 1

                metrics.recordMilliseconds(
                    "swift_text.cache_snapshot_save_ms",
                    value: elapsedMilliseconds(since: snapshotStartedAt)
                )
            }

            var completed = Melix_Worker_V1_Completed()
            completed.finishReason = (abortHandle?.isAborted ?? false) ? "cancelled" : "stop"
            completed.assistantText = outputState.assistantText
            completed.reasoningText = outputState.reasoningText

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
            outputState.eventCount += 1

            if !outputState.sawFirstToken {
                metrics.recordMilliseconds(
                    "swift_text.decode_ttft_ms",
                    value: elapsedMilliseconds(since: startedAt)
                )
            }
            metrics.recordMilliseconds("swift_text.decode_ms", value: elapsedMilliseconds(since: startedAt))
            let roundedTokensPerSecond = max(0, Int((tokensPerSecond ?? 0).rounded()))
            let roundedPerBatchTokensPerSecond = max(
                0,
                Int((perBatchOutputTokensPerSecond ?? tokensPerSecond ?? 0).rounded())
            )
            metrics.set("swift_text.decode_stream_event_count", value: outputState.eventCount)
            metrics.set("swift_text.decode_batch_size", value: max(1, decodeBatchSize))
            metrics.set("swift_text.model_eval_batch_size", value: max(1, modelEvalBatchSize))
            metrics.increment("swift_text.decode_batch_observation_count")
            metrics.set("swift_text.decode_loop_iterations", value: max(1, decodeLoopIterations))
            metrics.set(
                "swift_text.per_batch_output_token_count",
                value: max(0, perBatchOutputTokenCount ?? completionTokens)
            )
            metrics.set(
                "swift_text.decode_tokens_per_second",
                value: roundedTokensPerSecond
            )
            metrics.set(
                "swift_text.per_batch_output_tokens_per_second",
                value: roundedPerBatchTokensPerSecond
            )
            metrics.set(
                "swift_text.active_kv_quantization_ratio",
                value: activeKVQuantizationRatioPercent(for: acceleration)
            )
            recordActiveKVProbeMetrics(activeKVProbe)
            recordSpeculativeMetrics(
                accepted: speculativeAccepted,
                rejected: speculativeRejected,
                fallbackCount: speculativeFallbackCount,
                draftProposeMillis: speculativeDraftProposeMillis,
                targetVerifyMillis: speculativeTargetVerifyMillis
            )
            recordDFlashMetrics(
                enabled: dflashEnabled,
                blockSize: dflashBlockSize,
                rollbackCount: dflashRollbackCount,
                targetHiddenLayers: dflashTargetHiddenLayers
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

    private func resolveRuntimeStream(
        request: Melix_Worker_V1_DecodeRequest,
        requestID: String,
        lane: String,
        session: WorkerDecodeSession,
        sampling: Melix_Worker_V1_SamplingConfig,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        if let candidate = await makeBatchCandidateIfEligible(
            request: request,
            requestID: requestID,
            lane: lane,
            session: session,
            sampling: sampling,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        ), let batchCoordinator {
            switch await batchCoordinator.enqueue(candidate) {
            case .single:
                break
            case .batched(let stream, _):
                return stream
            }
        }

        return try await registry.decodeEvents(
            session: session,
            sampling: sampling,
            maxOutputTokens: request.maxOutputTokens,
            decodeStepSize: request.decodeStepSize,
            prefillToken: request.prefillToken,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    private func makeBatchCandidateIfEligible(
        request: Melix_Worker_V1_DecodeRequest,
        requestID: String,
        lane: String,
        session: WorkerDecodeSession,
        sampling: Melix_Worker_V1_SamplingConfig,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async -> TextDecodeBatchCandidate? {
        guard batchCoordinator != nil,
              await registry.supportsHomogeneousBatchDecode(),
              !requestID.isEmpty,
              !request.decodeHandle.isEmpty,
              !request.execution.cacheHints.saveBoundarySnapshot else {
            return nil
        }
        let maxBatchSize = decodeBatchSizeLimit(from: request.execution.ext)
        guard maxBatchSize > 1 else {
            return nil
        }

        let key = TextDecodeBatchEligibilityKey(
            modelHandle: session.loadedModel.handle,
            lane: lane,
            sampling: TextDecodeSamplingKey(sampling),
            acceleration: TextDecodeAccelerationKey(acceleration),
            maxOutputTokens: request.maxOutputTokens,
            decodeStepSize: request.decodeStepSize,
            prefillToken: request.prefillToken
        )
        return TextDecodeBatchCandidate(
            requestID: requestID,
            key: key,
            maxBatchSize: maxBatchSize,
            session: session,
            sampling: sampling,
            maxOutputTokens: request.maxOutputTokens,
            decodeStepSize: request.decodeStepSize,
            prefillToken: request.prefillToken,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    private func decodeBatchSizeLimit(from executionExt: [String: String]) -> Int {
        guard parseBool(
            executionExt["melix.gateway.concurrent_processing"],
            fallback: true
        ) else {
            return 1
        }
        let maxConcurrent = parsePositiveInt(
            executionExt["melix.gateway.max_concurrent_sequences"]
                ?? executionExt["melix.gateway.max_concurrent_requests"],
            fallback: 4
        )
        let completionBatchSize = parsePositiveInt(
            executionExt["melix.gateway.completion_batch_size"],
            fallback: 1
        )
        return max(1, min(maxConcurrent, completionBatchSize))
    }

    private func recordSpeculativeMetrics(
        accepted: Int?,
        rejected: Int?,
        fallbackCount: Int?,
        draftProposeMillis: Int?,
        targetVerifyMillis: Int?
    ) {
        let accepted = max(0, accepted ?? 0)
        let rejected = max(0, rejected ?? 0)
        let total = max(accepted + rejected, 1)
        metrics.set("swift_text.speculative_accepted_tokens", value: accepted)
        metrics.set("swift_text.speculative_rejected_tokens", value: rejected)
        metrics.set("swift_text.speculative_acceptance_rate", value: (accepted * 100) / total)
        metrics.set("swift_text.speculative_rollback_rate", value: (rejected * 100) / total)
        if let fallbackCount, fallbackCount > 0 {
            metrics.increment("swift_text.speculative_fallback_count", by: fallbackCount)
        }
        metrics.set("swift_text.speculative_draft_propose_ms", value: max(0, draftProposeMillis ?? 0))
        metrics.set("swift_text.speculative_target_verify_ms", value: max(0, targetVerifyMillis ?? 0))
    }

    private func recordSpeculativeRequestMetrics(_ resolution: DecodeAccelerationResolution) {
        guard resolution.requestedPolicy.mode == .speculativeDecode else {
            metrics.set("swift_text.speculative_draft_model_configured", value: 0)
            metrics.set("swift_text.speculative_num_draft_tokens", value: 0)
            return
        }

        metrics.set(
            "swift_text.speculative_draft_model_configured",
            value: resolution.requestedPolicy.draftModelID.isEmpty ? 0 : 1
        )
        metrics.set(
            "swift_text.speculative_num_draft_tokens",
            value: Int(resolution.requestedPolicy.numDraftTokens)
        )
        if resolution.fallbackReason != nil {
            metrics.increment("swift_text.speculative_fallback_count")
        }
    }

    private func recordDFlashMetrics(
        enabled: Bool,
        blockSize: Int?,
        rollbackCount: Int?,
        targetHiddenLayers: Int?
    ) {
        metrics.set("swift_text.dflash_enabled", value: enabled ? 1 : 0)
        metrics.set("swift_text.dflash_block_size", value: max(0, blockSize ?? 0))
        metrics.set("swift_text.dflash_rollback_count", value: max(0, rollbackCount ?? 0))
        metrics.set("swift_text.dflash_target_hidden_layers", value: max(0, targetHiddenLayers ?? 0))
    }

    private func recordActiveKVProbeMetrics(_ probe: ActiveKVProbeSummary?) {
        guard let probe else {
            return
        }

        metrics.set("swift_text.active_kv_quantization_ratio", value: probe.quantizationRatioPercent)
        metrics.set("swift_text.active_kv_backend_code", value: probe.backendCode)
        metrics.set("swift_text.active_kv_kernel_path_code", value: probe.kernelPathCode)
        metrics.set("swift_text.active_kv_runtime_route_code", value: probe.runtimeRouteCode)
        metrics.set(
            "swift_text.active_kv_runtime_block_reason_code",
            value: probe.runtimeBlockReasonCode
        )
        metrics.set("swift_text.active_kv_prefill_quantize_us", value: probe.prefillQuantizeMicros)
        metrics.set("swift_text.active_kv_decode_model_total_us", value: probe.decodeModelTotalMicros)
        metrics.set("swift_text.active_kv_decode_model_call_count", value: probe.decodeModelCallCount)
        metrics.set("swift_text.active_kv_decode_model_avg_us", value: probe.decodeModelAverageMicros)
        metrics.set("swift_text.active_kv_decode_token_eval_total_us", value: probe.decodeTokenEvalTotalMicros)
        metrics.set("swift_text.active_kv_decode_token_eval_call_count", value: probe.decodeTokenEvalCallCount)
        metrics.set("swift_text.active_kv_decode_token_eval_avg_us", value: probe.decodeTokenEvalAverageMicros)
        metrics.set(
            "swift_text.active_kv_decode_model_eval_sync_total_us",
            value: probe.decodeModelEvalSyncTotalMicros
        )
        metrics.set(
            "swift_text.active_kv_decode_model_eval_sync_call_count",
            value: probe.decodeModelEvalSyncCallCount
        )
        metrics.set(
            "swift_text.active_kv_decode_model_eval_sync_avg_us",
            value: probe.decodeModelEvalSyncAverageMicros
        )
        metrics.set("swift_text.active_kv_decode_sample_total_us", value: probe.decodeSampleTotalMicros)
        metrics.set("swift_text.active_kv_decode_sample_call_count", value: probe.decodeSampleCallCount)
        metrics.set("swift_text.active_kv_decode_sample_avg_us", value: probe.decodeSampleAverageMicros)
        metrics.set("swift_text.active_kv_decode_token_id_total_us", value: probe.decodeTokenIDTotalMicros)
        metrics.set("swift_text.active_kv_decode_token_id_call_count", value: probe.decodeTokenIDCallCount)
        metrics.set("swift_text.active_kv_decode_token_id_avg_us", value: probe.decodeTokenIDAverageMicros)
        metrics.set("swift_text.active_kv_decode_detokenize_total_us", value: probe.decodeDetokenizeTotalMicros)
        metrics.set("swift_text.active_kv_decode_detokenize_call_count", value: probe.decodeDetokenizeCallCount)
        metrics.set("swift_text.active_kv_decode_detokenize_avg_us", value: probe.decodeDetokenizeAverageMicros)
        metrics.set("swift_text.active_kv_decode_stream_yield_total_us", value: probe.decodeStreamYieldTotalMicros)
        metrics.set("swift_text.active_kv_decode_stream_yield_call_count", value: probe.decodeStreamYieldCallCount)
        metrics.set("swift_text.active_kv_decode_stream_yield_avg_us", value: probe.decodeStreamYieldAverageMicros)
        metrics.set("swift_text.active_kv_decode_summary_total_us", value: probe.decodeSummaryTotalMicros)
        metrics.set("swift_text.active_kv_decode_summary_call_count", value: probe.decodeSummaryCallCount)
        metrics.set("swift_text.active_kv_decode_summary_avg_us", value: probe.decodeSummaryAverageMicros)
        metrics.set("swift_text.active_kv_turboquant_candidate_total_us", value: probe.turboQuantCandidateTotalMicros)
        metrics.set("swift_text.active_kv_turboquant_candidate_call_count", value: probe.turboQuantCandidateCallCount)
        metrics.set("swift_text.active_kv_turboquant_candidate_avg_us", value: probe.turboQuantCandidateAverageMicros)
        metrics.set("swift_text.active_kv_decode_quantize_total_us", value: probe.decodeQuantizeTotalMicros)
        metrics.set("swift_text.active_kv_decode_quantize_avg_us", value: probe.decodeQuantizeAverageMicros)
        metrics.set("swift_text.active_kv_decode_loop_total_us", value: probe.decodeLoopTotalMicros)
        metrics.set("swift_text.active_kv_decode_token_count", value: probe.decodeTokenCount)
        metrics.set("swift_text.active_kv_fused_attention_total_us", value: probe.fusedAttentionTotalMicros)
        metrics.set("swift_text.active_kv_fused_attention_call_count", value: probe.fusedAttentionCallCount)
        metrics.set("swift_text.active_kv_fused_attention_avg_us", value: probe.fusedAttentionAverageMicros)
        metrics.set(
            "swift_text.active_kv_fused_attention_route_total_us",
            value: probe.fusedAttentionRouteTotalMicros
        )
        metrics.set(
            "swift_text.active_kv_fused_attention_route_avg_us",
            value: probe.fusedAttentionRouteAverageMicros
        )
        metrics.set(
            "swift_text.active_kv_fused_attention_active_lane_total",
            value: probe.fusedAttentionActiveLaneTotal
        )
        metrics.set(
            "swift_text.active_kv_fused_attention_launched_lane_total",
            value: probe.fusedAttentionLaunchedLaneTotal
        )
        metrics.set(
            "swift_text.active_kv_fused_attention_inactive_lane_total",
            value: probe.fusedAttentionInactiveLaneTotal
        )
        metrics.set(
            "swift_text.active_kv_fused_attention_softmax_lane_total",
            value: probe.fusedAttentionSoftmaxLaneTotal
        )
        metrics.set(
            "swift_text.active_kv_fused_attention_softmax_token_lane_total",
            value: probe.fusedAttentionSoftmaxTokenLaneTotal
        )
        metrics.set("swift_text.active_kv_cache_update_total_us", value: probe.cacheUpdateTotalMicros)
        metrics.set("swift_text.active_kv_cache_update_call_count", value: probe.cacheUpdateCallCount)
        metrics.set("swift_text.active_kv_cache_update_avg_us", value: probe.cacheUpdateAverageMicros)
        metrics.set("swift_text.active_kv_cache_expand_total_us", value: probe.cacheExpandTotalMicros)
        metrics.set("swift_text.active_kv_cache_quantize_total_us", value: probe.cacheQuantizeTotalMicros)
        metrics.set("swift_text.active_kv_cache_append_total_us", value: probe.cacheAppendTotalMicros)
        metrics.set("swift_text.active_kv_cache_materialize_total_us", value: probe.cacheMaterializeTotalMicros)
        metrics.set(
            "swift_text.active_kv_cache_materialize_call_count",
            value: probe.cacheMaterializeCallCount
        )
        metrics.set("swift_text.active_kv_cache_materialize_avg_us", value: probe.cacheMaterializeAverageMicros)
        metrics.set("swift_text.active_kv_estimated_fp16_bytes", value: probe.estimatedFP16Bytes)
        metrics.set("swift_text.active_kv_estimated_quantized_bytes", value: probe.estimatedQuantizedBytes)
        metrics.set(
            "swift_text.active_kv_estimated_memory_savings_pct",
            value: probe.estimatedMemorySavingsPercent
        )
        metrics.set("swift_text.active_kv_fallback_count", value: probe.fallbackCount)
        metrics.set(
            "swift_text.active_kv_candidate_dispatch_code",
            value: probe.candidateDispatchCode
        )
        metrics.set(
            "swift_text.active_kv_candidate_eligibility_check_count",
            value: probe.candidateEligibilityCheckCount
        )
    }
}

private struct DecodeAccelerationError: LocalizedError {
    let message: String

    var errorDescription: String? {
        message
    }
}

private struct DecodeAccelerationResolution {
    let policy: Melix_Worker_V1_AccelerationPolicy
    let requestedPolicy: Melix_Worker_V1_AccelerationPolicy
    let fallbackReason: String?
}

private func resolveDecodeAcceleration(
    requested: Melix_Worker_V1_AccelerationPolicy,
    stored: Melix_Worker_V1_AccelerationPolicy,
    sampling: Melix_Worker_V1_SamplingConfig,
    supportsSpeculative: Bool,
    requiresLoadedDraftModel: Bool,
    draftModelReadiness: @escaping @Sendable (String) async -> SpeculativeDraftModelReadiness
) async throws -> DecodeAccelerationResolution {
    var resolved = requested
    if resolved.mode == .unspecified {
        resolved = stored
    }
    if resolved.mode == .unspecified {
        resolved.mode = .baseline
    }
    let requestedPolicy = resolved

    if resolved.mode == .speculativeDecode && !supportsSpeculative {
        if resolved.allowBaselineFallback {
            resolved.mode = .baseline
            return DecodeAccelerationResolution(
                policy: resolved,
                requestedPolicy: requestedPolicy,
                fallbackReason: "backend_unsupported"
            )
        } else {
            throw DecodeAccelerationError(
                message: "Speculative decode is not available for the active Swift text backend."
            )
        }
    }

    if resolved.mode == .speculativeDecode && !isGreedySpeculativeSampling(sampling) {
        if resolved.allowBaselineFallback {
            resolved.mode = .baseline
            return DecodeAccelerationResolution(
                policy: resolved,
                requestedPolicy: requestedPolicy,
                fallbackReason: "non_greedy_sampling"
            )
        } else {
            throw DecodeAccelerationError(
                message: "Speculative decode currently requires greedy sampling: temperature=0, top_p=1, top_k=0."
            )
        }
    }

    if resolved.mode == .speculativeDecode && requiresLoadedDraftModel {
        let draftModelID = resolved.draftModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let draftReadiness = draftModelID.isEmpty
            ? .unavailable(reason: "draft_model_unavailable")
            : await draftModelReadiness(draftModelID)
        if !draftReadiness.available || !draftReadiness.compatible {
            if resolved.allowBaselineFallback {
                resolved.mode = .baseline
                return DecodeAccelerationResolution(
                    policy: resolved,
                    requestedPolicy: requestedPolicy,
                    fallbackReason: draftReadiness.fallbackReason
                )
            } else {
                throw DecodeAccelerationError(
                    message: draftReadiness.errorMessage
                )
            }
        }
    }

    return DecodeAccelerationResolution(
        policy: resolved,
        requestedPolicy: requestedPolicy,
        fallbackReason: nil
    )
}

private func isGreedySpeculativeSampling(_ sampling: Melix_Worker_V1_SamplingConfig) -> Bool {
    let effectiveTopP = sampling.topP > 0 ? sampling.topP : 1
    return sampling.temperature <= 0
        && effectiveTopP >= 1
        && sampling.topK == 0
}

private func parseBool(_ rawValue: String?, fallback: Bool) -> Bool {
    guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), !rawValue.isEmpty else {
        return fallback
    }
    switch rawValue {
    case "1", "true", "yes", "on":
        return true
    case "0", "false", "no", "off":
        return false
    default:
        return fallback
    }
}

private func parsePositiveInt(_ rawValue: String?, fallback: Int) -> Int {
    guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines),
          let parsed = Int(rawValue),
          parsed > 0 else {
        return fallback
    }
    return parsed
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
