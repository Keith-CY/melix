import Darwin.Mach
import Foundation
import MelixWorkerProtocol

struct LoadedTextModel: @unchecked Sendable {
    let storage: Any
    let residentBytesHint: UInt64

    init(storage: Any, residentBytesHint: UInt64 = 0) {
        self.storage = storage
        self.residentBytesHint = residentBytesHint
    }
}

struct RuntimeLoadResult: Sendable {
    let model: LoadedTextModel
    let estimatedResidentBytes: UInt64
}

struct TextPrefillContext: @unchecked Sendable {
    let storage: Any
    let promptTokens: Int
}

struct RuntimePrefillResult: Sendable {
    let context: TextPrefillContext
    let promptTokens: Int
    let appliedAcceleration: Melix_Worker_V1_AccelerationPolicy
    let acceleratedPrefillGainPct: Int
    let activeKVQuantizationRatio: Int
}

struct SparsePrefillPlan: Sendable {
    let acceptedSkipCount: Int
    let rejectedOpportunityCount: Int
    let protectedRegionCount: Int

    static let zero = SparsePrefillPlan(
        acceptedSkipCount: 0,
        rejectedOpportunityCount: 0,
        protectedRegionCount: 0
    )
}

struct ActiveKVProbeSummary: Sendable {
    let backendCode: Int
    let kernelPathCode: Int
    let runtimeRouteCode: Int
    let runtimeBlockReasonCode: Int
    let quantizationRatioPercent: Int
    let prefillQuantizeMicros: Int
    let decodeModelTotalMicros: Int
    let decodeModelCallCount: Int
    let decodeTokenEvalTotalMicros: Int
    let decodeTokenEvalCallCount: Int
    let decodeQuantizeTotalMicros: Int
    let decodeLoopTotalMicros: Int
    let decodeTokenCount: Int
    let estimatedFP16Bytes: Int
    let estimatedQuantizedBytes: Int
    let estimatedMemorySavingsPercent: Int
    let fallbackCount: Int
    let cacheUpdateTotalMicros: Int
    let cacheUpdateCallCount: Int
    let cacheExpandTotalMicros: Int
    let cacheQuantizeTotalMicros: Int
    let cacheAppendTotalMicros: Int
    let cacheMaterializeTotalMicros: Int
    let cacheMaterializeCallCount: Int
    let candidateDispatchCode: Int
    let candidateEligibilityCheckCount: Int

    init(
        backendCode: Int,
        kernelPathCode: Int,
        runtimeRouteCode: Int = 0,
        runtimeBlockReasonCode: Int = 0,
        quantizationRatioPercent: Int = 0,
        prefillQuantizeMicros: Int,
        decodeModelTotalMicros: Int,
        decodeModelCallCount: Int = 0,
        decodeTokenEvalTotalMicros: Int = 0,
        decodeTokenEvalCallCount: Int = 0,
        decodeQuantizeTotalMicros: Int,
        decodeLoopTotalMicros: Int = 0,
        decodeTokenCount: Int,
        estimatedFP16Bytes: Int,
        estimatedQuantizedBytes: Int,
        estimatedMemorySavingsPercent: Int,
        fallbackCount: Int,
        cacheUpdateTotalMicros: Int = 0,
        cacheUpdateCallCount: Int = 0,
        cacheExpandTotalMicros: Int = 0,
        cacheQuantizeTotalMicros: Int = 0,
        cacheAppendTotalMicros: Int = 0,
        cacheMaterializeTotalMicros: Int = 0,
        cacheMaterializeCallCount: Int = 0,
        candidateDispatchCode: Int = 0,
        candidateEligibilityCheckCount: Int = 0
    ) {
        self.backendCode = backendCode
        self.kernelPathCode = kernelPathCode
        self.runtimeRouteCode = runtimeRouteCode
        self.runtimeBlockReasonCode = runtimeBlockReasonCode
        self.quantizationRatioPercent = quantizationRatioPercent
        self.prefillQuantizeMicros = prefillQuantizeMicros
        self.decodeModelTotalMicros = decodeModelTotalMicros
        self.decodeModelCallCount = decodeModelCallCount
        self.decodeTokenEvalTotalMicros = decodeTokenEvalTotalMicros
        self.decodeTokenEvalCallCount = decodeTokenEvalCallCount
        self.decodeQuantizeTotalMicros = decodeQuantizeTotalMicros
        self.decodeLoopTotalMicros = decodeLoopTotalMicros
        self.decodeTokenCount = decodeTokenCount
        self.estimatedFP16Bytes = estimatedFP16Bytes
        self.estimatedQuantizedBytes = estimatedQuantizedBytes
        self.estimatedMemorySavingsPercent = estimatedMemorySavingsPercent
        self.fallbackCount = fallbackCount
        self.cacheUpdateTotalMicros = cacheUpdateTotalMicros
        self.cacheUpdateCallCount = cacheUpdateCallCount
        self.cacheExpandTotalMicros = cacheExpandTotalMicros
        self.cacheQuantizeTotalMicros = cacheQuantizeTotalMicros
        self.cacheAppendTotalMicros = cacheAppendTotalMicros
        self.cacheMaterializeTotalMicros = cacheMaterializeTotalMicros
        self.cacheMaterializeCallCount = cacheMaterializeCallCount
        self.candidateDispatchCode = candidateDispatchCode
        self.candidateEligibilityCheckCount = candidateEligibilityCheckCount
    }

