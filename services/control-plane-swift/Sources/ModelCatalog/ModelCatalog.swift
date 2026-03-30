import MelixControlPlaneProtocol
import MelixWorkerProtocol

public actor ModelCatalog {
    private var models: [String: Melix_Controlplane_V1_ModelSummary]
    private var dispatchHandles: [String: String]

    public init(seedModels: [Melix_Controlplane_V1_ModelSummary] = [ModelCatalog.devTextModel()]) {
        let normalizedSeedModels = seedModels.map { ModelCatalog.withSynchronizedResidency($0) }
        self.models = Dictionary(uniqueKeysWithValues: normalizedSeedModels.map { ($0.modelID, $0) })
        self.dispatchHandles = Dictionary(
            uniqueKeysWithValues: normalizedSeedModels.compactMap { model in
                guard model.state == .modelWarm || model.state == .modelPinned else {
                    return nil
                }
                return (model.modelID, ModelCatalog.defaultDispatchHandle(for: model.modelID))
            }
        )
    }

    public func listModels() -> [Melix_Controlplane_V1_ModelSummary] {
        models.values.sorted { $0.modelID < $1.modelID }
    }

    public func model(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        models[id]
    }

    public func beginLoad(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelLoading
        model.pinned = false
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model
        return model
    }

    public func recordLoadSucceeded(
        id: String,
        dispatchHandle: String,
        pinRequested: Bool = false,
        workerResidency: Melix_Worker_V1_ResidencyInfo? = nil
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
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model

        if loadedState == .modelWarm || loadedState == .modelPinned {
            dispatchHandles[id] = dispatchHandle
        } else {
            dispatchHandles.removeValue(forKey: id)
        }

        return model
    }

    public func recordLoadFailed(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelFailed
        model.pinned = false
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func beginUnload(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelEvicting
        model.pinned = false
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model
        return model
    }

    public func recordUnloadSucceeded(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelUnloaded
        model.pinned = false
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func recordUnloadFailed(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelFailed
        model.pinned = false
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func loadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginLoad(id: id)
        return recordLoadSucceeded(
            id: id,
            dispatchHandle: ModelCatalog.defaultDispatchHandle(for: id)
        )
    }

    public func loadModel(id: String, dispatchHandle: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginLoad(id: id)
        return recordLoadSucceeded(id: id, dispatchHandle: dispatchHandle)
    }

    public func unloadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginUnload(id: id)
        return recordUnloadSucceeded(id: id)
    }

    public func updateSettings(
        id: String,
        settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.settings = settings
        model = ModelCatalog.withSynchronizedResidency(model)
        models[id] = model
        return model
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
        model.features = ["chat"]
        model.settings.alias = "Melix Dev Text"
        model.settings.pinOnLoad = false
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.defaultAccelerationMode = .baseline
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

    private static func withSynchronizedResidency(
        _ source: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = source
        model.pinned = effectivePinnedFlag(for: model)
        model.residency = residencySummary(for: model)
        return model
    }

    private static func residencySummary(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ResidencySummary {
        var residency = Melix_Controlplane_V1_ResidencySummary()
        residency.state = residencyState(for: model.state)
        residency.policy = effectivePolicy(for: model.settings)
        residency.pinRequested = model.settings.pinOnLoad
        residency.pinned = model.state == .modelPinned || model.pinned
        residency.ttlSeconds = model.settings.ttlSeconds
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
}
