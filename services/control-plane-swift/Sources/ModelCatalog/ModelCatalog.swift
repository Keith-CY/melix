import MelixControlPlaneProtocol

public actor ModelCatalog {
    private var models: [String: Melix_Controlplane_V1_ModelSummary]
    private var dispatchHandles: [String: String]

    public init(seedModels: [Melix_Controlplane_V1_ModelSummary] = [ModelCatalog.devTextModel()]) {
        self.models = Dictionary(uniqueKeysWithValues: seedModels.map { ($0.modelID, $0) })
        self.dispatchHandles = Dictionary(
            uniqueKeysWithValues: seedModels.compactMap { model in
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

    public func loadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        loadModel(id: id, dispatchHandle: ModelCatalog.defaultDispatchHandle(for: id))
    }

    public func loadModel(id: String, dispatchHandle: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelWarm
        models[id] = model
        dispatchHandles[id] = dispatchHandle
        return model
    }

    public func unloadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelUnloaded
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func updateSettings(
        id: String,
        settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.settings = settings
        model.pinned = settings.pinOnLoad
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
        return dispatchHandles[id] ?? ModelCatalog.defaultDispatchHandle(for: id)
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
        return model
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
        return model
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
        return model
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
        return model
    }

    public static func phaseFiveSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        [
            devTextModel(),
            devEmbeddingModel(),
            devRerankModel(),
            devModelOpsModel(),
        ]
    }

    private static func defaultDispatchHandle(for id: String) -> String {
        "\(id)::local"
    }
}
