import Foundation
import MelixWorkerProtocol

struct DeterministicTextBackend: TextRuntimeBackend {
    let runtimeName: String = "deterministic-text"
    private let tokenDelayNanos: UInt64

    init(tokenDelayNanos: UInt64 = 20_000_000) {
        self.tokenDelayNanos = tokenDelayNanos
    }

    var supportsHomogeneousBatchDecode: Bool {
        true
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        let modelSource = spec.modelPath.isEmpty ? spec.modelID : spec.modelPath
        return LoadedTextModel(
            storage: [
                "model_id": spec.modelID,
                "model_path": modelSource,
            ],
            residentBytesHint: 2_048
        )
    }

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let prompt = deterministicPrompt(from: messages)
        let promptTokens = max(1, prompt.split(whereSeparator: \.isWhitespace).count)
        let appliedAcceleration = resolveDeterministicPrefillAcceleration(
            acceleration,
            prompt: prompt
        )
        let prefillDelay = deterministicPrefillDelay(
            baselineDelay: tokenDelayNanos,
            prompt: prompt,
            policy: appliedAcceleration,
            resumeHint: resumeHint
        )
        let prefillGainPct = gainPercent(
            baseline: tokenDelayNanos,
            effective: prefillDelay
        )
        let activeKVRatio = activeKVQuantizationRatioPercent(for: appliedAcceleration)
        var storage: [String: String] = [
            "prompt": prompt,
            "resume_hint": resumeHint,
            "prefill_acceleration_mode": String(describing: appliedAcceleration.mode),
            "prefill_gain_pct": String(prefillGainPct),
            "active_kv_quant_ratio": String(activeKVRatio),
        ]

        if !appliedAcceleration.prefillHint.isEmpty {
            storage["prefill_hint"] = appliedAcceleration.prefillHint
        }
        if !appliedAcceleration.activeKvQuantProfile.isEmpty {
            storage["active_kv_quant_profile"] = appliedAcceleration.activeKvQuantProfile
        }

