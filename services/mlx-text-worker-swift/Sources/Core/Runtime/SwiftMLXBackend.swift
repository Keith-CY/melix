import Foundation
import MelixWorkerProtocol

#if canImport(MLX)
@preconcurrency import MLX
#endif
#if canImport(MLXLMCommon)
@preconcurrency import MLXLMCommon
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
}

#if canImport(MLXLMCommon)
struct PreparedDecodeState: @unchecked Sendable {
    let input: LMInput
    let prepared: PrepareResult
    let cache: [KVCache]
    let promptPrefillTime: TimeInterval
}
#endif

enum RawTextGenerationEvent: Sendable {
    case chunk(String)
    case summary(TextGenerationSummary)
}

struct AutoSwiftMLXBackend: TextRuntimeBackend {
    let runtimeName: String

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
            acceleration: appliedAcceleration
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
            activeKVQuantizationRatio: activeKVQuantizationRatioPercent(for: appliedAcceleration)
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
            acceleration: effectiveAcceleration
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
    acceleration: Melix_Worker_V1_AccelerationPolicy
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
        applyActiveKVQuantizationIfNeeded(
            cache: &cache,
            acceleration: acceleration
        )
        let promptPrefillTime = Date.timeIntervalSinceReferenceDate - startedAt
        return PreparedDecodeState(
            input: input,
            prepared: prepared,
            cache: cache,
            promptPrefillTime: promptPrefillTime
        )
    }
    return PreparedPrefillContext(
        preparedInput: preparedState,
        promptTokens: preparedState.input.text.tokens.size
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
    acceleration: Melix_Worker_V1_AccelerationPolicy
) -> GenerateParameters {
    var parameters = makeGenerateParameters(from: sampling)

    if maxOutputTokens > 0 {
        parameters.maxTokens = Int(maxOutputTokens)
    }
    if decodeStepSize > 0 {
        parameters.prefillStepSize = Int(decodeStepSize)
    }

    if acceleration.mode == .activeKvQuantized {
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

#if canImport(MLXLMCommon)
private func applyActiveKVQuantizationIfNeeded(
    cache: inout [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy
) {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard normalized.mode == .activeKvQuantized else {
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
#endif

private func makePreparedDecodeGeneration(
    model: LoadedTextModel,
    context: TextPrefillContext,
    sampling: Melix_Worker_V1_SamplingConfig,
    maxOutputTokens: UInt32,
    decodeStepSize: UInt32,
    prefillToken: String,
    acceleration: Melix_Worker_V1_AccelerationPolicy
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
        acceleration: acceleration
    )

    let runtimeEvents = try await container.perform(values: decodeState) { modelContext, decodeState in
        try makePreparedDecodeEvents(
            decodeState: decodeState,
            context: modelContext,
            parameters: parameters
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
    parameters: GenerateParameters
) throws -> AsyncThrowingStream<RawTextGenerationEvent, Error> {
    let (stream, continuation) = AsyncThrowingStream<RawTextGenerationEvent, Error>.makeStream()

    let task = Task {
        do {
            var cache = decodeState.cache
            var processor = parameters.processor()
            let sampler = parameters.sampler()
            processor?.prompt(decodeState.input.text.tokens)

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
            let startedAt = Date.timeIntervalSinceReferenceDate

            while parameters.maxTokens.map({ generatedTokenCount < $0 }) ?? true {
                if Task.isCancelled {
                    break
                }

                let token = sampleNextToken(
                    logits: output.logits,
                    processor: &processor,
                    sampler: sampler
                )
                let tokenID = token.item(Int.self)

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

                let nextInput = LMInput.Text(tokens: token)
                output = context.model(
                    nextInput[text: .newAxis],
                    cache: cache.isEmpty ? nil : cache,
                    state: output.state
                )
                maybeQuantizeKVCache(
                    cache: &cache,
                    kvBits: parameters.kvBits,
                    kvGroupSize: parameters.kvGroupSize,
                    quantizedKVStart: parameters.quantizedKVStart
                )
            }

            let elapsed = max(Date.timeIntervalSinceReferenceDate - startedAt, 0.000_001)
            continuation.yield(.summary(
                TextGenerationSummary(
                    promptTokens: decodeState.input.text.tokens.size,
                    completionTokens: generatedTokenCount,
                    tokensPerSecond: Double(generatedTokenCount) / elapsed
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
#endif
