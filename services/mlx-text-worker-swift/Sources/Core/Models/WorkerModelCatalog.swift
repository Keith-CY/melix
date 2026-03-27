import Foundation
import MelixWorkerProtocol

struct WorkerModelCatalog: Sendable {
    private let environment: [String: String]
    private let models: [String: Melix_Worker_V1_ModelSpec]

    init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.environment = environment
        let devTextModel = Self.devTextModel(environment: environment)
        self.models = [devTextModel.modelID: devTextModel]
    }

    func get(_ modelID: String) -> Melix_Worker_V1_ModelSpec? {
        models[modelID]
    }

    static func devTextModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-text"
        model.modelPath = environment["MELIX_DEV_TEXT_MODEL_PATH"] ?? "models/melix-dev-text"
        model.modelKind = "text"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8_192
        return model
    }
}
