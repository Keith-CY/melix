import Foundation
import MelixWorkerProtocol

#if canImport(MLXLMCommon)
import MLXLMCommon
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
