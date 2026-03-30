import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public actor ModelCatalog {
    public struct EvictionDecision: Equatable, Sendable {
        public let modelID: String
        public let reason: String

        public init(modelID: String, reason: String) {
            self.modelID = modelID
            self.reason = reason
        }
    }

    public struct EvictionPlan: Equatable, Sendable {
        public let decisions: [EvictionDecision]
        public let pinnedProtectedModelIDs: [String]

        public init(
            decisions: [EvictionDecision] = [],
            pinnedProtectedModelIDs: [String] = []
        ) {
            self.decisions = decisions
            self.pinnedProtectedModelIDs = pinnedProtectedModelIDs
        }
    }

    private struct ResidencyLedger: Sendable {
        var lastAccessOrdinal: UInt64
        var lastAccessUnixMs: Int64
        var transitionReason: String
    }

    private var models: [String: Melix_Controlplane_V1_ModelSummary]
    private var dispatchHandles: [String: String]
    private var residencyLedger: [String: ResidencyLedger]
    private var nextAccessOrdinal: UInt64
    private let nowUnixMs: @Sendable () -> Int64

    public init(
        seedModels: [Melix_Controlplane_V1_ModelSummary] = [ModelCatalog.devTextModel()],
        nowUnixMs: @escaping @Sendable () -> Int64 = {
            Int64(Date().timeIntervalSince1970 * 1_000)
        }
    ) {
        let normalizedSeedModels = seedModels.map { ModelCatalog.withSynchronizedResidency($0) }
        let seededNow = nowUnixMs()
        var ledger: [String: ResidencyLedger] = [:]
        var accessOrdinal: UInt64 = 0
        for model in normalizedSeedModels {
            accessOrdinal += 1
            ledger[model.modelID] = ResidencyLedger(
                lastAccessOrdinal: accessOrdinal,
                lastAccessUnixMs: seededNow,
                transitionReason: ""
            )
        }
        self.models = Dictionary(uniqueKeysWithValues: normalizedSeedModels.map { ($0.modelID, $0) })
        self.dispatchHandles = Dictionary(
            uniqueKeysWithValues: normalizedSeedModels.compactMap { model in
                guard model.state == .modelWarm || model.state == .modelPinned else {
                    return nil
                }
                return (model.modelID, ModelCatalog.defaultDispatchHandle(for: model.modelID))
            }
        )
        self.residencyLedger = ledger
        self.nextAccessOrdinal = accessOrdinal
        self.nowUnixMs = nowUnixMs
    }

    public func listModels() -> [Melix_Controlplane_V1_ModelSummary] {
        models.values.sorted { $0.modelID < $1.modelID }
    }

    public func model(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        models[id]
    }

    public func beginLoad(
        id: String,
        reason: String = "load_requested"
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: reason)
        model.state = .modelLoading
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func recordLoadSucceeded(
        id: String,
        dispatchHandle: String,
        pinRequested: Bool = false,
        workerResidency: Melix_Worker_V1_ResidencyInfo? = nil,
        reason: String? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }

        let loadedState = ModelCatalog.loadedState(
            for: model.settings,
            pinRequested: pinRequested,
            workerResidency: workerResidency
        )
        model.state = loadedState
        model.pinned = loadedState == .modelPinned || workerResidency?.pinned == true
        touchModel(
            id: id,
            transitionReason: resolvedLoadTransitionReason(
                explicitReason: reason,
                workerResidency: workerResidency
            )
        )
        model = synchronized(model)
        models[id] = model

        if loadedState == .modelWarm || loadedState == .modelPinned {
            dispatchHandles[id] = dispatchHandle
        } else {
            dispatchHandles.removeValue(forKey: id)
        }

        return model
    }

    public func recordLoadFailed(
        id: String,
        reason: String = "load_failed"
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: reason)
        model.state = .modelFailed
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func beginUnload(
        id: String,
        reason: String = "operator_unload"
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: reason)
        model.state = .modelEvicting
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func recordUnloadSucceeded(
        id: String,
        reason: String? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: resolvedUnloadTransitionReason(for: id, fallback: reason))
        model.state = .modelUnloaded
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func recordUnloadFailed(
        id: String,
        reason: String? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: failedUnloadTransitionReason(for: id, fallback: reason))
        model.state = .modelFailed
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func loadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginLoad(id: id, reason: "operator_load")
        return recordLoadSucceeded(
            id: id,
            dispatchHandle: ModelCatalog.defaultDispatchHandle(for: id),
            reason: "operator_load"
        )
    }

    public func loadModel(id: String, dispatchHandle: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginLoad(id: id, reason: "operator_load")
        return recordLoadSucceeded(id: id, dispatchHandle: dispatchHandle, reason: "operator_load")
    }

    public func unloadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginUnload(id: id, reason: "operator_unload")
        return recordUnloadSucceeded(id: id, reason: "operator_unload")
    }

    public func updateSettings(
        id: String,
        settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.settings = settings
        touchModel(id: id, transitionReason: "settings_updated")
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func markModelUsed(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id)
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func evictionPlanForLoad(id targetID: String) -> EvictionPlan {
        guard let targetModel = models[targetID] else {
            return EvictionPlan()
        }

        let loadedModels = models.values.filter { model in
            model.modelID != targetID && ModelCatalog.isResident(model)
        }
        let currentNowUnixMs = nowUnixMs()

        let ttlExpiredModels = loadedModels
            .filter { model in
                ModelCatalog.isAutomaticallyEvictable(model)
                    && ModelCatalog.isTTLExpired(
                        model,
                        lastAccessUnixMs: lastAccessUnixMs(for: model.modelID),
                        nowUnixMs: currentNowUnixMs
                    )
            }
            .sorted(by: compareRecency)

        let ttlExpiredIDs = Set(ttlExpiredModels.map(\.modelID))
        var decisions = ttlExpiredModels.map { EvictionDecision(modelID: $0.modelID, reason: "ttl_expired") }

        let pinnedProtectedModelIDs = loadedModels
            .filter { model in
                !ttlExpiredIDs.contains(model.modelID)
                    && ModelCatalog.sameEvictionFamily(model, targetModel)
                    && ModelCatalog.isPinProtected(model)
            }
            .map(\.modelID)
            .sorted()

        let lruCandidate = loadedModels
            .filter { model in
                !ttlExpiredIDs.contains(model.modelID)
                    && ModelCatalog.sameEvictionFamily(model, targetModel)
                    && ModelCatalog.isAutomaticallyEvictable(model)
            }
            .sorted(by: compareRecency)
            .first
        if !ModelCatalog.isResident(targetModel),
           let lruCandidate {
            decisions.append(EvictionDecision(modelID: lruCandidate.modelID, reason: "lru_same_capability"))
        }

        return EvictionPlan(
            decisions: decisions,
            pinnedProtectedModelIDs: pinnedProtectedModelIDs
        )
    }

    public func dispatchHandle(for id: String) -> String? {
        guard let model = models[id] else {
            return nil
        }
        guard model.state == .modelWarm || model.state == .modelPinned else {
            return nil
        }
        return dispatchHandles[id]
    }

    public func storedDispatchHandle(for id: String) -> String? {
        dispatchHandles[id]
    }

    public static func devTextModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityText
        model.routeClass = .workerRouteSwiftText
        model.quantProfileID = "dev-q4"
        model.maxContext = 8192
        model.features = ["chat", "adaptive_thinking"]
        model.settings.alias = "Melix Dev Text"
        model.settings.pinOnLoad = false
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.defaultAccelerationMode = .baseline
        model.settings.adaptiveThinking.mode = "adaptive"
        model.settings.adaptiveThinking.budgetTokens = 192
        return withSynchronizedResidency(model)
    }

    public static func devEmbeddingModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-embed"
        model.kind = "embedding"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityEmbedding
        model.routeClass = .workerRoutePythonEmbedding
        model.quantProfileID = "dev-f16"
        model.maxContext = 8192
        model.features = ["embeddings"]
        model.settings.alias = "Melix Dev Embed"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["embedding_backend_id"] = "bert-v1"
        model.settings.ext["embedding_family_id"] = "bert"
        model.settings.ext["embedding_pooling_mode"] = "cls"
        model.settings.ext["embedding_normalization"] = "l2"
        model.settings.ext["embedding_dimensions"] = "8"
        return withSynchronizedResidency(model)
    }

    public static func devRerankModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-rerank"
        model.kind = "rerank"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityRerank
        model.routeClass = .workerRoutePythonRerank
        model.quantProfileID = "dev-f16"
        model.maxContext = 8192
        model.features = ["rerank"]
        model.settings.alias = "Melix Dev Rerank"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["rerank_backend_id"] = "token-overlap-v1"
        model.settings.ext["rerank_family_id"] = "jina-v3"
        model.settings.ext["rerank_scoring_mode"] = "order-aware-overlap"
        return withSynchronizedResidency(model)
    }

    public static func devModelOpsModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-model-ops"
        model.kind = "model_ops"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityModelOperations
        model.routeClass = .workerRoutePythonModelOperations
        model.quantProfileID = "dev-ops"
        model.maxContext = 0
        model.features = ["quantize", "download", "upload"]
        model.settings.alias = "Melix Dev Model Ops"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        return withSynchronizedResidency(model)
    }

    public static func devOCRModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-ocr"
        model.kind = "ocr"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityOcr
        model.routeClass = .workerRoutePythonOcr
        model.features = ["ocr", "vision"]
        model.supportedModalities = ["image"]
        model.supportedTasks = ["ocr"]
        model.settings.alias = "Melix Dev OCR"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.settings.ext["ocr_prompt_template"] = "OCR instruction: {prompt}"
        model.settings.ext["ocr_auto_prompt"] = "Extract the text from the image exactly as written."
        model.settings.ext["ocr_stop_sequences"] = "<ocr:end>"
        model.settings.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.settings.ext["ocr_default_temperature"] = "0.0"
        model.settings.ext["ocr_default_top_p"] = "1.0"
        model.settings.ext["ocr_default_max_tokens"] = "256"
        return withSynchronizedResidency(model)
    }

    public static func devVLMModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-vlm"
        model.kind = "vlm"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityVlm
        model.routeClass = .workerRoutePythonVlm
        model.features = ["vision", "chat"]
        model.supportedModalities = ["image", "text"]
        model.supportedTasks = ["vlm"]
        model.settings.alias = "Melix Dev VLM"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["vision_family_id"] = "llava-v1"
        model.settings.ext["vision_prompt_profile_id"] = "llava-chatml-v1"
        model.settings.ext["vision_tokenization_mode"] = "interleaved"
        model.settings.ext["vision_max_images_per_prompt"] = "8"
        model.settings.ext["vision_supports_tool_calls"] = "true"
        model.settings.ext["melix.multimodal_adapter_hash"] = "vision-family-llava-v1"
        return withSynchronizedResidency(model)
    }

    public static func devTranscriptionModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-transcribe"
        model.kind = "transcription"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityTranscription
        model.routeClass = .workerRoutePythonTranscription
        model.features = ["audio", "transcription"]
        model.supportedModalities = ["audio"]
        model.supportedTasks = ["transcribe"]
        model.settings.alias = "Melix Dev Transcription"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        return withSynchronizedResidency(model)
    }

    public static func devSpeechModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-speech"
        model.kind = "speech"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilitySpeech
        model.routeClass = .workerRoutePythonSpeech
        model.features = ["audio", "speech"]
        model.supportedModalities = ["text", "audio"]
        model.supportedTasks = ["speak"]
        model.settings.alias = "Melix Dev Speech"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        return withSynchronizedResidency(model)
    }

    public static func devImageModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-image"
        model.kind = "image"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityImageGeneration
        model.routeClass = .workerRoutePythonImage
        model.features = ["image_generate", "image_edit", "artifact_jobs"]
        model.supportedModalities = ["text", "image"]
        model.supportedTasks = ["image_generate", "image_edit"]
        model.settings.alias = "Melix Dev Image"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        return withSynchronizedResidency(model)
    }

    public static func phaseFiveSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        [
            devTextModel(),
            devEmbeddingModel(),
            devRerankModel(),
            devModelOpsModel(),
        ]
    }

    public static func phaseSixContractSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        phaseFiveSeedModels() + [
            devOCRModel(),
            devVLMModel(),
            devTranscriptionModel(),
            devSpeechModel(),
        ]
    }

    public static func phaseSevenContractSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        phaseSixContractSeedModels() + [
            devImageModel(),
        ]
    }

    private static func defaultDispatchHandle(for id: String) -> String {
        "\(id)::local"
    }

    private func synchronized(
        _ source: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelSummary {
        ModelCatalog.withSynchronizedResidency(
            source,
            transitionReason: residencyLedger[source.modelID]?.transitionReason ?? ""
        )
    }

    private static func withSynchronizedResidency(
        _ source: Melix_Controlplane_V1_ModelSummary,
        transitionReason: String = ""
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = source
        model.pinned = effectivePinnedFlag(for: model)
        model.residency = residencySummary(for: model, transitionReason: transitionReason)
        return model
    }

    private static func residencySummary(
        for model: Melix_Controlplane_V1_ModelSummary,
        transitionReason: String
    ) -> Melix_Controlplane_V1_ResidencySummary {
        var residency = Melix_Controlplane_V1_ResidencySummary()
        residency.state = residencyState(for: model.state)
        residency.policy = effectivePolicy(for: model.settings)
        residency.pinRequested = model.settings.pinOnLoad
        residency.pinned = model.state == .modelPinned || model.pinned
        residency.ttlSeconds = model.settings.ttlSeconds
        residency.transitionReason = transitionReason
        return residency
    }

    private static func effectivePolicy(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_MemoryResidencyPolicy {
        if settings.pinOnLoad {
            return .memoryResidencyPinned
        }
        if settings.memoryPolicy != .unspecified {
            return settings.memoryPolicy
        }
        if settings.ttlSeconds > 0 {
            return .memoryResidencyTtl
        }
        return .memoryResidencyEvictable
    }

    private static func loadState(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelState {
        effectivePolicy(for: settings) == .memoryResidencyPinned ? .modelPinned : .modelWarm
    }

    private static func loadedState(
        for settings: Melix_Controlplane_V1_ModelSettings,
        pinRequested: Bool,
        workerResidency: Melix_Worker_V1_ResidencyInfo?
    ) -> Melix_Controlplane_V1_ModelState {
        guard let workerResidency else {
            if pinRequested {
                return .modelPinned
            }
            return loadState(for: settings)
        }

        switch workerResidency.state {
        case .pinned:
            return .modelPinned
        case .warm:
            return .modelWarm
        case .loading:
            return .modelLoading
        case .evicting:
            return .modelEvicting
        case .unloaded:
            return .modelUnloaded
        case .failed:
            return .modelFailed
        default:
            return loadState(for: settings)
        }
    }

    private static func effectivePinnedFlag(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        switch model.state {
        case .modelPinned:
            return true
        case .modelWarm:
            return model.pinned
        default:
            return false
        }
    }

    private static func residencyState(
        for state: Melix_Controlplane_V1_ModelState
    ) -> Melix_Controlplane_V1_ResidencyState {
        switch state {
        case .modelDiscovered:
            return .discovered
        case .modelLoading:
            return .loading
        case .modelWarm:
            return .warm
        case .modelPinned:
            return .pinned
        case .modelEvicting:
            return .evicting
        case .modelUnloaded:
            return .unloaded
        case .modelFailed:
            return .failed
        default:
            return .unspecified
        }
    }

    private func touchModel(
        id: String,
        transitionReason: String? = nil
    ) {
        nextAccessOrdinal += 1
        var ledger = residencyLedger[id] ?? ResidencyLedger(
            lastAccessOrdinal: 0,
            lastAccessUnixMs: nowUnixMs(),
            transitionReason: ""
        )
        ledger.lastAccessOrdinal = nextAccessOrdinal
        ledger.lastAccessUnixMs = nowUnixMs()
        if let transitionReason, !transitionReason.isEmpty {
            ledger.transitionReason = transitionReason
        }
        residencyLedger[id] = ledger
    }

    private func lastAccessUnixMs(for modelID: String) -> Int64 {
        residencyLedger[modelID]?.lastAccessUnixMs ?? 0
    }

    private func compareRecency(
        _ lhs: Melix_Controlplane_V1_ModelSummary,
        _ rhs: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        let lhsOrdinal = residencyLedger[lhs.modelID]?.lastAccessOrdinal ?? 0
        let rhsOrdinal = residencyLedger[rhs.modelID]?.lastAccessOrdinal ?? 0
        if lhsOrdinal != rhsOrdinal {
            return lhsOrdinal < rhsOrdinal
        }
        return lhs.modelID < rhs.modelID
    }

    private func resolvedLoadTransitionReason(
        explicitReason: String?,
        workerResidency: Melix_Worker_V1_ResidencyInfo?
    ) -> String {
        if let explicitReason, !explicitReason.isEmpty {
            return explicitReason
        }
        if let workerResidency, !workerResidency.transitionReason.isEmpty {
            return workerResidency.transitionReason
        }
        return "load_succeeded"
    }

    private func resolvedUnloadTransitionReason(
        for modelID: String,
        fallback: String?
    ) -> String {
        if let fallback, !fallback.isEmpty {
            return fallback
        }
        if let existing = residencyLedger[modelID]?.transitionReason, !existing.isEmpty {
            return existing
        }
        return "operator_unload"
    }

    private func failedUnloadTransitionReason(
        for modelID: String,
        fallback: String?
    ) -> String {
        let baseReason = resolvedUnloadTransitionReason(for: modelID, fallback: fallback)
        if baseReason.hasSuffix("_failed") {
            return baseReason
        }
        return "\(baseReason)_failed"
    }

    private static func isResident(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        switch model.state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }

    private static func isPinProtected(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        if model.state == .modelPinned || model.pinned || model.settings.pinOnLoad {
            return true
        }
        return effectivePolicy(for: model.settings) == .memoryResidencyPinned
    }

    private static func isAutomaticallyEvictable(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        isResident(model) && !isPinProtected(model)
    }

    private static func isTTLExpired(
        _ model: Melix_Controlplane_V1_ModelSummary,
        lastAccessUnixMs: Int64,
        nowUnixMs: Int64
    ) -> Bool {
        guard effectivePolicy(for: model.settings) == .memoryResidencyTtl,
              model.settings.ttlSeconds > 0 else {
            return false
        }
        let ttlMilliseconds = Int64(model.settings.ttlSeconds) * 1_000
        return lastAccessUnixMs + ttlMilliseconds <= nowUnixMs
    }

    private static func sameEvictionFamily(
        _ lhs: Melix_Controlplane_V1_ModelSummary,
        _ rhs: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        if lhs.capabilityClass != .unspecified,
           rhs.capabilityClass != .unspecified {
            return lhs.capabilityClass == rhs.capabilityClass
        }
        if lhs.routeClass != .unspecified,
           rhs.routeClass != .unspecified {
            return lhs.routeClass == rhs.routeClass
        }
        return !lhs.kind.isEmpty && lhs.kind == rhs.kind
    }
}
