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
        model.quantProfileID = "dev-q4"
        model.maxContext = 8192
        model.features = ["chat"]
        return model
    }

    private static func defaultDispatchHandle(for id: String) -> String {
        "\(id)::local"
    }
}
