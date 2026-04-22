import MelixControlPlaneProtocol

public actor WorkerRegistry {
    private let defaultTextClient: any WorkerRoutingClient
    private let pythonCompatibilityClient: (any WorkerRoutingClient)?
    private let embeddingClient: (any WorkerRoutingClient)?
    private let rerankClient: (any WorkerRoutingClient)?
    private let modelOperationsClient: (any WorkerRoutingClient)?
    private let modelCatalog: ModelCatalog?

    public init(
        defaultTextClient: any WorkerRoutingClient,
        pythonCompatibilityClient: (any WorkerRoutingClient)? = nil,
        embeddingClient: (any WorkerRoutingClient)? = nil,
        rerankClient: (any WorkerRoutingClient)? = nil,
        modelOperationsClient: (any WorkerRoutingClient)? = nil,
        modelCatalog: ModelCatalog? = nil
    ) {
        self.defaultTextClient = defaultTextClient
        self.pythonCompatibilityClient = pythonCompatibilityClient
        self.embeddingClient = embeddingClient
        self.rerankClient = rerankClient
        self.modelOperationsClient = modelOperationsClient
        self.modelCatalog = modelCatalog
    }

    public func route(forModelID modelID: String) async -> WorkerRouteKind? {
        guard !modelID.isEmpty else {
            return nil
        }
        if let modelCatalog,
           let model = await modelCatalog.model(id: modelID) {
            return route(for: model)
        }
        return .swiftText
    }

    public func route(for model: Melix_Controlplane_V1_ModelSummary) -> WorkerRouteKind? {
        if let route = WorkerRouteKind(routeClass: model.routeClass) {
            return route
        }
        if let route = routeKind(fromMetadata: model.settings.ext["melix.capability.route_kind"]) {
            return route
        }
        if let route = routeKind(fromCapabilityIdentifier: model.settings.ext["melix.capability.class"]) {
            return route
        }

        switch model.capabilityClass {
        case .modelCapabilityText:
            return .swiftText
        case .modelCapabilityEmbedding:
            return .pythonEmbedding
        case .modelCapabilityRerank:
            return .pythonRerank
        case .modelCapabilityModelOperations:
            return .pythonModelOperations
        case .modelCapabilityOcr:
            return .pythonOCR
        case .modelCapabilityVlm:
            return .pythonVLM
        case .modelCapabilityTranscription:
            return .pythonTranscription
        case .modelCapabilitySpeech:
            return .pythonSpeech
        case .modelCapabilityImageGeneration:
            return .pythonImage
        default:
            return model.kind == "text" ? .swiftText : .pythonCompatibility
        }
    }

    private func routeKind(fromMetadata rawValue: String?) -> WorkerRouteKind? {
        guard let rawValue else {
            return nil
        }
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch normalized {
        case "python_text_compatibility":
            return .pythonCompatibility
        default:
            return WorkerRouteKind(rawValue: normalized)
        }
    }

    private func routeKind(fromCapabilityIdentifier identifier: String?) -> WorkerRouteKind? {
        guard let identifier else {
            return nil
        }
        switch identifier.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "text":
            return .swiftText
        case "embedding":
            return .pythonEmbedding
        case "rerank":
            return .pythonRerank
        case "model_operations":
            return .pythonModelOperations
        case "ocr":
            return .pythonOCR
        case "vlm":
            return .pythonVLM
        case "transcription":
            return .pythonTranscription
        case "speech":
            return .pythonSpeech
        case "image_generation":
            return .pythonImage
        default:
            return nil
        }
    }

    public func client(forModelID modelID: String) async -> (any WorkerRoutingClient)? {
        guard let route = await route(forModelID: modelID) else {
            return nil
        }
        return client(for: route)
    }

    public func client(for route: WorkerRouteKind) -> (any WorkerRoutingClient)? {
        switch route {
        case .swiftText:
            return defaultTextClient
        case .pythonCompatibility:
            return pythonCompatibilityClient
        case .pythonEmbedding:
            return embeddingClient ?? pythonCompatibilityClient
        case .pythonRerank:
            return rerankClient ?? pythonCompatibilityClient
        case .pythonModelOperations:
            return modelOperationsClient ?? pythonCompatibilityClient
        case .pythonOCR, .pythonVLM, .pythonTranscription, .pythonSpeech, .pythonImage:
            return pythonCompatibilityClient
        }
    }
}
