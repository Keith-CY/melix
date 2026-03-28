import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

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
    private let workerRegistry: WorkerRegistry?
    private let requestCoordinator: RequestCoordinator?
    private let chatTranslator: ChatRequestTranslator

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
        workerRegistry: WorkerRegistry? = nil,
        requestCoordinator: RequestCoordinator? = nil,
        chatTranslator: ChatRequestTranslator = ChatRequestTranslator()
    ) {
        let resolvedSchedulerReadModel = schedulerReadModel ?? SchedulerReadModel(
            metricsStore: metricsStore,
            eventPublisher: { event in
                await eventHub.publish(event)
            }
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
        self.workerRegistry = workerRegistry
        self.schedulerReadModel = resolvedSchedulerReadModel
        self.requestCoordinator = requestCoordinator ?? workerRegistry.map { registry in
            RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                schedulerReadModel: resolvedSchedulerReadModel,
                metricsStore: metricsStore,
                sessionGraphStore: sessionGraphStore,
                cacheMetadataStore: cacheMetadataStore
            )
        }
        self.chatTranslator = chatTranslator
    }

    public func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = request.protocolVersion
        response.serverVersion = serverVersion
        response.daemonInstanceID = daemonInstanceID
        response.features = ["xpc", "models", "metrics", "cache-metadata", "session-graph"]
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

        let normalized = chatTranslator.normalize(
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
        guard let modelHandle = await modelCatalog.dispatchHandle(for: normalized.model) else {
            throw ControlPlaneChatExecutionError.unavailable
        }
        let translated = try chatTranslator.translate(normalized, modelHandle: modelHandle)
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
            var reply = Melix_Controlplane_V1_ModelReply()
            reply.models = await modelCatalog.listModels()
            return okResponse(for: request, model: reply)
        case .load(let load):
            guard let model = await modelCatalog.loadModel(id: load.modelID) else {
                return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
            }
            await publishModelStateChanged(model)
            var reply = Melix_Controlplane_V1_ModelReply()
            reply.model = model
            reply.models = await modelCatalog.listModels()
            return okResponse(for: request, model: reply)
        case .unload(let unload):
            guard let model = await modelCatalog.unloadModel(id: unload.modelID) else {
                return errorResponse(for: request, code: "not_found", message: "Unknown model ID.")
            }
            await publishModelStateChanged(model)
            var reply = Melix_Controlplane_V1_ModelReply()
            reply.model = model
            reply.models = await modelCatalog.listModels()
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
        default:
            return errorResponse(
                for: request,
                code: "unimplemented",
                message: "Ops command is not implemented in the phase-0 control plane."
            )
        }
    }

    private func buildSnapshot() async -> Melix_Controlplane_V1_ServerSnapshot {
        let models = await modelCatalog.listModels()
        let metrics = await metricsStore.snapshot()
        let queues = await schedulerReadModel.snapshot()
        let cache = await cacheMetadataStore.cacheSummary()
        let sessions = await sessionGraphStore.sessionSummaries()
        return snapshotBuilder.build(
            models: models,
            metrics: metrics,
            queues: queues,
            cache: cache,
            sessions: sessions
        )
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
                case .completed(let completed):
                    operation.outputPath = completed.outputPath
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
                return errorResponse(
                    for: request,
                    code: operation.error.code.isEmpty ? "unknown" : operation.error.code,
                    message: operation.error.message.isEmpty ? "Model operation failed." : operation.error.message
                )
            }

            var reply = Melix_Controlplane_V1_ModelReply()
            reply.operation = operation
            return okResponse(for: request, model: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Model operation worker request failed: \(error)")
        }
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

    private func okResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest,
        server: Melix_Controlplane_V1_ServerReply? = nil,
        model: Melix_Controlplane_V1_ModelReply? = nil,
        cache: Melix_Controlplane_V1_CacheReply? = nil,
        session: Melix_Controlplane_V1_SessionReply? = nil,
        ops: Melix_Controlplane_V1_OpsReply? = nil
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
        }

        return response
    }

    private func errorResponse(
        for request: Melix_Controlplane_V1_ControlPlaneRequest,
        code: String,
        message: String
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        var response = baseResponse(for: request)
        response.ok = false
        response.error = Melix_Controlplane_V1_ErrorStatus()
        response.error.code = code
        response.error.message = message
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
