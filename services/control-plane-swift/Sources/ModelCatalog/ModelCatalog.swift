import MelixControlPlaneProtocol

public actor ModelCatalog {
    private var models: [String: Melix_Controlplane_V1_ModelSummary]

    public init(seedModels: [Melix_Controlplane_V1_ModelSummary] = [ModelCatalog.devTextModel()]) {
        self.models = Dictionary(uniqueKeysWithValues: seedModels.map { ($0.modelID, $0) })
    }

    public func listModels() -> [Melix_Controlplane_V1_ModelSummary] {
        models.values.sorted { $0.modelID < $1.modelID }
    }

    public func loadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelWarm
        models[id] = model
        return model
    }

    public func unloadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        model.state = .modelUnloaded
        models[id] = model
        return model
    }

    public static func devTextModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = .modelDiscovered
        model.quantProfileID = "dev-q4"
        model.maxContext = 8192
        model.features = ["chat"]
        return model
    }
}
