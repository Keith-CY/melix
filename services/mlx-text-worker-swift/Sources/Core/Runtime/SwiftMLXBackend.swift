import Foundation
import MelixWorkerProtocol

#if canImport(MLX)
@preconcurrency import MLX
#endif
#if canImport(MLXLMCommon)
@preconcurrency import MLXLMCommon
#endif
#if canImport(MLXLLM)
@preconcurrency import MLXLLM
#endif

struct RuntimeUnavailableError: LocalizedError {
    let message: String

    var errorDescription: String? {
        message
    }
}

struct PreparedTextGeneration: Sendable {
    let promptTokens: Int
    let runtimeEvents: AsyncThrowingStream<RawTextGenerationEvent, Error>
}

struct PreparedPrefillContext: @unchecked Sendable {
    let preparedInput: Any
    let promptTokens: Int
    let activeKVQuantizationRatio: Int
}

#if canImport(MLXLMCommon)
struct PreparedDecodeState: @unchecked Sendable {
    let input: LMInput
    let prepared: PrepareResult
    let cache: [KVCache]
    let promptPrefillTime: TimeInterval
    let prefillQuantizeMicros: Int
    let activeKVQuantizationRatio: Int
}
#endif

enum RawTextGenerationEvent: Sendable {
    case chunk(String)
    case summary(TextGenerationSummary)
}

struct AutoSwiftMLXBackend: TextRuntimeBackend {
    let runtimeName: String
    let turboQuantCandidateProbeEnabled: Bool

    private let directLoader: (@Sendable (String) async throws -> LoadedTextModel)?
    private let directoryLoader: @Sendable (URL) async throws -> LoadedTextModel
    private let identifierLoader: @Sendable (String, String) async throws -> LoadedTextModel
    private let preparedGenerationFactory: @Sendable (
        LoadedTextModel,
        [Melix_Worker_V1_ChatMessage],
        Melix_Worker_V1_SamplingConfig
    ) async throws -> PreparedTextGeneration

