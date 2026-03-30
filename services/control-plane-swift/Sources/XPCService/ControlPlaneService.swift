import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

private struct ModelLoadOutcome {
    let model: Melix_Controlplane_V1_ModelSummary
    let error: Melix_Controlplane_V1_ErrorStatus?
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
        chatTranslator: ChatRequestTranslator = ChatRequestTranslator()
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
    }

    public func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = request.protocolVersion
        response.serverVersion = serverVersion
        response.daemonInstanceID = daemonInstanceID
        response.features = ["xpc", "models", "metrics", "cache-metadata", "session-graph", "image-jobs"]
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
            reply.model = model
            reply.models = await modelCatalog.listModels()
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
        case .runDoctor(let runDoctor):
            return await handleRunDoctor(request: request, command: runDoctor)
        case .runBench(let runBench):
            return await handleRunBench(request: request, command: runBench)
        case .cancelRequest(let cancelRequest):
            return await handleCancelRequest(request: request, command: cancelRequest)
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

    private func handleRunBench(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        command _: Melix_Controlplane_V1_RunBench
    ) async -> Melix_Controlplane_V1_ControlPlaneResponse {
        let startedAt = Date()
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
        }

        var workerRequest = Melix_Worker_V1_RunBenchRequest()
        workerRequest.modelHandle = await preferredModelOperationsHandle()
        workerRequest.suites = ["smoke", "latency"]

        do {
            let stream = try await workerClient.runBench(request: workerRequest)
            var reply = Melix_Controlplane_V1_OpsReply()
            var benchJobID = ""
            var failedError: Melix_Controlplane_V1_ErrorStatus?

            for try await event in stream {
                switch event.payload {
                case .started(let started):
                    benchJobID = started.jobID
                case .progress(let progress):
                    await publishBenchProgress(jobID: benchJobID, suite: progress.suite, pct: progress.pct)
                case .metric(let metric):
                    reply.metrics.values[metric.name] = metric.value
                    await metricsStore.set(metric.value, forKey: metric.name)
                case .completed(let completed):
                    reply.reportPath = completed.reportPath
                    if let markdown = try? String(contentsOfFile: completed.reportPath, encoding: .utf8) {
                        reply.reportMarkdown = markdown
                    }
                case .failed(let failed):
                    failedError = makeErrorStatus(from: failed.error)
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
                    message: failedError.message.isEmpty ? "Bench request failed." : failedError.message
                )
            }

            return okResponse(for: request, ops: reply)
        } catch {
            return errorResponse(for: request, code: "unavailable", message: "Bench worker request failed: \(error)")
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
        let models = await modelCatalog.listModels()
        let metrics = await metricsStore.snapshot()
        let queues = await schedulerReadModel.snapshot()
        let cache = await cacheMetadataStore.cacheSummary()
        let sessions = await sessionGraphStore.sessionSummaries()
        let imageJobs = await imageJobReadModel.snapshot()
        return snapshotBuilder.build(
            models: models,
            metrics: metrics,
            queues: queues,
            cache: cache,
            sessions: sessions,
            imageJobs: imageJobs
        )
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
                    if command.operation == "train_lora" {
                        await recordTrainingMetrics(from: manifest.manifestJson)
                    }
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

    private func recordTrainingMetrics(from manifestJSON: String) async {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return
        }

        if let duration = payload["training_duration_ms"] as? Double {
            await metricsStore.set(duration, forKey: "training.job_duration_ms")
        }
        if let publish = payload["adapter_publish_ms"] as? Double {
            await metricsStore.set(publish, forKey: "training.adapter_publish_ms")
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
        message: String
    ) -> Melix_Controlplane_V1_ControlPlaneResponse {
        var response = baseResponse(for: request)
        response.ok = false
        response.error = Melix_Controlplane_V1_ErrorStatus()
        response.error.code = code
        response.error.message = message
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
        guard let workerRegistry,
              let modelSpec = BootstrapWorkerPreparation.modelSpec(for: modelID),
              let workerClient = await workerRegistry.client(forModelID: modelID) else {
            let model = await modelCatalog.recordLoadSucceeded(
                id: modelID,
                dispatchHandle: "\(modelID)::local",
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return ModelLoadOutcome(model: model, error: nil)
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
                return ModelLoadOutcome(model: model, error: explicitError)
            }
            let model = await modelCatalog.recordLoadSucceeded(
                id: modelID,
                dispatchHandle: response.modelHandle,
                pinRequested: workerRequest.pinOnLoad,
                workerResidency: response.hasResidency ? response.residency : nil,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return ModelLoadOutcome(model: model, error: nil)
        } catch {
            let model = await modelCatalog.recordLoadFailed(
                id: modelID,
                reason: "\(reason)_failed"
            ) ?? Melix_Controlplane_V1_ModelSummary()
            return ModelLoadOutcome(model: model, error: nil)
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
            return await modelCatalog.recordUnloadSucceeded(
                id: modelID,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
        }

        var workerRequest = Melix_Worker_V1_UnloadModelRequest()
        workerRequest.modelHandle = handle

        do {
            let response = try await workerClient.unloadModel(request: workerRequest)
            guard response.ok else {
                return await modelCatalog.recordUnloadFailed(
                    id: modelID,
                    reason: reason
                ) ?? Melix_Controlplane_V1_ModelSummary()
            }
            return await modelCatalog.recordUnloadSucceeded(
                id: modelID,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
        } catch {
            return await modelCatalog.recordUnloadFailed(
                id: modelID,
                reason: reason
            ) ?? Melix_Controlplane_V1_ModelSummary()
        }
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