    var decodeModelAverageMicros: Int {
        averageMicros(total: decodeModelTotalMicros)
    }

    var decodeTokenEvalAverageMicros: Int {
        averageMicros(total: decodeTokenEvalTotalMicros, count: decodeTokenEvalCallCount)
    }

    var decodeQuantizeAverageMicros: Int {
        averageMicros(total: decodeQuantizeTotalMicros)
    }

    var cacheUpdateAverageMicros: Int {
        averageMicros(total: cacheUpdateTotalMicros, count: cacheUpdateCallCount)
    }

    var cacheMaterializeAverageMicros: Int {
        averageMicros(total: cacheMaterializeTotalMicros, count: cacheMaterializeCallCount)
    }

    private func averageMicros(total: Int) -> Int {
        averageMicros(total: total, count: decodeTokenCount)
    }

    private func averageMicros(total: Int, count: Int) -> Int {
        guard count > 0 else {
            return 0
        }
        return max(0, total / count)
    }
}

struct TextGenerationSummary: Sendable {
    let promptTokens: Int
    let completionTokens: Int
    let tokensPerSecond: Double?
    let speculativeAcceptedTokens: Int?
    let speculativeRejectedTokens: Int?
    let activeKVProbe: ActiveKVProbeSummary?

    init(
        promptTokens: Int,
        completionTokens: Int,
        tokensPerSecond: Double?,
        speculativeAcceptedTokens: Int? = nil,
        speculativeRejectedTokens: Int? = nil,
        activeKVProbe: ActiveKVProbeSummary? = nil
    ) {
        self.promptTokens = promptTokens
        self.completionTokens = completionTokens
        self.tokensPerSecond = tokensPerSecond
        self.speculativeAcceptedTokens = speculativeAcceptedTokens
        self.speculativeRejectedTokens = speculativeRejectedTokens
        self.activeKVProbe = activeKVProbe
    }
}

enum TextGenerationEvent: Sendable {
    case prefillStarted(promptTokens: Int)
    case token(String)
    case summary(TextGenerationSummary)
}

protocol TextRuntimeBackend: Sendable {
    var runtimeName: String { get }
    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel
    func unloadModel(_ model: LoadedTextModel) async
    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult
    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error>
    func decodeEvents(
        model: LoadedTextModel,
        context: TextPrefillContext,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error>
}

extension TextRuntimeBackend {
    func unloadModel(_ model: LoadedTextModel) async {}

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        throw RuntimeUnavailableError(
            message: "Prefill is not available for the current backend."
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        throw RuntimeUnavailableError(
            message: "Text generation is not available for the current backend."
        )
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
        throw RuntimeUnavailableError(
            message: "Decode is not available for the current backend."
        )
    }
}

struct TextRuntime: Sendable {
    let backend: any TextRuntimeBackend
    private let residentMemoryReader: @Sendable () -> UInt64

    init(
        backend: some TextRuntimeBackend = AutoSwiftMLXBackend(),
        residentMemoryReader: @escaping @Sendable () -> UInt64 = processResidentMemoryBytes
    ) {
        self.backend = backend
        self.residentMemoryReader = residentMemoryReader
    }

