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
                execution: request.execution,
                messages: request.messages,
                prefillStepSize: request.prefillStepSize,
                returnDecodeHandle: request.returnDecodeHandle,
                resumeHint: request.resumeHint,
                acceleration: acceleration,
                shouldAbort: { abortHandle?.isAborted ?? false }
            )

            metrics.recordMilliseconds("swift_text.prefill_ms", value: elapsedMilliseconds(since: startedAt))
            metrics.set("swift_text.prefill_prompt_tokens", value: Int(clamping: result.promptTokens))
            let prefillChunkBoundaries = makeBoundarySafePrefillChunkBoundaries(
                messages: request.messages,
                chunkTokenTarget: request.prefillStepSize,
                restoredTokenCount: result.restorePlan?.restoredTokenCount ?? 0
            )
            metrics.set("swift_text.prefill_chunk_count", value: prefillChunkBoundaries.count)
            metrics.set(
                "swift_text.prefill_chunk_target_tokens",
                value: Int(clamping: request.prefillStepSize)
            )
            metrics.set(
                "swift_text.prefill_last_chunk_tokens",
                value: Int(clamping: prefillChunkBoundaries.last ?? 0)
            )
            metrics.set("swift_text.prefill_context_count", value: await registry.prefillContextCount())
            metrics.set("swift_text.accelerated_prefill_gain_pct", value: result.acceleratedPrefillGainPct)
            let sparsePrefill = sparsePrefillPlan(
                for: request.messages,
                policy: result.appliedAcceleration
            )
            metrics.set(
                "swift_text.sparse_prefill_accepted_skip_count",
                value: sparsePrefill.acceptedSkipCount
            )
            metrics.set(
                "swift_text.sparse_prefill_rejected_opportunity_count",
                value: sparsePrefill.rejectedOpportunityCount
            )
            metrics.set(
                "swift_text.sparse_prefill_protected_region_count",
                value: sparsePrefill.protectedRegionCount
            )
            metrics.set("swift_text.active_kv_quantization_ratio", value: result.activeKVQuantizationRatio)
            metrics.set("swift_text.cache_l1_bytes", value: Int(clamping: result.cacheStats.l1Bytes))
            metrics.set("swift_text.cache_block_count", value: Int(clamping: result.cacheStats.blockCount))
            metrics.set(
                "swift_text.cache_prefix_count",
                value: result.hotPrefixCount
            )
            metrics.set(
                "swift_text.cache_pinned_prefix_count",
                value: Int(clamping: result.cacheStats.pinnedPrefixCount)
            )
            metrics.set(
                "swift_text.cache_l1_hit_rate",
                value: Int((result.cacheStats.l1HitRate * 100.0).rounded())
            )
            metrics.set(
                "swift_text.cache_block_reuse_ratio",
                value: Int((result.cacheStats.dedupRatio * 100.0).rounded())
            )
            metrics.set(
                "swift_text.cache_exact_hit_count",
                value: Int(clamping: result.cacheHitTaxonomy.exactHitCount)
            )
            metrics.set(
                "swift_text.cache_partial_hit_count",
                value: Int(clamping: result.cacheHitTaxonomy.partialHitCount)
            )
            metrics.set(
                "swift_text.cache_fallback_count",
                value: Int(clamping: result.cacheHitTaxonomy.fallbackCount)
            )
            metrics.set(
                "swift_text.cache_reconstruction_failure_count",
                value: Int(clamping: result.cacheHitTaxonomy.reconstructionFailureCount)
            )
            if !result.restoredSnapshotID.isEmpty {
                metrics.recordMilliseconds(
                    "swift_text.cache_snapshot_restore_ms",
                    value: elapsedMilliseconds(since: startedAt)
                )
            }
            if let restorePlan = result.restorePlan {
                metrics.set(
                    "swift_text.partial_restore_restored_tokens",
                    value: Int(clamping: restorePlan.restoredTokenCount)
                )
                metrics.set(
                    "swift_text.partial_restore_total_tokens",
                    value: result.promptTokens
                )
                metrics.set(
                    "swift_text.partial_restore_last_ratio_pct",
                    value: result.promptTokens > 0
                        ? Int(
                            (Double(restorePlan.restoredTokenCount)
                                / Double(result.promptTokens) * 100.0
                            ).rounded()
                        )
                        : 0
                )
                if restorePlan.partial {
                    metrics.increment("swift_text.partial_restore_walk_back_count")
                }
            }

            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = true
            response.decodeHandle = result.decodeHandle
            response.blockTableID = result.blockTableID
            response.blockTable = result.blockTable
            response.promptTokens = UInt32(max(0, result.promptTokens))
            response.restoredSnapshotID = result.restoredSnapshotID
            response.lifecyclePhase = .executionPrefilling
            response.admissionState = .admissionAdmitted
            response.appliedAcceleration = result.appliedAcceleration
            if let restorePlan = result.restorePlan {
                response.restorePlan = restorePlan
            }
            return response
        } catch let error as WorkerRuntimeRegistryError where error == .unknownModelHandle {
            metrics.increment("swift_text.rpc_error_count")
            metrics.recordMilliseconds("swift_text.prefill_ms", value: elapsedMilliseconds(since: startedAt))

            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = false
            response.error = makePrefillErrorStatus(code: "not_found", message: "Unknown model handle.")
            return response
        } catch let error as WorkerRuntimeRegistryError where error.explicitPrefillErrorCode != nil {
            metrics.increment("swift_text.rpc_error_count")
            metrics.increment("swift_text.prefill_guard_rejection_count")
            if let promptTokens = error.explicitPrefillErrorDetails["prompt_tokens"].flatMap(Int.init) {
                metrics.set("swift_text.prefill_guard_last_prompt_tokens", value: promptTokens)
            }
            if let requiredBytes = error.explicitPrefillErrorDetails["required_bytes"].flatMap(Int.init) {
                metrics.set("swift_text.prefill_guard_last_required_bytes", value: requiredBytes)
            }
            if let budgetBytes = error.explicitPrefillErrorDetails["budget_bytes"].flatMap(Int.init) {
                metrics.set("swift_text.prefill_guard_last_budget_bytes", value: budgetBytes)
            }
            if case .contextLimitExceeded = error {
                metrics.increment("swift_text.prefill_context_limit_rejection_count")
            } else if case .prefillMemoryGuardExceeded = error {
                metrics.increment("swift_text.prefill_memory_guard_rejection_count")
            } else if case .quadraticPrefillGuardExceeded = error {
                metrics.increment("swift_text.prefill_quadratic_guard_rejection_count")
            }
            metrics.recordMilliseconds("swift_text.prefill_ms", value: elapsedMilliseconds(since: startedAt))

            var response = Melix_Worker_V1_PrefillResponse()
            response.ok = false
            response.error = makePrefillErrorStatus(
                code: error.explicitPrefillErrorCode ?? "runtime_error",
                message: error.localizedDescription,
                details: error.explicitPrefillErrorDetails
            )
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
    message: String,
    details: [String: String] = [:]
) -> Melix_Worker_V1_ErrorStatus {
    var status = Melix_Worker_V1_ErrorStatus()
    status.code = code
    status.message = message
    status.retriable = false
    status.details = details
    return status
}
