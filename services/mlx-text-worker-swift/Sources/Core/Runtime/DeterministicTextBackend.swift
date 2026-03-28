import Foundation
import MelixWorkerProtocol

struct DeterministicTextBackend: TextRuntimeBackend {
    let runtimeName: String = "deterministic-text"
    private let tokenDelayNanos: UInt64

    init(tokenDelayNanos: UInt64 = 20_000_000) {
        self.tokenDelayNanos = tokenDelayNanos
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
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        let prompt = deterministicPrompt(from: messages)
        let promptTokens = max(1, prompt.split(whereSeparator: \.isWhitespace).count)

        if tokenDelayNanos > 0 {
            try? await Task.sleep(nanoseconds: tokenDelayNanos)
        }

        if shouldAbort() {
            return RuntimePrefillResult(
                context: TextPrefillContext(
                    storage: [
                        "prompt": prompt,
                        "resume_hint": resumeHint,
                    ],
                    promptTokens: promptTokens
                ),
                promptTokens: promptTokens
            )
        }

        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: [
                    "prompt": prompt,
                    "resume_hint": resumeHint,
                    "prefill_step_size": String(prefillStepSize),
                ],
                promptTokens: promptTokens
            ),
            promptTokens: promptTokens
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