        if prefillDelay > 0 {
            try? await Task.sleep(nanoseconds: prefillDelay)
        }

        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        storage["prefill_step_size"] = String(prefillStepSize)
        let effectiveWindowSize = Int(clamping: max(prefillStepSize, 1))
        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: storage,
                promptTokens: promptTokens
            ),
            promptTokens: promptTokens,
            requestedPrefillStepTokens: Int(clamping: prefillStepSize),
            effectivePrefillWindowTokens: effectiveWindowSize,
            appliedAcceleration: appliedAcceleration,
            acceleratedPrefillGainPct: prefillGainPct,
            activeKVQuantizationRatio: activeKVRatio
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let prompt = deterministicPrompt(from: messages)
        let promptTokens = max(1, prompt.split(whereSeparator: \.isWhitespace).count)
        let response = "Echo: \(prompt.isEmpty ? "empty" : prompt)"
        let chunks = response
            .split(separator: " ", omittingEmptySubsequences: false)
            .enumerated()
            .map { index, part in
                index == response.split(separator: " ", omittingEmptySubsequences: false).count - 1
                    ? String(part)
                    : "\(part) "
            }

        return AsyncThrowingStream { continuation in
            continuation.yield(.prefillStarted(promptTokens: promptTokens))

            Task {
                let startedAt = ContinuousClock.now
                var emitted = 0

                for chunk in chunks {
                    if shouldAbort() {
                        break
                    }
                    if tokenDelayNanos > 0 {
                        try? await Task.sleep(nanoseconds: tokenDelayNanos)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    continuation.yield(.token(chunk))
                }

                let elapsed = startedAt.duration(to: .now)
                let elapsedSeconds = max(
                    Double(elapsed.components.seconds) + Double(elapsed.components.attoseconds) / 1_000_000_000_000_000_000,
                    0.000_001
                )
                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: promptTokens,
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) / elapsedSeconds : 0
                    )
                ))
                continuation.finish()
            }
        }
    }

    func decodeEvents(
        model: LoadedTextModel,
        draftModel: LoadedTextModel? = nil,
        context: TextPrefillContext,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let prompt = deterministicPrompt(from: context)
        let promptTokens = max(1, context.promptTokens)
        let response = deterministicDecodeResponse(prompt: prompt, prefillToken: prefillToken)
        let outputTokens = deterministicChunks(
            from: response,
            maxOutputTokens: maxOutputTokens
        )
        let tokenDelay = deterministicDecodeDelay(
            baselineDelay: tokenDelayNanos,
            mode: acceleration.mode,
            context: context
        )

        return AsyncThrowingStream { continuation in
            Task {
                let startedAt = ContinuousClock.now
                var emitted = 0

                for chunk in outputTokens {
                    if shouldAbort() {
                        break
                    }
                    if tokenDelay > 0 {
                        try? await Task.sleep(nanoseconds: tokenDelay)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    continuation.yield(.token(chunk))
                }

                let elapsed = startedAt.duration(to: .now)
                let elapsedSeconds = max(
                    Double(elapsed.components.seconds) + Double(elapsed.components.attoseconds) / 1_000_000_000_000_000_000,
                    0.000_001
                )
                let speculativeAccepted = acceleration.mode == .speculativeDecode ? max(emitted - 1, 0) : nil
                let speculativeRejected = acceleration.mode == .speculativeDecode && emitted > 0 ? 1 : nil

                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: promptTokens,
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) / elapsedSeconds : 0,
                        speculativeAcceptedTokens: speculativeAccepted,
                        speculativeRejectedTokens: speculativeRejected
                    )
                ))
                continuation.finish()
            }
        }
    }

    func decodeBatchEvents(
        requests: [TextRuntimeDecodeRequest]
    ) async throws -> AsyncThrowingStream<TextBatchGenerationEvent, Error> {
        let prepared = requests.map { request in
            let prompt = deterministicPrompt(from: request.context)
            let response = deterministicDecodeResponse(prompt: prompt, prefillToken: request.prefillToken)
            return DeterministicBatchDecodeState(
                promptTokens: max(1, request.context.promptTokens),
                outputTokens: deterministicChunks(
                    from: response,
                    maxOutputTokens: request.maxOutputTokens
                ),
                tokenDelayNanos: deterministicDecodeDelay(
                    baselineDelay: tokenDelayNanos,
                    mode: request.acceleration.mode,
                    context: request.context
                ),
                acceleration: request.acceleration,
                shouldAbort: request.shouldAbort
            )
        }

        return AsyncThrowingStream { continuation in
            Task {
                let startedAt = ContinuousClock.now
                let batchSize = prepared.count
                var emittedByRequest = Array(repeating: 0, count: prepared.count)
                var active = Array(repeating: true, count: prepared.count)
                var positionByRequest = Array(repeating: 0, count: prepared.count)
                var decodeLoopIterations = 0

                while active.contains(true) {
                    var yieldedInIteration = false

                    for index in prepared.indices where active[index] {
                        let state = prepared[index]
                        if state.shouldAbort() || positionByRequest[index] >= state.outputTokens.count {
                            active[index] = false
                            continue
                        }
                        if state.tokenDelayNanos > 0 {
                            try? await Task.sleep(nanoseconds: state.tokenDelayNanos)
                        }
                        if state.shouldAbort() {
                            active[index] = false
                            continue
                        }
                        let chunk = state.outputTokens[positionByRequest[index]]
                        positionByRequest[index] += 1
                        emittedByRequest[index] += 1
                        yieldedInIteration = true
                        continuation.yield(.token(requestIndex: index, text: chunk))
                    }

                    if !yieldedInIteration {
                        break
                    }
                    decodeLoopIterations += 1
                }

                let elapsed = startedAt.duration(to: .now)
                let elapsedSeconds = max(
                    Double(elapsed.components.seconds) + Double(elapsed.components.attoseconds) / 1_000_000_000_000_000_000,
                    0.000_001
                )
                let totalCompletionTokens = emittedByRequest.reduce(0, +)
                let batchTokensPerSecond = totalCompletionTokens > 0
                    ? Double(totalCompletionTokens) / elapsedSeconds
                    : 0
                let loopMicros = max(
                    1,
                    Int((elapsedSeconds * 1_000_000).rounded())
                )
                let batchProbe = DecodeBatchProbeSummary(
                    decodeLoopTotalMicros: loopMicros,
                    decodeModelTotalMicros: max(1, decodeLoopIterations),
                    decodeModelCallCount: decodeLoopIterations,
                    decodeSampleTotalMicros: max(1, totalCompletionTokens),
                    decodeSampleCallCount: totalCompletionTokens,
                    decodeTokenEvalTotalMicros: max(1, totalCompletionTokens),
                    decodeTokenEvalCallCount: totalCompletionTokens,
                    decodeTokenIDTotalMicros: max(1, totalCompletionTokens),
                    decodeTokenIDCallCount: totalCompletionTokens,
                    decodeDetokenizeTotalMicros: max(1, totalCompletionTokens),
                    decodeDetokenizeCallCount: totalCompletionTokens,
                    decodeStreamYieldTotalMicros: max(1, totalCompletionTokens),
                    decodeStreamYieldCallCount: totalCompletionTokens
                )

                for index in prepared.indices {
                    let emitted = emittedByRequest[index]
                    let state = prepared[index]
                    let speculativeAccepted = state.acceleration.mode == .speculativeDecode ? max(emitted - 1, 0) : nil
                    let speculativeRejected = state.acceleration.mode == .speculativeDecode && emitted > 0 ? 1 : nil
                    continuation.yield(.summary(
                        requestIndex: index,
                        TextGenerationSummary(
                            promptTokens: state.promptTokens,
                            completionTokens: emitted,
                            tokensPerSecond: emitted > 0 ? Double(emitted) / elapsedSeconds : 0,
                            decodeBatchSize: batchSize,
                            modelEvalBatchSize: batchSize,
                            decodeLoopIterations: decodeLoopIterations,
                            perBatchOutputTokenCount: totalCompletionTokens,
                            perBatchOutputTokensPerSecond: batchTokensPerSecond,
                            speculativeAcceptedTokens: speculativeAccepted,
                            speculativeRejectedTokens: speculativeRejected,
                            decodeBatchProbe: batchProbe
                        )
                    ))
                }
                continuation.yield(.batchSummary(
                    TextBatchGenerationSummary(
                        decodeBatchSize: batchSize,
                        modelEvalBatchSize: batchSize,
                        decodeLoopIterations: decodeLoopIterations,
                        outputTokenCount: totalCompletionTokens,
                        tokensPerSecond: batchTokensPerSecond
                    )
                ))
                continuation.finish()
            }
        }
    }
}