    init(
        runtimeName: String? = nil,
        turboQuantCandidateProbeEnabled: Bool = false,
        loader: (@Sendable (String) async throws -> Any)? = nil,
        directoryLoader: (@Sendable (URL) async throws -> LoadedTextModel)? = nil,
        identifierLoader: (@Sendable (String, String) async throws -> LoadedTextModel)? = nil,
        preparedGenerationFactory: (@Sendable (
            LoadedTextModel,
            [Melix_Worker_V1_ChatMessage],
            Melix_Worker_V1_SamplingConfig
        ) async throws -> PreparedTextGeneration)? = nil
    ) {
        if let loader {
            self.directLoader = { modelSource in
                LoadedTextModel(storage: try await loader(modelSource))
            }
        } else {
            self.directLoader = nil
        }

        if let directoryLoader {
            self.directoryLoader = directoryLoader
        } else {
            #if canImport(MLXLMCommon)
            self.directoryLoader = { directoryURL in
                LoadedTextModel(
                    storage: try await MLXLMCommon.loadModelContainer(directory: directoryURL)
                )
            }
            #else
            self.directoryLoader = { _ in
                throw RuntimeUnavailableError(
                    message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before loading models."
                )
            }
            #endif
        }

        if let identifierLoader {
            self.identifierLoader = identifierLoader
        } else {
            #if canImport(MLXLMCommon)
            self.identifierLoader = { modelSource, revision in
                LoadedTextModel(
                    storage: try await MLXLMCommon.loadModelContainer(
                        id: modelSource,
                        revision: revision
                    )
                )
            }
            #else
            self.identifierLoader = { _, _ in
                throw RuntimeUnavailableError(
                    message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before loading models."
                )
            }
            #endif
        }

        self.preparedGenerationFactory = preparedGenerationFactory ?? { model, messages, sampling in
            try await makePreparedTextGeneration(
                model: model,
                messages: messages,
                sampling: sampling
            )
        }
        self.turboQuantCandidateProbeEnabled = turboQuantCandidateProbeEnabled

        if let runtimeName {
            self.runtimeName = runtimeName
        } else {
            #if canImport(MLXLMCommon)
            self.runtimeName = "mlx-swift-lm"
            #else
            self.runtimeName = "swift-mlx-unavailable"
            #endif
        }
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        let modelSource = spec.modelPath.isEmpty ? spec.modelID : spec.modelPath

        if let directLoader {
            return try await directLoader(modelSource)
        }

        if FileManager.default.fileExists(atPath: modelSource) {
            return try await directoryLoader(URL(fileURLWithPath: modelSource, isDirectory: true))
        }

        let revision = spec.revision.isEmpty ? "main" : spec.revision
        return try await identifierLoader(modelSource, revision)
    }

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        let appliedAcceleration = resolveSwiftPrefillAcceleration(acceleration, messages: messages)
        let baseWindowSize = Int(max(prefillStepSize, 1))
        let effectiveWindowSize = acceleratedPrefillWindowSize(
            baseWindowSize: baseWindowSize,
            policy: appliedAcceleration,
            messages: messages
        )
        let prepared = try await makePreparedPromptContext(
            model: model,
            messages: messages,
            prefillStepSize: prefillStepSize,
            acceleration: appliedAcceleration,
            turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
        )
        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: prepared.preparedInput,
                promptTokens: prepared.promptTokens
            ),
            promptTokens: prepared.promptTokens,
            appliedAcceleration: appliedAcceleration,
            acceleratedPrefillGainPct: estimatedPrefillGainPercent(
                baselineWindowSize: baseWindowSize,
                effectiveWindowSize: effectiveWindowSize
            ),
            activeKVQuantizationRatio: prepared.activeKVQuantizationRatio
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let prepared = try await preparedGenerationFactory(model, messages, sampling)

        return AsyncThrowingStream { continuation in
            continuation.yield(.prefillStarted(promptTokens: prepared.promptTokens))

            Task {
                var emittedTokenCount = 0
                var summary = TextGenerationSummary(
                    promptTokens: prepared.promptTokens,
                    completionTokens: 0,
                    tokensPerSecond: nil
                )

                do {
                    for try await runtimeEvent in prepared.runtimeEvents {
                        if shouldAbort() {
                            break
                        }

                        switch runtimeEvent {
                        case .chunk(let text):
                            guard !text.isEmpty else {
                                continue
                            }
                            emittedTokenCount += 1
                            continuation.yield(.token(text))
                        case .summary(let runtimeSummary):
                            summary = runtimeSummary
                        }
                    }

                    if summary.completionTokens == 0 {
                        summary = TextGenerationSummary(
                            promptTokens: prepared.promptTokens,
                            completionTokens: emittedTokenCount,
                            tokensPerSecond: nil
                        )
                    }

                    continuation.yield(.summary(summary))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    func decodeEvents(
        model: LoadedTextModel,
        context: TextPrefillContext,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let effectiveAcceleration = try resolveSwiftDecodeAcceleration(acceleration)
        let prepared = try await makePreparedDecodeGeneration(
            model: model,
            context: context,
            sampling: sampling,
            maxOutputTokens: maxOutputTokens,
            decodeStepSize: decodeStepSize,
            prefillToken: prefillToken,
            acceleration: effectiveAcceleration,
            turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
        )

        return AsyncThrowingStream { continuation in
            Task {
                var emittedTokenCount = 0
                var summary = TextGenerationSummary(
                    promptTokens: prepared.promptTokens,
                    completionTokens: 0,
                    tokensPerSecond: nil
                )

                do {
                    for try await runtimeEvent in prepared.runtimeEvents {
                        if shouldAbort() {
                            break
                        }

                        switch runtimeEvent {
                        case .chunk(let text):
                            guard !text.isEmpty else {
                                continue
                            }
                            continuation.yield(.token(text))
                        case .summary(let runtimeSummary):
                            summary = runtimeSummary
                            emittedTokenCount = runtimeSummary.completionTokens
                        }
                    }

                    if summary.completionTokens == 0 {
                        summary = TextGenerationSummary(
                            promptTokens: prepared.promptTokens,
                            completionTokens: emittedTokenCount,
                            tokensPerSecond: nil
                        )
                    }

                    continuation.yield(.summary(summary))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}

func convertChatMessages(
    _ messages: [Melix_Worker_V1_ChatMessage]
) throws -> [Chat.Message] {
    guard !messages.isEmpty else {
        throw RuntimeUnavailableError(message: "Generate requires at least one chat message.")
    }

    return try messages.map { message in
        let content = try flattenTextContent(from: message)

        switch message.role.lowercased() {
        case "system":
            return .system(content)
        case "assistant":
            return .assistant(content)
        case "tool":
            return .tool(content)
        case "user", "":
            return .user(content)
        default:
            throw RuntimeUnavailableError(
                message: "Unsupported chat role '\(message.role)' for Swift text generation."
            )
        }
    }
}

func flattenTextContent(
    from message: Melix_Worker_V1_ChatMessage
) throws -> String {
    var fragments: [String] = []

    for part in message.parts {
        switch part.part {
        case .text(let text):
            fragments.append(text)
        case .some:
            throw RuntimeUnavailableError(
                message: "Only text message parts are supported in the Swift text worker during Phase 1."
            )
        case .none:
            continue
        }
    }

    return fragments.joined(separator: "\n")
}

func makeGenerateParameters(
    from sampling: Melix_Worker_V1_SamplingConfig
) -> GenerateParameters {
    let repetitionPenalty = max(sampling.frequencyPenalty, sampling.presencePenalty)

    return GenerateParameters(
        maxTokens: sampling.maxOutputTokens > 0 ? Int(sampling.maxOutputTokens) : 256,
        temperature: sampling.temperature,
        topP: sampling.topP > 0 ? sampling.topP : 1.0,
        repetitionPenalty: repetitionPenalty > 0 ? repetitionPenalty : nil
    )
}

private func makePreparedTextGeneration(
    model: LoadedTextModel,
    messages: [Melix_Worker_V1_ChatMessage],
    sampling: Melix_Worker_V1_SamplingConfig
) async throws -> PreparedTextGeneration {
    #if canImport(MLXLMCommon)
    guard let container = model.storage as? ModelContainer else {
        throw RuntimeUnavailableError(
            message: "Loaded model is not a Swift MLX model container."
        )
    }

    let chat = try convertChatMessages(messages)
    let userInput = UserInput(chat: chat)
    let input = try await container.prepare(input: userInput)
    let promptTokens = input.text.tokens.size
    let parameters = makeGenerateParameters(from: sampling)
    let runtimeStream = try await container.generate(input: input, parameters: parameters)

    let mappedEvents = AsyncThrowingStream<RawTextGenerationEvent, Error> { continuation in
        Task {
            for await generation in runtimeStream {
                switch generation {
                case .chunk(let text):
                    continuation.yield(.chunk(text))
                case .info(let info):
                    continuation.yield(.summary(
                        TextGenerationSummary(
                            promptTokens: info.promptTokenCount,
                            completionTokens: info.generationTokenCount,
                            tokensPerSecond: info.tokensPerSecond
                        )
                    ))
                case .toolCall:
                    continue
                }
            }
            continuation.finish()
        }
    }

    return PreparedTextGeneration(
        promptTokens: promptTokens,
        runtimeEvents: mappedEvents
    )
    #else
    throw RuntimeUnavailableError(
        message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before generating tokens."
    )
    #endif
}

private func makePreparedPromptContext(
    model: LoadedTextModel,
    messages: [Melix_Worker_V1_ChatMessage],
    prefillStepSize: UInt32,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) async throws -> PreparedPrefillContext {
    #if canImport(MLXLMCommon)
    guard let container = model.storage as? ModelContainer else {
        throw RuntimeUnavailableError(
            message: "Loaded model is not a Swift MLX model container."
        )
    }

    let chat = try convertChatMessages(messages)
    let userInput = UserInput(chat: chat)
    let effectiveWindowSize = acceleratedPrefillWindowSize(
        baseWindowSize: Int(max(prefillStepSize, 1)),
        policy: acceleration,
        messages: messages
    )
    let preparedState = try await container.perform { context in
        let input = try await context.processor.prepare(input: userInput)
        var cache = context.model.newCache(parameters: nil)
        let startedAt = Date.timeIntervalSinceReferenceDate
        let prepared = try context.model.prepare(
            input,
            cache: cache,
            windowSize: effectiveWindowSize
        )
        let quantizeStartedAt = Date.timeIntervalSinceReferenceDate
        applyActiveKVQuantizationIfNeeded(
            cache: &cache,
            acceleration: acceleration,
            turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
        )
        let prefillQuantizeMicros = elapsedMicros(since: quantizeStartedAt)
        let promptPrefillTime = Date.timeIntervalSinceReferenceDate - startedAt
        return PreparedDecodeState(
            input: input,
            prepared: prepared,
            cache: cache,
            promptPrefillTime: promptPrefillTime,
            prefillQuantizeMicros: prefillQuantizeMicros,
            activeKVQuantizationRatio: activeKVRuntimeQuantizationRatioPercent(
                for: acceleration,
                cache: cache
            )
        )
    }
    return PreparedPrefillContext(
        preparedInput: preparedState,
        promptTokens: preparedState.input.text.tokens.size,
        activeKVQuantizationRatio: preparedState.activeKVQuantizationRatio
    )
    #else
    throw RuntimeUnavailableError(
        message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before preparing prompts."
    )
    #endif
}

private func resolveSwiftPrefillAcceleration(
    _ acceleration: Melix_Worker_V1_AccelerationPolicy,
    messages: [Melix_Worker_V1_ChatMessage]
) -> Melix_Worker_V1_AccelerationPolicy {
    var normalized = normalizedAccelerationPolicy(acceleration)
    if normalized.mode == .sparsePrefill {
        let plan = sparsePrefillPlan(for: messages, policy: normalized)
        normalized.prefillHint = "sparse-prefill:accepted=\(plan.acceptedSkipCount)"
    }
    return normalized
}

private func acceleratedPrefillWindowSize(
    baseWindowSize: Int,
    policy: Melix_Worker_V1_AccelerationPolicy,
    messages: [Melix_Worker_V1_ChatMessage]
) -> Int {
    let normalized = normalizedAccelerationPolicy(policy)
    if normalized.mode == .sparsePrefill {
        let plan = sparsePrefillPlan(for: messages, policy: normalized)
        guard plan.acceptedSkipCount > 0 else {
            return baseWindowSize
        }
        return max(baseWindowSize, 16 + (plan.acceptedSkipCount * 16))
    }
    guard normalized.mode == .acceleratedPrefill else {
        return baseWindowSize
    }

    let hint = normalized.prefillHint.lowercased()
    if hint.contains("lookup") || hint.contains("schema") || hint.contains("json") {
        return max(baseWindowSize, 32)
    }
    if hint.contains("code") || hint.contains("structured") {
        return max(baseWindowSize, 24)
    }
    return max(baseWindowSize, 16)
}

private func estimatedPrefillGainPercent(
    baselineWindowSize: Int,
    effectiveWindowSize: Int
) -> Int {
    guard effectiveWindowSize > baselineWindowSize, baselineWindowSize > 0 else {
        return 0
    }

    return max(
        0,
        min(90, ((effectiveWindowSize - baselineWindowSize) * 100) / effectiveWindowSize)
    )
}

private func resolveSwiftDecodeAcceleration(
    _ acceleration: Melix_Worker_V1_AccelerationPolicy
) throws -> Melix_Worker_V1_AccelerationPolicy {
    guard acceleration.mode == .speculativeDecode else {
        return acceleration
    }

    if acceleration.allowBaselineFallback {
        var baseline = acceleration
        baseline.mode = .baseline
        return baseline
    }

    throw RuntimeUnavailableError(
        message: "Speculative decode is not yet available for the Swift MLX backend."
    )
}

private func makeDecodeParameters(
    from sampling: Melix_Worker_V1_SamplingConfig,
    maxOutputTokens: UInt32,
    decodeStepSize: UInt32,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) -> GenerateParameters {
    var parameters = makeGenerateParameters(from: sampling)

    if maxOutputTokens > 0 {
        parameters.maxTokens = Int(maxOutputTokens)
    }
    if decodeStepSize > 0 {
        parameters.prefillStepSize = Int(decodeStepSize)
    }

    if shouldUseActiveKVQuantization(
        for: acceleration,
        turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
    ) {
        applyActiveKVQuantizationProfile(
            to: &parameters,
            profile: acceleration.activeKvQuantProfile
        )
    }

    return parameters
}

private func applyActiveKVQuantizationProfile(
    to parameters: inout GenerateParameters,
    profile: String
) {
    let normalizedProfile = profile.lowercased()
    parameters.kvBits = normalizedProfile.contains("q8") ? 8 : 4
    parameters.quantizedKVStart = 0
}

private func isTurboQuantProfile(_ profile: String) -> Bool {
    profile.lowercased().hasPrefix("turboquant")
}

func turboQuantAffineFallbackEnabled(
    environment: [String: String] = ProcessInfo.processInfo.environment
) -> Bool {
    guard let rawValue = environment["MELIX_SWIFT_TURBOQUANT_AFFINE_FALLBACK"] else {
        return false
    }
    switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "1", "true", "yes", "on":
        return true
    default:
        return false
    }
}

func shouldUseActiveKVQuantization(
    for acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) -> Bool {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard normalized.mode == .activeKvQuantized else {
        return false
    }
    // TurboQuant now has a vendored q4 fused attention route. The candidate probe flag
    // only controls the synthetic capability smoke dispatch, not runtime enablement.
    _ = turboQuantCandidateProbeEnabled
    return true
}

#if canImport(MLXLMCommon)
enum TurboQuantRuntimeFusedAttentionBlockReason: Equatable {
    case unsupportedCacheState
    case attentionHookUnavailable
}

enum TurboQuantRuntimeFusedAttentionRoute: Equatable {
    case disabled
    case blocked(TurboQuantRuntimeFusedAttentionBlockReason)
    case routed
}

private func applyActiveKVQuantizationIfNeeded(
    cache: inout [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard shouldUseActiveKVQuantization(
        for: normalized,
        turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
    ) else {
        return
    }

    var parameters = makeGenerateParameters(from: Melix_Worker_V1_SamplingConfig())
    applyActiveKVQuantizationProfile(
        to: &parameters,
        profile: normalized.activeKvQuantProfile
    )
    maybeQuantizeKVCache(
        cache: &cache,
        kvBits: parameters.kvBits,
        kvGroupSize: parameters.kvGroupSize,
        quantizedKVStart: parameters.quantizedKVStart
    )
}

func shouldAttemptActiveKVDecodeQuantization(
    cache: [KVCache],
    kvBits: Int?,
    quantizedKVStart: Int,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) -> Bool {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard shouldUseActiveKVQuantization(
        for: normalized,
        turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
    ), kvBits != nil else {
        return false
    }
    guard let firstCache = cache.first, firstCache.offset > quantizedKVStart else {
        return false
    }
    return !(firstCache is QuantizedKVCacheProtocol)
}

private func activeKVRuntimeQuantizationRatioPercent(
    for acceleration: Melix_Worker_V1_AccelerationPolicy,
    cache: [KVCache]
) -> Int {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard normalized.mode == .activeKvQuantized,
          cache.contains(where: { $0 is QuantizedKVCacheProtocol })
    else {
        return 0
    }
    return activeKVQuantizationRatioPercent(for: normalized)
}
#endif

private func makePreparedDecodeGeneration(
    model: LoadedTextModel,
    context: TextPrefillContext,
    sampling: Melix_Worker_V1_SamplingConfig,
    maxOutputTokens: UInt32,
    decodeStepSize: UInt32,
    prefillToken: String,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) async throws -> PreparedTextGeneration {
    #if canImport(MLXLMCommon)
    _ = prefillToken

    guard let container = model.storage as? ModelContainer else {
        throw RuntimeUnavailableError(
            message: "Loaded model is not a Swift MLX model container."
        )
    }
    guard let decodeState = context.storage as? PreparedDecodeState else {
        throw RuntimeUnavailableError(
            message: "Decode context is not a prepared Swift MLX prefill state."
        )
    }

    let parameters = makeDecodeParameters(
        from: sampling,
        maxOutputTokens: maxOutputTokens,
        decodeStepSize: decodeStepSize,
        acceleration: acceleration,
        turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
    )

    let runtimeEvents = try await container.perform(values: decodeState) { modelContext, decodeState in
        try makePreparedDecodeEvents(
            decodeState: decodeState,
            context: modelContext,
            parameters: parameters,
            acceleration: acceleration,
            turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
        )
    }

    return PreparedTextGeneration(
        promptTokens: decodeState.input.text.tokens.size,
        runtimeEvents: runtimeEvents
    )
    #else
    throw RuntimeUnavailableError(
        message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before decoding."
    )
    #endif
}

#if canImport(MLXLMCommon)
private func makePreparedDecodeEvents(
    decodeState: PreparedDecodeState,
    context: ModelContext,
    parameters: GenerateParameters,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    turboQuantCandidateProbeEnabled: Bool = false
) throws -> AsyncThrowingStream<RawTextGenerationEvent, Error> {
    let (stream, continuation) = AsyncThrowingStream<RawTextGenerationEvent, Error>.makeStream()

    let task = Task {
        do {
            var cache = decodeState.cache
            var processor = parameters.processor()
            let sampler = parameters.sampler()
            processor?.prompt(decodeState.input.text.tokens)
            var decodeModelTotalMicros = 0
            var decodeModelCallCount = 0
            var decodeTokenEvalTotalMicros = 0
            var decodeTokenEvalCallCount = 0
            var decodeQuantizeTotalMicros = 0
            var prefillQuantizeMicros = decodeState.prefillQuantizeMicros

            let additionalEOSTokenIds = Set(
                context.configuration.extraEOSTokens.compactMap {
                    context.tokenizer.convertTokenToId($0)
                }
            )
            var detokenizer = NaiveStreamingDetokenizer(tokenizer: context.tokenizer)
            var output = try makeInitialDecodeOutput(
                decodeState: decodeState,
                context: context,
                cache: cache
            )
            var generatedTokenCount = 0
            if parameters.kvBits != nil {
                let initialQuantizeStartedAt = Date.timeIntervalSinceReferenceDate
                maybeQuantizeKVCache(
                    cache: &cache,
                    kvBits: parameters.kvBits,
                    kvGroupSize: parameters.kvGroupSize,
                    quantizedKVStart: parameters.quantizedKVStart
                )
                prefillQuantizeMicros += elapsedMicros(since: initialQuantizeStartedAt)
            }
            var didDispatchTurboQuantFusedAttention = false
            var turboQuantCandidateEligibilityCheckCount = 0
            let shouldEvaluateTurboQuantFusedAttentionCandidate = shouldDispatchTurboQuantFusedAttentionCandidate(
                cache: cache,
                acceleration: acceleration,
                candidateProbeEnabled: turboQuantCandidateProbeEnabled
            )
            var shouldMaintainQuantizedDecodeCache = shouldAttemptActiveKVDecodeQuantization(
                cache: cache,
                kvBits: parameters.kvBits,
                quantizedKVStart: parameters.quantizedKVStart,
                acceleration: acceleration,
                turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
            )
            let startedAt = Date.timeIntervalSinceReferenceDate

            while parameters.maxTokens.map({ generatedTokenCount < $0 }) ?? true {
                if Task.isCancelled {
                    break
                }

                let tokenEvalStartedAt = Date.timeIntervalSinceReferenceDate
                let token = sampleNextToken(
                    logits: output.logits,
                    processor: &processor,
                    sampler: sampler
                )
                let tokenID = token.item(Int.self)
                decodeTokenEvalCallCount += 1
                decodeTokenEvalTotalMicros += elapsedMicros(since: tokenEvalStartedAt)

                if tokenID == context.tokenizer.unknownTokenId
                    || tokenID == context.tokenizer.eosTokenId
                    || additionalEOSTokenIds.contains(tokenID)
                {
                    break
                }

                generatedTokenCount += 1
                detokenizer.append(token: tokenID)
                if let chunk = detokenizer.next() {
                    continuation.yield(.chunk(chunk))
                }

                if let maxTokens = parameters.maxTokens, generatedTokenCount >= maxTokens {
                    break
                }

                let nextInput = LMInput.Text(tokens: token)
                if shouldEvaluateTurboQuantFusedAttentionCandidate && !didDispatchTurboQuantFusedAttention {
                    turboQuantCandidateEligibilityCheckCount += 1
                    didDispatchTurboQuantFusedAttention = dispatchTurboQuantFusedAttentionCandidateIfNeeded(
                        cache: cache,
                        acceleration: acceleration,
                        candidateProbeEnabled: turboQuantCandidateProbeEnabled
                    )
                }
                let modelStartedAt = Date.timeIntervalSinceReferenceDate
                output = context.model(
                    nextInput[text: .newAxis],
                    cache: cache.isEmpty ? nil : cache,
                    state: output.state
                )
                decodeModelCallCount += 1
                decodeModelTotalMicros += elapsedMicros(since: modelStartedAt)
                if shouldMaintainQuantizedDecodeCache {
                    let quantizeStartedAt = Date.timeIntervalSinceReferenceDate
                    maybeQuantizeKVCache(
                        cache: &cache,
                        kvBits: parameters.kvBits,
                        kvGroupSize: parameters.kvGroupSize,
                        quantizedKVStart: parameters.quantizedKVStart
                    )
                    decodeQuantizeTotalMicros += elapsedMicros(since: quantizeStartedAt)
                    shouldMaintainQuantizedDecodeCache = shouldAttemptActiveKVDecodeQuantization(
                        cache: cache,
                        kvBits: parameters.kvBits,
                        quantizedKVStart: parameters.quantizedKVStart,
                        acceleration: acceleration,
                        turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
                    )
                }
            }

            let decodeLoopTotalMicros = elapsedMicros(since: startedAt)
            let elapsed = max(Double(decodeLoopTotalMicros) / 1_000_000, 0.000_001)
            let activeKVProbe = makeActiveKVProbeSummary(
                cache: cache,
                acceleration: acceleration,
                prefillQuantizeMicros: prefillQuantizeMicros,
                decodeModelTotalMicros: decodeModelTotalMicros,
                decodeModelCallCount: decodeModelCallCount,
                decodeTokenEvalTotalMicros: decodeTokenEvalTotalMicros,
                decodeTokenEvalCallCount: decodeTokenEvalCallCount,
                decodeQuantizeTotalMicros: decodeQuantizeTotalMicros,
                decodeLoopTotalMicros: decodeLoopTotalMicros,
                decodeTokenCount: generatedTokenCount,
                turboQuantFusedAttentionDispatched: didDispatchTurboQuantFusedAttention,
                turboQuantCandidateEligibilityCheckCount: turboQuantCandidateEligibilityCheckCount
            )
            continuation.yield(.summary(
                TextGenerationSummary(
                    promptTokens: decodeState.input.text.tokens.size,
                    completionTokens: generatedTokenCount,
                    tokensPerSecond: Double(generatedTokenCount) / elapsed,
                    activeKVProbe: activeKVProbe
                )
            ))
            continuation.finish()
        } catch {
            continuation.finish(throwing: error)
        }
    }

    continuation.onTermination = { _ in
        task.cancel()
    }

    return stream
}

private func makeInitialDecodeOutput(
    decodeState: PreparedDecodeState,
    context: ModelContext,
    cache: [KVCache]
) throws -> LMOutput {
    switch decodeState.prepared {
    case .tokens(let tokens):
        return context.model(
            tokens[text: .newAxis],
            cache: cache.isEmpty ? nil : cache,
            state: nil
        )
    case .logits(let output):
        return output
    }
}

private func sampleNextToken(
    logits: MLXArray,
    processor: inout (any LogitProcessor)?,
    sampler: any LogitSampler
) -> MLXArray {
    var logits = logits[0..., -1, 0...]
    logits = processor?.process(logits: logits) ?? logits
    let token = sampler.sample(logits: logits)
    processor?.didSample(token: token)
    return token
}

private struct QuantizedKVCacheTimingTotals {
    var updateTotalMicros = 0
    var updateCallCount = 0
    var expandTotalMicros = 0
    var quantizeTotalMicros = 0
    var appendTotalMicros = 0
    var materializeTotalMicros = 0
    var materializeCallCount = 0
}

private func makeActiveKVProbeSummary(
    cache: [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    prefillQuantizeMicros: Int,
    decodeModelTotalMicros: Int,
    decodeModelCallCount: Int,
    decodeTokenEvalTotalMicros: Int,
    decodeTokenEvalCallCount: Int,
    decodeQuantizeTotalMicros: Int,
    decodeLoopTotalMicros: Int,
    decodeTokenCount: Int,
    turboQuantFusedAttentionDispatched: Bool = false,
    turboQuantCandidateEligibilityCheckCount: Int = 0
) -> ActiveKVProbeSummary? {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard normalized.mode == .activeKvQuantized else {
        return nil
    }

    let quantizationRatio = activeKVRuntimeQuantizationRatioPercent(
        for: normalized,
        cache: cache
    )
    let cacheBytes = estimatedCacheStateBytes(cache)
    let quantizedBytes = quantizationRatio > 0 ? cacheBytes : 0
    let fp16Bytes = quantizationRatio > 0
        ? estimatedFP16Bytes(quantizedBytes: quantizedBytes, quantizationRatio: quantizationRatio)
        : cacheBytes
    let turboQuantRuntimeRoute = turboQuantRuntimeFusedAttentionRoute(
        cache: cache,
        acceleration: normalized
    )
    let kernelPathCode = activeKVKernelPathCode(
        for: normalized,
        turboQuantRuntimeRoute: turboQuantRuntimeRoute
    )
    let savingsPercent: Int
    if fp16Bytes > 0, quantizedBytes > 0 {
        savingsPercent = max(0, min(100, Int(((fp16Bytes - quantizedBytes) * 100) / fp16Bytes)))
    } else if quantizationRatio > 0 {
        savingsPercent = max(0, 100 - quantizationRatio)
    } else {
        savingsPercent = 0
    }
    let cacheTiming = quantizedKVCacheTimingTotals(cache: cache)

    return ActiveKVProbeSummary(
        backendCode: activeKVBackendCode(for: normalized),
        kernelPathCode: kernelPathCode,
        runtimeRouteCode: activeKVRuntimeRouteCode(for: turboQuantRuntimeRoute),
        runtimeBlockReasonCode: activeKVRuntimeBlockReasonCode(for: turboQuantRuntimeRoute),
        quantizationRatioPercent: quantizationRatio,
        prefillQuantizeMicros: prefillQuantizeMicros,
        decodeModelTotalMicros: decodeModelTotalMicros,
        decodeModelCallCount: decodeModelCallCount,
        decodeTokenEvalTotalMicros: decodeTokenEvalTotalMicros,
        decodeTokenEvalCallCount: decodeTokenEvalCallCount,
        decodeQuantizeTotalMicros: decodeQuantizeTotalMicros,
        decodeLoopTotalMicros: decodeLoopTotalMicros,
        decodeTokenCount: decodeTokenCount,
        estimatedFP16Bytes: Int(clamping: fp16Bytes),
        estimatedQuantizedBytes: Int(clamping: quantizedBytes),
        estimatedMemorySavingsPercent: savingsPercent,
        fallbackCount: activeKVFallbackCount(
            for: normalized,
            turboQuantRuntimeRoute: turboQuantRuntimeRoute
        ),
        cacheUpdateTotalMicros: cacheTiming.updateTotalMicros,
        cacheUpdateCallCount: cacheTiming.updateCallCount,
        cacheExpandTotalMicros: cacheTiming.expandTotalMicros,
        cacheQuantizeTotalMicros: cacheTiming.quantizeTotalMicros,
        cacheAppendTotalMicros: cacheTiming.appendTotalMicros,
        cacheMaterializeTotalMicros: cacheTiming.materializeTotalMicros,
        cacheMaterializeCallCount: cacheTiming.materializeCallCount,
        candidateDispatchCode: activeKVCandidateDispatchCode(
            for: normalized,
            turboQuantFusedAttentionDispatched: turboQuantFusedAttentionDispatched
        ),
        candidateEligibilityCheckCount: turboQuantCandidateEligibilityCheckCount
    )
}

private func quantizedKVCacheTimingTotals(cache: [KVCache]) -> QuantizedKVCacheTimingTotals {
    var totals = QuantizedKVCacheTimingTotals()
    for layer in cache {
        guard let quantizedCache = layer as? QuantizedKVCacheProtocol else {
            continue
        }
        totals.updateTotalMicros += quantizedCache.quantizedCacheUpdateTotalMicros
        totals.updateCallCount += quantizedCache.quantizedCacheUpdateCallCount
        totals.expandTotalMicros += quantizedCache.quantizedCacheExpandTotalMicros
        totals.quantizeTotalMicros += quantizedCache.quantizedCacheQuantizeTotalMicros
        totals.appendTotalMicros += quantizedCache.quantizedCacheAppendTotalMicros
        totals.materializeTotalMicros += quantizedCache.quantizedCacheMaterializeTotalMicros
        totals.materializeCallCount += quantizedCache.quantizedCacheMaterializeCallCount
    }
    return totals
}

private func activeKVBackendCode(for policy: Melix_Worker_V1_AccelerationPolicy) -> Int {
    let profile = policy.activeKvQuantProfile.lowercased()
    if profile.hasPrefix("turboquant") {
        return 2
    }
    return 1
}

func activeKVKernelPathCode(
    for policy: Melix_Worker_V1_AccelerationPolicy,
    turboQuantRuntimeRoute: TurboQuantRuntimeFusedAttentionRoute = .disabled
) -> Int {
    let profile = policy.activeKvQuantProfile.lowercased()
    if profile.hasPrefix("turboquant") {
        return turboQuantRuntimeRoute == .routed ? 20 : 90
    }
    return 10
}

func activeKVFallbackCount(
    for policy: Melix_Worker_V1_AccelerationPolicy,
    turboQuantRuntimeRoute: TurboQuantRuntimeFusedAttentionRoute
) -> Int {
    activeKVKernelPathCode(
        for: policy,
        turboQuantRuntimeRoute: turboQuantRuntimeRoute
    ) == 90 ? 1 : 0
}

func activeKVRuntimeRouteCode(for route: TurboQuantRuntimeFusedAttentionRoute) -> Int {
    switch route {
    case .disabled:
        return 0
    case .blocked:
        return 1
    case .routed:
        return 2
    }
}

func activeKVRuntimeBlockReasonCode(for route: TurboQuantRuntimeFusedAttentionRoute) -> Int {
    guard case .blocked(let reason) = route else {
        return 0
    }

    switch reason {
    case .unsupportedCacheState:
        return 1
    case .attentionHookUnavailable:
        return 2
    }
}

private func activeKVCandidateDispatchCode(
    for policy: Melix_Worker_V1_AccelerationPolicy,
    turboQuantFusedAttentionDispatched: Bool
) -> Int {
    let profile = policy.activeKvQuantProfile.lowercased()
    if profile.hasPrefix("turboquant"), turboQuantFusedAttentionDispatched {
        return 1
    }
    return 0
}

private func dispatchTurboQuantFusedAttentionCandidateIfNeeded(
    cache: [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    candidateProbeEnabled: Bool = false
) -> Bool {
    guard shouldDispatchTurboQuantFusedAttentionCandidate(
        cache: cache,
        acceleration: acceleration,
        candidateProbeEnabled: candidateProbeEnabled
    ) else {
        return false
    }

    #if canImport(MLX)
    return Device.withDefaultDevice(.gpu) {
        if dispatchTurboQuantFusedAttentionCandidateFromQuantizedCacheState(cache: cache) {
            return true
        }

        let query = MLXArray([Float(0.25), Float(-0.5), Float(0.75), Float(1.0)])
        let packedKeys = MLXArray(
            [
                Int32(0x31), Int32(0x75),
                Int32(0x42), Int32(0x86),
                Int32(0x0f), Int32(0xa9),
            ],
            [3, 2]
        )
        let keyScales = MLXArray(
            [Float(0.5), Float(0.25), Float(1.0), Float(0.125), Float(0.2), Float(0.75)],
            [3, 2]
        )
        let keyBiases = MLXArray(
            [Float(-1.0), Float(0.5), Float(-2.0), Float(-0.25), Float(0.0), Float(-3.0)],
            [3, 2]
        )
        let packedValues = MLXArray(
            [
                Int32(0x10), Int32(0x32),
                Int32(0x23), Int32(0x01),
                Int32(0x11), Int32(0x11),
            ],
            [3, 2]
        )
        let valueScales = MLXArray(
            [Float(1.0), Float(0.5), Float(0.25), Float(1.0), Float(0.5), Float(0.25)],
            [3, 2]
        )
        let valueBiases = MLXArray(
            [Float(0.0), Float(-1.0), Float(0.5), Float(0.0), Float(-0.5), Float(0.25)],
            [3, 2]
        )
        let output = TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionSmokeKernel(
            query: query,
            packedKeys: packedKeys,
            keyScales: keyScales,
            keyBiases: keyBiases,
            packedValues: packedValues,
            valueScales: valueScales,
            valueBiases: valueBiases,
            sequenceLength: 3,
            headDimension: 4,
            groupSize: 2
        )
        eval(output)
        return true
    }
    #else
    return false
    #endif
}

#if canImport(MLX)
private struct SupportedTurboQuantQ4QuantizedCacheState {
    let quantizedKeys: (MLXArray, MLXArray, MLXArray?)
    let quantizedValues: (MLXArray, MLXArray, MLXArray?)
    let sequenceLength: Int
    let headDimension: Int
    let groupSize: Int
    let bits: Int
}

func shouldDispatchTurboQuantFusedAttentionCandidate(
    cache: [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    candidateProbeEnabled: Bool
) -> Bool {
    _ = cache
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard candidateProbeEnabled,
          normalized.mode == .activeKvQuantized,
          normalized.activeKvQuantProfile.lowercased().hasPrefix("turboquant")
    else {
        return false
    }
    return true
}

func turboQuantRuntimeFusedAttentionRoute(
    cache: [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy
) -> TurboQuantRuntimeFusedAttentionRoute {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard normalized.mode == .activeKvQuantized,
          normalized.activeKvQuantProfile.lowercased().hasPrefix("turboquant")
    else {
        return .disabled
    }

    if turboQuantFusedAttentionDispatchCount(cache: cache) > 0 {
        guard firstSupportedTurboQuantQ4QuantizedCacheState(cache: cache) != nil else {
            return .blocked(.unsupportedCacheState)
        }
        return .routed
    }

    guard shouldUseActiveKVQuantization(for: normalized) else {
        return .blocked(.attentionHookUnavailable)
    }

    guard firstSupportedTurboQuantQ4QuantizedCacheState(cache: cache) != nil else {
        return .blocked(.unsupportedCacheState)
    }

    return .blocked(.attentionHookUnavailable)
}

private func turboQuantFusedAttentionDispatchCount(cache: [KVCache]) -> Int {
    cache.reduce(0) { partial, layer in
        guard let quantizedCache = layer as? QuantizedKVCacheProtocol else {
            return partial
        }
        return partial + quantizedCache.fusedAttentionDispatchCount
    }
}

func dispatchTurboQuantFusedAttentionCandidateFromQuantizedCacheState(cache: [KVCache]) -> Bool {
    guard let state = firstSupportedTurboQuantQ4QuantizedCacheState(cache: cache) else {
        return false
    }

    let query = MLXArray(turboQuantCandidateQueryValues(headDimension: state.headDimension))
    guard let output = TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
        query: query,
        quantizedKeys: state.quantizedKeys,
        quantizedValues: state.quantizedValues,
        sequenceLength: state.sequenceLength,
        headDimension: state.headDimension,
        groupSize: state.groupSize,
        bits: state.bits
    ) else {
        return false
    }
    eval(output)
    return true
}

private func firstSupportedTurboQuantQ4QuantizedCacheState(
    cache: [KVCache]
) -> SupportedTurboQuantQ4QuantizedCacheState? {
    for layer in cache {
        guard let quantizedCache = layer as? QuantizedKVCacheProtocol,
              quantizedCache.bits == 4,
              quantizedCache.mode.rawValue == QuantizationMode.affine.rawValue,
              let state = quantizedCache.getQuantizedState()
        else {
            continue
        }

        let quantizedKeys = state.0
        let quantizedValues = state.1
        guard quantizedKeys.0.shape.count >= 4, quantizedValues.0.shape.count >= 4 else {
            continue
        }
        guard quantizedKeys.0.dtype == DType.uint32, quantizedValues.0.dtype == DType.uint32 else {
            continue
        }

        let sequenceLength = quantizedKeys.0.dim(2)
        let keyHeadDimension = quantizedKeys.0.dim(3) * 8
        let valueHeadDimension = quantizedValues.0.dim(3) * 8
        guard sequenceLength > 0,
              keyHeadDimension > 0,
              keyHeadDimension == valueHeadDimension,
              keyHeadDimension % 8 == 0
        else {
            continue
        }

        return SupportedTurboQuantQ4QuantizedCacheState(
            quantizedKeys: quantizedKeys,
            quantizedValues: quantizedValues,
            sequenceLength: sequenceLength,
            headDimension: keyHeadDimension,
            groupSize: quantizedCache.groupSize,
            bits: quantizedCache.bits
        )
    }

    return nil
}

private func turboQuantCandidateQueryValues(headDimension: Int) -> [Float] {
    (0 ..< headDimension).map { index in
        Float((index % 17) - 8) / 16.0
    }
}
#endif

private func estimatedCacheStateBytes(_ cache: [KVCache]) -> UInt64 {
    cache.reduce(UInt64(0)) { partial, layer in
        partial + layer.innerState().reduce(UInt64(0)) { statePartial, array in
            let elementBytes = max(array.dtype.size, 1)
            return statePartial + UInt64(max(array.size, 0)) * UInt64(elementBytes)
        }
    }
}

private func estimatedFP16Bytes(quantizedBytes: UInt64, quantizationRatio: Int) -> UInt64 {
    guard quantizedBytes > 0, quantizationRatio > 0 else {
        return 0
    }
    return (quantizedBytes * 100) / UInt64(quantizationRatio)
}

private func elapsedMicros(since startedAt: TimeInterval) -> Int {
    max(0, Int(((Date.timeIntervalSinceReferenceDate - startedAt) * 1_000_000).rounded()))
}
#endif