    var runtimeName: String {
        backend.runtimeName
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> RuntimeLoadResult {
        let residentBefore = residentMemoryReader()
        let loadedModel = try await backend.loadModel(spec: spec)
        let residentAfter = residentMemoryReader()
        let residentDelta = residentAfter >= residentBefore ? residentAfter - residentBefore : 0
        return RuntimeLoadResult(
            model: loadedModel,
            estimatedResidentBytes: max(residentDelta, loadedModel.residentBytesHint)
        )
    }

    func unloadModel(_ model: LoadedTextModel) async {
        await backend.unloadModel(model)
    }

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        try await backend.prefill(
            model: model,
            messages: messages,
            prefillStepSize: prefillStepSize,
            resumeHint: resumeHint,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        try await backend.generateEvents(
            model: model,
            messages: messages,
            sampling: sampling,
            shouldAbort: shouldAbort
        )
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
        try await backend.decodeEvents(
            model: model,
            context: context,
            sampling: sampling,
            maxOutputTokens: maxOutputTokens,
            decodeStepSize: decodeStepSize,
            prefillToken: prefillToken,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }
}

func makeTextRuntime(
    for configuration: WorkerConfiguration,
    residentMemoryReader: @escaping @Sendable () -> UInt64 = processResidentMemoryBytes
) -> TextRuntime {
    switch configuration.backendMode.lowercased() {
    case "deterministic":
        return TextRuntime(
            backend: DeterministicTextBackend(),
            residentMemoryReader: residentMemoryReader
        )
    default:
        return TextRuntime(
            backend: AutoSwiftMLXBackend(
                turboQuantCandidateProbeEnabled: configuration.turboQuantCandidateProbeEnabled
            ),
            residentMemoryReader: residentMemoryReader
        )
    }
}

private func processResidentMemoryBytes() -> UInt64 {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info_data_t>.size / MemoryLayout<natural_t>.size)
    let result: kern_return_t = withUnsafeMutablePointer(to: &info) { pointer in
        pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { rebound in
            task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), rebound, &count)
        }
    }

    guard result == KERN_SUCCESS else {
        return 0
    }
    return UInt64(info.resident_size)
}

func normalizedAccelerationPolicy(
    _ policy: Melix_Worker_V1_AccelerationPolicy
) -> Melix_Worker_V1_AccelerationPolicy {
    var normalized = policy
    if normalized.mode == .unspecified {
        normalized.mode = .baseline
    }

    if normalized.mode == .activeKvQuantized,
       normalized.activeKvQuantProfile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        normalized.activeKvQuantProfile = "q4"
    }

    if normalized.mode == .sparsePrefill,
       normalized.prefillHint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        normalized.prefillHint = "sparse-prefill"
    }

    return normalized
}

func activeKVQuantizationRatioPercent(
    for policy: Melix_Worker_V1_AccelerationPolicy
) -> Int {
    let normalized = normalizedAccelerationPolicy(policy)
    guard normalized.mode == .activeKvQuantized else {
        return 0
    }

    let profile = normalized.activeKvQuantProfile.lowercased()
    if profile.contains("q8") {
        return 50
    }
    return 25
}

func gainPercent(
    baseline: UInt64,
    effective: UInt64
) -> Int {
    guard baseline > 0, effective < baseline else {
        return 0
    }

    return max(0, min(100, Int(((baseline - effective) * 100) / baseline)))
}

func sparsePrefillPlan(
    for messages: [Melix_Worker_V1_ChatMessage],
    policy: Melix_Worker_V1_AccelerationPolicy
) -> SparsePrefillPlan {
    let normalized = normalizedAccelerationPolicy(policy)
    guard normalized.mode == .sparsePrefill else {
        return .zero
    }

    var acceptedSkipCount = 0
    var rejectedOpportunityCount = 0
    var protectedRegionCount = 0

    for message in messages {
        let content = ((try? flattenTextContent(from: message)) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else {
            continue
        }

        let protectedRole = isProtectedSparsePrefillRole(message.role)
        if protectedRole {
            protectedRegionCount += 1
        }
        guard sparsePrefillEligibleText(content) else {
            continue
        }
        if protectedRole {
            rejectedOpportunityCount += 1
        } else {
            acceptedSkipCount += 1
        }
    }

    return SparsePrefillPlan(
        acceptedSkipCount: acceptedSkipCount,
        rejectedOpportunityCount: rejectedOpportunityCount,
        protectedRegionCount: protectedRegionCount
    )
}

func promptLooksStructuredForPrefill(_ prompt: String) -> Bool {
    let newlineCount = prompt.filter { $0 == "\n" }.count
    let punctuationCount = prompt.filter { "{}[]():,\"".contains($0) }.count
    return newlineCount >= 2 || punctuationCount >= max(4, prompt.count / 12)
}

func sparsePrefillEligibleText(_ text: String) -> Bool {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        return false
    }
    if promptLooksStructuredForPrefill(trimmed) {
        return true
    }
    return promptContainsSparseRepeats(trimmed)
}

private func isProtectedSparsePrefillRole(_ rawRole: String) -> Bool {
    switch rawRole.lowercased() {
    case "system", "developer":
        return true
    default:
        return false
    }
}

func promptContainsSparseRepeats(_ prompt: String) -> Bool {
    let lines = prompt
        .lowercased()
        .split(separator: "\n")
        .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
    guard lines.count >= 3 else {
        return false
    }
    return Set(lines).count < lines.count
}
