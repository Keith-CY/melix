import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

private struct ModelLoadOutcome {
    let model: Melix_Controlplane_V1_ModelSummary
    let error: Melix_Controlplane_V1_ErrorStatus?
}

private struct BenchmarkTargetResolutionError: Error {
    let code: String
    let message: String
}

private enum BenchmarkTaskKind: String {
    case textGeneration = "text-generation"
    case imageToText = "image-to-text"
    case imageTextToText = "image-text-to-text"
    case textToImage = "text-to-image"
    case imageTextToImage = "image-text-to-image"

    var importedModelKind: String {
        switch self {
        case .textGeneration:
            return "text"
        case .imageToText, .imageTextToText:
            return "vlm"
        case .textToImage, .imageTextToImage:
            return "image"
        }
    }

    var capabilityClass: Melix_Controlplane_V1_ModelCapabilityClass {
        switch self {
        case .textGeneration:
            return .modelCapabilityText
        case .imageToText, .imageTextToText:
            return .modelCapabilityVlm
        case .textToImage, .imageTextToImage:
            return .modelCapabilityImageGeneration
        }
    }

    var routeClass: Melix_Controlplane_V1_WorkerRouteClass {
        switch self {
        case .textGeneration:
            return .workerRoutePythonTextCompatibility
        case .imageToText, .imageTextToText:
            return .workerRoutePythonVlm
        case .textToImage, .imageTextToImage:
            return .workerRoutePythonImage
        }
    }

    var capabilityIdentifier: String {
        switch self {
        case .textGeneration:
            return "text"
        case .imageToText, .imageTextToText:
            return "vlm"
        case .textToImage, .imageTextToImage:
            return "image_generation"
        }
    }

    var metricsPrefix: String {
        switch self {
        case .textGeneration:
            return "text"
        case .imageToText, .imageTextToText:
            return "vision"
        case .textToImage, .imageTextToImage:
            return "image"
        }
    }

    var supportedModalities: [String] {
        switch self {
        case .textGeneration:
            return ["text"]
        case .imageToText, .imageTextToText, .textToImage, .imageTextToImage:
            return ["text", "image"]
        }
    }

    var supportedTasks: [String] {
        switch self {
        case .textGeneration:
            return ["generate"]
        case .imageToText:
            return ["vlm", "generate", "image_to_text"]
        case .imageTextToText:
            return ["vlm", "generate", "image_text_to_text"]
        case .textToImage:
            return ["image_generate"]
        case .imageTextToImage:
            return ["image_edit"]
        }
    }

    var supportedParsers: [String] {
        switch self {
        case .textGeneration:
            return ["text"]
        case .imageToText:
            return ["text"]
        case .imageTextToText:
            return ["text", "qwen"]
        case .textToImage, .imageTextToImage:
            return ["text"]
        }
    }

    var features: [String] {
        switch self {
        case .textGeneration:
            return ["chat"]
        case .imageToText:
            return ["vision", "caption"]
        case .imageTextToText:
            return ["vision", "chat"]
        case .textToImage:
            return ["image_generate", "artifact_jobs"]
        case .imageTextToImage:
            return ["image_edit", "artifact_jobs"]
        }
    }
}

