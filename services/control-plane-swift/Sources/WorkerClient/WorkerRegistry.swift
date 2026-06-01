import MelixControlPlaneProtocol

public actor WorkerRegistry {
    public struct InferenceRouteAdmission: Sendable, Equatable {
        public let selection: RequestRouteSelection
        public let routeKind: WorkerRouteKind
        public let client: any WorkerRoutingClient

        public static func == (lhs: InferenceRouteAdmission, rhs: InferenceRouteAdmission) -> Bool {
            lhs.selection == rhs.selection && lhs.routeKind == rhs.routeKind
        }
    }

    private let defaultTextClient: any WorkerRoutingClient
    private let visionClient: (any WorkerRoutingClient)?
    private let pythonCompatibilityClient: (any WorkerRoutingClient)?
    private let embeddingClient: (any WorkerRoutingClient)?
    private let rerankClient: (any WorkerRoutingClient)?
    private let modelOperationsClient: (any WorkerRoutingClient)?
    private let modelCatalog: ModelCatalog?

    public init(
        defaultTextClient: any WorkerRoutingClient,
        visionClient: (any WorkerRoutingClient)? = nil,
        pythonCompatibilityClient: (any WorkerRoutingClient)? = nil,
        embeddingClient: (any WorkerRoutingClient)? = nil,
        rerankClient: (any WorkerRoutingClient)? = nil,
        modelOperationsClient: (any WorkerRoutingClient)? = nil,
        modelCatalog: ModelCatalog? = nil
    ) {
        self.defaultTextClient = defaultTextClient
        self.visionClient = visionClient
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
        if let route = WorkerRouteKind(metadataIdentifier: model.settings.ext["melix.capability.route_kind"]) {
            return route
        }
        if let route = WorkerRouteKind(routeClass: model.routeClass) {
            return route
        }
        if let route = WorkerRouteKind(capabilityIdentifier: model.settings.ext["melix.capability.class"]) {
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
        case .swiftVision:
            return visionClient
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

    public func admitInferenceRoute(
        requestID: String,
        modelID: String,
        task: Melix_Controlplane_V1_InferenceTask,
        requestModalities: Set<Melix_Controlplane_V1_RouteModality>,
        preferredWorkerInstanceID: String? = nil,
        selectedAtUnixMs: Int64 = 0,
        checkReadiness: Bool = true
    ) async -> RequestRouteResolution {
        guard !modelID.isEmpty else {
            return .rejected(modelLookupError(requestID: requestID, modelID: modelID, task: task, requestModalities: requestModalities))
        }
        guard let model = await structuredRouteModel(modelID: modelID) else {
            return .rejected(modelLookupError(requestID: requestID, modelID: modelID, task: task, requestModalities: requestModalities))
        }
        return RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: requestID,
                modelID: modelID,
                task: task,
                requestModalities: requestModalities,
                routes: model.requestRoutes,
                workerInstances: await workerInstanceSnapshots(checkReadiness: checkReadiness),
                preferredWorkerInstanceID: preferredWorkerInstanceID,
                selectionSnapshotID: 1,
                selectedAtUnixMs: selectedAtUnixMs
            )
        )
    }

    public func admission(
        for selection: RequestRouteSelection
    ) -> InferenceRouteAdmission? {
        guard let routeKind = WorkerRouteKind(workerFamily: selection.route.workerFamily),
              let client = client(for: routeKind)
        else {
            return nil
        }
        return InferenceRouteAdmission(
            selection: selection,
            routeKind: routeKind,
            client: client
        )
    }

    private func structuredRouteModel(modelID: String) async -> Melix_Controlplane_V1_ModelSummary? {
        if let modelCatalog,
           let model = await modelCatalog.model(id: modelID) {
            return model
        }
        let builtInModels = ModelCatalog.phaseSevenContractSeedModels()
        if let model = builtInModels.first(where: { $0.modelID == modelID }) {
            return model
        }
        return nil
    }

    private func workerInstanceSnapshots(checkReadiness: Bool) async -> [WorkerInstanceSnapshot] {
        var snapshots: [WorkerInstanceSnapshot] = [
            WorkerInstanceSnapshot(
                instanceID: "swift-text-worker",
                workerFamily: .text,
                ready: checkReadiness ? await defaultTextClient.canDispatchRequests() : true
            ),
        ]
        if let visionClient {
            snapshots.append(
                WorkerInstanceSnapshot(
                    instanceID: "swift-vision-worker",
                    workerFamily: .vision,
                    ready: checkReadiness ? await visionClient.canDispatchRequests() : true
                )
            )
        }
        return snapshots
    }

    private func modelLookupError(
        requestID: String,
        modelID: String,
        task: Melix_Controlplane_V1_InferenceTask,
        requestModalities: Set<Melix_Controlplane_V1_RouteModality>
    ) -> Melix_Controlplane_V1_ErrorStatus {
        _ = requestID
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = "route_not_supported"
        error.retriable = false
        error.message = "Request route admission failed for model \(modelID) with reason missing_request_routes."
        error.details = [
            "model_id": modelID,
            "task": RequestRouteResolver.canonicalName(task),
            "requested_modalities": RequestRouteResolver.canonicalModalities(requestModalities)
                .map(RequestRouteResolver.canonicalName)
                .joined(separator: ","),
            "required_modality_suite": "",
            "available_routes": "[]",
            "available_modality_suites": "",
            "worker_family_candidates": "",
            "reason": RequestRouteRejectionReason.missingRequestRoutes.rawValue,
        ]
        return error
    }
}