private struct DeterministicBatchDecodeState: @unchecked Sendable {
    let promptTokens: Int
    let outputTokens: [String]
    let tokenDelayNanos: UInt64
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let shouldAbort: @Sendable () -> Bool
}

private func deterministicPrompt(
    from messages: [Melix_Worker_V1_ChatMessage]
) -> String {
    let lines = messages.compactMap { message -> String? in
        try? flattenTextContent(from: message)
    }.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }

    return lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
}

private func deterministicPrompt(
    from context: TextPrefillContext
) -> String {
    ((context.storage as? [String: String])?["prompt"] ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

private func deterministicDecodeResponse(
    prompt: String,
    prefillToken: String
) -> String {
    let base = prompt.isEmpty ? "empty" : prompt
    if prefillToken.isEmpty {
        return "Decoded: \(base)"
    }
    return "Decoded: \(prefillToken) \(base)"
}

private func deterministicChunks(
    from response: String,
    maxOutputTokens: UInt32
) -> [String] {
    let chunks = response
        .split(separator: " ", omittingEmptySubsequences: false)
        .enumerated()
        .map { index, part in
            index == response.split(separator: " ", omittingEmptySubsequences: false).count - 1
                ? String(part)
                : "\(part) "
        }

    guard maxOutputTokens > 0 else {
        return chunks
    }
    return Array(chunks.prefix(Int(maxOutputTokens)))
}

private func deterministicDecodeDelay(
    baselineDelay: UInt64,
    mode: Melix_Worker_V1_AccelerationMode,
    context: TextPrefillContext
) -> UInt64 {
    let storage = context.storage as? [String: String]
    let resumeHint = storage?["resume_hint"]?.lowercased() ?? ""
    if resumeHint.contains("snapshot-restore:") {
        if resumeHint.contains(":partial:") {
            return max(baselineDelay / 4, 1_000_000)
        }
        return max(baselineDelay / 8, 1_000_000)
    }
    let prefillMode = storage?["prefill_acceleration_mode"]?.lowercased() ?? ""
    if prefillMode.contains("acceleratedprefill") {
        return max(baselineDelay / 3, 1_000_000)
    }

    switch mode {
    case .speculativeDecode:
        return max(baselineDelay / 2, 1_000_000)
    default:
        return baselineDelay
    }
}

private func deterministicPrefillDelay(
    baselineDelay: UInt64,
    prompt: String,
    policy: Melix_Worker_V1_AccelerationPolicy,
    resumeHint: String
) -> UInt64 {
    let normalized = normalizedAccelerationPolicy(policy)
    if resumeHint.lowercased().contains("snapshot-restore:") {
        if resumeHint.lowercased().contains(":partial:") {
            return max(baselineDelay / 4, 1_000_000)
        }
        return max(baselineDelay / 8, 1_000_000)
    }
    if normalized.mode == .sparsePrefill {
        guard promptLooksStructuredForPrefill(prompt) else {
            return baselineDelay
        }
        return max(baselineDelay / 6, 1_000_000)
    }
    guard normalized.mode == .acceleratedPrefill else {
        return baselineDelay
    }

    let hint = normalized.prefillHint.lowercased()
    let isStructured = promptLooksStructuredForPrefill(prompt)
    if hint.contains("lookup") || hint.contains("schema") || isStructured {
        return max(baselineDelay / 5, 1_000_000)
    }
    return max(baselineDelay / 3, 1_000_000)
}

private func resolveDeterministicPrefillAcceleration(
    _ policy: Melix_Worker_V1_AccelerationPolicy,
    prompt: String
) -> Melix_Worker_V1_AccelerationPolicy {
    var normalized = normalizedAccelerationPolicy(policy)
    if normalized.mode == .acceleratedPrefill,
       normalized.prefillHint.isEmpty,
       promptLooksStructuredForPrefill(prompt) {
        normalized.prefillHint = "structured-reuse"
    }
    if normalized.mode == .sparsePrefill,
       normalized.prefillHint == "sparse-prefill",
       promptLooksStructuredForPrefill(prompt) {
        normalized.prefillHint = "sparse-prefill:structured"
    }
    return normalized
}
