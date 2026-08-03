import Foundation
import MelixWorkerProtocol

#if canImport(MLX)
@preconcurrency import MLX
#endif
#if canImport(MLXLMCommon)
@preconcurrency import MLXLMCommon
#endif
#if canImport(Tokenizers)
@preconcurrency import Tokenizers
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
    let effectivePrefillWindowTokens: Int
    let activeKVQuantizationRatio: Int
    let pagedCacheEvidence: RuntimePagedCacheEvidence?
}

#if canImport(MLXLMCommon)
private let shortPromptBatchDecodeLookaheadMaxPromptTokens = 256

struct PreparedDecodeState: @unchecked Sendable {
    let input: LMInput
    let prepared: PrepareResult
    let cache: [KVCache]
    let promptPrefillTime: TimeInterval
    let prefillQuantizeMicros: Int
    let activeKVQuantizationRatio: Int
}

private func supportsArgMaxTokenIDFastPath(_ parameters: GenerateParameters) -> Bool {
    parameters.temperature == 0 && parameters.repetitionPenalty == nil
}
#endif

enum RawTextGenerationEvent: Sendable {
    case chunk(String)
    case summary(TextGenerationSummary)
}

func normalizeGemma4ChatTemplateTokenIDs(
    _ tokenIDs: [Int],
    modelFamilyID: String,
    startOfTurnTokenID: Int,
    endOfTurnTokenID: Int,
    thinkTokenID: Int,
    newlineTokenIDs: [Int],
    doubleNewlineTokenIDs: [Int]
) -> [Int] {
    guard isGemma4TextFamilyID(modelFamilyID),
          tokenIDs.contains(thinkTokenID),
          !newlineTokenIDs.isEmpty,
          !doubleNewlineTokenIDs.isEmpty,
          newlineTokenIDs != doubleNewlineTokenIDs
    else {
        return tokenIDs
    }

    let nonCanonicalBoundary = [endOfTurnTokenID]
        + doubleNewlineTokenIDs
        + [startOfTurnTokenID]
    let canonicalBoundary = [endOfTurnTokenID]
        + newlineTokenIDs
        + [startOfTurnTokenID]
    guard nonCanonicalBoundary.count <= tokenIDs.count else {
        return tokenIDs
    }

    var normalized: [Int] = []
    normalized.reserveCapacity(tokenIDs.count)
    var index = 0
    while index < tokenIDs.count {
        let remainingCount = tokenIDs.count - index
        if remainingCount >= nonCanonicalBoundary.count,
           Array(tokenIDs[index ..< index + nonCanonicalBoundary.count]) == nonCanonicalBoundary {
            normalized.append(contentsOf: canonicalBoundary)
            index += nonCanonicalBoundary.count
        } else {
            normalized.append(tokenIDs[index])
            index += 1
        }
    }
    return normalized
}

func isGemma4TextFamilyID(_ rawValue: String) -> Bool {
    let normalized = rawValue
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "_", with: "-")
    return normalized == "gemma4"
        || normalized == "gemma-4"
        || normalized == "gemma4-v1"
        || normalized == "gemma-4-v1"
        || normalized == "gemma4-text"
        || normalized == "gemma-4-text"
}

#if canImport(MLXLMCommon)
private func normalizingGemma4ChatTemplateWhitespace(
    in input: LMInput,
    tokenizer: Tokenizer,
    modelFamilyID: String
) -> LMInput {
    guard input.text.tokens.ndim == 1,
          input.text.mask == nil,
          let startOfTurnTokenID = tokenizer.convertTokenToId("<|turn>"),
          let endOfTurnTokenID = tokenizer.convertTokenToId("<turn|>"),
          let thinkTokenID = tokenizer.convertTokenToId("<|think|>")
    else {
        return input
    }

    let tokenIDs = input.text.tokens.asArray(Int.self)
    let normalizedTokenIDs = normalizeGemma4ChatTemplateTokenIDs(
        tokenIDs,
        modelFamilyID: modelFamilyID,
        startOfTurnTokenID: startOfTurnTokenID,
        endOfTurnTokenID: endOfTurnTokenID,
        thinkTokenID: thinkTokenID,
        newlineTokenIDs: tokenizer.encode(text: "\n", addSpecialTokens: false),
        doubleNewlineTokenIDs: tokenizer.encode(text: "\n\n", addSpecialTokens: false)
    )
    guard normalizedTokenIDs != tokenIDs else {
        return input
    }
    return LMInput(
        text: LMInput.Text(tokens: MLXArray(normalizedTokenIDs)),
        image: input.image,
        video: input.video
    )
}
#endif

private func tokenizerConfigEndOfTurnToken(in directoryURL: URL) -> String? {
    let configurationURL = directoryURL.appendingPathComponent("tokenizer_config.json")
    guard let data = try? Data(contentsOf: configurationURL),
          let object = try? JSONSerialization.jsonObject(with: data),
          let configuration = object as? [String: Any]
    else {
        return nil
    }

    func tokenString(from value: Any?) -> String? {
        if let token = value as? String, !token.isEmpty {
            return token
        }
        if let token = (value as? [String: Any])?["content"] as? String, !token.isEmpty {
            return token
        }
        return nil
    }

    if let token = tokenString(from: configuration["eot_token"]) {
        return token
    }
    let modelSpecificTokens = configuration["model_specific_special_tokens"] as? [String: Any]
    return tokenString(from: modelSpecificTokens?["eot_token"])
}

private func mergingTokenizerConfigEndOfTurnToken(
    into loadedModel: LoadedTextModel,
    preferredDirectoryURL: URL?,
    textFamilyID: String
) async -> LoadedTextModel {
    let identifiedModel = LoadedTextModel(
        storage: loadedModel.storage,
        residentBytesHint: loadedModel.residentBytesHint,
        textFamilyID: textFamilyID,
        cacheEpochID: loadedModel.cacheEpochID
    )
    #if canImport(MLXLMCommon)
    guard let container = identifiedModel.storage as? ModelContainer else {
        return identifiedModel
    }

    let configuration = await container.configuration
    let directoryURL = preferredDirectoryURL ?? configuration.modelDirectory(hub: defaultHubApi)
    guard let token = tokenizerConfigEndOfTurnToken(in: directoryURL) else {
        return identifiedModel
    }

    await container.update { context in
        context.configuration.extraEOSTokens.insert(token)
    }
    #endif
    return identifiedModel
}

func swiftTextModelFamilyID(from spec: Melix_Worker_V1_ModelSpec) -> String {
    let candidates = [
        spec.ext["text_family_id"],
        spec.ext["melix.text.family_id"],
        spec.ext["detected_family_id"],
        spec.ext["model_architecture"],
        spec.ext["detected_architecture"],
        spec.settings.ext["text_family_id"],
        spec.settings.ext["melix.text.family_id"],
        spec.settings.ext["detected_family_id"],
        spec.settings.ext["model_architecture"],
        spec.settings.ext["detected_architecture"],
        spec.modelID,
    ]
    for candidate in candidates.compactMap({ $0 }) {
        let normalized = candidate
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if normalized.contains("gemma4") || normalized.contains("gemma-4") {
            return "gemma4-v1"
        }
    }
    return ""
}

func makeSwiftMLXPromptTemplateAdditionalContext(
    from execution: Melix_Worker_V1_ExecutionMetadata
) throws -> [String: any Sendable]? {
    var context: [String: any Sendable] = [:]

    if let rawJSON = execution.ext["melix.chat_template_kwargs.effective_json"]?
        .trimmingCharacters(in: .whitespacesAndNewlines),
       !rawJSON.isEmpty {
        guard let data = rawJSON.data(using: .utf8) else {
            throw RuntimeUnavailableError(
                message: "Effective chat-template kwargs are not valid UTF-8 JSON."
            )
        }

        let object: Any
        do {
            object = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw RuntimeUnavailableError(
                message: "Effective chat-template kwargs must contain valid JSON."
            )
        }
        guard let values = object as? [String: Any] else {
            throw RuntimeUnavailableError(
                message: "Effective chat-template kwargs must be a JSON object."
            )
        }
        for (key, value) in values {
            context[key] = try swiftMLXPromptTemplateSendableJSONValue(value)
        }
    }

    if let enableThinking = resolvedSwiftMLXEnableThinking(from: execution) {
        context["enable_thinking"] = enableThinking
    }

    let reasoningMode = execution.reasoning.mode
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if !reasoningMode.isEmpty {
        context["reasoning_mode"] = reasoningMode
    }

    let reasoningEffort = execution.reasoning.effort
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if !reasoningEffort.isEmpty {
        context["reasoning_effort"] = reasoningEffort
    }

    return context.isEmpty ? nil : context
}

private func resolvedSwiftMLXEnableThinking(
    from execution: Melix_Worker_V1_ExecutionMetadata
) -> Bool? {
    if execution.reasoning.enabled {
        return true
    }

    let messagesThinkingType = execution.ext["melix.messages.thinking.type"]?
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased() ?? ""
    if !messagesThinkingType.isEmpty {
        return !["disabled", "none", "off"].contains(messagesThinkingType)
    }

    let reasoningMode = execution.reasoning.mode
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
    if !reasoningMode.isEmpty {
        return !["disabled", "none", "off"].contains(reasoningMode)
    }

    return nil
}

private func swiftMLXPromptTemplateSendableJSONValue(
    _ value: Any
) throws -> any Sendable {
    switch value {
    case let value as String:
        return value
    case let value as NSNumber:
        if CFGetTypeID(value) == CFBooleanGetTypeID() {
            return value.boolValue
        }
        if CFNumberIsFloatType(value) == false,
           let integer = Int(value.stringValue) {
            return integer
        }
        return value.doubleValue
    case let value as Bool:
        return value
    case let value as [Any]:
        return try value.map(swiftMLXPromptTemplateSendableJSONValue)
    case let value as [String: Any]:
        return try value.mapValues(swiftMLXPromptTemplateSendableJSONValue)
    case _ as NSNull:
        throw RuntimeUnavailableError(
            message: "Effective chat-template kwargs cannot contain null values."
        )
    default:
        throw RuntimeUnavailableError(
            message: "Effective chat-template kwargs contain an unsupported JSON value."
        )
    }
}

struct AutoSwiftMLXBackend: TextRuntimeBackend {
    let runtimeName: String
    let turboQuantCandidateProbeEnabled: Bool
    let pagedKVPool: PagedKVBlockPool

    var supportsHomogeneousBatchDecode: Bool {
        #if canImport(MLXLMCommon)
        true
        #else
        false
        #endif
    }

    var supportsPagedKVCache: Bool {
        #if canImport(MLXLMCommon)
        true
        #else
        false
        #endif
    }

    private let directLoader: (@Sendable (String) async throws -> LoadedTextModel)?
    private let directoryLoader: @Sendable (URL) async throws -> LoadedTextModel
    private let identifierLoader: @Sendable (String, String) async throws -> LoadedTextModel
    private let preparedGenerationFactory: @Sendable (
        LoadedTextModel,
        [Melix_Worker_V1_ChatMessage],
        Melix_Worker_V1_SamplingConfig,
        [String: any Sendable]?
    ) async throws -> PreparedTextGeneration