public actor ControlPlaneService {
    public let serverVersion: String
    private let daemonInstanceID: String
    private let modelCatalog: ModelCatalog
    private let metricsStore: MetricsStore
    private let eventHub: EventSubscriptionHub
    private let snapshotBuilder: ServerSnapshotBuilder
    private let enginePool: EnginePool
    private let schedulerReadModel: SchedulerReadModel
    private let cacheMetadataStore: CacheMetadataStore
    private let sessionGraphStore: SessionGraphStore
    private let imageJobReadModel: ImageJobReadModel
    private let imageJobAdmissionController: any ImageJobAdmissionControlling
    private let workerRegistry: WorkerRegistry?
    private let requestCoordinator: RequestCoordinator?
    private let chatTranslator: ChatRequestTranslator
    private let mcpToolCatalog: MCPToolCatalog
    private let audioAssetManager: AudioAssetManager
    private let gatewayAccessPolicyStore: GatewayAccessPolicyStore
    private let persistentAuthSessionStore: PersistentAuthSessionStore?

    public init(
        serverVersion: String = "0.1.0",
        daemonInstanceID: String = UUID().uuidString,
        modelCatalog: ModelCatalog = ModelCatalog(),
        metricsStore: MetricsStore = MetricsStore(),
        eventHub: EventSubscriptionHub = EventSubscriptionHub(),
        snapshotBuilder: ServerSnapshotBuilder = ServerSnapshotBuilder(),
        enginePool: EnginePool = EnginePool(),
        schedulerReadModel: SchedulerReadModel? = nil,
        cacheMetadataStore: CacheMetadataStore = CacheMetadataStore(),
        sessionGraphStore: SessionGraphStore = SessionGraphStore(),
        imageJobReadModel: ImageJobReadModel? = nil,
        imageJobAdmissionController: (any ImageJobAdmissionControlling)? = nil,
        workerRegistry: WorkerRegistry? = nil,
        requestCoordinator: RequestCoordinator? = nil,
        chatTranslator: ChatRequestTranslator = ChatRequestTranslator(),
        mcpToolCatalog: MCPToolCatalog = .empty,
        gatewayAccessPolicy: GatewayAccessPolicy = .localTrust,
        audioAssetManager: AudioAssetManager = AudioAssetManager(),
        gatewayAccessPolicyStore: GatewayAccessPolicyStore? = nil,
        persistentAuthSessionStore: PersistentAuthSessionStore? = nil
    ) {
        let resolvedSchedulerReadModel = schedulerReadModel ?? SchedulerReadModel(
            metricsStore: metricsStore,
            eventPublisher: { event in
                await eventHub.publish(event)
            }
        )
        let resolvedImageJobReadModel = imageJobReadModel ?? ImageJobReadModel(
            eventPublisher: { event in
                await eventHub.publish(event)
            }
        )
        let resolvedImageJobAdmissionController = imageJobAdmissionController ?? ImageJobAdmissionController(
            schedulerReadModel: resolvedSchedulerReadModel,
            metricsStore: metricsStore
        )
        self.serverVersion = serverVersion
        self.daemonInstanceID = daemonInstanceID
        self.modelCatalog = modelCatalog
        self.metricsStore = metricsStore
        self.eventHub = eventHub
        self.snapshotBuilder = snapshotBuilder
        self.enginePool = enginePool
        self.cacheMetadataStore = cacheMetadataStore
        self.sessionGraphStore = sessionGraphStore
        self.imageJobReadModel = resolvedImageJobReadModel
        self.imageJobAdmissionController = resolvedImageJobAdmissionController
        self.workerRegistry = workerRegistry
        self.schedulerReadModel = resolvedSchedulerReadModel
        self.requestCoordinator = requestCoordinator ?? workerRegistry.map { registry in
            RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                schedulerReadModel: resolvedSchedulerReadModel,
                metricsStore: metricsStore,
                modelCatalog: modelCatalog,
                sessionGraphStore: sessionGraphStore,
                cacheMetadataStore: cacheMetadataStore
            )
        }
        self.chatTranslator = chatTranslator
        self.mcpToolCatalog = mcpToolCatalog
        self.audioAssetManager = audioAssetManager
        self.gatewayAccessPolicyStore = gatewayAccessPolicyStore ?? GatewayAccessPolicyStore(gatewayAccessPolicy)
        self.persistentAuthSessionStore = persistentAuthSessionStore
    }

    public func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = request.protocolVersion
        response.serverVersion = serverVersion
        response.daemonInstanceID = daemonInstanceID
        response.features = [
            "xpc",
            "models",
            "metrics",
            "cache-metadata",
            "session-graph",
            "image-jobs",
            "audio-assets",
        ]
        if !mcpToolCatalog.sources.isEmpty || !mcpToolCatalog.configPath.isEmpty {
            response.features.append("mcp-tools")
        }
        response.snapshot = await buildSnapshot()
        return response
    }

    public func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch request.command {
        case .server(let command):
            return await handleServer(request: request, command: command)
        case .model(let command):
            return await handleModel(request: request, command: command)
        case .cache(let command):
            return await handleCache(request: request, command: command)
        case .session(let command):
            return await handleSession(request: request, command: command)
        case .ops(let command):
            return await handleOps(request: request, command: command)
        case .image(let command):
            return await handleImage(request: request, command: command)
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Command family is not implemented in the phase-0 control plane."
            )
        }
    }

    public func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest = Melix_Controlplane_V1_SubscribeRequest()
    ) async -> ControlPlaneSubscription {
        await eventHub.subscribe(lastSeenSeq: request.lastSeenSeq)
    }

    public func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        guard let requestCoordinator else {
            throw ControlPlaneChatExecutionError.unavailable
        }

        let normalized = try chatTranslator.normalize(
            OpenAIChatCompletionsRequest(
                model: request.modelID,
                messages: request.messages.map {
                    OpenAIChatCompletionsRequest.Message(role: $0.role, content: $0.content)
                },
                stream: true,
                temperature: request.temperature,
                topP: request.topP,
                maxTokens: request.maxTokens
            )
        )
        let modelHandle: String
        do {
            modelHandle = try await OnDemandModelLoader.ensureTextModelReady(
                modelID: normalized.model,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
        } catch {
            throw ControlPlaneChatExecutionError.unavailable
        }
        let modelToolParser: ToolParserSelection? = if let model = await modelCatalog.model(id: normalized.model) {
            ToolParserSelection(modelSettings: model.settings)
        } else {
            nil
        }
        let modelChatTemplatePolicy: ModelChatTemplatePolicy? = if let model = await modelCatalog.model(id: normalized.model) {
            try ModelChatTemplatePolicy(modelSettings: model.settings)
        } else {
            nil
        }
        let modelOCRPolicy: OCRExecutionPolicy? = if let model = await modelCatalog.model(id: normalized.model) {
            OCRExecutionPolicy(modelSettings: model.settings)
        } else {
            nil
        }
        let translated = try chatTranslator.translate(
            normalized,
            modelHandle: modelHandle,
            modelToolParser: modelToolParser,
            modelChatTemplatePolicy: modelChatTemplatePolicy,
            modelOCRPolicy: modelOCRPolicy,
            mcpToolCatalog: mcpToolCatalog
        )
        let execution = try await requestCoordinator.startChatCompletion(translated)

        let stream = AsyncThrowingStream<ControlPlaneChatStreamEvent, Error> { continuation in
            let forwardTask = Task {
                do {
                    for try await event in execution.stream {
                        guard let mapped = ControlPlaneChatStreamEvent(executeEvent: event) else {
                            continue
                        }
                        continuation.yield(mapped)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                forwardTask.cancel()
            }
        }

        return ControlPlaneChatExecution(
            requestID: execution.requestID,
            modelID: execution.modelID,
            stream: stream
        )
    }

    public func unsubscribe(_ subscriptionID: String) async {
        await eventHub.unsubscribe(subscriptionID)
    }

    private func handleServer(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_ServerCommand
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch command.kind {
        case .getSnapshot:
            var reply = Melix_Controlplane_V1_ServerReply()
            reply.snapshot = await buildSnapshot()
            return okResponse(for: request, server: reply)
        case .applyGatewayAccess(let apply):
            return await handleApplyGatewayAccess(request: request, command: apply)
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Server command is not implemented in the phase-0 control plane."
            )
        }
    }

    private func handleModel(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_ModelCommand
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch command.kind {
        case .list:
            await syncRegistryModelsFromWorkerIfAvailable()
            var reply = Melix_Controlplane_V1_ModelReply()
            reply.models = hydratedModels(await modelCatalog.listModels())
            return okResponse(for: request, model: reply)
        case .load(let load):
            guard await modelCatalog.model(id: load.modelID) != nil else {
                return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
            }
            await performEvictionsForLoad(targetModelID: load.modelID)
            if let loading = await modelCatalog.beginLoad(id: load.modelID, reason: "operator_load"),
               workerRegistry != nil {
                await publishModelStateChanged(loading)
            }
            let outcome = await handleModelLoad(modelID: load.modelID, reason: "operator_load")
            let model = outcome.model
            if workerRegistry != nil {
                await publishModelStateChanged(model)
            }
            guard model.state != .modelFailed else {
                if let error = outcome.error {
                    return errorResponse(for: request, error: error)
                }
                return errorResponse(
                    for: request,
                    code: "unavailable",
                    message: "The worker could not load the requested model."
                )
            }
            var reply = Melix_Controlplane_V1_ModelReply()
            reply.model = hydrate(model)
            reply.models = hydratedModels(await modelCatalog.listModels())
            return okResponse(for: request, model: reply)
        case .unload(let unload):
            guard await modelCatalog.model(id: unload.modelID) != nil else {
                return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
            }
            if let evicting = await modelCatalog.beginUnload(id: unload.modelID, reason: "operator_unload"),
               workerRegistry != nil {
                await publishModelStateChanged(evicting)
            }
            let model = await handleModelUnload(modelID: unload.modelID, reason: "operator_unload")
            if workerRegistry != nil {
                await publishModelStateChanged(model)
            }
            guard model.state != .modelFailed else {
                return errorResponse(
                    for: request,
                    code: "unavailable",
                    message: "The worker could not unload the requested model."
                )
            }
            var reply = Melix_Controlplane_V1_ModelReply()
            reply.model = hydrate(model)
            reply.models = hydratedModels(await modelCatalog.listModels())
            return okResponse(for: request, model: reply)
        case .setPolicy(let setPolicy):
            return await handleSetModelPolicy(request: request, command: setPolicy)
        case .getInfo(let getInfo):
            return await handleGetModelInfo(request: request, command: getInfo)
        case .runOperation(let runOperation):
            return await handleRunModelOperation(request: request, command: runOperation)
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Model command is not implemented in the phase-0 control plane."
            )
        }
    }

    private func handleCache(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_CacheCommand
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch command.kind {
        case .getSnapshot:
            var reply = Melix_Controlplane_V1_CacheReply()
            reply.snapshot = await cacheMetadataStore.cacheSnapshot()
            reply.summary = reply.snapshot.summary
            return okResponse(for: request, cache: reply)
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Cache command is not implemented in the current control plane."
            )
        }
    }

    private func handleSession(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_SessionCommand
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch command.kind {
        case .createSession:
            let session = await sessionGraphStore.createSession()
            await publishSessionStateChanged(session)
            var reply = Melix_Controlplane_V1_SessionReply()
            reply.session = session
            return okResponse(for: request, session: reply)
        case .createBranch(let createBranch):
            do {
                let session = try await sessionGraphStore.createBranch(
                    sessionID: createBranch.sessionID,
                    parentBranchID: createBranch.parentBranchID
                )
                await publishSessionStateChanged(session)
                var reply = Melix_Controlplane_V1_SessionReply()
                reply.session = session
                return okResponse(for: request, session: reply)
            } catch {
                return sessionErrorResponse(for: request, error: error)
            }
        case .closeSession(let closeSession):
            guard let session = await sessionGraphStore.closeSession(sessionID: closeSession.sessionID) else {
                return errorResponse(for: request, code: "not_found", message: "Unknown session ID.")
            }
            await publishSessionStateChanged(session)
            var reply = Melix_Controlplane_V1_SessionReply()
            reply.session = session
            return okResponse(for: request, session: reply)
        case .getState(let getState):
            guard let session = await sessionGraphStore.state(for: getState.sessionID) else {
                return errorResponse(for: request, code: "not_found", message: "Unknown session ID.")
            }
            var reply = Melix_Controlplane_V1_SessionReply()
            reply.session = session
            return okResponse(for: request, session: reply)
        case .registerToolResult(let registerToolResult):
            do {
                let session = try await sessionGraphStore.registerToolResult(
                    sessionID: registerToolResult.sessionID,
                    branchID: registerToolResult.branchID,
                    toolCallID: registerToolResult.toolCallID
                )
                await publishSessionStateChanged(session)
                var reply = Melix_Controlplane_V1_SessionReply()
                reply.session = session
                return okResponse(for: request, session: reply)
            } catch {
                return sessionErrorResponse(for: request, error: error)
            }
        case .resumeAfterTool(let resumeAfterTool):
            do {
                let session = try await sessionGraphStore.resumeAfterTool(
                    sessionID: resumeAfterTool.sessionID,
                    branchID: resumeAfterTool.branchID,
                    snapshotID: resumeAfterTool.snapshotID
                )
                await publishSessionStateChanged(session)
                var reply = Melix_Controlplane_V1_SessionReply()
                reply.session = session
                return okResponse(for: request, session: reply)
            } catch {
                return sessionErrorResponse(for: request, error: error)
            }
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Session command is not implemented in the current control plane."
            )
        }
    }

    private func handleOps(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_OpsCommand
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch command.kind {
        case .getMetrics:
            var reply = Melix_Controlplane_V1_OpsReply()
            reply.metrics = await metricsStore.snapshot()
            return okResponse(for: request, ops: reply)
        case .runDoctor(let runDoctor):
            return await handleRunDoctor(request: request, command: runDoctor)
        case .searchHubModels(let searchHubModels):
            return await handleSearchHubModels(request: request, command: searchHubModels)
        case .getHubModelCard(let getHubModelCard):
            return await handleGetHubModelCard(request: request, command: getHubModelCard)
        case .runBench(let runBench):
            return await handleRunBench(request: request, command: runBench)
        case .runBenchMatrix(let runBenchMatrix):
            return await handleRunBenchMatrix(request: request, command: runBenchMatrix)
        case .runEvaluation(let runEvaluation):
            return await handleRunEvaluation(request: request, command: runEvaluation)
        case .cancelRequest(let cancelRequest):
            return await handleCancelRequest(request: request, command: cancelRequest)
        case .exportResults(let exportResults):
            return await handleExportResults(request: request, command: exportResults)
        case .submitResults(let submitResults):
            return await handleSubmitResults(request: request, command: submitResults)
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Ops command is not implemented in the phase-0 control plane."
            )
        }
    }

    private func handleRunDoctor(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command _: Melix_Controlplane_V1_RunDoctor
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_RunDoctorRequest()
        workerRequest.modelHandle = await preferredModelOperationsHandle()
        workerRequest.includeCacheDiagnostics = true
        workerRequest.includeMemoryReport = true

        do {
            let workerResponse = try await workerClient.runDoctor(request: workerRequest)
            guard workerResponse.ok else {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Doctor request failed." : workerResponse.error.message
                )
            }

            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "control_plane.ops_doctor_ms"
            )

            var reply = Melix_Controlplane_V1_OpsReply()
            reply.reportMarkdown = workerResponse.reportMarkdown
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Doctor worker request failed: \(error)")
        }
    }

    private func handleSearchHubModels(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_SearchHubModels
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_SearchHubModelsRequest()
        workerRequest.query = command.query
        workerRequest.pageSize = command.pageSize == 0 ? 20 : command.pageSize
        workerRequest.cursor = command.cursor
        workerRequest.mlxOnly = command.mlxOnly

        do {
            let workerResponse = try await workerClient.searchHubModels(request: workerRequest)
            guard workerResponse.ok else {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Hub search failed." : workerResponse.error.message
                )
            }

            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "hub.search_latency_ms"
            )

            var reply = Melix_Controlplane_V1_OpsReply()
            reply.hubSearch = makeHubSearchResult(from: workerResponse)
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Hub search worker request failed: \(error)")
        }
    }

    private func handleGetHubModelCard(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_GetHubModelCard
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_GetHubModelCardRequest()
        workerRequest.repoID = command.repoID

        do {
            let workerResponse = try await workerClient.getHubModelCard(request: workerRequest)
            guard workerResponse.ok else {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Hub model card request failed." : workerResponse.error.message
                )
            }

            var reply = Melix_Controlplane_V1_OpsReply()
            reply.hubModelCard = makeHubModelCard(from: workerResponse.card)
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Hub model card worker request failed: \(error)")
        }
    }

    private func handleRunBench(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_RunBench
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        let requestedModelID = command.modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let requestedHFRepoID = command.hfRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
        let benchmarkModel: Melix_Controlplane_V1_ModelSummary
        do {
            benchmarkModel = try await resolvedBenchmarkModel(
                preferredModelID: requestedModelID,
                hfRepoID: requestedHFRepoID,
                workerClient: workerClient
            )
        } catch let error as BenchmarkTargetResolutionError {
            return errorResponse(for: request, code: error.code, message: error.message)
        } catch {
            return errorResponse(for: request, code: "not_found", message: "Benchmark target resolution failed: \(error)")
        }

        guard !benchmarkModel.modelID.isEmpty else {
            let modelLabel = requestedHFRepoID.isEmpty
                ? (requestedModelID.isEmpty ? "preferred benchmark model" : requestedModelID)
                : requestedHFRepoID
            return errorResponse(
                for: request,
                code: "not_found",
                message: "No loaded benchmark target is available for \(modelLabel)."
            )
        }
        let requestedSuites = Array(command.suites)
        guard requestedSuites.isEmpty == false else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "At least one benchmark suite is required."
            )
        }

        let normalizedContextLengths = ControlPlaneBenchRequest.normalizedBenchValues(command.contextLengths)
        guard normalizedContextLengths.isEmpty == false else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "At least one benchmark context length is required."
            )
        }

        guard command.repeats >= 1 else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Benchmark repeats must be at least 1."
            )
        }

        guard command.cacheProfile.isEmpty || ControlPlaneBenchRequest.validCacheProfiles.contains(command.cacheProfile) else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Benchmark cache profile must be one of: \(ControlPlaneBenchRequest.validCacheProfiles.joined(separator: ", "))."
            )
        }

        let normalizedBatchSizes = ControlPlaneBenchRequest.normalizedBenchValues(command.batchSizes)
        let modelHandle: String
        do {
            modelHandle = try await benchmarkModelHandle(for: benchmarkModel)
        } catch {
            return errorResponse(
                for: request,
                code: "not_found",
                message: "No loaded benchmark target is available for \(benchmarkModel.modelID)."
            )
        }

        var workerRequest = Melix_Worker_V1_RunBenchRequest()
        workerRequest.modelHandle = modelHandle
        workerRequest.suites = requestedSuites
        workerRequest.parameters = command.parameters
        workerRequest.contextLengths = normalizedContextLengths
        workerRequest.generationLength = command.generationLength
        workerRequest.batchSizes = normalizedBatchSizes
        workerRequest.repeats = command.repeats
        workerRequest.cacheProfile = command.cacheProfile
        workerRequest.reasoningMode = command.reasoningMode
        workerRequest.structuredOutputMode = command.structuredOutputMode
        workerRequest.taskKind = benchmarkTaskKind(for: benchmarkModel)
        workerRequest.sourceRepo = benchmarkSourceRepo(for: benchmarkModel)

        do {
            let stream = try await workerClient.runBench(request: workerRequest)
            var reply = Melix_Controlplane_V1_OpsReply()
            var benchJobID = ""
            var metricUnits: [String: String] = [:]
            var failedError: Melix_Controlplane_V1_ErrorStatus?

            for try await event in stream {
                switch event.payload {
                case .started(let started):
                    benchJobID = started.jobID
                    reply.benchmarkJob = makeBenchmarkJobSummary(
                        jobID: started.jobID,
                        modelID: benchmarkModel.modelID,
                        suites: requestedSuites,
                        parameters: command.parameters,
                        status: "running",
                        outputDir: "",
                        taskKind: workerRequest.taskKind,
                        sourceRepo: workerRequest.sourceRepo
                    )
                case .progress(let progress):
                    await publishBenchProgress(jobID: benchJobID, suite: progress.suite, pct: progress.pct)
                case .metric(let metric):
                    reply.metrics.values[metric.name] = metric.value
                    metricUnits[metric.name] = metric.unit
                    await metricsStore.set(metric.value, forKey: metric.name)
                case .completed(let completed):
                    reply.reportPath = completed.reportPath
                    if let markdown = try? String(contentsOfFile: completed.reportPath, encoding: .utf8) {
                        reply.reportMarkdown = markdown
                    }
                    let resolvedJobID = benchJobID.isEmpty ? "bench-unknown" : benchJobID
                    reply.benchmarkJob = makeBenchmarkJobSummary(
                        jobID: resolvedJobID,
                        modelID: benchmarkModel.modelID,
                        suites: requestedSuites,
                        parameters: command.parameters,
                        status: "completed",
                        outputDir: URL(fileURLWithPath: completed.reportPath).deletingLastPathComponent().path,
                        taskKind: workerRequest.taskKind,
                        sourceRepo: workerRequest.sourceRepo
                    )
                    reply.benchmarkResults = makeBenchmarkResultSummaries(
                        jobID: resolvedJobID,
                        metrics: reply.metrics.values,
                        metricUnits: metricUnits,
                        reportPath: reply.reportPath,
                        reportMarkdown: reply.reportMarkdown
                    )
                case .failed(let failed):
                    failedError = makeErrorStatus(from: failed.error)
                    let resolvedJobID = benchJobID.isEmpty ? "bench-unknown" : benchJobID
                    reply.benchmarkJob = makeBenchmarkJobSummary(
                        jobID: resolvedJobID,
                        modelID: benchmarkModel.modelID,
                        suites: requestedSuites,
                        parameters: command.parameters,
                        status: "failed",
                        outputDir: "",
                        taskKind: workerRequest.taskKind,
                        sourceRepo: workerRequest.sourceRepo
                    )
                case nil:
                    break
                }
            }

            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "control_plane.ops_bench_ms"
            )

            if let failedError {
                return errorResponse(
                    for: request,
                    code: failedError.code.isEmpty ? "unknown" : failedError.code,
                    message: failedError.message.isEmpty ? "Bench request failed." : failedError.message,
                    ops: reply
                )
            }

            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Bench worker request failed: \(error)")
        }
    }

    private func handleRunBenchMatrix(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_RunBenchMatrix
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        let requestedModelID = command.modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let requestedHFRepoID = command.hfRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
        let benchmarkModel: Melix_Controlplane_V1_ModelSummary
        do {
            benchmarkModel = try await resolvedBenchmarkModel(
                preferredModelID: requestedModelID,
                hfRepoID: requestedHFRepoID,
                workerClient: workerClient
            )
        } catch let error as BenchmarkTargetResolutionError {
            return errorResponse(for: request, code: error.code, message: error.message)
        } catch {
            return errorResponse(for: request, code: "not_found", message: "Benchmark target resolution failed: \(error)")
        }

        let suites = Array(Set(command.suiteIds.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty })).sorted()
        let contextLengths = ControlPlaneBenchRequest.normalizedBenchValues(command.contextLengths)
        let generationLengths = ControlPlaneBenchRequest.normalizedBenchValues(command.generationLengths)
        let batchSizes = ControlPlaneBenchRequest.normalizedBenchValues(command.batchSizes)
        let cacheProfiles = ControlPlaneBenchMatrixRequest.normalizedStringValues(command.cacheProfiles)
        let reasoningModes = ControlPlaneBenchMatrixRequest.normalizedStringValues(command.reasoningModes)
        let structuredOutputModes = ControlPlaneBenchMatrixRequest.normalizedStringValues(command.structuredOutputModes)
        let concurrencyLevels = ControlPlaneBenchRequest.normalizedBenchValues(command.concurrencyLevels)

        guard suites.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark suite is required.")
        }
        guard contextLengths.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark context length is required.")
        }
        guard generationLengths.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark generation length is required.")
        }
        guard batchSizes.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark batch size is required.")
        }
        guard cacheProfiles.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark cache profile is required.")
        }
        guard reasoningModes.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark reasoning mode is required.")
        }
        guard structuredOutputModes.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark structured output mode is required.")
        }
        guard concurrencyLevels.isEmpty == false else {
            return errorResponse(for: request, code: "invalid_argument", message: "At least one matrix benchmark concurrency level is required.")
        }
        let loadBudgetCount = [command.requests > 0, command.durationSeconds > 0].filter(\.self).count
        guard loadBudgetCount == 1 else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Exactly one of requests or duration_seconds must be set for matrix benchmarks."
            )
        }
        for cacheProfile in cacheProfiles where ControlPlaneBenchRequest.validCacheProfiles.contains(cacheProfile) == false {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Benchmark cache profile must be one of: \(ControlPlaneBenchRequest.validCacheProfiles.joined(separator: ", "))."
            )
        }

        let taskKind = benchmarkTaskKind(for: benchmarkModel)
        let supportedTaskKinds = Set([
            BenchmarkTaskKind.textGeneration.rawValue,
            BenchmarkTaskKind.imageToText.rawValue,
            BenchmarkTaskKind.imageTextToText.rawValue,
        ])
        guard supportedTaskKinds.contains(taskKind) else {
            return errorResponse(
                for: request,
                code: "unsupported_task_family",
                message: "Benchmark matrix supports only text-generation, image-to-text, and image-text-to-text targets."
            )
        }

        let normalizedRequest = ControlPlaneBenchMatrixRequest(
            modelID: benchmarkModel.modelID,
            hfRepoID: requestedHFRepoID,
            taskKind: taskKind,
            suites: suites,
            contextLengths: contextLengths,
            generationLengths: generationLengths,
            batchSizes: batchSizes,
            cacheProfiles: cacheProfiles,
            reasoningModes: reasoningModes,
            structuredOutputModes: structuredOutputModes,
            concurrencyLevels: concurrencyLevels,
            repeats: command.repeats,
            requests: command.requests,
            durationSeconds: command.durationSeconds,
            allowLargeMatrix: command.allowLargeMatrix
        )
        guard normalizedRequest.allowLargeMatrix || normalizedRequest.matrixCellCount <= ControlPlaneBenchMatrixRequest.maxMatrixCellCount else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Matrix benchmark expands to \(normalizedRequest.matrixCellCount) cells; pass allow_large_matrix to continue."
            )
        }

        let modelHandle: String
        do {
            modelHandle = try await benchmarkModelHandle(for: benchmarkModel)
        } catch {
            return errorResponse(
                for: request,
                code: "not_found",
                message: "No loaded benchmark target is available for \(benchmarkModel.modelID)."
            )
        }

        var workerRequest = Melix_Worker_V1_RunBenchMatrixRequest()
        workerRequest.modelHandle = modelHandle
        workerRequest.taskKind = taskKind
        workerRequest.sourceRepo = benchmarkSourceRepo(for: benchmarkModel)
        workerRequest.suiteIds = normalizedRequest.suites
        workerRequest.contextLengths = normalizedRequest.contextLengths
        workerRequest.generationLengths = normalizedRequest.generationLengths
        workerRequest.batchSizes = normalizedRequest.batchSizes
        workerRequest.cacheProfiles = normalizedRequest.cacheProfiles
        workerRequest.reasoningModes = normalizedRequest.reasoningModes
        workerRequest.structuredOutputModes = normalizedRequest.structuredOutputModes
        workerRequest.concurrencyLevels = normalizedRequest.concurrencyLevels
        workerRequest.repeats = normalizedRequest.repeats
        workerRequest.requests = normalizedRequest.requests
        workerRequest.durationSeconds = normalizedRequest.durationSeconds
        workerRequest.allowLargeMatrix = normalizedRequest.allowLargeMatrix

        do {
            let workerResponse = try await workerClient.runBenchMatrix(request: workerRequest)
            var reply = Melix_Controlplane_V1_OpsReply()
            reply.benchmarkMatrixJob = makeBenchmarkMatrixJobSummary(from: workerResponse.job)
            reply.benchmarkMatrixSummaryRows = workerResponse.summaryRows.map(makeBenchmarkMatrixSummaryRow)
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Matrix benchmark worker request failed: \(error)")
        }
    }

    private func handleRunEvaluation(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_RunEvaluation
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        let requestedModelID = command.modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let requestedHFRepoID = command.hfRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
        let evaluationModel: Melix_Controlplane_V1_ModelSummary
        do {
            evaluationModel = try await resolvedBenchmarkModel(
                preferredModelID: requestedModelID,
                hfRepoID: requestedHFRepoID,
                workerClient: workerClient
            )
        } catch {
            let resolvedError = (error as? BenchmarkTargetResolutionError)
                .map { ($0.code, $0.message) }
                ?? ("not_found", "Evaluation target resolution failed: \(error)")
            return errorResponse(for: request, code: resolvedError.0, message: resolvedError.1)
        }

        let taskKind = benchmarkTaskKind(for: evaluationModel)
        guard taskKind == BenchmarkTaskKind.textGeneration.rawValue else {
            return errorResponse(
                for: request,
                code: "unsupported_task_family",
                message: "Evaluation currently supports text-generation targets only. Resolved task_kind=\(taskKind)."
            )
        }

        let modelHandle: String
        do {
            modelHandle = try await benchmarkModelHandle(for: evaluationModel)
        } catch {
            return errorResponse(
                for: request,
                code: "not_found",
                message: "No loaded evaluation target is available for \(evaluationModel.modelID)."
            )
        }

        var workerRequest = Melix_Worker_V1_RunEvaluationRequest()
        workerRequest.modelHandle = modelHandle
        workerRequest.suiteID = command.suiteID
        workerRequest.datasetID = command.datasetID
        workerRequest.sampleSize = command.sampleSize
        workerRequest.fewShot = command.fewShot
        workerRequest.seed = command.seed
        workerRequest.scoringMode = command.scoringMode
        workerRequest.codeExecPolicy = command.codeExecPolicy
        workerRequest.parameters = command.parameters
        workerRequest.taskKind = taskKind
        workerRequest.sourceRepo = benchmarkSourceRepo(for: evaluationModel)

        do {
            let workerResponse = try await workerClient.runEvaluation(request: workerRequest)
            guard workerResponse.ok else {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Evaluation request failed." : workerResponse.error.message
                )
            }

            var reply = Melix_Controlplane_V1_OpsReply()
            reply.evaluationJob = makeEvaluationJobSummary(from: workerResponse.job)
            reply.evaluationResults = workerResponse.results.map(makeEvaluationResultSummary)
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Evaluation worker request failed: \(error)")
        }
    }

    private func handleExportResults(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_ExportResults
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_ExportResultsRequest()
        workerRequest.outputDir = command.outputDir

        do {
            let workerResponse = try await workerClient.exportResults(request: workerRequest)
            guard workerResponse.ok else {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Export request failed." : workerResponse.error.message
                )
            }

            var reply = Melix_Controlplane_V1_OpsReply()
            reply.exportBundleJson = workerResponse.exportJson
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Export worker request failed: \(error)")
        }
    }

    private func handleSubmitResults(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_SubmitResults
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_SubmitResultsRequest()
        workerRequest.outputDir = command.outputDir
        workerRequest.deviceMetadata = command.deviceMetadata

        do {
            let workerResponse = try await workerClient.submitResults(request: workerRequest)
            guard workerResponse.ok else {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Submit request failed." : workerResponse.error.message
                )
            }

            var reply = Melix_Controlplane_V1_OpsReply()
            reply.submissionJson = workerResponse.submissionJson
            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Submit worker request failed: \(error)")
        }
    }

    private func handleImage(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_ImageCommand
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch command.kind {
        case .generate(let generate):
            return await handleGenerateImage(request: request, command: generate)
        case .edit(let edit):
            return await handleEditImage(request: request, command: edit)
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Image command is not implemented in the current control plane."
            )
        }
    }

    private func buildSnapshot() async -> Melix_Controlplane_V1_ServerSnapshot {
        let models = hydratedModels(await modelCatalog.listModels())
        let metrics = await metricsStore.snapshot()
        let queues = await schedulerReadModel.snapshot()
        let cache = await cacheMetadataStore.cacheSummary()
        let sessions = await sessionGraphStore.sessionSummaries()
        let imageJobs = await imageJobReadModel.snapshot()
        let gatewayAccessSummary = await gatewayAccessPolicyStore.summary()
        return snapshotBuilder.build(
            models: models,
            metrics: metrics,
            queues: queues,
            cache: cache,
            sessions: sessions,
            imageJobs: imageJobs,
            mcpTools: mcpToolCatalog.summary(),
            gatewayAccess: gatewayAccessSummary
        )
    }

    private func handleApplyGatewayAccess(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_ApplyGatewayAccess
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        if request.targetID.isEmpty || request.targetID != command.serverSessionID {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Target server session does not match gateway access payload."
            )
        }
        guard let policy = GatewayAccessPolicy(apply: command) else {
            return errorResponse(
                for: request,
                code: "invalid_argument",
                message: "Gateway access payload is invalid."
            )
        }

        let appliedPolicy = await gatewayAccessPolicyStore.replace(
            with: policy,
            serverSessionID: appliedPolicyServerSessionID(policy: policy, command: command)
        )
        if let persistentAuthSessionStore {
            try? await persistentAuthSessionStore.reconcile(with: appliedPolicy)
        }
        await metricsStore.set(appliedPolicy.metricModeCode, forKey: "gateway.auth_mode_code")
        await metricsStore.set(Double(appliedPolicy.acceptedAPIKeyCount), forKey: "gateway.accepted_api_key_count")
        await metricsStore.set(appliedPolicy.sharedAccessEnabled ? 1 : 0, forKey: "shared_access.enabled")
        await metricsStore.set(appliedPolicy.sharedAccessReady ? 1 : 0, forKey: "shared_access.ready")
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "gateway.api_key_apply_ms"
        )

        var reply = Melix_Controlplane_V1_ServerReply()
        reply.snapshot = await buildSnapshot()
        return okResponse(for: request, server: reply)
    }

    private func appliedPolicyServerSessionID(
        policy: GatewayAccessPolicy,
        command: Melix_Controlplane_V1_ApplyGatewayAccess
    ) -> String? {
        policy.mode == .none ? nil : command.serverSessionID
    }

    private func handleGenerateImage(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_GenerateImage
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard let modelHandle = await modelCatalog.dispatchHandle(for: command.modelID) else {
            return errorResponse(for: request, code: "not_ready", message: "Image model is not loaded.")
        }
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(forModelID: command.modelID) as? any NonTextInferenceWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Image worker is unavailable.")
        }

        let routeKind = await workerRegistry.route(forModelID: command.modelID) ?? .pythonImage
        let jobID = "\(request.requestID)::image-generate"

        var workerRequest = Melix_Worker_V1_ImageGenerateRequest()
        workerRequest.id.requestID = request.requestID
        workerRequest.modelHandle = modelHandle
        workerRequest.prompt = command.prompt
        workerRequest.size = command.size.isEmpty ? "1024x1024" : command.size
        workerRequest.n = command.n == 0 ? 1 : command.n
        workerRequest.responseFormat = command.responseFormat.isEmpty ? "png" : command.responseFormat
        workerRequest.artifactNamespace = command.artifactNamespace

        await imageJobReadModel.recordQueued(
            requestID: request.requestID,
            jobID: jobID,
            modelID: command.modelID,
            operation: "image_generate",
            lane: routeKind.defaultSchedulingLane
        )
        do {
            try await imageJobAdmissionController.acquire(
                requestID: request.requestID,
                laneHint: routeKind.defaultSchedulingLane,
                workerID: routeKind.workerSourceID
            )
        } catch ImageJobAdmissionError.cancelled {
            await imageJobReadModel.recordCanceled(jobID: jobID)
            return errorResponse(for: request, code: "cancelled", message: "Image job was cancelled before execution.")
        } catch ImageJobAdmissionError.saturated {
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: controlPlaneError(
                    code: "resource_exhausted",
                    message: "Image queue is saturated. Wait for the current job to finish."
                )
            )
            return errorResponse(
                for: request,
                code: "resource_exhausted",
                message: "Image queue is saturated. Wait for the current job to finish."
            )
        } catch {
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "unavailable", message: "Image admission failed: \(error)")
            )
            return errorResponse(for: request, code: "unavailable", message: "Image admission failed: \(error)")
        }

        await imageJobReadModel.recordRunning(jobID: jobID, workerID: routeKind.workerSourceID, pct: 0)

        do {
            let workerResponse = try await workerClient.imageGenerate(request: workerRequest)
            let resolvedJobID = workerResponse.job.jobID.isEmpty ? jobID : workerResponse.job.jobID
            let artifacts = workerResponse.job.artifacts.map(imageArtifactRef(from:))
            await recordImageJobTerminalState(
                jobID: resolvedJobID,
                workerJob: workerResponse.job,
                artifacts: artifacts,
                fallbackError: workerResponse.error
            )
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "images.request_latency_ms"
            )
            await metricsStore.set(
                Double(workerResponse.images.reduce(0) { $0 + $1.count }),
                forKey: "images.output_bytes"
            )
            await imageJobAdmissionController.finish(
                requestID: request.requestID,
                phase: imageJobPhase(for: workerResponse.job, error: workerResponse.error),
                workerID: routeKind.workerSourceID
            )

            if !workerResponse.error.code.isEmpty {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code,
                    message: workerResponse.error.message
                )
            }

            var reply = Melix_Controlplane_V1_ImageReply()
            reply.job = controlPlaneImageJob(from: workerResponse.job, modelID: command.modelID)
            if reply.job.jobID.isEmpty {
                reply.job.jobID = resolvedJobID
            }
            return okResponse(for: request, image: reply)
        } catch {
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "unavailable", message: "Image worker request failed: \(error)")
            )
            await imageJobAdmissionController.finish(
                requestID: request.requestID,
                phase: .requestFailed,
                workerID: routeKind.workerSourceID
            )
            return errorResponse(for: request, code: "unavailable", message: "Image worker request failed: \(error)")
        }
    }

    private func handleEditImage(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_EditImage
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard !command.image.isEmpty || !command.imageUri.isEmpty else {
            return errorResponse(for: request, code: "invalid_argument", message: "Image edit source is required.")
        }
        let startedAt = Date()
        guard let modelHandle = await modelCatalog.dispatchHandle(for: command.modelID) else {
            return errorResponse(for: request, code: "not_ready", message: "Image model is not loaded.")
        }
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(forModelID: command.modelID) as? any NonTextInferenceWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Image worker is unavailable.")
        }

        let routeKind = await workerRegistry.route(forModelID: command.modelID) ?? .pythonImage
        let jobID = "\(request.requestID)::image-edit"

        var workerRequest = Melix_Worker_V1_ImageEditRequest()
        workerRequest.id.requestID = request.requestID
        workerRequest.modelHandle = modelHandle
        workerRequest.prompt = command.prompt
        workerRequest.image = command.image
        workerRequest.imageUri = command.imageUri
        workerRequest.mask = command.mask
        workerRequest.maskUri = command.maskUri
        workerRequest.strength = command.strength == 0 ? 1 : command.strength
        workerRequest.size = command.size.isEmpty ? "1024x1024" : command.size
        workerRequest.n = command.n == 0 ? 1 : command.n
        workerRequest.responseFormat = command.responseFormat.isEmpty ? "png" : command.responseFormat

        await imageJobReadModel.recordQueued(
            requestID: request.requestID,
            jobID: jobID,
            modelID: command.modelID,
            operation: "image_edit",
            lane: routeKind.defaultSchedulingLane
        )
        do {
            try await imageJobAdmissionController.acquire(
                requestID: request.requestID,
                laneHint: routeKind.defaultSchedulingLane,
                workerID: routeKind.workerSourceID
            )
        } catch ImageJobAdmissionError.cancelled {
            await imageJobReadModel.recordCanceled(jobID: jobID)
            return errorResponse(for: request, code: "cancelled", message: "Image job was cancelled before execution.")
        } catch ImageJobAdmissionError.saturated {
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: controlPlaneError(
                    code: "resource_exhausted",
                    message: "Image queue is saturated. Wait for the current job to finish."
                )
            )
            return errorResponse(
                for: request,
                code: "resource_exhausted",
                message: "Image queue is saturated. Wait for the current job to finish."
            )
        } catch {
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "unavailable", message: "Image admission failed: \(error)")
            )
            return errorResponse(for: request, code: "unavailable", message: "Image admission failed: \(error)")
        }

        await imageJobReadModel.recordRunning(jobID: jobID, workerID: routeKind.workerSourceID, pct: 0)

        do {
            let workerResponse = try await workerClient.imageEdit(request: workerRequest)
            let resolvedJobID = workerResponse.job.jobID.isEmpty ? jobID : workerResponse.job.jobID
            let artifacts = workerResponse.job.artifacts.map(imageArtifactRef(from:))
            await recordImageJobTerminalState(
                jobID: resolvedJobID,
                workerJob: workerResponse.job,
                artifacts: artifacts,
                fallbackError: workerResponse.error
            )
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "images.request_latency_ms"
            )
            await metricsStore.set(
                Double(workerResponse.images.reduce(0) { $0 + $1.count }),
                forKey: "images.output_bytes"
            )
            await imageJobAdmissionController.finish(
                requestID: request.requestID,
                phase: imageJobPhase(for: workerResponse.job, error: workerResponse.error),
                workerID: routeKind.workerSourceID
            )

            if !workerResponse.error.code.isEmpty {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code,
                    message: workerResponse.error.message
                )
            }

            var reply = Melix_Controlplane_V1_ImageReply()
            reply.job = controlPlaneImageJob(from: workerResponse.job, modelID: command.modelID)
            if reply.job.jobID.isEmpty {
                reply.job.jobID = resolvedJobID
            }
            return okResponse(for: request, image: reply)
        } catch {
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "unavailable", message: "Image worker request failed: \(error)")
            )
            await imageJobAdmissionController.finish(
                requestID: request.requestID,
                phase: .requestFailed,
                workerID: routeKind.workerSourceID
            )
            return errorResponse(for: request, code: "unavailable", message: "Image worker request failed: \(error)")
        }
    }

    private func handleCancelRequest(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_CancelRequest
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        if let requestCoordinator {
            do {
                if try await requestCoordinator.cancel(requestID: command.requestID) {
                    var reply = Melix_Controlplane_V1_OpsReply()
                    reply.reportMarkdown = "cancel_requested"
                    return okResponse(for: request, ops: reply)
                }
            } catch {
                return errorResponse(for: request, code: "unavailable", message: "Cancel request failed: \(error)")
            }
        }

        guard let imageJob = await imageJobReadModel.job(requestID: command.requestID) else {
            return errorResponse(for: request, code: "not_found", message: "Unknown request ID.")
        }

        await metricsStore.increment("images.cancel_requested_total")
        switch await imageJobAdmissionController.cancel(requestID: command.requestID) {
        case .queued:
            await imageJobReadModel.recordCanceled(jobID: imageJob.jobID)
            await metricsStore.increment("images.cancel_success_total")
            var reply = Melix_Controlplane_V1_OpsReply()
            reply.reportMarkdown = "cancelled"
            return okResponse(for: request, ops: reply)
        case .running:
            guard
                let workerRegistry,
                let workerClient = await workerRegistry.client(forModelID: imageJob.modelID)
            else {
                return errorResponse(for: request, code: "unavailable", message: "Image worker is unavailable.")
            }

            do {
                if try await workerClient.abort(requestID: command.requestID) {
                    await metricsStore.increment("images.cancel_success_total")
                    var reply = Melix_Controlplane_V1_OpsReply()
                    reply.reportMarkdown = "cancel_requested"
                    return okResponse(for: request, ops: reply)
                }
                return errorResponse(for: request, code: "not_found", message: "Image request is no longer active.")
            } catch {
                return errorResponse(for: request, code: "unavailable", message: "Image cancel failed: \(error)")
            }
        case .notFound:
            return errorResponse(for: request, code: "not_found", message: "Image request is no longer active.")
        }
    }

    private func handleSetModelPolicy(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_SetModelPolicy
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard let existingModel = await modelCatalog.model(id: command.modelID) else {
            return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
        }

        var settings = existingModel.settings
        applyModelPolicy(command.values, to: &settings)

        guard let model = await modelCatalog.updateSettings(id: command.modelID, settings: settings) else {
            return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
        }

        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "control_plane.model_settings_ms"
        )

        var reply = Melix_Controlplane_V1_ModelReply()
        reply.model = model
        reply.models = await modelCatalog.listModels()
        return okResponse(for: request, model: reply)
    }

    private func handleGetModelInfo(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_GetModelInfo
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard await modelCatalog.model(id: command.modelID) != nil else {
            return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
        }
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_GetModelInfoRequest()
        workerRequest.sourceModel = command.modelID

        do {
            let workerResponse = try await workerClient.getModelInfo(request: workerRequest)
            if !workerResponse.ok {
                return errorResponse(
                    for: request,
                    code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                    message: workerResponse.error.message.isEmpty ? "Model info request failed." : workerResponse.error.message
                )
            }

            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "control_plane.model_info_ms"
            )

            var reply = Melix_Controlplane_V1_ModelReply()
            reply.info.ok = workerResponse.ok
            reply.info.modelKind = workerResponse.modelKind
            reply.info.maxContext = workerResponse.maxContext
            reply.info.supportedParsers = workerResponse.supportedParsers
            reply.info.supportedModalities = workerResponse.supportedModalities
            return okResponse(for: request, model: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Model info worker request failed: \(error)")
        }
    }

    private func handleRunModelOperation(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command: Melix_Controlplane_V1_RunModelOperation
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard await modelCatalog.model(id: command.modelID) != nil else {
            return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
        }
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_ConvertModelRequest()
        workerRequest.sourceModel = command.modelID
        workerRequest.outputDir = command.outputDir
        workerRequest.weightQuant = command.weightQuant
        workerRequest.kvQuant = command.kvQuant
        workerRequest.generateManifest = command.generateManifest
        workerRequest.runSmokeTest = command.runSmokeTest
        workerRequest.ext = command.ext
        if workerRequest.ext["operation"] == nil {
            workerRequest.ext["operation"] = command.operation
        }
        if let quantProfile = normalizedWorkerQuantProfile(for: command) {
            workerRequest.quantProfile = quantProfile
        }

        do {
            let stream = try await workerClient.convertModel(request: workerRequest)
            var operation = Melix_Controlplane_V1_ModelOperationResult()
            operation.ok = true
            operation.operation = command.operation

            for try await event in stream {
                switch event.payload {
                case .started(let started):
                    operation.jobID = started.jobID
                case .progress(let progress):
                    operation.stage = progress.stage
                    operation.pct = progress.pct
                case .manifest(let manifest):
                    operation.manifestJson = manifest.manifestJson
                    if manifest.hasQuantProfile {
                        operation.quantProfile = controlPlaneQuantProfile(from: manifest.quantProfile)
                    }
                    if manifest.hasArtifact {
                        operation.artifact = controlPlaneArtifact(from: manifest.artifact)
                    }
                    if command.operation == "train_lora" || command.operation == "activate_adapter" {
                        await recordModelOperationMetrics(from: manifest.manifestJson, operation: command.operation)
                    }
                case .completed(let completed):
                    operation.outputPath = completed.outputPath
                    if completed.hasQuantProfile {
                        operation.quantProfile = controlPlaneQuantProfile(from: completed.quantProfile)
                    }
                    if completed.hasArtifact {
                        operation.artifact = controlPlaneArtifact(from: completed.artifact)
                    }
                case .failed(let failed):
                    operation.ok = false
                    operation.error = makeErrorStatus(from: failed.error)
                case nil:
                    break
                }
            }

            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "control_plane.model_operation_ms"
            )

            guard operation.ok else {
                var response = errorResponse(
                    for: request,
                    code: operation.error.code.isEmpty ? "unknown" : operation.error.code,
                    message: operation.error.message.isEmpty ? "Model operation failed." : operation.error.message
                )
                response.model = Melix_Controlplane_V1_ModelReply()
                response.model.operation = operation
                return response
            }

            if command.operation == "activate_adapter" {
                await registerActivatedDerivedModel(from: operation.manifestJson)
            }
            do {
                try await finalizeAudioModelOperation(command: command, operation: &operation)
            } catch {
                return errorResponse(
                    for: request,
                    code: "runtime_error",
                    message: "Audio asset bookkeeping failed: \(error)"
                )
            }

            var reply = Melix_Controlplane_V1_ModelReply()
            reply.operation = operation
            return okResponse(for: request, model: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Model operation worker request failed: \(error)")
        }
    }

    private func syncRegistryModelsFromWorkerIfAvailable() async {
        await RegistrySnapshotSync.syncModelsIfAvailable(
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore
        )
    }

    private func finalizeAudioModelOperation(
        command: Melix_Controlplane_V1_RunModelOperation,
        operation: inout Melix_Controlplane_V1_ModelOperationResult
    ) async throws {
        let selectedModel = hydratedModel(await modelCatalog.model(id: command.modelID))
        guard let selectedModel else {
            return
        }

        let backendID = selectedModel.settings.ext["melix.audio.backend_id"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard backendID.hasPrefix("mlx_audio.") else {
            return
        }

        if command.operation == "install_audio_runtime" {
            let installProfile = selectedModel.settings.ext["melix.audio.install_profile"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard !installProfile.isEmpty else {
                return
            }
            let packID = normalizedAudioMetadataValue(command.ext["melix.audio.runtime_pack_id"])
                ?? normalizedAudioMetadataValue(selectedModel.settings.ext["melix.audio.runtime_pack_id"])
                ?? audioAssetManager.runtimePackID(for: installProfile)
            let version = normalizedAudioMetadataValue(command.ext["melix.audio.runtime_pack_version"]) ?? "0.3.0"
            try audioAssetManager.recordRuntimePackInstall(
                packID: packID,
                version: version,
                profiles: sharedAudioRuntimeProfiles(for: installProfile)
            )
            operation.outputPath = audioAssetManager.audioRuntimePackRootURL
                .appendingPathComponent(packID, isDirectory: true)
                .appendingPathComponent(version, isDirectory: true)
                .path
            return
        }

        guard command.operation == "download",
              let modelSpec = BootstrapWorkerPreparation.modelSpec(for: selectedModel)
        else {
            return
        }

        let sourceModelPath = normalizedAudioMetadataValue(modelSpec.modelPath) ?? command.modelID
        let revision = normalizedAudioMetadataValue(selectedModel.settings.ext["melix.model_revision"])
            ?? normalizedAudioMetadataValue(modelSpec.revision)
            ?? "managed"
        let localModelDirectory = audioAssetManager.managedModelDirectoryURL(
            sourceModelPath: sourceModelPath,
            revision: revision
        )
        try audioAssetManager.recordManagedModel(
            modelID: command.modelID,
            revision: revision,
            sourceModelPath: sourceModelPath,
            localModelPath: localModelDirectory.path
        )
        operation.outputPath = localModelDirectory.path
    }

    private func normalizedAudioMetadataValue(_ rawValue: String?) -> String? {
        guard let rawValue else {
            return nil
        }
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? nil : normalized
    }

    private func sharedAudioRuntimeProfiles(for installProfile: String) -> [String] {
        let normalizedInstallProfile = installProfile.trimmingCharacters(in: .whitespacesAndNewlines)
        switch normalizedInstallProfile {
        case "audio-stt", "audio-tts", "audio":
            return ["audio-stt", "audio-tts"]
        default:
            return normalizedInstallProfile.isEmpty ? [] : [normalizedInstallProfile]
        }
    }

    private func normalizedWorkerQuantProfile(
        for command: Melix_Controlplane_V1_RunModelOperation
    ) -> Melix_Worker_V1_QuantizationProfile? {
        guard command.operation == "quantize" || command.hasQuantProfile else {
            return nil
        }

        var profile = Melix_Worker_V1_QuantizationProfile()
        if command.hasQuantProfile {
            profile.algorithm = command.quantProfile.algorithm
            profile.schemaVersion = command.quantProfile.schemaVersion
            profile.quantProfileID = command.quantProfile.quantProfileID
            profile.weightQuant = command.quantProfile.weightQuant
            profile.kvQuant = command.quantProfile.kvQuant
            profile.ext = command.quantProfile.ext
        }

        if profile.algorithm.isEmpty {
            profile.algorithm = "oq"
        }
        if profile.schemaVersion.isEmpty {
            profile.schemaVersion = "melix.quant_profile.v1"
        }
        if profile.quantProfileID.isEmpty {
            profile.quantProfileID = command.weightQuant.isEmpty ? "q4" : command.weightQuant
        }
        if profile.weightQuant.isEmpty {
            profile.weightQuant = command.weightQuant.isEmpty ? profile.quantProfileID : command.weightQuant
        }
        if profile.kvQuant.isEmpty {
            profile.kvQuant = command.kvQuant
        }
        return profile
    }

    private func controlPlaneQuantProfile(
        from profile: Melix_Worker_V1_QuantizationProfile
    ) -> Melix_Controlplane_V1_QuantizationProfile {
        var message = Melix_Controlplane_V1_QuantizationProfile()
        message.algorithm = profile.algorithm
        message.schemaVersion = profile.schemaVersion
        message.quantProfileID = profile.quantProfileID
        message.weightQuant = profile.weightQuant
        message.kvQuant = profile.kvQuant
        message.ext = profile.ext
        return message
    }

    private func controlPlaneArtifact(
        from artifact: Melix_Worker_V1_QuantizedArtifact
    ) -> Melix_Controlplane_V1_ModelOperationArtifact {
        var message = Melix_Controlplane_V1_ModelOperationArtifact()
        message.schemaVersion = artifact.schemaVersion
        message.artifactKind = artifact.artifactKind
        message.manifestPath = artifact.manifestPath
        message.bundlePath = artifact.bundlePath
        message.artifactBytes = artifact.artifactBytes
        message.manifestBytes = artifact.manifestBytes
        message.servingCompatible = artifact.servingCompatible
        message.smokeTestRequested = artifact.smokeTestRequested
        message.smokeTestPassed = artifact.smokeTestPassed
        message.runtime = artifact.runtime
        return message
    }

    private func applyModelPolicy(
        _ values: [String: String],
        to settings: inout Melix_Controlplane_V1_ModelSettings
    ) {
        for (key, value) in values {
            switch key {
            case "alias":
                settings.alias = value
            case "type_override":
                settings.typeOverride = value
            case "ttl_seconds":
                if let ttl = UInt32(value) {
                    settings.ttlSeconds = ttl
                }
            case "pin_on_load":
                settings.pinOnLoad = parseBool(value)
            case "memory_policy":
                settings.memoryPolicy = memoryPolicy(for: value)
            case "default_acceleration_mode":
                settings.defaultAccelerationMode = accelerationMode(for: value)
            case "acceleration_profile_id":
                settings.accelerationProfileID = value
            default:
                settings.ext[key] = value
            }
        }
    }

    private func parseBool(_ value: String) -> Bool {
        switch value.lowercased() {
        case "1", "true", "yes", "on":
            return true
        default:
            return false
        }
    }

    private func preferredModelOperationsHandle() async -> String {
        let models = await modelCatalog.listModels()
        for model in models where model.kind == "text" || model.capabilityClass == .modelCapabilityText {
            if let handle = await modelCatalog.dispatchHandle(for: model.modelID) {
                return handle
            }
        }
        for model in models {
            if let handle = await modelCatalog.dispatchHandle(for: model.modelID) {
                return handle
            }
        }
        return ""
    }

    private func resolvedBenchmarkModelID(preferred modelID: String) async -> String {
        if !modelID.isEmpty {
            return modelID
        }
        let models = await modelCatalog.listModels()

        for model in models where model.kind == "text" || model.capabilityClass == .modelCapabilityText {
            return model.modelID
        }
        return models.first?.modelID ?? ""
    }

    private func resolvedBenchmarkModel(
        preferredModelID modelID: String,
        hfRepoID: String,
        workerClient: any ModelOperationsWorkerClientProtocol
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        if !hfRepoID.isEmpty {
            return try await importBenchmarkTargetFromHub(repoID: hfRepoID, workerClient: workerClient)
        }
        let benchmarkModelID = await resolvedBenchmarkModelID(preferred: modelID)
        guard let benchmarkModel = await modelCatalog.model(id: benchmarkModelID) else {
            throw BenchmarkTargetResolutionError(
                code: "not_found",
                message: "No loaded benchmark target is available for \(benchmarkModelID.isEmpty ? "preferred benchmark model" : benchmarkModelID)."
            )
        }
        return benchmarkModel
    }

    private func benchmarkModelHandle(for model: Melix_Controlplane_V1_ModelSummary) async throws -> String {
        try await OnDemandModelLoader.ensureModelReady(
            modelID: model.modelID,
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            loadReason: "lazy_benchmark_load",
            metricsPrefix: benchmarkMetricsPrefix(for: model),
            requiresTextCapability: false
        )
    }

    private func benchmarkTaskKind(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        for key in ["melix.benchmark.task_kind", "melix.task_kind"] {
            if let explicitTaskKind = model.settings.ext[key]?.trimmingCharacters(in: .whitespacesAndNewlines),
               !explicitTaskKind.isEmpty {
                return explicitTaskKind
            }
        }

        switch model.kind {
        case "text":
            return BenchmarkTaskKind.textGeneration.rawValue
        case "ocr":
            return BenchmarkTaskKind.imageToText.rawValue
        case "vlm":
            return BenchmarkTaskKind.imageTextToText.rawValue
        case "image":
            return BenchmarkTaskKind.textToImage.rawValue
        default:
            return BenchmarkTaskKind.textGeneration.rawValue
        }
    }

    private func benchmarkSourceRepo(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        for key in ["melix.hf_repo_id", "melix.source_repo", "melix.model_path"] {
            if let value = model.settings.ext[key]?.trimmingCharacters(in: .whitespacesAndNewlines),
               !value.isEmpty {
                return value
            }
        }
        return ""
    }

    private func benchmarkMetricsPrefix(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        switch benchmarkTaskKind(for: model) {
        case BenchmarkTaskKind.textGeneration.rawValue:
            return BenchmarkTaskKind.textGeneration.metricsPrefix
        case BenchmarkTaskKind.imageToText.rawValue,
             BenchmarkTaskKind.imageTextToText.rawValue:
            return BenchmarkTaskKind.imageTextToText.metricsPrefix
        case BenchmarkTaskKind.textToImage.rawValue,
             BenchmarkTaskKind.imageTextToImage.rawValue:
            return BenchmarkTaskKind.textToImage.metricsPrefix
        default:
            return "model"
        }
    }

    private func importBenchmarkTargetFromHub(
        repoID: String,
        workerClient: any ModelOperationsWorkerClientProtocol
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        if let existing = await modelCatalog.model(id: repoID) {
            return existing
        }

        var workerRequest = Melix_Worker_V1_GetHubModelCardRequest()
        workerRequest.repoID = repoID
        let workerResponse: Melix_Worker_V1_GetHubModelCardResponse
        do {
            workerResponse = try await workerClient.getHubModelCard(request: workerRequest)
        } catch {
            throw BenchmarkTargetResolutionError(
                code: "unavailable",
                message: "Hub model card worker request failed: \(error)"
            )
        }

        guard workerResponse.ok else {
            throw BenchmarkTargetResolutionError(
                code: workerResponse.error.code.isEmpty ? "unknown" : workerResponse.error.code,
                message: workerResponse.error.message.isEmpty
                    ? "Hub model card request failed."
                    : workerResponse.error.message
            )
        }
        guard workerResponse.card.mlxCompatible else {
            throw BenchmarkTargetResolutionError(
                code: "unsupported_model_family",
                message: "Hub repo \(repoID) is not MLX-compatible."
            )
        }

        let taskKind = try benchmarkTaskKind(from: workerResponse.card)
        let imported = makeImportedBenchmarkModel(card: workerResponse.card, taskKind: taskKind)
        return await modelCatalog.registerModel(imported, reason: "hub_benchmark_import")
    }

    private func benchmarkTaskKind(
        from card: Melix_Worker_V1_HubModelCard
    ) throws -> BenchmarkTaskKind {
        let pipelineTag = card.pipelineTag.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch pipelineTag {
        case BenchmarkTaskKind.textGeneration.rawValue:
            return .textGeneration
        case BenchmarkTaskKind.imageToText.rawValue:
            return .imageToText
        case BenchmarkTaskKind.imageTextToText.rawValue:
            return .imageTextToText
        case BenchmarkTaskKind.textToImage.rawValue:
            return .textToImage
        case BenchmarkTaskKind.imageTextToImage.rawValue:
            return .imageTextToImage
        default:
            throw BenchmarkTargetResolutionError(
                code: "unsupported_task_family",
                message: "Hub repo \(card.repoID) declares unsupported pipeline_tag=\(card.pipelineTag)."
            )
        }
    }

    private func makeImportedBenchmarkModel(
        card: Melix_Worker_V1_HubModelCard,
        taskKind: BenchmarkTaskKind
    ) -> Melix_Controlplane_V1_ModelSummary {
        let benchmarkTaskKind = inferredBenchmarkTaskKind(for: card, taskKind: taskKind)
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = card.repoID
        model.kind = taskKind.importedModelKind
        model.state = .modelDiscovered
        model.capabilityClass = taskKind.capabilityClass
        model.routeClass = taskKind.routeClass
        model.features = taskKind.features
        model.supportedModalities = taskKind.supportedModalities
        model.supportedTasks = taskKind.supportedTasks
        model.settings.alias = card.modelName.isEmpty ? card.repoID : card.modelName
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.maxContext = taskKind == .textGeneration ? 8192 : 4096
        model.settings.ext["melix.source_kind"] = "hf_repo"
        model.settings.ext["melix.hf_repo_id"] = card.repoID
        model.settings.ext["melix.source_repo"] = card.repoID
        model.settings.ext["melix.task_kind"] = taskKind.rawValue
        if benchmarkTaskKind != taskKind.rawValue {
            model.settings.ext["melix.benchmark.task_kind"] = benchmarkTaskKind
        }
        model.settings.ext["melix.model_path"] = card.repoID
        model.settings.ext["melix.model_revision"] = "main"
        model.settings.ext["melix.tokenizer_hash"] = "hf.\(card.repoID.replacingOccurrences(of: "/", with: "."))"
        model.settings.ext["melix.capability.route_kind"] = WorkerRouteKind(routeClass: taskKind.routeClass)?.rawValue ?? ""
        model.settings.ext["melix.capability.class"] = taskKind.capabilityIdentifier
        model.settings.ext["melix.capability.supported_modalities"] = taskKind.supportedModalities.joined(separator: ",")
        model.settings.ext["melix.capability.supported_tasks"] = taskKind.supportedTasks.joined(separator: ",")
        model.settings.ext["melix.capability.supported_parsers"] = taskKind.supportedParsers.joined(separator: ",")

        switch taskKind {
        case .textGeneration:
            break
        case .imageToText, .imageTextToText:
            let familyID = benchmarkVisionFamilyID(for: card)
            model.settings.ext["vision_family_id"] = familyID
            model.settings.ext["vision_prompt_profile_id"] = familyID == "paligemma-v1"
                ? "paligemma-caption-v1"
                : (familyID == "gemma4-v1" ? "gemma4-chatml-v1" : "llava-chatml-v1")
            model.settings.ext["vision_tokenization_mode"] = familyID == "paligemma-v1" ? "prefix" : "interleaved"
            model.settings.ext["vision_max_images_per_prompt"] = familyID == "paligemma-v1" ? "1" : "8"
            model.settings.ext["vision_supports_tool_calls"] = familyID == "paligemma-v1" ? "false" : "true"
            model.settings.ext["melix.multimodal_adapter_hash"] = "vision-family-\(familyID)"
            model.settings.ext["melix.vlm.backend_id"] = "mlx_vlm"
            if benchmarkTaskKind == BenchmarkTaskKind.textGeneration.rawValue {
                model.settings.ext["melix.vlm.execution_mode"] = "text_backed"
            }
        case .textToImage, .imageTextToImage:
            model.settings.ext["melix.image.backend_id"] = "deterministic"
            model.settings.ext["melix.image.task_kind"] = taskKind.rawValue
        }

        return model
    }

    private func inferredBenchmarkTaskKind(
        for card: Melix_Worker_V1_HubModelCard,
        taskKind: BenchmarkTaskKind
    ) -> String {
        switch taskKind {
        case .imageToText, .imageTextToText:
            let siblingFiles = Set(card.siblingFiles.map { $0.lowercased() })
            let hasMultimodalProcessorFiles =
                siblingFiles.contains("processor_config.json")
                || siblingFiles.contains("preprocessor_config.json")
            if !hasMultimodalProcessorFiles {
                return BenchmarkTaskKind.textGeneration.rawValue
            }
        default:
            break
        }
        return taskKind.rawValue
    }

    private func benchmarkVisionFamilyID(
        for card: Melix_Worker_V1_HubModelCard
    ) -> String {
        let normalizedTags = Set(card.tags.map { $0.lowercased() })
        let normalizedRepoID = card.repoID.lowercased()
        if normalizedTags.contains("gemma4") || normalizedRepoID.contains("gemma-4") {
            return "gemma4-v1"
        }
        if normalizedTags.contains("paligemma") || normalizedRepoID.contains("paligemma") {
            return "paligemma-v1"
        }
        return "llava-v1"
    }

    private func publishBenchProgress(jobID: String, suite: String, pct: Float) async {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "bench.progress"
        event.source = "control-plane"
        event.requestID = jobID
        event.benchProgress = Melix_Controlplane_V1_BenchmarkProgressEvent()
        event.benchProgress.jobID = jobID
        event.benchProgress.suite = suite
        event.benchProgress.pct = Double(pct)
        await eventHub.publish(event)
    }

    private func makeBenchmarkJobSummary(
        jobID: String,
        modelID: String,
        suites: [String],
        parameters: [String: String],
        status: String,
        outputDir: String,
        taskKind: String,
        sourceRepo: String
    ) -> Melix_Controlplane_V1_BenchmarkJobSummary {
        var summary = Melix_Controlplane_V1_BenchmarkJobSummary()
        summary.schemaVersion = "melix.serving_benchmark_job.v1"
        summary.jobID = jobID
        summary.modelID = modelID.isEmpty ? "melix-dev-text" : modelID
        summary.suites = suites
        summary.parameters = parameters
        summary.status = status
        summary.outputDir = outputDir
        summary.taskKind = taskKind
        summary.sourceRepo = sourceRepo
        summary.benchmarkMode = "standard"
        return summary
    }

    private func makeBenchmarkMatrixJobSummary(
        from workerSummary: Melix_Worker_V1_BenchmarkMatrixJobSummary
    ) -> Melix_Controlplane_V1_BenchmarkMatrixJobSummary {
        var summary = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
        summary.schemaVersion = workerSummary.schemaVersion
        summary.jobID = workerSummary.jobID
        summary.modelID = workerSummary.modelID
        summary.taskKind = workerSummary.taskKind
        summary.sourceRepo = workerSummary.sourceRepo
        summary.suiteIds = workerSummary.suiteIds
        summary.benchmarkMode = workerSummary.benchmarkMode
        summary.status = workerSummary.status
        summary.outputDir = workerSummary.outputDir
        summary.createdAtUnixMs = workerSummary.createdAtUnixMs
        summary.updatedAtUnixMs = workerSummary.updatedAtUnixMs
        return summary
    }

    private func makeBenchmarkMatrixSummaryRow(
        from workerRow: Melix_Worker_V1_BenchmarkMatrixSummaryRow
    ) -> Melix_Controlplane_V1_BenchmarkMatrixSummaryRow {
        var row = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
        row.jobID = workerRow.jobID
        row.taskKind = workerRow.taskKind
        row.sourceRepo = workerRow.sourceRepo
        row.modelID = workerRow.modelID
        row.suiteID = workerRow.suiteID
        row.contextLength = workerRow.contextLength
        row.generationLength = workerRow.generationLength
        row.batchSize = workerRow.batchSize
        row.cacheProfile = workerRow.cacheProfile
        row.reasoningMode = workerRow.reasoningMode
        row.structuredOutputMode = workerRow.structuredOutputMode
        row.concurrencyLevel = workerRow.concurrencyLevel
        row.repeats = workerRow.repeats
        row.requests = workerRow.requests
        row.durationSeconds = workerRow.durationSeconds
        row.ttftMeanMs = workerRow.ttftMeanMs
        row.ttftStdMs = workerRow.ttftStdMs
        row.requestLatencyMeanMs = workerRow.requestLatencyMeanMs
        row.requestLatencyStdMs = workerRow.requestLatencyStdMs
        row.prefillTokensPerSecondMean = workerRow.prefillTokensPerSecondMean
        row.decodeTokensPerSecondMean = workerRow.decodeTokensPerSecondMean
        row.throughputRequestsPerSecond = workerRow.throughputRequestsPerSecond
        row.throughputTokensPerSecond = workerRow.throughputTokensPerSecond
        row.successRate = workerRow.successRate
        row.peakMemoryBytesMax = workerRow.peakMemoryBytesMax
        row.queueWaitMeanMs = workerRow.queueWaitMeanMs
        row.queueWaitP95Ms = workerRow.queueWaitP95Ms
        row.createdAtUnixMs = workerRow.createdAtUnixMs
        return row
    }

    private func makeBenchmarkResultSummaries(
        jobID: String,
        metrics: [String: Double],
        metricUnits: [String: String],
        reportPath: String,
        reportMarkdown: String
    ) -> [Melix_Controlplane_V1_BenchmarkResultSummary] {
        var grouped: [String: [Melix_Controlplane_V1_BenchmarkMetricValue]] = [:]

        for name in metrics.keys.sorted() {
            var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
            metric.name = name
            metric.value = metrics[name] ?? 0
            metric.unit = metricUnits[name] ?? ""
            grouped[benchmarkSuiteName(for: name), default: []].append(metric)
        }

        return grouped.keys.sorted().map { suite in
            var result = Melix_Controlplane_V1_BenchmarkResultSummary()
            result.schemaVersion = "melix.serving_benchmark_result.v1"
            result.jobID = jobID
            result.suite = suite
            result.metrics = grouped[suite] ?? []
            result.reportPath = reportPath
            result.reportMarkdown = reportMarkdown
            return result
        }
    }

    private func makeEvaluationJobSummary(
        from job: Melix_Worker_V1_WorkerEvaluationJob
    ) -> Melix_Controlplane_V1_EvaluationJobSummary {
        var summary = Melix_Controlplane_V1_EvaluationJobSummary()
        summary.schemaVersion = job.schemaVersion
        summary.jobID = job.jobID
        summary.modelID = job.modelID
        summary.suiteID = job.suiteID
        summary.datasetID = job.datasetID
        summary.sampleSize = job.sampleSize
        summary.scoringMode = job.scoringMode
        summary.parameters = job.parameters
        summary.status = job.status
        summary.taskKind = job.taskKind
        summary.sourceRepo = job.sourceRepo
        summary.outputDir = job.outputDir
        summary.createdAtUnixMs = job.createdAtUnixMs
        summary.updatedAtUnixMs = job.updatedAtUnixMs
        return summary
    }

    private func makeEvaluationResultSummary(
        from result: Melix_Worker_V1_WorkerEvaluationResult
    ) -> Melix_Controlplane_V1_EvaluationResultSummary {
        var summary = Melix_Controlplane_V1_EvaluationResultSummary()
        summary.schemaVersion = result.schemaVersion
        summary.jobID = result.jobID
        summary.suiteID = result.suiteID
        summary.datasetID = result.datasetID
        summary.sampleSize = result.sampleSize
        summary.reportPath = result.reportPath
        summary.metrics = result.metrics.map { metric in
            var value = Melix_Controlplane_V1_BenchmarkMetricValue()
            value.name = metric.name
            value.value = metric.value
            value.unit = metric.unit
            return value
        }
        return summary
    }

    private func makeHubSearchResult(
        from response: Melix_Worker_V1_SearchHubModelsResponse
    ) -> Melix_Controlplane_V1_HubSearchResult {
        var result = Melix_Controlplane_V1_HubSearchResult()
        result.nextCursor = response.nextCursor
        result.models = response.models.map(makeHubModelSummary)
        return result
    }

    private func makeHubModelSummary(
        from model: Melix_Worker_V1_HubModelSummary
    ) -> Melix_Controlplane_V1_HubModelSummary {
        var summary = Melix_Controlplane_V1_HubModelSummary()
        summary.repoID = model.repoID
        summary.author = model.author
        summary.modelName = model.modelName
        summary.summary = model.summary
        summary.pipelineTag = model.pipelineTag
        summary.tags = model.tags
        summary.downloads = model.downloads
        summary.likes = model.likes
        summary.mlxCompatible = model.mlxCompatible
        summary.libraryName = model.libraryName
        summary.siblingFiles = model.siblingFiles
        summary.lastModified = model.lastModified
        return summary
    }

    private func makeHubModelCard(
        from card: Melix_Worker_V1_HubModelCard
    ) -> Melix_Controlplane_V1_HubModelCard {
        var result = Melix_Controlplane_V1_HubModelCard()
        result.repoID = card.repoID
        result.author = card.author
        result.modelName = card.modelName
        result.summary = card.summary
        result.license = card.license
        result.pipelineTag = card.pipelineTag
        result.tags = card.tags
        result.downloads = card.downloads
        result.likes = card.likes
        result.mlxCompatible = card.mlxCompatible
        result.libraryName = card.libraryName
        result.siblingFiles = card.siblingFiles
        result.baseModels = card.baseModels
        result.lastModified = card.lastModified
        return result
    }

    private func benchmarkSuiteName(for metricName: String) -> String {
        let parts = metricName.split(separator: ".")
        guard parts.count >= 3, parts.first == "bench" else {
            return "summary"
        }
        return String(parts[1])
    }

    private func recordModelOperationMetrics(from manifestJSON: String, operation: String) async {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return
        }

        if operation == "train_lora" {
            if let duration = payload["training_duration_ms"] as? Double {
                await metricsStore.set(duration, forKey: "training.job_duration_ms")
            }
            if let tokensSeen = payload["tokens_seen"] as? Double {
                await metricsStore.set(tokensSeen, forKey: "training.tokens_seen")
            }
            if let lossFinal = payload["loss_final"] as? Double {
                await metricsStore.set(lossFinal, forKey: "training.loss_final")
            }
            if let publish = payload["adapter_publish_ms"] as? Double {
                await metricsStore.set(publish, forKey: "training.adapter_publish_ms")
            }
            return
        }

        if let duration = payload["activation_duration_ms"] as? Double {
            await metricsStore.set(duration, forKey: "activation.job_duration_ms")
        }
    }

    private func registerActivatedDerivedModel(from manifestJSON: String) async {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            (payload["schema_version"] as? String) == "melix.derived_text_model.v1",
            (payload["activation_mode"] as? String) == "fused_derived_model",
            let modelID = payload["derived_model_id"] as? String,
            !modelID.isEmpty,
            let modelPath = payload["derived_model_path"] as? String,
            !modelPath.isEmpty
        else {
            return
        }

        let sourceModelID = (payload["source_model"] as? String) ?? "melix-dev-text"
        let sourceModel = await modelCatalog.model(id: sourceModelID)

        var model = sourceModel ?? ModelCatalog.devTextModel()
        model.modelID = modelID
        model.kind = "text"
        model.state = .modelDiscovered
        model.pinned = false
        model.inflightRequests = 0
        model.estimatedBytes = 0
        model.capabilityClass = .modelCapabilityText
        model.routeClass = .workerRouteSwiftText
        model.supportedModalities = ["text"]
        model.supportedTasks = ["generate"]
        if let sourceModel {
            model.features = sourceModel.features
            model.maxContext = sourceModel.maxContext
            model.quantProfileID = sourceModel.quantProfileID
            model.settings = sourceModel.settings
        } else {
            model.features = ["chat"]
            model.maxContext = 8192
            model.quantProfileID = "q4"
        }

        let adapterName = (payload["adapter_name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        model.settings.alias = adapterName.isEmpty ? modelID : "\(adapterName) Activated"
        model.settings.pinOnLoad = false
        model.settings.ext["melix.model_path"] = modelPath
        model.settings.ext["melix.model_revision"] = (payload["source_model_revision"] as? String) ?? "derived"
        model.settings.ext["melix.parser_mode"] = "text"
        model.settings.ext["melix.reasoning_mode"] = "off"
        model.settings.ext["melix.derived_from_adapter"] = "true"
        model.settings.ext["melix.derived_from_model_id"] = sourceModelID
        model.settings.ext["melix.derived_from_model_revision"] = (payload["source_model_revision"] as? String) ?? ""
        model.settings.ext["melix.activation_mode"] = "fused_derived_model"
        if let adapterSetHash = payload["adapter_set_hash"] as? String, !adapterSetHash.isEmpty {
            model.settings.ext["melix.adapter_set_hash"] = adapterSetHash
        }

        _ = await modelCatalog.registerModel(model, reason: "adapter_activation")
    }

    private func memoryPolicy(for rawValue: String) -> Melix_Controlplane_V1_MemoryResidencyPolicy {
        switch rawValue.lowercased() {
        case "pinned":
            return .memoryResidencyPinned
        case "ttl":
            return .memoryResidencyTtl
        default:
            return .memoryResidencyEvictable
        }
    }

    private func accelerationMode(for rawValue: String) -> Melix_Controlplane_V1_AccelerationMode {
        switch rawValue.lowercased() {
        case "speculative_decode":
            return .speculativeDecode
        case "accelerated_prefill":
            return .acceleratedPrefill
        case "sparse_prefill":
            return .sparsePrefill
        case "active_kv_quantized":
            return .activeKvQuantized
        default:
            return .baseline
        }
    }

    private func makeErrorStatus(
        from workerError: Melix_Worker_V1_ErrorStatus
    ) -> Melix_Controlplane_V1_ErrorStatus {
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = workerError.code
        error.message = workerError.message
        error.retriable = workerError.retriable
        error.details = workerError.details
        return error
    }

    private func imageArtifactRef(
        from artifact: Melix_Worker_V1_ImageArtifactMetadata
    ) -> Melix_Controlplane_V1_ImageArtifactRef {
        var ref = Melix_Controlplane_V1_ImageArtifactRef()
        ref.artifactID = artifact.artifactID
        ref.jobID = artifact.jobID
        ref.role = Melix_Controlplane_V1_ImageArtifactRole(rawValue: artifact.role.rawValue) ?? .unspecified
        ref.mimeType = artifact.mimeType
        ref.format = artifact.format
        ref.width = artifact.width
        ref.height = artifact.height
        ref.byteLength = artifact.byteLength
        ref.storageUri = artifact.storageUri
        ref.sha256 = artifact.sha256
        ref.variantIndex = artifact.variantIndex
        ref.ext = artifact.ext
        return ref
    }

    private func controlPlaneImageJob(
        from workerJob: Melix_Worker_V1_ImageJobDescriptor,
        modelID: String
    ) -> Melix_Controlplane_V1_ImageJobSummary {
        var job = Melix_Controlplane_V1_ImageJobSummary()
        job.jobID = workerJob.jobID
        job.requestID = workerJob.requestID
        job.modelID = modelID
        job.operation = workerJob.operation
        job.state = Melix_Controlplane_V1_ImageJobState(rawValue: workerJob.state.rawValue) ?? .unspecified
        job.workerID = workerJob.modelHandle
        job.progress.stage = workerJob.progress.stage
        job.progress.pct = workerJob.progress.pct
        job.progress.completedSteps = workerJob.progress.completedSteps
        job.progress.totalSteps = workerJob.progress.totalSteps
        job.artifacts = workerJob.artifacts.map(imageArtifactRef(from:))
        job.error = controlPlaneError(from: workerJob.error)
        job.cancelable = workerJob.cancelable
        job.createdAtUnixMs = workerJob.createdAtUnixMs
        job.updatedAtUnixMs = workerJob.updatedAtUnixMs
        return job
    }

    private func controlPlaneError(from workerError: Melix_Worker_V1_ErrorStatus) -> Melix_Controlplane_V1_ErrorStatus {
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = workerError.code
        error.message = workerError.message
        error.retriable = workerError.retriable
        error.details = workerError.details
        return error
    }

    private func controlPlaneError(code: String, message: String) -> Melix_Controlplane_V1_ErrorStatus {
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = code
        error.message = message
        return error
    }

    private func imageJobPhase(
        for workerJob: Melix_Worker_V1_ImageJobDescriptor,
        error: Melix_Worker_V1_ErrorStatus
    ) -> Melix_Controlplane_V1_RequestPhase {
        if error.code == "cancelled" || workerJob.state == .imageJobCanceled {
            return .requestAborted
        }
        if !error.code.isEmpty {
            return .requestFailed
        }

        switch workerJob.state {
        case .imageJobCompleted:
            return .requestCompleted
        case .imageJobFailed:
            return .requestFailed
        default:
            return .requestFailed
        }
    }

    private func recordImageJobTerminalState(
        jobID: String,
        workerJob: Melix_Worker_V1_ImageJobDescriptor,
        artifacts: [Melix_Controlplane_V1_ImageArtifactRef],
        fallbackError: Melix_Worker_V1_ErrorStatus
    ) async {
        let resolvedError = if !workerJob.error.code.isEmpty {
            controlPlaneError(from: workerJob.error)
        } else {
            controlPlaneError(from: fallbackError)
        }

        switch workerJob.state {
        case .imageJobCompleted:
            await imageJobReadModel.recordCompleted(jobID: jobID, artifacts: artifacts)
        case .imageJobCanceled:
            await imageJobReadModel.recordCanceled(jobID: jobID)
        case .imageJobFailed, .unspecified:
            await imageJobReadModel.recordFailed(jobID: jobID, error: resolvedError)
        default:
            await imageJobReadModel.recordFailed(
                jobID: jobID,
                error: resolvedError.code.isEmpty
                    ? controlPlaneError(code: "runtime_error", message: "Image job finished in an invalid state.")
                    : resolvedError
            )
        }
    }

    private func okResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest,
        server: Melix_Controlplane_V1_ServerReply? = nil,
        model: Melix_Controlplane_V1_ModelReply? = nil,
        cache: Melix_Controlplane_V1_CacheReply? = nil,
        session: Melix_Controlplane_V1_SessionReply? = nil,
        ops: Melix_Controlplane_V1_OpsReply? = nil,
        image: Melix_Controlplane_V1_ImageReply? = nil
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        var response = baseResponse(for: request)
        response.ok = true

        if let server {
            response.server = server
        } else if let model {
            response.model = model
        } else if let cache {
            response.cache = cache
        } else if let session {
            response.session = session
        } else if let ops {
            response.ops = ops
        } else if let image {
            response.image = image
        }

        return response
    }

    private func errorResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest,
        code: String,
        message: String,
        ops: Melix_Controlplane_V1_OpsReply? = nil
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        var response = baseResponse(for: request)
        response.ok = false
        response.error = Melix_Controlplane_V1_ErrorStatus()
        response.error.code = code
        response.error.message = message
        if let ops {
            response.ops = ops
        }
        return response
    }

    private func errorResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest,
        error: Melix_Controlplane_V1_ErrorStatus
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        var response = baseResponse(for: request)
        response.ok = false
        response.error = error
        return response
    }

    private func baseResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.requestID = request.requestID
        response.commandType = request.commandType
        response.correlationID = request.correlationID
        response.causationID = request.causationID
        return response
    }

    private func publishModelStateChanged(_ model: Melix_Controlplane_V1_ModelSummary) async {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.source = "model_catalog"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = model.modelID
        event.modelState.state = model.state
        await eventHub.publish(event)
    }

    private func handleModelLoad(
        modelID: String,
        reason: String
    ) async -> ModelLoadOutcome {
        let preparedModelSpec = await modelCatalog.model(id: modelID).flatMap(BootstrapWorkerPreparation.modelSpec(for:))
        let hydratedPreparedModelSpec = hydratedModel(await modelCatalog.model(id: modelID))
            .flatMap(BootstrapWorkerPreparation.modelSpec(for:))
        guard let workerRegistry,
              let modelSpec = hydratedPreparedModelSpec ?? preparedModelSpec,
              let workerClient = await workerRegistry.client(forModelID: modelID) else {
            let model = await modelCatalog.recordLoadSucceeded(
                id: modelID,
                dispatchHandle: "\(modelID)::local",
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return ModelLoadOutcome(model: hydrate(model), error: nil)
        }

        var workerRequest = Melix_Worker_V1_LoadModelRequest()
        workerRequest.model = modelSpec
        workerRequest.memoryBudgetBytes = 0
        workerRequest.pinOnLoad = false
        workerRequest.warmupAfterLoad = false

        do {
            let response = try await workerClient.loadModel(request: workerRequest)
            guard response.ok, !response.modelHandle.isEmpty else {
                let explicitError = response.error.code.isEmpty ? nil : makeErrorStatus(from: response.error)
                let failureReason = explicitError.map { "\(reason)_\(sanitizeTransitionReasonComponent($0.code))" } ?? "\(reason)_failed"
                let model = await modelCatalog.recordLoadFailed(
                    id: modelID,
                    reason: failureReason
                ) ?? Melix_Controlplane_V1_ModelSummary()
                return ModelLoadOutcome(model: hydrate(model), error: explicitError)
            }
            let model = await modelCatalog.recordLoadSucceeded(
                id: modelID,
                dispatchHandle: response.modelHandle,
                pinRequested: workerRequest.pinOnLoad,
                workerResidency: response.hasResidency ? response.residency : nil,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return ModelLoadOutcome(model: hydrate(model), error: nil)
        } catch {
            let model = await modelCatalog.recordLoadFailed(
                id: modelID,
                reason: "\(reason)_failed"
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return ModelLoadOutcome(model: hydrate(model), error: nil)
        }
    }

    private func sanitizeTransitionReasonComponent(_ rawCode: String) -> String {
        let lowered = rawCode.lowercased()
        return String(lowered.map { character in
            switch character {
            case "a"..."z", "0"..."9", "_":
                return character
            default:
                return "_"
            }
        })
    }

    private func handleModelUnload(
        modelID: String,
        reason: String
    ) async -> Melix_Controlplane_V1_ModelSummary {
        guard let workerRegistry,
              let handle = await modelCatalog.storedDispatchHandle(for: modelID),
              let workerClient = await workerRegistry.client(forModelID: modelID) else {
            let unloaded = await modelCatalog.recordUnloadSucceeded(
                id: modelID,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return hydrate(unloaded)
        }

        var workerRequest = Melix_Worker_V1_UnloadModelRequest()
        workerRequest.modelHandle = handle

        do {
            let response = try await workerClient.unloadModel(request: workerRequest)
            guard response.ok else {
                let failed = await modelCatalog.recordUnloadFailed(
                    id: modelID,
                    reason: reason
                ) ?? Melix_Controlplane_V1_ModelSummary()
                return hydrate(failed)
            }
            let unloaded = await modelCatalog.recordUnloadSucceeded(
                id: modelID,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return hydrate(unloaded)
        } catch {
            let failed = await modelCatalog.recordUnloadFailed(
                id: modelID,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return hydrate(failed)
        }
    }

    private func hydrate(_ model: Melix_Controlplane_V1_ModelSummary) -> Melix_Controlplane_V1_ModelSummary {
        audioAssetManager.hydrate(model)
    }

    private func hydratedModel(
        _ model: Melix_Controlplane_V1_ModelSummary?
    ) -> Melix_Controlplane_V1_ModelSummary? {
        model.map(hydrate)
    }

    private func hydratedModels(
        _ models: [Melix_Controlplane_V1_ModelSummary]
    ) -> [Melix_Controlplane_V1_ModelSummary] {
        models.map(hydrate)
    }

    private func performEvictionsForLoad(targetModelID: String) async {
        let plan = await modelCatalog.evictionPlanForLoad(id: targetModelID)
        await recordEvictionPlanMetrics(plan)

        for decision in plan.decisions {
            await metricsStore.increment("control_plane.model_eviction_decision_count")
            await metricsStore.increment(evictionMetricKey(for: decision.reason))

            guard let evicting = await modelCatalog.beginUnload(id: decision.modelID, reason: decision.reason) else {
                await metricsStore.increment("control_plane.model_eviction_failure_count")
                continue
            }
            if workerRegistry != nil {
                await publishModelStateChanged(evicting)
            }

            let unloaded = await handleModelUnload(modelID: decision.modelID, reason: decision.reason)
            if workerRegistry != nil {
                await publishModelStateChanged(unloaded)
            }

            if unloaded.state == .modelUnloaded {
                await metricsStore.increment("control_plane.model_eviction_success_count")
            } else {
                await metricsStore.increment("control_plane.model_eviction_failure_count")
            }
        }
    }

    private func recordEvictionPlanMetrics(
        _ plan: ModelCatalog.EvictionPlan
    ) async {
        await metricsStore.set(
            Double(plan.decisions.count),
            forKey: "control_plane.model_eviction_last_plan_size"
        )
        await metricsStore.set(
            Double(plan.pinnedProtectedModelIDs.count),
            forKey: "control_plane.model_eviction_last_pinned_protected_count"
        )
        if !plan.decisions.isEmpty || !plan.pinnedProtectedModelIDs.isEmpty {
            await metricsStore.increment("control_plane.model_eviction_plan_count")
        }
        if !plan.pinnedProtectedModelIDs.isEmpty {
            await metricsStore.increment(
                "control_plane.model_eviction_pinned_protected_count",
                by: Double(plan.pinnedProtectedModelIDs.count)
            )
        }
    }

    func evictionMetricKey(for reason: String) -> String {
        switch reason {
        case "ttl_expired":
            return "control_plane.model_eviction_ttl_count"
        case "lru_same_capability":
            return "control_plane.model_eviction_lru_same_capability_count"
        default:
            return "control_plane.model_eviction_other_count"
        }
    }

    private func publishSessionStateChanged(_ session: Melix_Controlplane_V1_SessionState) async {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "session.state_changed"
        event.source = "session_graph"
        event.sessionState = Melix_Controlplane_V1_SessionStateChanged()
        event.sessionState.state = session
        await eventHub.publish(event)
    }

    private func sessionErrorResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest,
        error: Error
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        switch error {
        case SessionGraphStoreError.unknownSessionID:
            return errorResponse(for: request, code: "not_found", message: "Unknown session ID.")
        case SessionGraphStoreError.unknownBranchID:
            return errorResponse(for: request, code: "not_found", message: "Unknown branch ID.")
        default:
            return errorResponse(for: request, code: "internal", message: "Failed to mutate session state.")
        }
    }
}