    init(
        runtimeName: String? = nil,
        turboQuantCandidateProbeEnabled: Bool = false,
        loader: (@Sendable (String) async throws -> Any)? = nil,
        directoryLoader: (@Sendable (URL) async throws -> LoadedTextModel)? = nil,
        identifierLoader: (@Sendable (String, String) async throws -> LoadedTextModel)? = nil,
        pagedKVPool: PagedKVBlockPool? = nil,
        preparedGenerationFactory: (@Sendable (
            LoadedTextModel,
            [Melix_Worker_V1_ChatMessage],
            Melix_Worker_V1_SamplingConfig,
            [String: any Sendable]?
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

        self.preparedGenerationFactory = preparedGenerationFactory ?? { model, messages, sampling, additionalContext in
            try await makePreparedTextGeneration(
                model: model,
                messages: messages,
                sampling: sampling,
                additionalContext: additionalContext
            )
        }
        self.turboQuantCandidateProbeEnabled = turboQuantCandidateProbeEnabled
        self.pagedKVPool = pagedKVPool ?? PagedKVBlockPool()

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

    func pagedKVPoolStats() async -> RuntimePagedKVPoolStats {
        pagedKVPool.stats()
    }

    func unloadModel(_ model: LoadedTextModel) async {
        pagedKVPool.removeAll(compatibilitySignaturePrefix: "\(model.cacheEpochID)::")
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        let modelSource = spec.modelPath.isEmpty ? spec.modelID : spec.modelPath
        let textFamilyID = swiftTextModelFamilyID(from: spec)
        let isDFlashSpec = DFlashDraftSupport.isDFlashDraftModelSpec(spec)

        if let directLoader, !isDFlashSpec {
            let loadedModel = try await directLoader(modelSource)
            let directoryURL = FileManager.default.fileExists(atPath: modelSource)
                ? URL(fileURLWithPath: modelSource, isDirectory: true)
                : nil
            return await mergingTokenizerConfigEndOfTurnToken(
                into: loadedModel,
                preferredDirectoryURL: directoryURL,
                textFamilyID: textFamilyID
            )
        }

        if FileManager.default.fileExists(atPath: modelSource) {
            let directoryURL = URL(fileURLWithPath: modelSource, isDirectory: true)
            if DFlashDraftSupport.isDFlashDraftDirectory(directoryURL) {
                #if canImport(MLXLMCommon) && canImport(MLXLLM)
                return LoadedTextModel(
                    storage: try SwiftDFlashDraftRuntime.load(
                        directoryURL: directoryURL,
                        modelID: spec.modelID
                    ),
                    textFamilyID: textFamilyID
                )
                #else
                throw RuntimeUnavailableError(message: DFlashDraftSupport.unsupportedMessage)
                #endif
            }
            let loadedModel = try await directoryLoader(directoryURL)
            return await mergingTokenizerConfigEndOfTurnToken(
                into: loadedModel,
                preferredDirectoryURL: directoryURL,
                textFamilyID: textFamilyID
            )
        }

        let revision = spec.revision.isEmpty ? "main" : spec.revision
        if isDFlashSpec || DFlashDraftSupport.looksLikeDFlashIdentifier(modelSource) {
            #if canImport(MLXLMCommon) && canImport(MLXLLM)
            return LoadedTextModel(
                storage: try await SwiftDFlashDraftRuntime.downloadAndLoad(
                    modelSource: modelSource,
                    revision: revision
                ),
                textFamilyID: textFamilyID
            )
            #else
            throw RuntimeUnavailableError(message: DFlashDraftSupport.unsupportedMessage)
            #endif
        }

        let loadedModel = try await identifierLoader(modelSource, revision)
        return await mergingTokenizerConfigEndOfTurnToken(
            into: loadedModel,
            preferredDirectoryURL: nil,
            textFamilyID: textFamilyID
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
        try await prefill(
            model: model,
            execution: Melix_Worker_V1_ExecutionMetadata(),
            messages: messages,
            prefillStepSize: prefillStepSize,
            resumeHint: resumeHint,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    func prefill(
        model: LoadedTextModel,
        execution: Melix_Worker_V1_ExecutionMetadata,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        let appliedAcceleration = resolveSwiftPrefillAcceleration(acceleration, messages: messages)
        let baseWindowSize = Int(clamping: max(prefillStepSize, 1))
        let prepared = try await makePreparedPromptContext(
            model: model,
            execution: execution,
            messages: messages,
            additionalContext: try makeSwiftMLXPromptTemplateAdditionalContext(from: execution),
            prefillStepSize: prefillStepSize,
            acceleration: appliedAcceleration,
            pagedKVPool: pagedKVPool,
            shouldAbort: shouldAbort
        )
        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: prepared.preparedInput,
                promptTokens: prepared.promptTokens
            ),
            promptTokens: prepared.promptTokens,
            requestedPrefillStepTokens: Int(clamping: prefillStepSize),
            effectivePrefillWindowTokens: prepared.effectivePrefillWindowTokens,
            appliedAcceleration: appliedAcceleration,
            acceleratedPrefillGainPct: estimatedPrefillGainPercent(
                baselineWindowSize: baseWindowSize,
                effectiveWindowSize: prepared.effectivePrefillWindowTokens
            ),
            activeKVQuantizationRatio: prepared.activeKVQuantizationRatio,
            pagedCacheEvidence: prepared.pagedCacheEvidence
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        try await generateEvents(
            model: model,
            execution: Melix_Worker_V1_ExecutionMetadata(),
            messages: messages,
            sampling: sampling,
            shouldAbort: shouldAbort
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        execution: Melix_Worker_V1_ExecutionMetadata,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let prepared = try await preparedGenerationFactory(
            model,
            messages,
            sampling,
            makeSwiftMLXPromptTemplateAdditionalContext(from: execution)
        )

        return AsyncThrowingStream { continuation in
            continuation.yield(.prefillStarted(promptTokens: prepared.promptTokens))

            let task = Task {
                var emittedTokenCount = 0
                var sawSummary = false
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
                            sawSummary = true
                        }
                    }

                    if !sawSummary {
                        summary = TextGenerationSummary(
                            promptTokens: prepared.promptTokens,
                            completionTokens: emittedTokenCount,
                            tokensPerSecond: nil,
                            finishReason: shouldAbort() ? "cancelled" : "stop"
                        )
                    }

                    continuation.yield(.summary(summary))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
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
        let effectiveAcceleration = try resolveSwiftDecodeAcceleration(
            acceleration,
            draftModel: draftModel
        )
        let prepared = try await makePreparedDecodeGeneration(
            model: model,
            draftModel: draftModel,
            context: context,
            sampling: sampling,
            maxOutputTokens: maxOutputTokens,
            decodeStepSize: decodeStepSize,
            prefillToken: prefillToken,
            acceleration: effectiveAcceleration,
            turboQuantCandidateProbeEnabled: turboQuantCandidateProbeEnabled
        )

        return AsyncThrowingStream { continuation in
            let task = Task {
                var emittedTokenCount = 0
                var sawSummary = false
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
                            sawSummary = true
                        }
                    }

                    if !sawSummary {
                        summary = TextGenerationSummary(
                            promptTokens: prepared.promptTokens,
                            completionTokens: emittedTokenCount,
                            tokensPerSecond: nil,
                            finishReason: shouldAbort() ? "cancelled" : "stop"
                        )
                    }

                    continuation.yield(.summary(summary))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    func decodeBatchEvents(
        requests: [TextRuntimeDecodeRequest]
    ) async throws -> AsyncThrowingStream<TextBatchGenerationEvent, Error> {
        #if canImport(MLXLMCommon)
        let admission = makeSwiftMLXBatchDecodeAdmission(from: requests)
        guard let batchInput = admission.input else {
            return try await makeFallbackDecodeBatchEvents(
                requests: requests,
                backend: self,
                fallbackReason: admission.fallbackReason
            )
        }

        let runtimeStream = try await batchInput.container.perform(values: batchInput) { modelContext, batchInput in
            try makePreparedBatchDecodeEvents(
                batchInput: batchInput,
                context: modelContext
            )
        }
        return runtimeStream
        #else
        _ = requests
        throw RuntimeUnavailableError(
            message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before batch decoding."
        )
        #endif
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
        topK: Int(sampling.topK),
        repetitionPenalty: repetitionPenalty > 0 ? repetitionPenalty : nil
    )
}

private func makePreparedTextGeneration(
    model: LoadedTextModel,
    messages: [Melix_Worker_V1_ChatMessage],
    sampling: Melix_Worker_V1_SamplingConfig,
    additionalContext: [String: any Sendable]?
) async throws -> PreparedTextGeneration {
    #if canImport(MLXLMCommon)
    guard let container = model.storage as? ModelContainer else {
        throw RuntimeUnavailableError(
            message: "Loaded model is not a Swift MLX model container."
        )
    }

    let chat = try convertChatMessages(messages)
    let userInput = UserInput(chat: chat, additionalContext: additionalContext)
    let preparedInput = try await container.prepare(input: userInput)
    let input = normalizingGemma4ChatTemplateWhitespace(
        in: preparedInput,
        tokenizer: await container.tokenizer,
        modelFamilyID: model.textFamilyID
    )
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
                            tokensPerSecond: info.tokensPerSecond,
                            finishReason: info.finishReason.rawValue
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
    execution: Melix_Worker_V1_ExecutionMetadata,
    messages: [Melix_Worker_V1_ChatMessage],
    additionalContext: [String: any Sendable]?,
    prefillStepSize: UInt32,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    pagedKVPool: PagedKVBlockPool,
    shouldAbort: @escaping @Sendable () -> Bool
) async throws -> PreparedPrefillContext {
    #if canImport(MLXLMCommon)
    guard let container = model.storage as? ModelContainer else {
        throw RuntimeUnavailableError(
            message: "Loaded model is not a Swift MLX model container."
        )
    }

    try throwIfTextRuntimeCancellationRequested(shouldAbort)
    let chat = try convertChatMessages(messages)
    let userInput = UserInput(chat: chat, additionalContext: additionalContext)
    let effectiveWindowSize = acceleratedPrefillWindowSize(
        baseWindowSize: Int(clamping: max(prefillStepSize, 1)),
        policy: acceleration,
        messages: messages
    )
    let preparedExecution = try await container.perform { context in
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let preparedInput = try await context.processor.prepare(input: userInput)
        let input = normalizingGemma4ChatTemplateWhitespace(
            in: preparedInput,
            tokenizer: context.tokenizer,
            modelFamilyID: model.textFamilyID
        )
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        return try makePagedOrContiguousPrefillState(
            input: input,
            context: context,
            model: model,
            execution: execution,
            acceleration: acceleration,
            effectiveWindowSize: effectiveWindowSize,
            pagedKVPool: pagedKVPool,
            shouldAbort: shouldAbort
        )
    }
    try throwIfTextRuntimeCancellationRequested(shouldAbort)
    let preparedState = preparedExecution.state
    return PreparedPrefillContext(
        preparedInput: preparedState,
        promptTokens: preparedState.input.text.tokens.size,
        effectivePrefillWindowTokens: effectiveWindowSize,
        activeKVQuantizationRatio: preparedState.activeKVQuantizationRatio,
        pagedCacheEvidence: preparedExecution.evidence
    )
    #else
    throw RuntimeUnavailableError(
        message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before preparing prompts."
    )
    #endif
}

#if canImport(MLXLMCommon)
private struct PreparedPrefillExecutionState: @unchecked Sendable {
    let state: PreparedDecodeState
    let evidence: RuntimePagedCacheEvidence
}

private func makePagedOrContiguousPrefillState(
    input: LMInput,
    context: ModelContext,
    model: LoadedTextModel,
    execution: Melix_Worker_V1_ExecutionMetadata,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    effectiveWindowSize: Int,
    pagedKVPool: PagedKVBlockPool,
    shouldAbort: @escaping @Sendable () -> Bool
) throws -> PreparedPrefillExecutionState {
    let cacheMode = CacheModePolicy.resolve(from: execution.cacheHints)
    guard cacheMode == .tiered else {
        return try makeContiguousPrefillState(
            input: input,
            context: context,
            acceleration: acceleration,
            effectiveWindowSize: effectiveWindowSize,
            fallbackReason: "cache_mode_unsupported",
            shouldAbort: shouldAbort
        )
    }
    guard normalizedAccelerationPolicy(acceleration).mode != .activeKvQuantized else {
        return try makeContiguousPrefillState(
            input: input,
            context: context,
            acceleration: acceleration,
            effectiveWindowSize: effectiveWindowSize,
            fallbackReason: "active_kv_layout_unsupported",
            shouldAbort: shouldAbort
        )
    }
    guard pagedKVPrefillShapeIsSupported(input) else {
        return try makeContiguousPrefillState(
            input: input,
            context: context,
            acceleration: acceleration,
            effectiveWindowSize: effectiveWindowSize,
            fallbackReason: "prefill_shape_unsupported",
            shouldAbort: shouldAbort
        )
    }

    let modelCaches = context.model.newCache(parameters: nil)
    guard pagedKVCacheLayoutIsSupported(modelCaches) else {
        return try makeContiguousPrefillState(
            input: input,
            context: context,
            acceleration: acceleration,
            effectiveWindowSize: effectiveWindowSize,
            fallbackReason: "cache_layout_unsupported",
            shouldAbort: shouldAbort
        )
    }

    let blockSize = max(Int(execution.cacheHints.preferredBlockSize), 16)
    let modelPrefillChunkTokens = pagedKVPrefillForwardChunkTokens(
        effectiveWindowSize: effectiveWindowSize,
        blockSize: blockSize
    )
    let promptTokenCount = input.text.tokens.size
    let storedTokenBoundary = max(0, ((promptTokenCount - 1) / blockSize) * blockSize)
    guard storedTokenBoundary > 0 else {
        return try makeContiguousPrefillState(
            input: input,
            context: context,
            acceleration: acceleration,
            effectiveWindowSize: effectiveWindowSize,
            fallbackReason: "prompt_below_block_boundary",
            shouldAbort: shouldAbort
        )
    }

    let tokenIDs = input.text.tokens.asArray(Int.self)
    let compatibilitySignature = pagedKVCompatibilitySignature(
        model: model,
        execution: execution,
        acceleration: acceleration,
        blockSize: blockSize,
        prefillShapeSignature: pagedKVPrefillShapeSignature(
            input,
            blockSize: blockSize,
            forwardChunkTokens: modelPrefillChunkTokens
        )
    ) + "::layout::" + modelCaches.map { String(reflecting: type(of: $0)) }.joined(separator: ",")
    let lookup = pagedKVPool.lookup(
        compatibilitySignature: compatibilitySignature,
        tokenIDs: tokenIDs,
        storedTokenBoundary: storedTokenBoundary,
        blockSize: blockSize
    )
    let restoreStartedAt = Date.timeIntervalSinceReferenceDate
    var cache: [KVCache]
    var processedTokens: Int
    let reusedSnapshot: PagedKVPrefixSnapshot?
    if let snapshot = lookup.snapshot,
       snapshot.layerCount == modelCaches.count,
       let restoredCaches = lookup.makeCaches() {
        cache = restoredCaches
        processedTokens = snapshot.tokenCount
        reusedSnapshot = snapshot
    } else {
        cache = (0 ..< modelCaches.count).map { PagedKVCache(blockSize: blockSize, layerIndex: $0) }
        processedTokens = 0
        reusedSnapshot = nil
    }
    let restoreMicros = reusedSnapshot == nil ? 0 : elapsedMicros(since: restoreStartedAt)
    let prefillStartedAt = Date.timeIntervalSinceReferenceDate
    var modelPrefillCallTokenCounts: [Int] = []

    while processedTokens < storedTokenBoundary {
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let end = min(storedTokenBoundary, processedTokens + modelPrefillChunkTokens)
        let chunk = input.text[text: processedTokens ..< end][.newAxis]
        let output = context.model(chunk, cache: cache, state: nil)
        if output.state != nil {
            return try makeContiguousPrefillState(
                input: input,
                context: context,
                acceleration: acceleration,
                effectiveWindowSize: effectiveWindowSize,
                fallbackReason: "composite_runtime_state_unsupported",
                shouldAbort: shouldAbort
            )
        }
        eval(cache)
        modelPrefillCallTokenCounts.append(end - processedTokens)
        processedTokens = end
    }

    let stored = pagedKVPool.store(
        compatibilitySignature: compatibilitySignature,
        tokenIDs: tokenIDs,
        storedTokenBoundary: storedTokenBoundary,
        blockSize: blockSize,
        caches: cache,
        reusedLookup: reusedSnapshot == nil ? nil : lookup,
        budgetBytes: execution.cacheHints.cacheMemoryBudgetBytes
    )
    let recoveredTokens = reusedSnapshot?.tokenCount ?? 0
    let hitMode = recoveredTokens == 0
        ? "none"
        : (recoveredTokens == storedTokenBoundary ? "exact" : "partial")
    guard let snapshot = stored.snapshot,
          let storedCaches = stored.makeCaches() else {
        let fallbackReason = stored.fallbackReason.isEmpty
            ? "cache_store_result_unavailable"
            : stored.fallbackReason
        let state = PreparedDecodeState(
            input: input,
            prepared: .tokens(input.text[text: storedTokenBoundary...]),
            cache: cache,
            promptPrefillTime: Date.timeIntervalSinceReferenceDate - prefillStartedAt,
            prefillQuantizeMicros: 0,
            activeKVQuantizationRatio: 0
        )
        return PreparedPrefillExecutionState(
            state: state,
            evidence: RuntimePagedCacheEvidence(
                admitted: false,
                cacheHitMode: hitMode,
                fallbackReason: fallbackReason,
                recoveredPrefixTokens: recoveredTokens,
                blocks: reusedSnapshot?.descriptors ?? [],
                lookupMicros: lookup.lookupMicros,
                restoreMicros: restoreMicros,
                streamOwnerMatch: true,
                copyOnWriteBlockCount: 0,
                computedPrefixTokens: storedTokenBoundary - recoveredTokens,
                modelPrefillMicros: elapsedMicros(since: prefillStartedAt),
                modelPrefillChunkTokens: modelPrefillChunkTokens,
                modelPrefillCallTokenCounts: modelPrefillCallTokenCounts,
                blockTableBytes: reusedSnapshot?.blocks.reduce(UInt64(0)) { $0 + $1.bytes } ?? 0
            )
        )
    }

    cache = storedCaches
    let remaining = input.text[text: storedTokenBoundary...]
    let state = PreparedDecodeState(
        input: input,
        prepared: .tokens(remaining),
        cache: cache,
        promptPrefillTime: Date.timeIntervalSinceReferenceDate - prefillStartedAt,
        prefillQuantizeMicros: 0,
        activeKVQuantizationRatio: 0
    )
    return PreparedPrefillExecutionState(
        state: state,
        evidence: RuntimePagedCacheEvidence(
            admitted: true,
            cacheHitMode: hitMode,
            fallbackReason: "",
            recoveredPrefixTokens: recoveredTokens,
            blocks: snapshot.descriptors,
            lookupMicros: lookup.lookupMicros,
            restoreMicros: restoreMicros,
            streamOwnerMatch: true,
            copyOnWriteBlockCount: stored.copyOnWriteBlockCount,
            computedPrefixTokens: storedTokenBoundary - recoveredTokens,
            modelPrefillMicros: elapsedMicros(since: prefillStartedAt),
            modelPrefillChunkTokens: modelPrefillChunkTokens,
            modelPrefillCallTokenCounts: modelPrefillCallTokenCounts,
            blockTableBytes: snapshot.blocks.reduce(UInt64(0)) { $0 + $1.bytes }
        )
    )
}

private func makeContiguousPrefillState(
    input: LMInput,
    context: ModelContext,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    effectiveWindowSize: Int,
    fallbackReason: String,
    shouldAbort: @escaping @Sendable () -> Bool
) throws -> PreparedPrefillExecutionState {
    var cache = context.model.newCache(parameters: nil)
    let startedAt = Date.timeIntervalSinceReferenceDate
    let prepared = try context.model.prepare(input, cache: cache, windowSize: effectiveWindowSize)
    try throwIfTextRuntimeCancellationRequested(shouldAbort)
    let quantizeStartedAt = Date.timeIntervalSinceReferenceDate
    applyActiveKVQuantizationIfNeeded(cache: &cache, acceleration: acceleration)
    try throwIfTextRuntimeCancellationRequested(shouldAbort)
    let state = PreparedDecodeState(
        input: input,
        prepared: prepared,
        cache: cache,
        promptPrefillTime: Date.timeIntervalSinceReferenceDate - startedAt,
        prefillQuantizeMicros: elapsedMicros(since: quantizeStartedAt),
        activeKVQuantizationRatio: activeKVRuntimeQuantizationRatioPercent(
            for: acceleration,
            cache: cache
        )
    )
    return PreparedPrefillExecutionState(
        state: state,
        evidence: .fallback(
            fallbackReason,
            computedPrefixTokens: input.text.tokens.size,
            modelPrefillMicros: elapsedMicros(since: startedAt)
        )
    )
}

private func pagedKVCompatibilitySignature(
    model: LoadedTextModel,
    execution: Melix_Worker_V1_ExecutionMetadata,
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    blockSize: Int,
    prefillShapeSignature: String
) -> String {
    let scope = execution.scope
    return [
        model.cacheEpochID,
        String(reflecting: ObjectIdentifier(StreamOrDevice.default.stream)),
        model.textFamilyID,
        scope.modelID,
        scope.revision,
        scope.tokenizerHash,
        scope.quantProfileID,
        scope.promptTemplateHash,
        scope.parserMode,
        scope.reasoningMode,
        scope.reasoningEffort,
        scope.toolParserMode,
        scope.structuredOutputMode,
        scope.chatTemplateKwargsHash,
        scope.multimodalAdapterHash,
        String(scope.reasoningContinuityPresent),
        accelerationModeName(acceleration.mode),
        acceleration.profileID,
        prefillShapeSignature,
        String(blockSize),
    ].joined(separator: "::")
}

func pagedKVPrefillForwardChunkTokens(effectiveWindowSize: Int, blockSize: Int) -> Int {
    let normalizedBlockSize = max(1, blockSize)
    let window = max(normalizedBlockSize, effectiveWindowSize)
    return max(normalizedBlockSize, (window / normalizedBlockSize) * normalizedBlockSize)
}

func pagedKVPrefillShapeSignature(
    _ input: LMInput,
    blockSize: Int,
    forwardChunkTokens: Int? = nil
) -> String {
    let tokens = input.text.tokens
    let modelCallTokens = max(1, forwardChunkTokens ?? blockSize)
    let tokenPrefixShape = tokens.shape.dropLast().map { String($0) }.joined(separator: "x")
    let maskShape = input.text.mask.map {
        "\($0.dtype):\($0.shape.map { String($0) }.joined(separator: "x"))"
    } ?? "none"
    return [
        "text-dtype=\(tokens.dtype)",
        "text-rank=\(tokens.ndim)",
        "text-prefix-shape=\(tokenPrefixShape.isEmpty ? "scalar-batch" : tokenPrefixShape)",
        "model-call-max-shape=1x\(modelCallTokens)",
        "mask=\(maskShape)",
        "image=\(input.image == nil ? "none" : "present")",
        "video=\(input.video == nil ? "none" : "present")",
    ].joined(separator: ";")
}

func pagedKVPrefillShapeIsSupported(_ input: LMInput) -> Bool {
    input.text.tokens.ndim == 1
        && input.text.mask == nil
        && input.image == nil
        && input.video == nil
}
#endif

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
    _ acceleration: Melix_Worker_V1_AccelerationPolicy,
    draftModel: LoadedTextModel?
) throws -> Melix_Worker_V1_AccelerationPolicy {
    guard acceleration.mode == .speculativeDecode else {
        return acceleration
    }

    if draftModel != nil {
        return acceleration
    }

    if acceleration.allowBaselineFallback {
        var baseline = acceleration
        baseline.mode = .baseline
        return baseline
    }

    throw RuntimeUnavailableError(
        message: "Speculative decode requires a loaded draft model for the Swift MLX backend."
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

    if shouldUseActiveKVQuantization(for: acceleration) {
        applyActiveKVQuantizationProfile(
            to: &parameters,
            profile: acceleration.activeKvQuantProfile
        )
    }

    return parameters
}

private func resolvedTextGenerationFinishReason(
    completionTokens: Int,
    maxTokens: Int?,
    wasCancelled: Bool
) -> String {
    if wasCancelled {
        return "cancelled"
    }
    if let maxTokens, completionTokens >= maxTokens {
        return "length"
    }
    return "stop"
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

func shouldUseActiveKVQuantization(
    for acceleration: Melix_Worker_V1_AccelerationPolicy
) -> Bool {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard normalized.mode == .activeKvQuantized else {
        return false
    }
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
    acceleration: Melix_Worker_V1_AccelerationPolicy
) {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard shouldUseActiveKVQuantization(for: normalized) else {
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
    acceleration: Melix_Worker_V1_AccelerationPolicy
) -> Bool {
    let normalized = normalizedAccelerationPolicy(acceleration)
    guard shouldUseActiveKVQuantization(for: normalized), kvBits != nil else {
        return false
    }

    return cache.contains { layer in
        guard let simpleCache = layer as? KVCacheSimple else {
            return false
        }
        return simpleCache.offset > quantizedKVStart
    }
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

private struct SpeculativeTokenMetadata: Sendable {
    let unknownTokenID: Int?
    let eosTokenID: Int?
    let additionalEOSTokenIDs: Set<Int>
}

private struct SpeculativeDecodeRuntimeState: @unchecked Sendable {
    var cache: [KVCache]
    var output: LMOutput
    let promptTokenCount: Int
    let prefillQuantizeMicros: Int
}

private struct BatchDecodeRequestState: @unchecked Sendable {
    let request: TextRuntimeDecodeRequest
    let maxTokens: Int?
    var output: LMOutput
    var processor: (any LogitProcessor)?
    let sampler: any LogitSampler
    var detokenizer: NaiveStreamingDetokenizer
    var pendingToken: MLXArray?
    var pendingTokenID: Int?
    var pendingBatchedTokenRow: MLXArray?
    var generatedTokenCount: Int
    var isFinished: Bool
    var finishReason: String?
}

private struct SwiftMLXBatchDecodeInput: @unchecked Sendable {
    let container: ModelContainer
    let requests: [TextRuntimeDecodeRequest]
    let states: [PreparedDecodeState]
    let parametersByRequest: [GenerateParameters]

    var supportsBatchedArgMaxTokenIDs: Bool {
        parametersByRequest.allSatisfy(supportsArgMaxTokenIDFastPath)
    }
}

private struct SwiftMLXBatchDecodeAdmission: @unchecked Sendable {
    let input: SwiftMLXBatchDecodeInput?
    let fallbackReason: String?

    static func accepted(_ input: SwiftMLXBatchDecodeInput) -> SwiftMLXBatchDecodeAdmission {
        SwiftMLXBatchDecodeAdmission(input: input, fallbackReason: nil)
    }

    static func rejected(_ reason: String?) -> SwiftMLXBatchDecodeAdmission {
        SwiftMLXBatchDecodeAdmission(input: nil, fallbackReason: reason)
    }
}

private struct BatchDecodeCacheState: @unchecked Sendable {
    var cache: [KVCache]?
    var sourceRequestIndices: [Int]
}

private struct DFlashTargetDecodeState: @unchecked Sendable {
    let state: SpeculativeDecodeRuntimeState
    let logits: MLXArray
    let hidden: MLXArray
}

private struct KVCacheLayerSnapshot: @unchecked Sendable {
    let state: [MLXArray]
    let metaState: [String]
}

private struct SpeculativeModelStepInput: @unchecked Sendable {
    var state: SpeculativeDecodeRuntimeState
    let tokenIDs: [Int]
}

private func makePreparedSpeculativeDecodeEvents(
    targetContainer: ModelContainer,
    draftContainer: ModelContainer,
    decodeState: PreparedDecodeState,
    targetContext: ModelContext,
    parameters: GenerateParameters,
    acceleration: Melix_Worker_V1_AccelerationPolicy
) async throws -> AsyncThrowingStream<RawTextGenerationEvent, Error> {
    let promptTokenIDs = decodeState.input.text.tokens.asArray(Int.self)
    let targetCache = decodeState.cache
    let targetOutput = try makeInitialDecodeOutput(
        decodeState: decodeState,
        context: targetContext,
        cache: targetCache
    )
    eval(targetOutput.logits)

    let initialTargetState = SpeculativeDecodeRuntimeState(
        cache: targetCache,
        output: targetOutput,
        promptTokenCount: promptTokenIDs.count,
        prefillQuantizeMicros: decodeState.prefillQuantizeMicros
    )
    let initialDraftState = try await makeRebuiltSpeculativeDecodeState(
        container: draftContainer,
        tokenIDs: promptTokenIDs,
        promptTokenCount: promptTokenIDs.count,
        prefillQuantizeMicros: 0,
        parameters: parameters
    )
    let additionalEOSTokenIDs = Set(
        targetContext.configuration.extraEOSTokens.compactMap {
            targetContext.tokenizer.convertTokenToId($0)
        }
    )
    let tokenMetadata = SpeculativeTokenMetadata(
        unknownTokenID: targetContext.tokenizer.unknownTokenId,
        eosTokenID: targetContext.tokenizer.eosTokenId,
        additionalEOSTokenIDs: additionalEOSTokenIDs
    )
    let maxDraftTokens = max(1, Int(acceleration.numDraftTokens == 0 ? 4 : acceleration.numDraftTokens))
    let (stream, continuation) = AsyncThrowingStream<RawTextGenerationEvent, Error>.makeStream()

    let task = Task {
        do {
            var targetState = initialTargetState
            var draftState = initialDraftState
            var generatedTokenIDs: [Int] = []
            var generatedTokenCount = 0
            var acceptedTokenCount = 0
            var rejectedTokenCount = 0
            var proposedTokenCount = 0
            var runtimeFallbackCount = 0
            var draftProposeMicros = 0
            var targetVerifyMicros = 0
            var forceBaselineDecode = false
            var targetProcessor = parameters.processor()
            var draftProcessor = parameters.processor()
            let targetSampler = parameters.sampler()
            let draftSampler = parameters.sampler()
            var detokenizer = NaiveStreamingDetokenizer(tokenizer: targetContext.tokenizer)

            func resetProcessors(prefixTokenIDs: [Int]) {
                let prefix = MLXArray(prefixTokenIDs)
                targetProcessor = parameters.processor()
                draftProcessor = parameters.processor()
                targetProcessor?.prompt(prefix)
                draftProcessor?.prompt(prefix)
            }

            resetProcessors(prefixTokenIDs: promptTokenIDs)
            let startedAt = Date.timeIntervalSinceReferenceDate

            var finished = false
            while !finished && (parameters.maxTokens.map { generatedTokenCount < $0 } ?? true) {
                if Task.isCancelled {
                    break
                }

                if forceBaselineDecode {
                    let targetToken = sampleNextToken(
                        logits: targetState.output.logits,
                        processor: &targetProcessor,
                        sampler: targetSampler
                    )
                    let targetTokenID = targetToken.item(Int.self)
                    if isSpeculativeTerminalToken(targetTokenID, metadata: tokenMetadata) {
                        break
                    }

                    generatedTokenIDs.append(targetTokenID)
                    generatedTokenCount += 1
                    detokenizer.append(token: targetTokenID)
                    if let chunk = detokenizer.next() {
                        continuation.yield(.chunk(chunk))
                    }

                    if let maxTokens = parameters.maxTokens, generatedTokenCount >= maxTokens {
                        break
                    }

                    targetState = advanceSpeculativeDecodeState(
                        context: targetContext,
                        state: targetState,
                        tokenIDs: [targetTokenID]
                    )
                    continue
                }

                let remainingTokens = parameters.maxTokens.map { max(0, $0 - generatedTokenCount) } ?? maxDraftTokens
                guard remainingTokens > 0 else {
                    break
                }

                let verifiedDecisionCount = acceptedTokenCount + rejectedTokenCount
                let proposalWindow = verifiedDecisionCount < 4 ? 1 : maxDraftTokens
                let proposalCount = min(proposalWindow, remainingTokens)
                var proposedTokenIDs: [Int] = []
                let proposalStartedAt = Date.timeIntervalSinceReferenceDate
                for _ in 0 ..< proposalCount {
                    if Task.isCancelled {
                        finished = true
                        break
                    }

                    let draftToken = sampleNextToken(
                        logits: draftState.output.logits,
                        processor: &draftProcessor,
                        sampler: draftSampler
                    )
                    let draftTokenID = draftToken.item(Int.self)
                    proposedTokenIDs.append(draftTokenID)

                    draftState = try await advanceSpeculativeDecodeState(
                        container: draftContainer,
                        state: draftState,
                        tokenIDs: [draftTokenID]
                    )
                }
                draftProposeMicros += elapsedMicros(since: proposalStartedAt)
                proposedTokenCount += proposedTokenIDs.count

                if finished || proposedTokenIDs.isEmpty {
                    break
                }

                if proposedTokenIDs.count == 1 {
                    let verifyStartedAt = Date.timeIntervalSinceReferenceDate
                    let proposedTokenID = proposedTokenIDs[0]
                    let targetToken = sampleNextToken(
                        logits: targetState.output.logits,
                        processor: &targetProcessor,
                        sampler: targetSampler
                    )
                    let targetTokenID = targetToken.item(Int.self)
                    targetVerifyMicros += elapsedMicros(since: verifyStartedAt)

                    if isSpeculativeTerminalToken(targetTokenID, metadata: tokenMetadata) {
                        break
                    }

                    let emittedTokenID: Int
                    let acceptedProposal = targetTokenID == proposedTokenID
                    if acceptedProposal {
                        acceptedTokenCount += 1
                        emittedTokenID = proposedTokenID
                    } else {
                        rejectedTokenCount += 1
                        emittedTokenID = targetTokenID
                    }

                    generatedTokenIDs.append(emittedTokenID)
                    generatedTokenCount += 1
                    detokenizer.append(token: emittedTokenID)
                    if let chunk = detokenizer.next() {
                        continuation.yield(.chunk(chunk))
                    }

                    if let maxTokens = parameters.maxTokens, generatedTokenCount >= maxTokens {
                        break
                    }

                    targetState = advanceSpeculativeDecodeState(
                        context: targetContext,
                        state: targetState,
                        tokenIDs: [emittedTokenID]
                    )

                    if shouldFallbackSpeculativeDecodeRuntime(
                        acceptedTokenCount: acceptedTokenCount,
                        rejectedTokenCount: rejectedTokenCount,
                        proposedTokenCount: proposedTokenCount,
                        draftProposeMicros: draftProposeMicros,
                        targetVerifyMicros: targetVerifyMicros
                    ) {
                        forceBaselineDecode = true
                        runtimeFallbackCount = 1
                        continue
                    }

                    if !acceptedProposal {
                        let rebuiltPrefix = promptTokenIDs + generatedTokenIDs
                        draftState = try await makeRebuiltSpeculativeDecodeState(
                            container: draftContainer,
                            tokenIDs: rebuiltPrefix,
                            promptTokenCount: promptTokenIDs.count,
                            prefillQuantizeMicros: 0,
                            parameters: parameters
                        )
                        resetProcessors(prefixTokenIDs: rebuiltPrefix)
                    }
                    continue
                }

                let verifyStartedAt = Date.timeIntervalSinceReferenceDate
                let verifiedTargetState = advanceSpeculativeDecodeState(
                    context: targetContext,
                    state: targetState,
                    tokenIDs: proposedTokenIDs
                )

                var rejectionTokenID: Int?
                var acceptedThisRound = 0
                for (index, proposedTokenID) in proposedTokenIDs.enumerated() {
                    if Task.isCancelled {
                        finished = true
                        break
                    }

                    let targetLogits: MLXArray
                    if index == 0 {
                        targetLogits = targetState.output.logits
                    } else {
                        targetLogits = verifiedTargetState.output.logits
                    }
                    let targetToken = sampleNextToken(
                        logits: targetLogits,
                        position: index == 0 ? nil : index - 1,
                        processor: &targetProcessor,
                        sampler: targetSampler
                    )
                    let targetTokenID = targetToken.item(Int.self)
                    if isSpeculativeTerminalToken(targetTokenID, metadata: tokenMetadata) {
                        finished = true
                        break
                    }

                    if targetTokenID == proposedTokenID {
                        acceptedTokenCount += 1
                        acceptedThisRound += 1
                        generatedTokenIDs.append(proposedTokenID)
                        generatedTokenCount += 1
                        detokenizer.append(token: proposedTokenID)
                        if let chunk = detokenizer.next() {
                            continuation.yield(.chunk(chunk))
                        }

                        if let maxTokens = parameters.maxTokens, generatedTokenCount >= maxTokens {
                            finished = true
                            break
                        }
                    } else {
                        rejectedTokenCount += 1
                        rejectionTokenID = targetTokenID
                        break
                    }
                }
                targetVerifyMicros += elapsedMicros(since: verifyStartedAt)

                if finished {
                    break
                }

                if let rejectionTokenID {
                    generatedTokenIDs.append(rejectionTokenID)
                    generatedTokenCount += 1
                    detokenizer.append(token: rejectionTokenID)
                    if let chunk = detokenizer.next() {
                        continuation.yield(.chunk(chunk))
                    }

                    if let maxTokens = parameters.maxTokens, generatedTokenCount >= maxTokens {
                        break
                    }

                    let rebuiltPrefix = promptTokenIDs + generatedTokenIDs
                    targetState = try makeRebuiltSpeculativeDecodeState(
                        context: targetContext,
                        tokenIDs: rebuiltPrefix,
                        promptTokenCount: promptTokenIDs.count,
                        prefillQuantizeMicros: decodeState.prefillQuantizeMicros,
                        parameters: parameters
                    )
                    draftState = try await makeRebuiltSpeculativeDecodeState(
                        container: draftContainer,
                        tokenIDs: rebuiltPrefix,
                        promptTokenCount: promptTokenIDs.count,
                        prefillQuantizeMicros: 0,
                        parameters: parameters
                    )
                    resetProcessors(prefixTokenIDs: rebuiltPrefix)
                } else if acceptedThisRound == proposedTokenIDs.count {
                    targetState = verifiedTargetState
                }

                if shouldFallbackSpeculativeDecodeRuntime(
                    acceptedTokenCount: acceptedTokenCount,
                    rejectedTokenCount: rejectedTokenCount,
                    proposedTokenCount: proposedTokenCount,
                    draftProposeMicros: draftProposeMicros,
                    targetVerifyMicros: targetVerifyMicros
                ) {
                    forceBaselineDecode = true
                    runtimeFallbackCount = 1
                }
            }

            let decodeLoopTotalMicros = elapsedMicros(since: startedAt)
            let elapsed = max(Double(decodeLoopTotalMicros) / 1_000_000, 0.000_001)
            continuation.yield(.summary(
                TextGenerationSummary(
                    promptTokens: promptTokenIDs.count,
                    completionTokens: generatedTokenCount,
                    tokensPerSecond: Double(generatedTokenCount) / elapsed,
                    finishReason: resolvedTextGenerationFinishReason(
                        completionTokens: generatedTokenCount,
                        maxTokens: parameters.maxTokens,
                        wasCancelled: Task.isCancelled
                    ),
                    speculativeAcceptedTokens: acceptedTokenCount,
                    speculativeRejectedTokens: rejectedTokenCount,
                    speculativeFallbackCount: runtimeFallbackCount,
                    speculativeDraftProposeMillis: milliseconds(fromMicros: draftProposeMicros),
                    speculativeTargetVerifyMillis: milliseconds(fromMicros: targetVerifyMicros)
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

private func makeSwiftMLXBatchDecodeAdmission(
    from requests: [TextRuntimeDecodeRequest]
) -> SwiftMLXBatchDecodeAdmission {
    guard requests.count > 1 else {
        return .rejected(nil)
    }
    guard let firstRequest = requests.first else {
        return .rejected(nil)
    }
    guard firstRequest.draftModel == nil else {
        return .rejected("not_batchable:draft_model")
    }
    guard normalizedAccelerationPolicy(firstRequest.acceleration).mode == .baseline else {
        return .rejected("not_batchable:acceleration_mode")
    }
    guard let container = firstRequest.model.storage as? ModelContainer else {
        return .rejected("not_batchable:model_container")
    }
    guard let firstState = firstRequest.context.storage as? PreparedDecodeState else {
        return .rejected("not_batchable:prepared_state")
    }
    guard isTextOnlyBatchDecodeState(firstState) else {
        return .rejected("not_batchable:state_modality")
    }
    guard firstState.activeKVQuantizationRatio == 0 else {
        return .rejected("not_batchable:active_kv_quantized")
    }

    var parametersByRequest = [makeDecodeParameters(
        from: firstRequest.sampling,
        maxOutputTokens: firstRequest.maxOutputTokens,
        decodeStepSize: firstRequest.decodeStepSize,
        acceleration: firstRequest.acceleration
    )]
    var states = [firstState]

    for request in requests.dropFirst() {
        guard request.draftModel == nil else {
            return .rejected("not_batchable:draft_model")
        }
        guard normalizedAccelerationPolicy(request.acceleration).mode == .baseline else {
            return .rejected("not_batchable:acceleration_mode")
        }
        guard let requestContainer = request.model.storage as? ModelContainer,
              requestContainer === container else {
            return .rejected("not_batchable:model_container_mismatch")
        }
        guard let state = request.context.storage as? PreparedDecodeState else {
            return .rejected("not_batchable:prepared_state")
        }
        guard request.decodeStepSize == firstRequest.decodeStepSize else {
            return .rejected("not_batchable:decode_step_size_mismatch")
        }
        guard request.prefillToken == firstRequest.prefillToken else {
            return .rejected("not_batchable:prefill_token_mismatch")
        }
        guard isTextOnlyBatchDecodeState(state) else {
            return .rejected("not_batchable:state_modality")
        }
        guard state.activeKVQuantizationRatio == 0 else {
            return .rejected("not_batchable:active_kv_quantized")
        }
        states.append(state)
        parametersByRequest.append(makeDecodeParameters(
            from: request.sampling,
            maxOutputTokens: request.maxOutputTokens,
            decodeStepSize: request.decodeStepSize,
            acceleration: request.acceleration
        ))
    }

    if let cacheFailure = batchDecodeCacheCompatibilityFailure(states) {
        return .rejected(cacheFailure)
    }

    return .accepted(SwiftMLXBatchDecodeInput(
        container: container,
        requests: requests,
        states: states,
        parametersByRequest: parametersByRequest
    ))
}

private func batchDecodeCacheCompatibilityFailure(_ states: [PreparedDecodeState]) -> String? {
    guard states.count > 1,
          let first = states.first
    else {
        return "not_batchable:single_request"
    }

    guard let firstCacheSignature = cacheBatchSignature(first.cache),
          !firstCacheSignature.isEmpty
    else {
        return "not_batchable:cache_signature_unsupported"
    }

    for state in states.dropFirst() {
        guard state.input.text.tokens.size == first.input.text.tokens.size else {
            return "not_batchable:prompt_length_mismatch"
        }
        guard let signature = cacheBatchSignature(state.cache),
              !signature.isEmpty else {
            return "not_batchable:cache_signature_unsupported"
        }
        guard signature == firstCacheSignature else {
            return "not_batchable:cache_signature_mismatch"
        }
    }

    return nil
}

private func isTextOnlyBatchDecodeState(_ state: PreparedDecodeState) -> Bool {
    guard state.input.image == nil,
          state.input.video == nil
    else {
        return false
    }
    if case .tokens = state.prepared {
        return true
    }
    return false
}

private func cacheBatchSignature(_ cache: [KVCache]) -> [String]? {
    var signature: [String] = []
    for layer in cache {
        if let paged = layer as? PagedKVCache {
            signature.append(paged.decodeBatchSignature)
            continue
        }
        guard layer is KVCacheSimple || layer is RotatingKVCache else {
            return nil
        }
        signature.append(
            "\(type(of: layer)):\(layer.offset):\(layer.maxSize ?? -1):\(layer.state.map(\.shape)):\(layer.metaState)"
        )
    }
    return signature
}

private func makeFallbackDecodeBatchEvents(
    requests: [TextRuntimeDecodeRequest],
    backend: AutoSwiftMLXBackend,
    fallbackReason: String?
) async throws -> AsyncThrowingStream<TextBatchGenerationEvent, Error> {
    let (stream, continuation) = AsyncThrowingStream<TextBatchGenerationEvent, Error>.makeStream()
    let task = Task {
        do {
            try await withThrowingTaskGroup(of: Void.self) { group in
                for (requestIndex, request) in requests.enumerated() {
                    group.addTask {
                        let fallbackStream = try await backend.decodeEvents(
                            model: request.model,
                            draftModel: request.draftModel,
                            context: request.context,
                            sampling: request.sampling,
                            maxOutputTokens: request.maxOutputTokens,
                            decodeStepSize: request.decodeStepSize,
                            prefillToken: request.prefillToken,
                            acceleration: request.acceleration,
                            shouldAbort: request.shouldAbort
                        )
                        for try await event in fallbackStream {
                            switch event {
                            case .prefillStarted:
                                continue
                            case .token(let text):
                                continuation.yield(.token(requestIndex: requestIndex, text: text))
                            case .summary(let summary):
                                continuation.yield(.summary(
                                    requestIndex: requestIndex,
                                    summary.withDecodeBatchFallbackReason(fallbackReason)
                                ))
                            }
                        }
                    }
                }
                try await group.waitForAll()
            }
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

private func makeInitialBatchDecodeOutputs(
    batchInput: SwiftMLXBatchDecodeInput,
    context: ModelContext,
    cacheState: inout BatchDecodeCacheState,
    requestCaches: inout [[KVCache]]
) throws -> [LMOutput] {
    if let batchCache = cacheState.cache,
       let tokens = makeInitialBatchDecodeTokens(for: batchInput.states) {
        let output = context.model(
            tokens,
            cache: batchCache,
            state: nil
        )
        eval(output.logits)
        return batchInput.requests.indices.map { requestIndex in
            LMOutput(logits: output.logits[requestIndex ..< (requestIndex + 1), 0..., 0...])
        }
    }

    cacheState = BatchDecodeCacheState(cache: nil, sourceRequestIndices: [])
    return try batchInput.states.indices.map { requestIndex in
        try makeInitialDecodeOutput(
            decodeState: batchInput.states[requestIndex],
            context: context,
            cache: requestCaches[requestIndex]
        )
    }
}

private func makeInitialBatchDecodeTokens(for states: [PreparedDecodeState]) -> LMInput.Text? {
    var tokenArrays: [MLXArray] = []
    for state in states {
        guard case .tokens(let tokens) = state.prepared,
              tokens.tokens.dim(0) == 1
        else {
            return nil
        }
        tokenArrays.append(tokens.tokens)
    }
    return LMInput.Text(tokens: stacked(tokenArrays, axis: 0))
}

private func makePreparedBatchDecodeEvents(
    batchInput: SwiftMLXBatchDecodeInput,
    context: ModelContext
) throws -> AsyncThrowingStream<TextBatchGenerationEvent, Error> {
    let (stream, continuation) = AsyncThrowingStream<TextBatchGenerationEvent, Error>.makeStream()

    let task = Task {
        do {
            var requestCaches = batchInput.states.map(\.cache)
            for index in requestCaches.indices {
                let parameters = batchInput.parametersByRequest[index]
                guard parameters.kvBits != nil else {
                    continue
                }
                maybeQuantizeKVCache(
                    cache: &requestCaches[index],
                    kvBits: parameters.kvBits,
                    kvGroupSize: parameters.kvGroupSize,
                    quantizedKVStart: parameters.quantizedKVStart
                )
            }
            var batchCacheState = BatchDecodeCacheState(
                cache: makeBatchDecodeCache(from: requestCaches),
                sourceRequestIndices: batchInput.requests.indices.map { $0 }
            )
            let initialOutputs = try makeInitialBatchDecodeOutputs(
                batchInput: batchInput,
                context: context,
                cacheState: &batchCacheState,
                requestCaches: &requestCaches
            )

            var states: [BatchDecodeRequestState] = batchInput.requests.enumerated().map { requestIndex, request in
                let parameters = batchInput.parametersByRequest[requestIndex]
                var processor = parameters.processor()
                processor?.prompt(batchInput.states[requestIndex].input.text.tokens)
                return BatchDecodeRequestState(
                    request: request,
                    maxTokens: parameters.maxTokens,
                    output: initialOutputs[requestIndex],
                    processor: processor,
                    sampler: parameters.sampler(),
                    detokenizer: NaiveStreamingDetokenizer(tokenizer: context.tokenizer),
                    pendingToken: nil,
                    pendingTokenID: nil,
                    pendingBatchedTokenRow: nil,
                    generatedTokenCount: 0,
                    isFinished: false,
                    finishReason: nil
                )
            }

            let additionalEOSTokenIds = Set(
                context.configuration.extraEOSTokens.compactMap {
                    context.tokenizer.convertTokenToId($0)
                }
            )
            var decodeModelTotalMicros = 0
            var decodeModelCallCount = 0
            var decodeModelEvalSyncTotalMicros = 0
            var decodeModelEvalSyncCallCount = 0
            var decodeModelEvalSyncFirstMicros = 0
            var decodeModelEvalSyncMaxMicros = 0
            var decodeSampleTotalMicros = 0
            var decodeSampleCallCount = 0
            var decodeTokenEvalTotalMicros = 0
            var decodeTokenEvalCallCount = 0
            var decodeTokenIDTotalMicros = 0
            var decodeTokenIDCallCount = 0
            var decodeAsyncEvalTotalMicros = 0
            var decodeAsyncEvalCallCount = 0
            var decodeDetokenizeTotalMicros = 0
            var decodeDetokenizeCallCount = 0
            var decodeStreamYieldTotalMicros = 0
            var decodeStreamYieldCallCount = 0
            let shouldForceBatchModelEvalProbe =
                ProcessInfo.processInfo.environment["MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE"] == "1"
            let startedAt = Date.timeIntervalSinceReferenceDate
            var decodeLoopIterations = 0
            var maxModelEvalBatchSize = max(1, batchCacheState.sourceRequestIndices.count)
            let supportsBatchDecodeLookahead = shouldUseBatchDecodeLookahead(for: batchInput.states)

            for index in states.indices {
                if states[index].request.shouldAbort() {
                    states[index].isFinished = true
                    states[index].finishReason = "cancelled"
                    continue
                }
                if states[index].maxTokens.map({ $0 <= 0 }) ?? false {
                    states[index].isFinished = true
                    states[index].finishReason = "length"
                    continue
                }
                let sampleStartedAt = Date.timeIntervalSinceReferenceDate
                let token = sampleNextToken(
                    logits: states[index].output.logits,
                    processor: &states[index].processor,
                    sampler: states[index].sampler
                )
                decodeSampleCallCount += 1
                decodeSampleTotalMicros += elapsedMicros(since: sampleStartedAt)
                recordDecodeAsyncEval(
                    token,
                    shouldRecord: true,
                    totalMicros: &decodeAsyncEvalTotalMicros,
                    callCount: &decodeAsyncEvalCallCount
                )
                states[index].pendingToken = token
            }

            @discardableResult
            func consumeBatchDecodeLookaheadStep() -> Bool {
                guard let batchCache = batchCacheState.cache,
                      supportsBatchDecodeLookahead,
                      let lookaheadInput = makeBatchDecodeLookaheadInput(
                        sourceRequestIndices: batchCacheState.sourceRequestIndices,
                        states: states,
                        supportsBatchedArgMaxTokenIDs: batchInput.supportsBatchedArgMaxTokenIDs
                      )
                else {
                    return false
                }

                let activeIndices = batchCacheState.sourceRequestIndices
                let shouldAdvanceModel = activeIndices.contains { requestIndex in
                    states[requestIndex].maxTokens.map {
                        states[requestIndex].generatedTokenCount + 1 < $0
                    } ?? true
                }

                decodeLoopIterations += 1
                maxModelEvalBatchSize = max(maxModelEvalBatchSize, activeIndices.count)

                if shouldAdvanceModel {
                    let modelStartedAt = Date.timeIntervalSinceReferenceDate
                    let logits = context.model(lookaheadInput, cache: batchCache)
                    decodeModelCallCount += 1
                    decodeModelTotalMicros += elapsedMicros(since: modelStartedAt)
                    recordBatchModelEvalSyncProbe(
                        logits,
                        shouldForce: shouldForceBatchModelEvalProbe,
                        totalMicros: &decodeModelEvalSyncTotalMicros,
                        callCount: &decodeModelEvalSyncCallCount,
                        firstMicros: &decodeModelEvalSyncFirstMicros,
                        maxMicros: &decodeModelEvalSyncMaxMicros
                    )

                    updatePendingTokensFromBatchLogits(
                        logits,
                        activeIndices: activeIndices,
                        states: &states,
                        supportsBatchedArgMaxTokenIDs: batchInput.supportsBatchedArgMaxTokenIDs,
                        decodeSampleTotalMicros: &decodeSampleTotalMicros,
                        decodeSampleCallCount: &decodeSampleCallCount,
                        decodeTokenEvalTotalMicros: &decodeTokenEvalTotalMicros,
                        decodeTokenEvalCallCount: &decodeTokenEvalCallCount,
                        decodeTokenIDTotalMicros: &decodeTokenIDTotalMicros,
                        decodeTokenIDCallCount: &decodeTokenIDCallCount,
                        decodeAsyncEvalTotalMicros: &decodeAsyncEvalTotalMicros,
                        decodeAsyncEvalCallCount: &decodeAsyncEvalCallCount
                    )
                }

                let tokenEvalStartedAt = Date.timeIntervalSinceReferenceDate
                let emittedTokenIDs = lookaheadInput.reshaped([activeIndices.count])
                    .asArray(UInt32.self)
                    .map(Int.init)
                let tokenEvalMicros = elapsedMicros(since: tokenEvalStartedAt)
                decodeTokenEvalCallCount += 1
                decodeTokenEvalTotalMicros += tokenEvalMicros
                decodeTokenIDCallCount += emittedTokenIDs.count
                decodeTokenIDTotalMicros += tokenEvalMicros

                for (batchIndex, requestIndex) in activeIndices.enumerated() {
                    let tokenID = emittedTokenIDs[batchIndex]
                    if tokenID == context.tokenizer.unknownTokenId
                        || tokenID == context.tokenizer.eosTokenId
                        || additionalEOSTokenIds.contains(tokenID)
                    {
                        states[requestIndex].isFinished = true
                        states[requestIndex].finishReason = "stop"
                        clearPendingBatchDecodeToken(&states[requestIndex])
                        continue
                    }

                    states[requestIndex].generatedTokenCount += 1
                    let detokenizeStartedAt = Date.timeIntervalSinceReferenceDate
                    states[requestIndex].detokenizer.append(token: tokenID)
                    let chunk = states[requestIndex].detokenizer.next()
                    decodeDetokenizeCallCount += 1
                    decodeDetokenizeTotalMicros += elapsedMicros(since: detokenizeStartedAt)
                    if let chunk, !chunk.isEmpty {
                        let yieldStartedAt = Date.timeIntervalSinceReferenceDate
                        continuation.yield(.token(requestIndex: requestIndex, text: chunk))
                        decodeStreamYieldCallCount += 1
                        decodeStreamYieldTotalMicros += elapsedMicros(since: yieldStartedAt)
                    }

                    if states[requestIndex].maxTokens.map({ states[requestIndex].generatedTokenCount >= $0 }) ?? false {
                        states[requestIndex].isFinished = true
                        states[requestIndex].finishReason = "length"
                        clearPendingBatchDecodeToken(&states[requestIndex])
                        continue
                    }

                    if !shouldAdvanceModel {
                        clearPendingBatchDecodeToken(&states[requestIndex])
                    }
                }

                return true
            }

            while states.contains(where: { !$0.isFinished && $0.pendingToken != nil }) {
                if Task.isCancelled {
                    break
                }

                if consumeBatchDecodeLookaheadStep() {
                    continue
                }

                var activeIndices: [Int] = []
                var activeTokenIDs: [Int] = []
                for index in states.indices {
                    guard !states[index].isFinished,
                          let token = states[index].pendingToken
                    else {
                        continue
                    }

                    if states[index].request.shouldAbort() {
                        states[index].isFinished = true
                        states[index].finishReason = "cancelled"
                        states[index].pendingToken = nil
                        states[index].pendingTokenID = nil
                        states[index].pendingBatchedTokenRow = nil
                        continue
                    }

                    let tokenID: Int
                    if let pendingTokenID = states[index].pendingTokenID {
                        tokenID = pendingTokenID
                        states[index].pendingTokenID = nil
                    } else {
                        let tokenIDStartedAt = Date.timeIntervalSinceReferenceDate
                        tokenID = token.item(Int.self)
                        let tokenIDMicros = elapsedMicros(since: tokenIDStartedAt)
                        decodeTokenEvalCallCount += 1
                        decodeTokenEvalTotalMicros += tokenIDMicros
                        decodeTokenIDCallCount += 1
                        decodeTokenIDTotalMicros += tokenIDMicros
                    }
                    if tokenID == context.tokenizer.unknownTokenId
                        || tokenID == context.tokenizer.eosTokenId
                        || additionalEOSTokenIds.contains(tokenID)
                    {
                        states[index].isFinished = true
                        states[index].finishReason = "stop"
                        states[index].pendingToken = nil
                        states[index].pendingTokenID = nil
                        states[index].pendingBatchedTokenRow = nil
                        continue
                    }

                    states[index].generatedTokenCount += 1
                    let detokenizeStartedAt = Date.timeIntervalSinceReferenceDate
                    states[index].detokenizer.append(token: tokenID)
                    let chunk = states[index].detokenizer.next()
                    decodeDetokenizeCallCount += 1
                    decodeDetokenizeTotalMicros += elapsedMicros(since: detokenizeStartedAt)
                    if let chunk, !chunk.isEmpty {
                        let yieldStartedAt = Date.timeIntervalSinceReferenceDate
                        continuation.yield(.token(requestIndex: index, text: chunk))
                        decodeStreamYieldCallCount += 1
                        decodeStreamYieldTotalMicros += elapsedMicros(since: yieldStartedAt)
                    }

                    if states[index].maxTokens.map({ states[index].generatedTokenCount >= $0 }) ?? false {
                        states[index].isFinished = true
                        states[index].finishReason = "length"
                        states[index].pendingToken = nil
                        states[index].pendingTokenID = nil
                        states[index].pendingBatchedTokenRow = nil
                        continue
                    }

                    activeIndices.append(index)
                    activeTokenIDs.append(tokenID)
                }

                guard !activeIndices.isEmpty else {
                    break
                }

                decodeLoopIterations += 1
                if activeIndices == batchCacheState.sourceRequestIndices,
                   let batchCache = batchCacheState.cache {
                    maxModelEvalBatchSize = max(maxModelEvalBatchSize, activeIndices.count)
                    let nextInput = makeBatchDecodeNextInput(
                        activeIndices: activeIndices,
                        activeTokenIDs: activeTokenIDs,
                        states: states,
                        supportsBatchedArgMaxTokenIDs: batchInput.supportsBatchedArgMaxTokenIDs
                    )
                    let modelStartedAt = Date.timeIntervalSinceReferenceDate
                    let logits = context.model(nextInput, cache: batchCache)
                    decodeModelCallCount += 1
                    decodeModelTotalMicros += elapsedMicros(since: modelStartedAt)
                    recordBatchModelEvalSyncProbe(
                        logits,
                        shouldForce: shouldForceBatchModelEvalProbe,
                        totalMicros: &decodeModelEvalSyncTotalMicros,
                        callCount: &decodeModelEvalSyncCallCount,
                        firstMicros: &decodeModelEvalSyncFirstMicros,
                        maxMicros: &decodeModelEvalSyncMaxMicros
                    )

                    updatePendingTokensFromBatchLogits(
                        logits,
                        activeIndices: activeIndices,
                        states: &states,
                        supportsBatchedArgMaxTokenIDs: batchInput.supportsBatchedArgMaxTokenIDs,
                        decodeSampleTotalMicros: &decodeSampleTotalMicros,
                        decodeSampleCallCount: &decodeSampleCallCount,
                        decodeTokenEvalTotalMicros: &decodeTokenEvalTotalMicros,
                        decodeTokenEvalCallCount: &decodeTokenEvalCallCount,
                        decodeTokenIDTotalMicros: &decodeTokenIDTotalMicros,
                        decodeTokenIDCallCount: &decodeTokenIDCallCount,
                        decodeAsyncEvalTotalMicros: &decodeAsyncEvalTotalMicros,
                        decodeAsyncEvalCallCount: &decodeAsyncEvalCallCount
                    )
                } else {
                    materializeBatchCacheState(&batchCacheState, into: &requestCaches)
                    if activeIndices.count > 1,
                       let rebuiltCache = makeBatchDecodeCache(from: activeIndices.map { requestCaches[$0] }) {
                        batchCacheState = BatchDecodeCacheState(
                            cache: rebuiltCache,
                            sourceRequestIndices: activeIndices
                        )
                        maxModelEvalBatchSize = max(maxModelEvalBatchSize, activeIndices.count)
                        let nextInput = makeBatchDecodeNextInput(
                            activeIndices: activeIndices,
                            activeTokenIDs: activeTokenIDs,
                            states: states,
                            supportsBatchedArgMaxTokenIDs: batchInput.supportsBatchedArgMaxTokenIDs
                        )
                        let modelStartedAt = Date.timeIntervalSinceReferenceDate
                        let logits = context.model(nextInput, cache: rebuiltCache)
                        decodeModelCallCount += 1
                        decodeModelTotalMicros += elapsedMicros(since: modelStartedAt)
                        recordBatchModelEvalSyncProbe(
                            logits,
                            shouldForce: shouldForceBatchModelEvalProbe,
                            totalMicros: &decodeModelEvalSyncTotalMicros,
                            callCount: &decodeModelEvalSyncCallCount,
                            firstMicros: &decodeModelEvalSyncFirstMicros,
                            maxMicros: &decodeModelEvalSyncMaxMicros
                        )

                        updatePendingTokensFromBatchLogits(
                            logits,
                            activeIndices: activeIndices,
                            states: &states,
                            supportsBatchedArgMaxTokenIDs: batchInput.supportsBatchedArgMaxTokenIDs,
                            decodeSampleTotalMicros: &decodeSampleTotalMicros,
                            decodeSampleCallCount: &decodeSampleCallCount,
                            decodeTokenEvalTotalMicros: &decodeTokenEvalTotalMicros,
                            decodeTokenEvalCallCount: &decodeTokenEvalCallCount,
                            decodeTokenIDTotalMicros: &decodeTokenIDTotalMicros,
                            decodeTokenIDCallCount: &decodeTokenIDCallCount,
                            decodeAsyncEvalTotalMicros: &decodeAsyncEvalTotalMicros,
                            decodeAsyncEvalCallCount: &decodeAsyncEvalCallCount
                        )
                    } else {
                        for (tokenIndex, requestIndex) in activeIndices.enumerated() {
                            let nextInput = LMInput.Text(tokens: MLXArray([activeTokenIDs[tokenIndex]]))
                            let modelStartedAt = Date.timeIntervalSinceReferenceDate
                            let nextOutput = context.model(
                                nextInput[text: .newAxis],
                                cache: requestCaches[requestIndex].isEmpty ? nil : requestCaches[requestIndex],
                                state: states[requestIndex].output.state
                            )
                            decodeModelCallCount += 1
                            decodeModelTotalMicros += elapsedMicros(since: modelStartedAt)
                            states[requestIndex].output = nextOutput
                            let sampleStartedAt = Date.timeIntervalSinceReferenceDate
                            let token = sampleNextToken(
                                logits: nextOutput.logits,
                                processor: &states[requestIndex].processor,
                                sampler: states[requestIndex].sampler
                            )
                            decodeSampleCallCount += 1
                            decodeSampleTotalMicros += elapsedMicros(since: sampleStartedAt)
                            recordDecodeAsyncEval(
                                token,
                                shouldRecord: true,
                                totalMicros: &decodeAsyncEvalTotalMicros,
                                callCount: &decodeAsyncEvalCallCount
                            )
                            states[requestIndex].pendingToken = token
                            states[requestIndex].pendingTokenID = nil
                            states[requestIndex].pendingBatchedTokenRow = nil
                        }
                    }
                }
            }

            let decodeLoopTotalMicros = elapsedMicros(since: startedAt)
            Stream().synchronize()
            let elapsed = max(Double(decodeLoopTotalMicros) / 1_000_000, 0.000_001)
            let totalCompletionTokens = states.reduce(0) { $0 + $1.generatedTokenCount }
            let batchTokensPerSecond = Double(totalCompletionTokens) / elapsed
            let decodeBatchProbe = DecodeBatchProbeSummary(
                decodeLoopTotalMicros: decodeLoopTotalMicros,
                decodeModelTotalMicros: decodeModelTotalMicros,
                decodeModelCallCount: decodeModelCallCount,
                decodeModelEvalSyncTotalMicros: decodeModelEvalSyncTotalMicros,
                decodeModelEvalSyncCallCount: decodeModelEvalSyncCallCount,
                decodeModelEvalSyncFirstMicros: decodeModelEvalSyncFirstMicros,
                decodeModelEvalSyncMaxMicros: decodeModelEvalSyncMaxMicros,
                decodeAsyncEvalTotalMicros: decodeAsyncEvalTotalMicros,
                decodeAsyncEvalCallCount: decodeAsyncEvalCallCount,
                decodeSampleTotalMicros: decodeSampleTotalMicros,
                decodeSampleCallCount: decodeSampleCallCount,
                decodeTokenEvalTotalMicros: decodeTokenEvalTotalMicros,
                decodeTokenEvalCallCount: decodeTokenEvalCallCount,
                decodeTokenIDTotalMicros: decodeTokenIDTotalMicros,
                decodeTokenIDCallCount: decodeTokenIDCallCount,
                decodeDetokenizeTotalMicros: decodeDetokenizeTotalMicros,
                decodeDetokenizeCallCount: decodeDetokenizeCallCount,
                decodeStreamYieldTotalMicros: decodeStreamYieldTotalMicros,
                decodeStreamYieldCallCount: decodeStreamYieldCallCount
            )

            for (requestIndex, state) in states.enumerated() {
                let finishReason = state.finishReason ?? resolvedTextGenerationFinishReason(
                    completionTokens: state.generatedTokenCount,
                    maxTokens: state.maxTokens,
                    wasCancelled: state.request.shouldAbort() || (Task.isCancelled && !state.isFinished)
                )
                continuation.yield(.summary(
                    requestIndex: requestIndex,
                    TextGenerationSummary(
                        promptTokens: batchInput.states[requestIndex].input.text.tokens.size,
                        completionTokens: state.generatedTokenCount,
                        tokensPerSecond: Double(state.generatedTokenCount) / elapsed,
                        finishReason: finishReason,
                        decodeBatchSize: maxModelEvalBatchSize,
                        modelEvalBatchSize: maxModelEvalBatchSize,
                        decodeLoopIterations: decodeLoopIterations,
                        perBatchOutputTokenCount: totalCompletionTokens,
                        perBatchOutputTokensPerSecond: batchTokensPerSecond,
                        decodeBatchProbe: decodeBatchProbe
                    )
                ))
            }

            continuation.yield(.batchSummary(
                TextBatchGenerationSummary(
                    decodeBatchSize: maxModelEvalBatchSize,
                    modelEvalBatchSize: maxModelEvalBatchSize,
                    decodeLoopIterations: decodeLoopIterations,
                    outputTokenCount: totalCompletionTokens,
                    tokensPerSecond: batchTokensPerSecond
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

private func clearPendingBatchDecodeToken(_ state: inout BatchDecodeRequestState) {
    state.pendingToken = nil
    state.pendingTokenID = nil
    state.pendingBatchedTokenRow = nil
}

private func recordBatchModelEvalSyncProbe(
    _ logits: MLXArray,
    shouldForce: Bool,
    totalMicros: inout Int,
    callCount: inout Int,
    firstMicros: inout Int,
    maxMicros: inout Int
) {
    guard shouldForce else {
        return
    }

    let modelEvalStartedAt = Date.timeIntervalSinceReferenceDate
    eval(logits)
    callCount += 1
    let modelEvalSyncMicros = elapsedMicros(since: modelEvalStartedAt)
    if callCount == 1 {
        firstMicros = modelEvalSyncMicros
    }
    totalMicros += modelEvalSyncMicros
    maxMicros = max(maxMicros, modelEvalSyncMicros)
}

private func recordDecodeAsyncEval(
    _ array: MLXArray,
    shouldRecord: Bool,
    totalMicros: inout Int,
    callCount: inout Int
) {
    let startedAt = shouldRecord ? Date.timeIntervalSinceReferenceDate : 0
    asyncEval(array)
    guard shouldRecord else {
        return
    }
    callCount += 1
    totalMicros += elapsedMicros(since: startedAt)
}

private func updatePendingTokensFromBatchLogits(
    _ logits: MLXArray,
    activeIndices: [Int],
    states: inout [BatchDecodeRequestState],
    supportsBatchedArgMaxTokenIDs: Bool,
    decodeSampleTotalMicros: inout Int,
    decodeSampleCallCount: inout Int,
    decodeTokenEvalTotalMicros: inout Int,
    decodeTokenEvalCallCount: inout Int,
    decodeTokenIDTotalMicros: inout Int,
    decodeTokenIDCallCount: inout Int,
    decodeAsyncEvalTotalMicros: inout Int,
    decodeAsyncEvalCallCount: inout Int
) {
    guard supportsBatchedArgMaxTokenIDs,
          activeIndices.allSatisfy({ states[$0].processor == nil })
    else {
        for (batchIndex, requestIndex) in activeIndices.enumerated() {
            states[requestIndex].output = LMOutput(
                logits: logits[batchIndex ..< (batchIndex + 1), 0..., 0...]
            )
            let sampleStartedAt = Date.timeIntervalSinceReferenceDate
            let token = sampleNextToken(
                logits: states[requestIndex].output.logits,
                processor: &states[requestIndex].processor,
                sampler: states[requestIndex].sampler
            )
            decodeSampleCallCount += 1
            decodeSampleTotalMicros += elapsedMicros(since: sampleStartedAt)
            recordDecodeAsyncEval(
                token,
                shouldRecord: true,
                totalMicros: &decodeAsyncEvalTotalMicros,
                callCount: &decodeAsyncEvalCallCount
            )
            states[requestIndex].pendingToken = token
            states[requestIndex].pendingTokenID = nil
            states[requestIndex].pendingBatchedTokenRow = nil
        }
        return
    }

    let sampleStartedAt = Date.timeIntervalSinceReferenceDate
    let tokenIDs = batchedArgMaxTokenIDs(from: logits)
    decodeSampleCallCount += activeIndices.count
    decodeSampleTotalMicros += elapsedMicros(since: sampleStartedAt)
    recordDecodeAsyncEval(
        tokenIDs,
        shouldRecord: true,
        totalMicros: &decodeAsyncEvalTotalMicros,
        callCount: &decodeAsyncEvalCallCount
    )

    for (batchIndex, requestIndex) in activeIndices.enumerated() {
        states[requestIndex].output = LMOutput(
            logits: logits[batchIndex ..< (batchIndex + 1), 0..., 0...]
        )
        states[requestIndex].pendingToken = tokenIDs[batchIndex ..< (batchIndex + 1)]
        states[requestIndex].pendingTokenID = nil
        states[requestIndex].pendingBatchedTokenRow = tokenIDs[batchIndex ..< (batchIndex + 1)]
    }
}

private func makeBatchDecodeNextInput(
    activeIndices: [Int],
    activeTokenIDs: [Int],
    states: [BatchDecodeRequestState],
    supportsBatchedArgMaxTokenIDs: Bool
) -> MLXArray {
    guard supportsBatchedArgMaxTokenIDs,
          activeIndices.allSatisfy({ states[$0].processor == nil }),
          activeIndices.allSatisfy({ states[$0].pendingBatchedTokenRow != nil })
    else {
        return MLXArray(activeTokenIDs, [activeTokenIDs.count, 1])
    }
    let rows = activeIndices.compactMap { states[$0].pendingBatchedTokenRow }
    return stacked(rows, axis: 0)
}

private func makeBatchDecodeLookaheadInput(
    sourceRequestIndices: [Int],
    states: [BatchDecodeRequestState],
    supportsBatchedArgMaxTokenIDs: Bool
) -> MLXArray? {
    guard supportsBatchedArgMaxTokenIDs,
          !sourceRequestIndices.isEmpty,
          sourceRequestIndices.allSatisfy({
              !states[$0].isFinished
                  && states[$0].processor == nil
                  && !states[$0].request.shouldAbort()
                  && states[$0].pendingBatchedTokenRow != nil
          })
    else {
        return nil
    }
    let rows = sourceRequestIndices.compactMap { states[$0].pendingBatchedTokenRow }
    return stacked(rows, axis: 0)
}

private func shouldUseBatchDecodeLookahead(for states: [PreparedDecodeState]) -> Bool {
    guard states.count > 1 else {
        return false
    }
    return states.allSatisfy { state in
        state.input.text.tokens.size <= shortPromptBatchDecodeLookaheadMaxPromptTokens
    }
}

private func batchedArgMaxTokenIDs(from logits: MLXArray) -> MLXArray {
    argMax(logits[0..., -1, 0...], axis: -1)
}

private final class BatchPositionedKVCacheAdapter: KVCache, BatchPositionedKVCache {
    private var wrapped: KVCache
    private var currentBatchOffset: MLXArray
    let sourceSimpleStep: Int?

    init(wrapped: KVCache, batchOffset: MLXArray) {
        self.wrapped = wrapped
        self.currentBatchOffset = batchOffset
        self.sourceSimpleStep = (wrapped as? KVCacheSimple)?.step
    }

    var offset: Int { wrapped.offset }
    fileprivate var underlyingLayer: KVCache { wrapped }
    var batchOffset: MLXArray { currentBatchOffset }
    var maxSize: Int? { wrapped.maxSize }
    var state: [MLXArray] {
        get { wrapped.state }
        set {
            wrapped.state = newValue
            currentBatchOffset = MLXArray(
                Array(repeating: Int32(wrapped.offset), count: newValue.first?.dim(0) ?? 1)
            )
        }
    }
    var metaState: [String] {
        get { wrapped.metaState }
        set { wrapped.metaState = newValue }
    }
    var isTrimmable: Bool { wrapped.isTrimmable }

    func innerState() -> [MLXArray] {
        wrapped.innerState()
    }

    func update(keys: MLXArray, values: MLXArray) -> (MLXArray, MLXArray) {
        let result = wrapped.update(keys: keys, values: values)
        currentBatchOffset = currentBatchOffset + keys.dim(2)
        return result
    }

    @discardableResult
    func trim(_ n: Int) -> Int {
        wrapped.trim(n)
    }

    func makeMask(
        n: Int,
        windowSize: Int?,
        returnArray: Bool
    ) -> MLXFast.ScaledDotProductAttentionMaskMode {
        wrapped.makeMask(n: n, windowSize: windowSize, returnArray: returnArray)
    }
}

private final class BatchedPagedKVCache: KVCache, BatchPositionedKVCache {
    private let rowCaches: [PagedKVCache]

    init?(rowCaches: [PagedKVCache]) {
        guard let first = rowCaches.first,
              rowCaches.allSatisfy({ $0.decodeBatchSignature == first.decodeBatchSignature })
        else {
            return nil
        }
        self.rowCaches = rowCaches
    }

    var offset: Int { rowCaches[0].offset }
    var batchOffset: MLXArray { MLXArray(rowCaches.map { Int32($0.offset) }) }
    var maxSize: Int? { nil }
    var isTrimmable: Bool { true }

    var state: [MLXArray] {
        get {
            let rowStates = rowCaches.map(\.state)
            guard let first = rowStates.first, !first.isEmpty else { return [] }
            return first.indices.map { stateIndex in
                concatenated(rowStates.map { $0[stateIndex] }, axis: 0)
            }
        }
        set {
            precondition(newValue.count == 2, "Batched paged KV state requires keys and values.")
            precondition(
                newValue.allSatisfy { $0.dim(0) == rowCaches.count },
                "Batched paged KV state must contain one row per source cache."
            )
            for rowIndex in rowCaches.indices {
                rowCaches[rowIndex].state = newValue.map { array in
                    array[rowIndex ..< (rowIndex + 1), 0..., 0..., 0...]
                }
            }
        }
    }

    var metaState: [String] {
        get { rowCaches[0].metaState }
        set {
            for cache in rowCaches {
                cache.metaState = newValue
            }
        }
    }

    func innerState() -> [MLXArray] {
        state
    }

    func update(keys: MLXArray, values: MLXArray) -> (MLXArray, MLXArray) {
        precondition(keys.dim(0) == rowCaches.count, "Paged KV batch size must match row cache count.")
        precondition(values.dim(0) == rowCaches.count, "Paged KV batch size must match row cache count.")
        let updated = rowCaches.indices.map { rowIndex in
            rowCaches[rowIndex].update(
                keys: keys[rowIndex ..< (rowIndex + 1), 0..., 0..., 0...],
                values: values[rowIndex ..< (rowIndex + 1), 0..., 0..., 0...]
            )
        }
        return (
            concatenated(updated.map(\.0), axis: 0),
            concatenated(updated.map(\.1), axis: 0)
        )
    }

    @discardableResult
    func trim(_ n: Int) -> Int {
        let trimmed = rowCaches.map { $0.trim(n) }
        precondition(Set(trimmed).count == 1, "Paged KV batch rows must trim equally.")
        return trimmed[0]
    }

    func makeMask(
        n: Int,
        windowSize: Int?,
        returnArray: Bool
    ) -> MLXFast.ScaledDotProductAttentionMaskMode {
        rowCaches[0].makeMask(n: n, windowSize: windowSize, returnArray: returnArray)
    }

    fileprivate func rowCache(at index: Int) -> PagedKVCache {
        rowCaches[index]
    }
}

private func makeBatchDecodeCache(from caches: [[KVCache]]) -> [KVCache]? {
    guard let first = caches.first,
          !first.isEmpty
    else {
        return nil
    }

    var result: [KVCache] = []
    for layerIndex in first.indices {
        let layers = caches.map { $0[layerIndex] }
        guard let batchedLayer = makeBatchDecodeCacheLayer(from: layers) else {
            return nil
        }
        result.append(batchedLayer)
    }
    return result
}

private func makeBatchDecodeCacheLayer(from layers: [KVCache]) -> KVCache? {
    guard let first = layers.first,
          layers.allSatisfy({ type(of: $0) == type(of: first) && $0.offset == first.offset && $0.metaState == first.metaState })
    else {
        return nil
    }

    let pagedRows = layers.compactMap { $0 as? PagedKVCache }
    if pagedRows.count == layers.count {
        return BatchedPagedKVCache(rowCaches: pagedRows)
    }

    let stateCount = first.state.count
    guard stateCount > 0 else {
        return nil
    }
    let batchedState = (0 ..< stateCount).map { stateIndex in
        concatenated(layers.map { $0.state[stateIndex] }, axis: 0)
    }

    var batched: KVCache
    switch first {
    case is RotatingKVCache:
        guard let maxSize = first.maxSize else {
            return nil
        }
        batched = RotatingKVCache(maxSize: maxSize)
    default:
        let simple = KVCacheSimple()
        if let firstSimple = first as? KVCacheSimple {
            simple.step = firstSimple.step
        }
        batched = simple
    }

    batched.state = batchedState
    if !first.metaState.isEmpty {
        batched.metaState = first.metaState
    }
    let batchOffset = MLXArray(layers.map { Int32($0.offset) })
    return BatchPositionedKVCacheAdapter(wrapped: batched, batchOffset: batchOffset)
}

private func materializeBatchCacheState(
    _ cacheState: inout BatchDecodeCacheState,
    into requestCaches: inout [[KVCache]]
) {
    guard let cache = cacheState.cache,
          !cacheState.sourceRequestIndices.isEmpty
    else {
        cacheState = BatchDecodeCacheState(cache: nil, sourceRequestIndices: [])
        return
    }

    let splitCaches = splitBatchDecodeCache(
        cache,
        batchSize: cacheState.sourceRequestIndices.count
    )
    for (batchIndex, requestIndex) in cacheState.sourceRequestIndices.enumerated()
        where requestCaches.indices.contains(requestIndex)
    {
        requestCaches[requestIndex] = splitCaches[batchIndex]
    }
    cacheState = BatchDecodeCacheState(cache: nil, sourceRequestIndices: [])
}

private func splitBatchDecodeCache(_ cache: [KVCache], batchSize: Int) -> [[KVCache]] {
    (0 ..< batchSize).map { batchIndex in
        cache.map { splitBatchDecodeCacheLayer($0, batchIndex: batchIndex) }
    }
}

private func splitBatchDecodeCacheLayer(_ layer: KVCache, batchIndex: Int) -> KVCache {
    if let paged = layer as? BatchedPagedKVCache {
        return paged.rowCache(at: batchIndex)
    }
    let adapter = layer as? BatchPositionedKVCacheAdapter
    let underlyingLayer = adapter?.underlyingLayer ?? layer
    let state = layer.state
    let metaState = layer.metaState
    let splitState = state.map { array in
        array[batchIndex ..< (batchIndex + 1), 0..., 0..., 0...]
    }

    var split: KVCache
    if underlyingLayer is RotatingKVCache {
        let maxSize = underlyingLayer.maxSize ?? Int(metaState.dropFirst().first ?? "0") ?? 0
        split = RotatingKVCache(maxSize: max(1, maxSize))
    } else {
        let simple = KVCacheSimple()
        if let sourceStep = adapter?.sourceSimpleStep {
            simple.step = sourceStep
        } else if let source = underlyingLayer as? KVCacheSimple {
            simple.step = source.step
        }
        split = simple
    }

    split.state = splitState
    if !metaState.isEmpty {
        split.metaState = metaState
    }
    return split
}

func melixTestingBatchedArgMaxTokenIDs(from logits: MLXArray) -> [Int] {
    batchedArgMaxTokenIDs(from: logits).asArray(UInt32.self).map(Int.init)
}

func melixTestingMakeBatchDecodeCache(from caches: [[KVCache]]) -> [KVCache]? {
    makeBatchDecodeCache(from: caches)
}

func melixTestingSplitBatchDecodeCache(_ cache: [KVCache], batchSize: Int) -> [[KVCache]] {
    splitBatchDecodeCache(cache, batchSize: batchSize)
}

#if canImport(MLXLLM)
private func makePreparedDFlashSpeculativeDecodeEvents(
    draftRuntime: SwiftDFlashDraftRuntime,
    decodeState: PreparedDecodeState,
    targetContext: ModelContext,
    parameters: GenerateParameters,
    acceleration: Melix_Worker_V1_AccelerationPolicy
) throws -> AsyncThrowingStream<RawTextGenerationEvent, Error> {
    guard let draftModel = draftRuntime.model else {
        throw RuntimeUnavailableError(
            message: "DFlash speculative decode requires loaded DFlash draft weights."
        )
    }
    guard let targetModel = targetContext.model as? DFlashTargetModel else {
        throw RuntimeUnavailableError(
            message: "DFlash speculative decode requires a Swift MLX target model with DFlash hidden-state hooks."
        )
    }
    guard targetModel.dflashHiddenSize == draftRuntime.configuration.hiddenSize else {
        throw RuntimeUnavailableError(
            message: "DFlash draft hidden size does not match the target model hidden size."
        )
    }

    let promptTokenIDs = decodeState.input.text.tokens.asArray(Int.self)
    guard !promptTokenIDs.isEmpty else {
        throw RuntimeUnavailableError(message: "DFlash speculative decode requires a non-empty prompt.")
    }

    let targetLayerIDs = draftRuntime.configuration.targetLayerIDs
    let configuredBlockSize = max(1, draftRuntime.configuration.blockSize)
    let requestedDraftTokens = acceleration.numDraftTokens == 0
        ? configuredBlockSize
        : Int(acceleration.numDraftTokens)
    let maxDraftTokens = max(1, min(configuredBlockSize, requestedDraftTokens))
    let maskTokenID = draftRuntime.configuration.maskTokenID
    let maxTokens = parameters.maxTokens ?? 256
    let additionalEOSTokenIDs = Set(
        targetContext.configuration.extraEOSTokens.compactMap {
            targetContext.tokenizer.convertTokenToId($0)
        }
    )
    let tokenMetadata = SpeculativeTokenMetadata(
        unknownTokenID: targetContext.tokenizer.unknownTokenId,
        eosTokenID: targetContext.tokenizer.eosTokenId,
        additionalEOSTokenIDs: additionalEOSTokenIDs
    )
    let dflashProbe = DFlashSpeculativeProbeLogger.fromEnvironment()
    dflashProbe?.record(
        stage: "preflight",
        fields: [
            "runtime": "swift-mlx-native-dflash",
            "reference_runtime": "dflash-mlx",
            "uses_dflash_mlx": false,
            "draft_model_id": draftRuntime.modelID,
            "draft_directory": draftRuntime.directoryURL?.path ?? "",
            "target_hidden_size": targetModel.dflashHiddenSize,
            "target_layer_count": targetModel.dflashLayerCount,
            "draft_hidden_size": draftRuntime.configuration.hiddenSize,
            "draft_hidden_layers": draftRuntime.configuration.hiddenLayers,
            "draft_block_size": configuredBlockSize,
            "requested_draft_tokens": requestedDraftTokens,
            "effective_draft_tokens": maxDraftTokens,
            "mask_token_id": maskTokenID,
            "target_layer_ids": targetLayerIDs,
            "prompt_tokens": dflashTokenIDPreview(promptTokenIDs),
        ]
    )
    let (stream, continuation) = AsyncThrowingStream<RawTextGenerationEvent, Error>.makeStream()

    func makeTargetState(tokenIDs: [Int]) throws -> DFlashTargetDecodeState {
        let cache = targetContext.model.newCache(parameters: nil)
        let input = LMInput.Text(tokens: MLXArray(tokenIDs))[text: .newAxis]
        let result = try targetModel.dflashForward(
            input: input,
            cache: cache,
            targetLayerIDs: targetLayerIDs
        )
        eval(result.logits)
        eval(result.hidden)
        return DFlashTargetDecodeState(
            state: SpeculativeDecodeRuntimeState(
                cache: cache,
                output: LMOutput(logits: result.logits),
                promptTokenCount: promptTokenIDs.count,
                prefillQuantizeMicros: decodeState.prefillQuantizeMicros
            ),
            logits: result.logits,
            hidden: result.hidden
        )
    }

    func advanceTargetState(
        _ state: SpeculativeDecodeRuntimeState,
        tokenIDs: [Int]
    ) throws -> DFlashTargetDecodeState {
        var advancedState = state
        let input = LMInput.Text(tokens: MLXArray(tokenIDs))[text: .newAxis]
        let result = try targetModel.dflashForward(
            input: input,
            cache: advancedState.cache.isEmpty ? nil : advancedState.cache,
            targetLayerIDs: targetLayerIDs
        )
        eval(result.logits)
        eval(result.hidden)
        advancedState.output = LMOutput(logits: result.logits, state: advancedState.output.state)
        return DFlashTargetDecodeState(
            state: advancedState,
            logits: result.logits,
            hidden: result.hidden
        )
    }

    func snapshotCache(_ cache: [KVCache]) -> [KVCacheLayerSnapshot] {
        cache.map { layer in
            KVCacheLayerSnapshot(state: layer.state, metaState: layer.metaState)
        }
    }

    func makeState(
        byRestoring state: SpeculativeDecodeRuntimeState,
        from snapshot: [KVCacheLayerSnapshot]
    ) -> SpeculativeDecodeRuntimeState {
        var restoredState = state
        var restoredCache = targetContext.model.newCache(parameters: nil)
        for index in 0 ..< min(restoredCache.count, snapshot.count) {
            if !snapshot[index].state.isEmpty {
                restoredCache[index].state = snapshot[index].state
            }
            if !snapshot[index].metaState.isEmpty {
                restoredCache[index].metaState = snapshot[index].metaState
            }
        }
        restoredState.cache = restoredCache
        return restoredState
    }

    let task = Task {
        do {
            var committedTokenIDs = promptTokenIDs
            var currentTargetState = try makeTargetState(tokenIDs: committedTokenIDs)
            var currentTargetHidden = currentTargetState.hidden
            var generatedTokenCount = 0
            var acceptedTokenCount = 0
            var rejectedTokenCount = 0
            var proposedTokenCount = 0
            var draftProposeMicros = 0
            var targetVerifyMicros = 0
            var targetRepairMicros = 0
            var targetFinalRebuildSkippedCount = 0
            var targetBonusAdvanceSkippedCount = 0
            var rollbackCount = 0
            var detokenizer = NaiveStreamingDetokenizer(tokenizer: targetContext.tokenizer)
            let targetSampler = parameters.sampler()
            let draftSampler = parameters.sampler()
            let startedAt = Date.timeIntervalSinceReferenceDate
            var finished = false
            var roundIndex = 0

            dflashProbe?.record(
                stage: "prefill",
                fields: [
                    "prompt_token_count": promptTokenIDs.count,
                    "target_logits": dflashArrayDescriptor(currentTargetState.logits),
                    "target_hidden": dflashArrayDescriptor(currentTargetHidden),
                    "target_cache_layers": currentTargetState.state.cache.count,
                ]
            )

            @discardableResult
            func emitToken(_ tokenID: Int) -> Bool {
                if isSpeculativeTerminalToken(tokenID, metadata: tokenMetadata) {
                    return false
                }
                committedTokenIDs.append(tokenID)
                generatedTokenCount += 1
                detokenizer.append(token: tokenID)
                if let chunk = detokenizer.next() {
                    continuation.yield(.chunk(chunk))
                }
                return true
            }

            while !finished && generatedTokenCount < maxTokens {
                if Task.isCancelled {
                    break
                }

                let remainingTokens = max(0, maxTokens - generatedTokenCount)
                let proposalCount = min(maxDraftTokens, remainingTokens)
                guard proposalCount > 0 else {
                    break
                }

                let currentRoundIndex = roundIndex
                roundIndex += 1
                var stagedFirstProcessor = parameters.processor()
                stagedFirstProcessor?.prompt(MLXArray(committedTokenIDs))
                let stagedFirstCandidate = sampleNextToken(
                    logits: currentTargetState.state.output.logits,
                    processor: &stagedFirstProcessor,
                    sampler: targetSampler
                )
                let stagedFirstCandidateID = stagedFirstCandidate.item(Int.self)
                if isSpeculativeTerminalToken(stagedFirstCandidateID, metadata: tokenMetadata) {
                    finished = true
                    break
                }

                let draftBlockTokenIDs = [stagedFirstCandidateID]
                    + Array(repeating: maskTokenID, count: max(0, proposalCount - 1))
                let draftTailCount = max(0, proposalCount - 1)
                dflashProbe?.record(
                    stage: "draft_request",
                    fields: [
                        "round": currentRoundIndex,
                        "generated_token_count": generatedTokenCount,
                        "committed_token_count": committedTokenIDs.count,
                        "proposal_count": proposalCount,
                        "target_staged_first_candidate_id": stagedFirstCandidateID,
                        "draft_block_token_ids": draftBlockTokenIDs,
                        "draft_block_token_text": draftBlockTokenIDs.map {
                            targetContext.tokenizer.decode(tokens: [$0])
                        },
                        "draft_block_starts_with_target_staged_first": draftBlockTokenIDs.first
                            == stagedFirstCandidateID,
                        "omlx_expected_block_prefix": [stagedFirstCandidateID],
                        "mask_token_id": maskTokenID,
                        "target_hidden": dflashArrayDescriptor(currentTargetHidden),
                        "draft_cache_used": false,
                    ]
                )

                if draftTailCount == 0 {
                    let generatedBeforeCommit = generatedTokenCount
                    let committedBeforeCommit = committedTokenIDs.count
                    guard emitToken(stagedFirstCandidateID) else {
                        break
                    }
                    if generatedTokenCount < maxTokens {
                        currentTargetState = try advanceTargetState(
                            currentTargetState.state,
                            tokenIDs: [stagedFirstCandidateID]
                        )
                        currentTargetHidden = concatenated(
                            [currentTargetHidden, currentTargetState.hidden],
                            axis: 1
                        )
                    } else {
                        finished = true
                    }
                    dflashProbe?.record(
                        stage: "commit",
                        fields: [
                            "round": currentRoundIndex,
                            "action": "staged_first_only",
                            "accepted_this_round": 0,
                            "staged_first_token_id": stagedFirstCandidateID,
                            "generated_before": generatedBeforeCommit,
                            "generated_after": generatedTokenCount,
                            "committed_before": committedBeforeCommit,
                            "committed_after": committedTokenIDs.count,
                            "committed_tokens": dflashTokenIDPreview(committedTokenIDs),
                            "target_hidden": dflashArrayDescriptor(currentTargetHidden),
                            "rollback_count": rollbackCount,
                        ]
                    )
                    continue
                }

                let proposalStartedAt = Date.timeIntervalSinceReferenceDate
                let draftInput = LMInput.Text(tokens: MLXArray(draftBlockTokenIDs))[text: .newAxis]
                let inputEmbeddings = try targetModel.dflashTokenEmbeddings(draftInput.tokens)
                let draftHidden = draftModel.callAsFunction(
                    inputEmbeddings: inputEmbeddings,
                    targetHidden: currentTargetHidden,
                    cache: nil
                )
                let draftLogits = try targetModel.dflashLogits(fromHiddenStates: draftHidden)
                eval(draftLogits)

                var draftProcessor = parameters.processor()
                draftProcessor?.prompt(MLXArray(committedTokenIDs + [stagedFirstCandidateID]))
                var proposedTailTokenIDs = [Int]()
                for position in 0 ..< draftTailCount {
                    let token = sampleNextToken(
                        logits: draftLogits,
                        position: position + 1,
                        processor: &draftProcessor,
                        sampler: draftSampler
                    )
                    proposedTailTokenIDs.append(token.item(Int.self))
                }
                let proposalElapsedMicros = elapsedMicros(since: proposalStartedAt)
                draftProposeMicros += proposalElapsedMicros
                proposedTokenCount += proposedTailTokenIDs.count
                dflashProbe?.record(
                    stage: "draft_result",
                    fields: [
                        "round": currentRoundIndex,
                        "staged_first_token_id": stagedFirstCandidateID,
                        "proposed_token_ids": proposedTailTokenIDs,
                        "proposed_token_text": proposedTailTokenIDs.map {
                            targetContext.tokenizer.decode(tokens: [$0])
                        },
                        "input_embeddings": dflashArrayDescriptor(inputEmbeddings),
                        "draft_hidden": dflashArrayDescriptor(draftHidden),
                        "draft_logits": dflashArrayDescriptor(draftLogits),
                        "draft_logits_tail_offset": 1,
                        "draft_propose_us": proposalElapsedMicros,
                        "draft_cache_used": false,
                    ]
                )

                let verifyInputTokenIDs = [stagedFirstCandidateID] + proposedTailTokenIDs
                let targetStateBeforeVerify = currentTargetState.state
                let targetCacheBeforeVerify = snapshotCache(targetStateBeforeVerify.cache)
                let verifyStartedAt = Date.timeIntervalSinceReferenceDate
                let verifiedTargetState = try advanceTargetState(
                    targetStateBeforeVerify,
                    tokenIDs: verifyInputTokenIDs
                )
                let verifyElapsedMicros = elapsedMicros(since: verifyStartedAt)
                targetVerifyMicros += verifyElapsedMicros

                var targetProcessor = parameters.processor()
                targetProcessor?.prompt(MLXArray(committedTokenIDs + [stagedFirstCandidateID]))
                var acceptedThisRound = 0
                var rejectionTokenID: Int?
                var targetTokenIDs = [Int]()
                var firstMismatchIndex: Int?

                for (index, proposedTokenID) in proposedTailTokenIDs.enumerated() {
                    let targetToken = sampleNextToken(
                        logits: verifiedTargetState.logits,
                        position: index,
                        processor: &targetProcessor,
                        sampler: targetSampler
                    )
                    let targetTokenID = targetToken.item(Int.self)
                    targetTokenIDs.append(targetTokenID)
                    if isSpeculativeTerminalToken(targetTokenID, metadata: tokenMetadata) {
                        finished = true
                        break
                    }

                    if targetTokenID == proposedTokenID {
                        acceptedTokenCount += 1
                        acceptedThisRound += 1
                    } else {
                        rejectedTokenCount += 1
                        rollbackCount += 1
                        rejectionTokenID = targetTokenID
                        firstMismatchIndex = index
                        break
                    }
                }
                dflashProbe?.record(
                    stage: "target_verify",
                    fields: [
                        "round": currentRoundIndex,
                        "staged_first_token_id": stagedFirstCandidateID,
                        "proposed_token_ids": proposedTailTokenIDs,
                        "target_token_ids": targetTokenIDs,
                        "target_token_text": targetTokenIDs.map {
                            targetContext.tokenizer.decode(tokens: [$0])
                        },
                        "accepted_this_round": acceptedThisRound,
                        "first_mismatch_index": firstMismatchIndex ?? -1,
                        "rejection_token_id": rejectionTokenID ?? -1,
                        "verify_input_token_ids": verifyInputTokenIDs,
                        "target_verify_us": verifyElapsedMicros,
                        "verified_logits": dflashArrayDescriptor(verifiedTargetState.logits),
                        "verified_hidden": dflashArrayDescriptor(verifiedTargetState.hidden),
                    ]
                )

                let generatedBeforeCommit = generatedTokenCount
                let committedBeforeCommit = committedTokenIDs.count
                var commitTargetRepairMicros = 0
                var commitAction = "none"
                guard emitToken(stagedFirstCandidateID) else {
                    break
                }
                for proposedTokenID in proposedTailTokenIDs.prefix(acceptedThisRound) {
                    guard generatedTokenCount < maxTokens else {
                        finished = true
                        break
                    }
                    guard emitToken(proposedTokenID) else {
                        finished = true
                        break
                    }
                }
                if finished || generatedTokenCount >= maxTokens {
                    targetFinalRebuildSkippedCount += 1
                    dflashProbe?.record(
                        stage: "commit",
                        fields: [
                            "round": currentRoundIndex,
                            "action": "max_tokens_after_accept",
                            "accepted_this_round": acceptedThisRound,
                            "staged_first_token_id": stagedFirstCandidateID,
                            "generated_before": generatedBeforeCommit,
                            "generated_after": generatedTokenCount,
                            "committed_before": committedBeforeCommit,
                            "committed_after": committedTokenIDs.count,
                            "committed_tokens": dflashTokenIDPreview(committedTokenIDs),
                            "target_hidden": dflashArrayDescriptor(currentTargetHidden),
                            "target_final_rebuild_skipped": true,
                            "rollback_count": rollbackCount,
                        ]
                    )
                    break
                }

                if let rejectionTokenID {
                    commitAction = "rejected_emit_target_repair"
                    guard emitToken(rejectionTokenID) else {
                        break
                    }
                    if generatedTokenCount < maxTokens {
                        let repairStartedAt = Date.timeIntervalSinceReferenceDate
                        let acceptedPrefix = Array(proposedTailTokenIDs.prefix(acceptedThisRound))
                        let restoredBaseState = makeState(
                            byRestoring: targetStateBeforeVerify,
                            from: targetCacheBeforeVerify
                        )
                        let repairedTargetState = try advanceTargetState(
                            restoredBaseState,
                            tokenIDs: [stagedFirstCandidateID] + acceptedPrefix + [rejectionTokenID]
                        )
                        commitTargetRepairMicros = elapsedMicros(since: repairStartedAt)
                        targetRepairMicros += commitTargetRepairMicros
                        currentTargetState = repairedTargetState
                        currentTargetHidden = concatenated(
                            [currentTargetHidden, repairedTargetState.hidden],
                            axis: 1
                        )
                    }
                } else if acceptedThisRound == proposedTailTokenIDs.count,
                          generatedTokenCount < maxTokens {
                    commitAction = "all_accepted_no_bonus"
                    targetBonusAdvanceSkippedCount += 1
                    currentTargetState = verifiedTargetState
                    currentTargetHidden = concatenated([currentTargetHidden, verifiedTargetState.hidden], axis: 1)
                } else if acceptedThisRound == proposedTailTokenIDs.count {
                    commitAction = "all_accepted_no_bonus"
                    currentTargetState = verifiedTargetState
                    currentTargetHidden = concatenated([currentTargetHidden, verifiedTargetState.hidden], axis: 1)
                }
                dflashProbe?.record(
                    stage: "commit",
                    fields: [
                        "round": currentRoundIndex,
                        "action": commitAction,
                        "accepted_this_round": acceptedThisRound,
                        "staged_first_token_id": stagedFirstCandidateID,
                        "generated_before": generatedBeforeCommit,
                        "generated_after": generatedTokenCount,
                        "committed_before": committedBeforeCommit,
                        "committed_after": committedTokenIDs.count,
                        "committed_tokens": dflashTokenIDPreview(committedTokenIDs),
                        "target_hidden": dflashArrayDescriptor(currentTargetHidden),
                        "target_cache_restore_used": rejectionTokenID != nil,
                        "target_repair_us": commitTargetRepairMicros,
                        "target_bonus_advance_skipped": rejectionTokenID == nil
                            && acceptedThisRound == proposedTailTokenIDs.count,
                        "rollback_count": rollbackCount,
                    ]
                )
            }

            let decodeLoopTotalMicros = elapsedMicros(since: startedAt)
            let elapsed = max(Double(decodeLoopTotalMicros) / 1_000_000, 0.000_001)
            let finishReason = resolvedTextGenerationFinishReason(
                completionTokens: generatedTokenCount,
                maxTokens: maxTokens,
                wasCancelled: Task.isCancelled
            )
            dflashProbe?.record(
                stage: "summary",
                fields: [
                    "generated_token_count": generatedTokenCount,
                    "accepted_token_count": acceptedTokenCount,
                    "rejected_token_count": rejectedTokenCount,
                    "proposed_token_count": proposedTokenCount,
                    "rollback_count": rollbackCount,
                    "draft_propose_us": draftProposeMicros,
                    "target_verify_us": targetVerifyMicros,
                    "target_repair_us": targetRepairMicros,
                    "target_final_rebuild_skipped_count": targetFinalRebuildSkippedCount,
                    "target_bonus_advance_skipped_count": targetBonusAdvanceSkippedCount,
                    "decode_loop_total_us": decodeLoopTotalMicros,
                    "finish_reason": finishReason,
                    "acceptance_rate": proposedTokenCount == 0
                        ? 0
                        : Double(acceptedTokenCount) / Double(proposedTokenCount),
                ]
            )
            continuation.yield(.summary(
                TextGenerationSummary(
                    promptTokens: promptTokenIDs.count,
                    completionTokens: generatedTokenCount,
                    tokensPerSecond: Double(generatedTokenCount) / elapsed,
                    finishReason: finishReason,
                    speculativeAcceptedTokens: acceptedTokenCount,
                    speculativeRejectedTokens: rejectedTokenCount,
                    speculativeFallbackCount: 0,
                    speculativeDraftProposeMillis: milliseconds(fromMicros: draftProposeMicros),
                    speculativeTargetVerifyMillis: milliseconds(fromMicros: targetVerifyMicros),
                    dflashEnabled: true,
                    dflashBlockSize: maxDraftTokens,
                    dflashRollbackCount: rollbackCount,
                    dflashTargetHiddenLayers: targetLayerIDs.count
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
#endif

private func makeRebuiltSpeculativeDecodeState(
    container: ModelContainer,
    tokenIDs: [Int],
    promptTokenCount: Int,
    prefillQuantizeMicros: Int,
    parameters: GenerateParameters
) async throws -> SpeculativeDecodeRuntimeState {
    try await container.perform { context in
        let input = LMInput(tokens: MLXArray(tokenIDs))
        let cache = context.model.newCache(parameters: nil)
        let prepared = try context.model.prepare(
            input,
            cache: cache,
            windowSize: parameters.prefillStepSize
        )
        let output = try makeInitialDecodeOutput(
            input: input,
            prepared: prepared,
            context: context,
            cache: cache
        )
        eval(output.logits)
        return SpeculativeDecodeRuntimeState(
            cache: cache,
            output: output,
            promptTokenCount: promptTokenCount,
            prefillQuantizeMicros: prefillQuantizeMicros
        )
    }
}

private func makeRebuiltSpeculativeDecodeState(
    context: ModelContext,
    tokenIDs: [Int],
    promptTokenCount: Int,
    prefillQuantizeMicros: Int,
    parameters: GenerateParameters
) throws -> SpeculativeDecodeRuntimeState {
    let input = LMInput(tokens: MLXArray(tokenIDs))
    let cache = context.model.newCache(parameters: nil)
    let prepared = try context.model.prepare(
        input,
        cache: cache,
        windowSize: parameters.prefillStepSize
    )
    let output = try makeInitialDecodeOutput(
        input: input,
        prepared: prepared,
        context: context,
        cache: cache
    )
    eval(output.logits)
    return SpeculativeDecodeRuntimeState(
        cache: cache,
        output: output,
        promptTokenCount: promptTokenCount,
        prefillQuantizeMicros: prefillQuantizeMicros
    )
}

private func advanceSpeculativeDecodeState(
    container: ModelContainer,
    state: SpeculativeDecodeRuntimeState,
    tokenIDs: [Int]
) async throws -> SpeculativeDecodeRuntimeState {
    guard !tokenIDs.isEmpty else {
        return state
    }

    let input = SpeculativeModelStepInput(state: state, tokenIDs: tokenIDs)
    return await container.perform(values: input) { context, input in
        var state = input.state
        let nextInput = LMInput.Text(tokens: MLXArray(input.tokenIDs))
        state.output = context.model(
            nextInput[text: .newAxis],
            cache: state.cache.isEmpty ? nil : state.cache,
            state: state.output.state
        )
        eval(state.output.logits)
        return state
    }
}

private func advanceSpeculativeDecodeState(
    context: ModelContext,
    state: SpeculativeDecodeRuntimeState,
    tokenIDs: [Int]
) -> SpeculativeDecodeRuntimeState {
    guard !tokenIDs.isEmpty else {
        return state
    }

    var state = state
    let nextInput = LMInput.Text(tokens: MLXArray(tokenIDs))
    state.output = context.model(
        nextInput[text: .newAxis],
        cache: state.cache.isEmpty ? nil : state.cache,
        state: state.output.state
    )
    eval(state.output.logits)
    return state
}

private func isSpeculativeTerminalToken(
    _ tokenID: Int,
    metadata: SpeculativeTokenMetadata
) -> Bool {
    if let unknownTokenID = metadata.unknownTokenID, tokenID == unknownTokenID {
        return true
    }
    if let eosTokenID = metadata.eosTokenID, tokenID == eosTokenID {
        return true
    }
    return metadata.additionalEOSTokenIDs.contains(tokenID)
}

private func shouldFallbackSpeculativeDecodeRuntime(
    acceptedTokenCount: Int,
    rejectedTokenCount: Int,
    proposedTokenCount: Int,
    draftProposeMicros: Int,
    targetVerifyMicros: Int
) -> Bool {
    let verifiedTokenCount = acceptedTokenCount + rejectedTokenCount
    if verifiedTokenCount == 1, acceptedTokenCount == 0, rejectedTokenCount == 1 {
        return true
    }
    guard verifiedTokenCount >= 4, proposedTokenCount >= 4 else {
        return false
    }

    let acceptanceRatePercent = (acceptedTokenCount * 100) / max(verifiedTokenCount, 1)
    if acceptanceRatePercent < 75 {
        return true
    }

    let draftMicrosPerProposal = Double(draftProposeMicros) / Double(max(proposedTokenCount, 1))
    let targetMicrosPerVerifiedToken = Double(targetVerifyMicros) / Double(max(verifiedTokenCount, 1))
    return draftMicrosPerProposal >= targetMicrosPerVerifiedToken * 0.75
}

private func milliseconds(fromMicros micros: Int) -> Int {
    max(0, Int((Double(micros) / 1_000.0).rounded()))
}
#endif

private func makePreparedDecodeGeneration(
    model: LoadedTextModel,
    draftModel: LoadedTextModel?,
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
        acceleration: acceleration
    )

    if acceleration.mode == .speculativeDecode {
        guard let draftModel else {
            throw RuntimeUnavailableError(
                message: "Speculative decode requires a loaded Swift MLX draft model."
            )
        }

        #if canImport(MLXLLM)
        if let dflashRuntime = draftModel.storage as? SwiftDFlashDraftRuntime {
            let runtimeEvents = try await container.perform(values: decodeState) { targetContext, decodeState in
                try makePreparedDFlashSpeculativeDecodeEvents(
                    draftRuntime: dflashRuntime,
                    decodeState: decodeState,
                    targetContext: targetContext,
                    parameters: parameters,
                    acceleration: acceleration
                )
            }
            return PreparedTextGeneration(
                promptTokens: decodeState.input.text.tokens.size,
                runtimeEvents: runtimeEvents
            )
        }
        #endif

        guard let draftContainer = draftModel.storage as? ModelContainer else {
            throw RuntimeUnavailableError(
                message: "Speculative decode requires a loaded Swift MLX draft model container."
            )
        }
        let runtimeEvents = try await container.perform(values: decodeState) { targetContext, decodeState in
            try await makePreparedSpeculativeDecodeEvents(
                targetContainer: container,
                draftContainer: draftContainer,
                decodeState: decodeState,
                targetContext: targetContext,
                parameters: parameters,
                acceleration: acceleration
            )
        }
        return PreparedTextGeneration(
            promptTokens: decodeState.input.text.tokens.size,
            runtimeEvents: runtimeEvents
        )
    }

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
            var decodeModelEvalSyncTotalMicros = 0
            var decodeModelEvalSyncCallCount = 0
            var decodeSampleTotalMicros = 0
            var decodeSampleCallCount = 0
            var decodeTokenIDTotalMicros = 0
            var decodeTokenIDCallCount = 0
            var decodeAsyncEvalTotalMicros = 0
            var decodeAsyncEvalCallCount = 0
            var decodeDetokenizeTotalMicros = 0
            var decodeDetokenizeCallCount = 0
            var decodeStreamYieldTotalMicros = 0
            var decodeStreamYieldCallCount = 0
            var turboQuantCandidateTotalMicros = 0
            var turboQuantCandidateCallCount = 0
            let decodeQuantizeTotalMicros = 0
            var prefillQuantizeMicros = decodeState.prefillQuantizeMicros
            let shouldRecordActiveKVDecodeProbe =
                normalizedAccelerationPolicy(acceleration).mode == .activeKvQuantized
            let shouldRecordBaselineDecodeProbe =
                ProcessInfo.processInfo.environment["MELIX_SWIFT_BASELINE_DECODE_PROBE"] == "1"
            let shouldRecordDecodeProbe = shouldRecordActiveKVDecodeProbe || shouldRecordBaselineDecodeProbe

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
            let shouldForceModelEvalProbe =
                ProcessInfo.processInfo.environment["MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE"] == "1"
                && normalizedAccelerationPolicy(acceleration).mode == .activeKvQuantized
            let supportsArgMaxTokenIDFastPath = supportsArgMaxTokenIDFastPath(parameters)
            let startedAt = Date.timeIntervalSinceReferenceDate

            func sampleDecodeToken(from logits: MLXArray) -> (token: MLXArray, tokenIDRow: MLXArray?) {
                let sampleStartedAt = shouldRecordDecodeProbe
                    ? Date.timeIntervalSinceReferenceDate
                    : 0
                let token: MLXArray
                let tokenIDRow: MLXArray?
                if supportsArgMaxTokenIDFastPath, processor == nil {
                    token = batchedArgMaxTokenIDs(from: logits)
                    tokenIDRow = token
                } else {
                    token = sampleNextToken(
                        logits: logits,
                        processor: &processor,
                        sampler: sampler
                    )
                    tokenIDRow = nil
                }
                if shouldRecordDecodeProbe {
                    decodeSampleCallCount += 1
                    decodeSampleTotalMicros += elapsedMicros(since: sampleStartedAt)
                }
                return (token: token, tokenIDRow: tokenIDRow)
            }

            func makeNextDecodeOutput(from token: MLXArray, state: LMOutput.State?) -> LMOutput {
                let nextInput = LMInput.Text(tokens: token)
                if shouldEvaluateTurboQuantFusedAttentionCandidate && !didDispatchTurboQuantFusedAttention {
                    turboQuantCandidateEligibilityCheckCount += 1
                    let candidateStartedAt = shouldRecordDecodeProbe
                        ? Date.timeIntervalSinceReferenceDate
                        : 0
                    didDispatchTurboQuantFusedAttention = dispatchTurboQuantFusedAttentionCandidateIfNeeded(
                        cache: cache,
                        acceleration: acceleration,
                        candidateProbeEnabled: turboQuantCandidateProbeEnabled
                    )
                    if shouldRecordDecodeProbe {
                        turboQuantCandidateCallCount += 1
                        turboQuantCandidateTotalMicros += elapsedMicros(since: candidateStartedAt)
                    }
                }
                let modelStartedAt = shouldRecordDecodeProbe
                    ? Date.timeIntervalSinceReferenceDate
                    : 0
                let nextOutput = context.model(
                    nextInput[text: .newAxis],
                    cache: cache.isEmpty ? nil : cache,
                    state: state
                )
                if shouldRecordDecodeProbe {
                    decodeModelCallCount += 1
                    decodeModelTotalMicros += elapsedMicros(since: modelStartedAt)
                }
                if let modelEvalSyncMicros = activeKVModelEvalSyncMicrosIfNeeded(
                    enabled: shouldForceModelEvalProbe,
                    logits: nextOutput.logits
                ) {
                    decodeModelEvalSyncCallCount += 1
                    decodeModelEvalSyncTotalMicros += modelEvalSyncMicros
                }
                return nextOutput
            }

            var pendingToken: MLXArray?
            var pendingTokenIDRow: MLXArray?
            if parameters.maxTokens.map({ $0 > 0 }) ?? true {
                let sampledToken = sampleDecodeToken(from: output.logits)
                recordDecodeAsyncEval(
                    sampledToken.token,
                    shouldRecord: shouldRecordDecodeProbe,
                    totalMicros: &decodeAsyncEvalTotalMicros,
                    callCount: &decodeAsyncEvalCallCount
                )
                pendingToken = sampledToken.token
                pendingTokenIDRow = sampledToken.tokenIDRow
            }

            while let token = pendingToken,
                  parameters.maxTokens.map({ generatedTokenCount < $0 }) ?? true
            {
                if Task.isCancelled {
                    break
                }

                let canAdvanceModel = parameters.maxTokens.map { generatedTokenCount + 1 < $0 } ?? true
                let shouldAdvanceModelBeforeTokenID =
                    canAdvanceModel && supportsArgMaxTokenIDFastPath && processor == nil && pendingTokenIDRow != nil
                var advancedOutput: LMOutput?
                var nextToken: MLXArray?
                var nextTokenIDRow: MLXArray?
                if shouldAdvanceModelBeforeTokenID, let tokenIDRow = pendingTokenIDRow {
                    let nextOutput = makeNextDecodeOutput(from: tokenIDRow, state: output.state)
                    let sampledNextToken = sampleDecodeToken(from: nextOutput.logits)
                    recordDecodeAsyncEval(
                        sampledNextToken.token,
                        shouldRecord: shouldRecordDecodeProbe,
                        totalMicros: &decodeAsyncEvalTotalMicros,
                        callCount: &decodeAsyncEvalCallCount
                    )
                    advancedOutput = nextOutput
                    nextToken = sampledNextToken.token
                    nextTokenIDRow = sampledNextToken.tokenIDRow
                }

                let tokenEvalStartedAt = shouldRecordDecodeProbe
                    ? Date.timeIntervalSinceReferenceDate
                    : 0
                let tokenIDStartedAt = shouldRecordDecodeProbe
                    ? Date.timeIntervalSinceReferenceDate
                    : 0
                let tokenID = token.item(Int.self)
                if shouldRecordDecodeProbe {
                    decodeTokenIDCallCount += 1
                    decodeTokenIDTotalMicros += elapsedMicros(since: tokenIDStartedAt)
                    decodeTokenEvalCallCount += 1
                    decodeTokenEvalTotalMicros += elapsedMicros(since: tokenEvalStartedAt)
                }

                if tokenID == context.tokenizer.unknownTokenId
                    || tokenID == context.tokenizer.eosTokenId
                    || additionalEOSTokenIds.contains(tokenID)
                {
                    break
                }

                generatedTokenCount += 1
                if let advancedOutput {
                    output = advancedOutput
                } else if canAdvanceModel {
                    let nextOutput = makeNextDecodeOutput(from: pendingTokenIDRow ?? token, state: output.state)
                    let sampledNextToken = sampleDecodeToken(from: nextOutput.logits)
                    recordDecodeAsyncEval(
                        sampledNextToken.token,
                        shouldRecord: shouldRecordDecodeProbe,
                        totalMicros: &decodeAsyncEvalTotalMicros,
                        callCount: &decodeAsyncEvalCallCount
                    )
                    output = nextOutput
                    nextToken = sampledNextToken.token
                    nextTokenIDRow = sampledNextToken.tokenIDRow
                }

                let detokenizeStartedAt = shouldRecordDecodeProbe
                    ? Date.timeIntervalSinceReferenceDate
                    : 0
                detokenizer.append(token: tokenID)
                let chunk = detokenizer.next()
                if shouldRecordDecodeProbe {
                    decodeDetokenizeCallCount += 1
                    decodeDetokenizeTotalMicros += elapsedMicros(since: detokenizeStartedAt)
                }
                if let chunk {
                    let yieldStartedAt = shouldRecordDecodeProbe
                        ? Date.timeIntervalSinceReferenceDate
                        : 0
                    continuation.yield(.chunk(chunk))
                    if shouldRecordDecodeProbe {
                        decodeStreamYieldCallCount += 1
                        decodeStreamYieldTotalMicros += elapsedMicros(since: yieldStartedAt)
                    }
                }

                if let nextToken {
                    pendingToken = nextToken
                    pendingTokenIDRow = nextTokenIDRow
                } else {
                    break
                }
            }

            let decodeLoopTotalMicros = elapsedMicros(since: startedAt)
            // `asyncEval` keeps the next-token graph in flight while the current
            // chunk is streamed; synchronize before finishing so canceled or
            // terminal streams do not leave MLX work running past stream teardown.
            Stream().synchronize()
            let elapsed = max(Double(decodeLoopTotalMicros) / 1_000_000, 0.000_001)
            let summaryStartedAt = shouldRecordActiveKVDecodeProbe
                ? Date.timeIntervalSinceReferenceDate
                : nil
            let activeKVProbe = makeActiveKVProbeSummary(
                cache: cache,
                acceleration: acceleration,
                prefillQuantizeMicros: prefillQuantizeMicros,
                decodeModelTotalMicros: decodeModelTotalMicros,
                decodeModelCallCount: decodeModelCallCount,
                decodeTokenEvalTotalMicros: decodeTokenEvalTotalMicros,
                decodeTokenEvalCallCount: decodeTokenEvalCallCount,
                decodeModelEvalSyncTotalMicros: decodeModelEvalSyncTotalMicros,
                decodeModelEvalSyncCallCount: decodeModelEvalSyncCallCount,
                decodeSampleTotalMicros: decodeSampleTotalMicros,
                decodeSampleCallCount: decodeSampleCallCount,
                decodeTokenIDTotalMicros: decodeTokenIDTotalMicros,
                decodeTokenIDCallCount: decodeTokenIDCallCount,
                decodeDetokenizeTotalMicros: decodeDetokenizeTotalMicros,
                decodeDetokenizeCallCount: decodeDetokenizeCallCount,
                decodeStreamYieldTotalMicros: decodeStreamYieldTotalMicros,
                decodeStreamYieldCallCount: decodeStreamYieldCallCount,
                decodeSummaryStartedAt: summaryStartedAt,
                turboQuantCandidateTotalMicros: turboQuantCandidateTotalMicros,
                turboQuantCandidateCallCount: turboQuantCandidateCallCount,
                decodeQuantizeTotalMicros: decodeQuantizeTotalMicros,
                decodeLoopTotalMicros: decodeLoopTotalMicros,
                decodeTokenCount: generatedTokenCount,
                turboQuantFusedAttentionDispatched: didDispatchTurboQuantFusedAttention,
                turboQuantCandidateEligibilityCheckCount: turboQuantCandidateEligibilityCheckCount
            )
            let baselineDecodeProbe = shouldRecordBaselineDecodeProbe
                ? DecodeBatchProbeSummary(
                    decodeLoopTotalMicros: decodeLoopTotalMicros,
                    decodeModelTotalMicros: decodeModelTotalMicros,
                    decodeModelCallCount: decodeModelCallCount,
                    decodeModelEvalSyncTotalMicros: decodeModelEvalSyncTotalMicros,
                    decodeModelEvalSyncCallCount: decodeModelEvalSyncCallCount,
                    decodeModelEvalSyncFirstMicros: 0,
                    decodeModelEvalSyncMaxMicros: 0,
                    decodeAsyncEvalTotalMicros: decodeAsyncEvalTotalMicros,
                    decodeAsyncEvalCallCount: decodeAsyncEvalCallCount,
                    decodeSampleTotalMicros: decodeSampleTotalMicros,
                    decodeSampleCallCount: decodeSampleCallCount,
                    decodeTokenEvalTotalMicros: decodeTokenEvalTotalMicros,
                    decodeTokenEvalCallCount: decodeTokenEvalCallCount,
                    decodeTokenIDTotalMicros: decodeTokenIDTotalMicros,
                    decodeTokenIDCallCount: decodeTokenIDCallCount,
                    decodeDetokenizeTotalMicros: decodeDetokenizeTotalMicros,
                    decodeDetokenizeCallCount: decodeDetokenizeCallCount,
                    decodeStreamYieldTotalMicros: decodeStreamYieldTotalMicros,
                    decodeStreamYieldCallCount: decodeStreamYieldCallCount
                )
                : nil
            continuation.yield(.summary(
                TextGenerationSummary(
                    promptTokens: decodeState.input.text.tokens.size,
                    completionTokens: generatedTokenCount,
                    tokensPerSecond: Double(generatedTokenCount) / elapsed,
                    finishReason: resolvedTextGenerationFinishReason(
                        completionTokens: generatedTokenCount,
                        maxTokens: parameters.maxTokens,
                        wasCancelled: Task.isCancelled
                    ),
                    activeKVProbe: activeKVProbe,
                    decodeBatchProbe: baselineDecodeProbe
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
    try makeInitialDecodeOutput(
        input: decodeState.input,
        prepared: decodeState.prepared,
        context: context,
        cache: cache
    )
}

private func makeInitialDecodeOutput(
    input: LMInput,
    prepared: PrepareResult,
    context: ModelContext,
    cache: [KVCache]
) throws -> LMOutput {
    switch prepared {
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
    position: Int? = nil,
    processor: inout (any LogitProcessor)?,
    sampler: any LogitSampler
) -> MLXArray {
    var selectedLogits: MLXArray
    if let position {
        selectedLogits = logits[0..., position, 0...]
    } else {
        selectedLogits = logits[0..., -1, 0...]
    }
    selectedLogits = processor?.process(logits: selectedLogits) ?? selectedLogits
    let token = sampler.sample(logits: selectedLogits)
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
    var fusedAttentionTotalMicros = 0
    var fusedAttentionCallCount = 0
    var fusedAttentionRouteTotalMicros = 0
    var fusedAttentionActiveLaneTotal = 0
    var fusedAttentionLaunchedLaneTotal = 0
    var fusedAttentionSoftmaxLaneTotal = 0
    var fusedAttentionSoftmaxTokenLaneTotal = 0
}

private func makeActiveKVProbeSummary(
    cache: [KVCache],
    acceleration: Melix_Worker_V1_AccelerationPolicy,
    prefillQuantizeMicros: Int,
    decodeModelTotalMicros: Int,
    decodeModelCallCount: Int,
    decodeTokenEvalTotalMicros: Int,
    decodeTokenEvalCallCount: Int,
    decodeModelEvalSyncTotalMicros: Int,
    decodeModelEvalSyncCallCount: Int,
    decodeSampleTotalMicros: Int = 0,
    decodeSampleCallCount: Int = 0,
    decodeTokenIDTotalMicros: Int = 0,
    decodeTokenIDCallCount: Int = 0,
    decodeDetokenizeTotalMicros: Int = 0,
    decodeDetokenizeCallCount: Int = 0,
    decodeStreamYieldTotalMicros: Int = 0,
    decodeStreamYieldCallCount: Int = 0,
    decodeSummaryStartedAt: TimeInterval? = nil,
    turboQuantCandidateTotalMicros: Int = 0,
    turboQuantCandidateCallCount: Int = 0,
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
        decodeModelEvalSyncTotalMicros: decodeModelEvalSyncTotalMicros,
        decodeModelEvalSyncCallCount: decodeModelEvalSyncCallCount,
        decodeSampleTotalMicros: decodeSampleTotalMicros,
        decodeSampleCallCount: decodeSampleCallCount,
        decodeTokenIDTotalMicros: decodeTokenIDTotalMicros,
        decodeTokenIDCallCount: decodeTokenIDCallCount,
        decodeDetokenizeTotalMicros: decodeDetokenizeTotalMicros,
        decodeDetokenizeCallCount: decodeDetokenizeCallCount,
        decodeStreamYieldTotalMicros: decodeStreamYieldTotalMicros,
        decodeStreamYieldCallCount: decodeStreamYieldCallCount,
        decodeSummaryTotalMicros: decodeSummaryStartedAt.map(elapsedMicros) ?? 0,
        decodeSummaryCallCount: decodeSummaryStartedAt == nil ? 0 : 1,
        turboQuantCandidateTotalMicros: turboQuantCandidateTotalMicros,
        turboQuantCandidateCallCount: turboQuantCandidateCallCount,
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
        fusedAttentionTotalMicros: cacheTiming.fusedAttentionTotalMicros,
        fusedAttentionCallCount: cacheTiming.fusedAttentionCallCount,
        fusedAttentionRouteTotalMicros: cacheTiming.fusedAttentionRouteTotalMicros,
        fusedAttentionActiveLaneTotal: cacheTiming.fusedAttentionActiveLaneTotal,
        fusedAttentionLaunchedLaneTotal: cacheTiming.fusedAttentionLaunchedLaneTotal,
        fusedAttentionSoftmaxLaneTotal: cacheTiming.fusedAttentionSoftmaxLaneTotal,
        fusedAttentionSoftmaxTokenLaneTotal: cacheTiming.fusedAttentionSoftmaxTokenLaneTotal,
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
        totals.fusedAttentionTotalMicros += quantizedCache.fusedAttentionTotalMicros
        totals.fusedAttentionCallCount += quantizedCache.fusedAttentionCallCount
        totals.fusedAttentionRouteTotalMicros += quantizedCache.fusedAttentionRouteTotalMicros
        totals.fusedAttentionActiveLaneTotal += quantizedCache.fusedAttentionActiveLaneTotal
        totals.fusedAttentionLaunchedLaneTotal += quantizedCache.fusedAttentionLaunchedLaneTotal
        totals.fusedAttentionSoftmaxLaneTotal += quantizedCache.fusedAttentionSoftmaxLaneTotal
        totals.fusedAttentionSoftmaxTokenLaneTotal += quantizedCache.fusedAttentionSoftmaxTokenLaneTotal
    }
    return totals
}

private func activeKVBackendCode(for policy: Melix_Worker_V1_AccelerationPolicy) -> Int {
    if isTurboQuantProfile(policy.activeKvQuantProfile) {
        return 2
    }
    return 1
}

func activeKVKernelPathCode(
    for policy: Melix_Worker_V1_AccelerationPolicy,
    turboQuantRuntimeRoute: TurboQuantRuntimeFusedAttentionRoute = .disabled
) -> Int {
    if isTurboQuantProfile(policy.activeKvQuantProfile) {
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
    if isTurboQuantProfile(policy.activeKvQuantProfile), turboQuantFusedAttentionDispatched {
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
          isTurboQuantProfile(normalized.activeKvQuantProfile)
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
          isTurboQuantProfile(normalized.activeKvQuantProfile)
    else {
        return .disabled
    }

    if turboQuantFusedAttentionDispatchCount(cache: cache) > 0 {
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

func activeKVModelEvalSyncMicrosIfNeeded(enabled: Bool, logits: MLXArray) -> Int? {
    guard enabled else {
        return nil
    }
    let startedAt = Date.timeIntervalSinceReferenceDate
    eval(logits)
    return elapsedMicros(since: startedAt)
}

private func elapsedMicros(since startedAt: TimeInterval) -> Int {
    max(0, Int(((Date.timeIntervalSinceReferenceDate - startedAt) * 1_000_000).rounded()))
}
#endif
