import Foundation

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

enum MenuBarTestEnvironment {
    static var isHeadlessCI: Bool {
        let environment = ProcessInfo.processInfo.environment
        return environment["GITHUB_ACTIONS"] == "true" || environment["CI"] == "true"
    }
}

actor FakeControlPlaneXPCClient: ControlPlaneXPCClient {
    private var streamContinuations: [AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation] = []
    private var nextEventSequence: UInt64 = 1

    private(set) var recordedActions: [String] = []
    private(set) var handshakeCount = 0
    private(set) var subscriptionRequests: [UInt64] = []
    private var modelState: Melix_Controlplane_V1_ModelState = .modelDiscovered
    private var handshakeError: Error?
    private var loadError: Error?
    private var unloadError: Error?
    private var snapshotError: Error?
    private var modelSettingsError: Error?
    private var modelInfoError: Error?
    private var modelOperationError: Error?
    private var doctorError: Error?
    private var benchError: Error?
    private var chatError: Error?
    private var imageGenerateError: Error?
    private var imageEditError: Error?
    private var cancelError: Error?
    private var snapshotOverride: Melix_Controlplane_V1_ServerSnapshot?
    private var responseFeatures: [String] = ["chat"]
    private var modelSettings = FakeControlPlaneXPCClient.defaultModelSettings()
    private var modelInfoResponse = FakeControlPlaneXPCClient.defaultModelInfo()
    private var modelOperationResponse = FakeControlPlaneXPCClient.defaultModelOperation()
    private var modelOperationResponsesByName: [String: Melix_Controlplane_V1_ModelOperationResult] = [:]
    private var doctorResponse = "# Melix Doctor\n\n- worker_state: idle\n"
    private var benchResponse = ControlPlaneBenchResult(
        reportPath: "/tmp/melix-fake/bench-report.md",
        reportMarkdown: "# Melix Bench\n\n- bench.smoke.ttft_ms: 24.45 ms\n",
        metrics: ["bench.smoke.ttft_ms": 24.45]
    )
    private var chatEvents = FakeControlPlaneXPCClient.defaultChatEvents()
    private var imageGenerateResponse = makeMenuBarImageJobSummary(
        jobID: "image-generate-1::image-generate",
        requestID: "image-generate-1",
        modelID: "melix-dev-image",
        operation: "image_generate"
    )
    private var imageEditResponse = makeMenuBarImageJobSummary(
        jobID: "image-edit-1::image-edit",
        requestID: "image-edit-1",
        modelID: "melix-dev-image",
        operation: "image_edit"
    )

    init() {}

    func configureErrors(
        handshake: Error? = nil,
        load: Error? = nil,
        unload: Error? = nil,
        snapshot: Error? = nil,
        modelSettings: Error? = nil,
        modelInfo: Error? = nil,
        modelOperation: Error? = nil,
        doctor: Error? = nil,
        bench: Error? = nil,
        chat: Error? = nil,
        imageGenerate: Error? = nil,
        imageEdit: Error? = nil,
        cancel: Error? = nil
    ) {
        handshakeError = handshake
        loadError = load
        unloadError = unload
        snapshotError = snapshot
        modelSettingsError = modelSettings
        modelInfoError = modelInfo
        modelOperationError = modelOperation
        doctorError = doctor
        benchError = bench
        chatError = chat
        imageGenerateError = imageGenerate
        imageEditError = imageEdit
        cancelError = cancel
    }

    func configureModelResponseFeatures(_ features: [String]) {
        responseFeatures = features
    }

    func configureModelInfo(_ info: Melix_Controlplane_V1_ModelInfo) {
        modelInfoResponse = info
    }

    func configureModelOperation(_ operation: Melix_Controlplane_V1_ModelOperationResult) {
        modelOperationResponse = operation
    }

    func configureModelOperation(
        _ operation: Melix_Controlplane_V1_ModelOperationResult,
        forNamedOperation operationName: String
    ) {
        modelOperationResponsesByName[operationName] = operation
    }

    func configureDoctorResponse(_ markdown: String) {
        doctorResponse = markdown
    }

    func configureBenchResponse(_ result: ControlPlaneBenchResult) {
        benchResponse = result
    }

    func configureChatEvents(_ events: [ControlPlaneChatStreamEvent]) {
        chatEvents = events
    }

    func configureImageResponses(
        generation: Melix_Controlplane_V1_ImageJobSummary? = nil,
        edit: Melix_Controlplane_V1_ImageJobSummary? = nil
    ) {
        if let generation {
            imageGenerateResponse = generation
        }
        if let edit {
            imageEditResponse = edit
        }
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        handshakeCount += 1
        if let handshakeError {
            throw handshakeError
        }

        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-1"
        response.features = ["xpc", "models", "metrics", "cache-metadata", "session-graph", "image-jobs"]
        response.snapshot = makeSnapshot(state: modelState)
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        subscriptionRequests.append(lastSeenSeq)
        return AsyncStream { continuation in
            streamContinuations.append(continuation)
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        recordedActions.append("chat:\(request.modelID)")
        if let chatError {
            throw chatError
        }
        let events = chatEvents
        return ControlPlaneChatExecution(
            requestID: "chat-request-1",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                for event in events {
                    continuation.yield(event)
                }
                continuation.finish()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("snapshot")
        if let snapshotError {
            throw snapshotError
        }
        return makeSnapshot(state: modelState)
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("load:\(modelID)")
        if let loadError {
            throw loadError
        }

        modelState = .modelWarm
        return makeModelSummary(state: modelState)
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("unload:\(modelID)")
        if let unloadError {
            throw unloadError
        }

        modelState = .modelUnloaded
        return makeModelSummary(state: modelState)
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("settings:\(modelID)")
        if let modelSettingsError {
            throw modelSettingsError
        }
        if let alias = values["alias"] {
            modelSettings.alias = alias
        }
        if let typeOverride = values["type_override"] {
            modelSettings.typeOverride = typeOverride
        }
        if let ttl = values["ttl_seconds"], let ttlSeconds = UInt32(ttl) {
            modelSettings.ttlSeconds = ttlSeconds
        }
        if let pinOnLoad = values["pin_on_load"] {
            modelSettings.pinOnLoad = ["1", "true", "yes", "on"].contains(pinOnLoad.lowercased())
        }
        if let memoryPolicy = values["memory_policy"] {
            modelSettings.memoryPolicy = switch memoryPolicy.lowercased() {
            case "pinned": .memoryResidencyPinned
            case "ttl": .memoryResidencyTtl
            default: .memoryResidencyEvictable
            }
        }
        if let accelerationMode = values["default_acceleration_mode"] {
            modelSettings.defaultAccelerationMode = switch accelerationMode.lowercased() {
            case "speculative_decode": .speculativeDecode
            case "accelerated_prefill": .acceleratedPrefill
            case "active_kv_quantized": .activeKvQuantized
            default: .baseline
            }
        }
        if let profileID = values["acceleration_profile_id"] {
            modelSettings.accelerationProfileID = profileID
        }
        return makeModelSummary(state: modelState)
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        recordedActions.append("info:\(modelID)")
        if let modelInfoError {
            throw modelInfoError
        }
        return modelInfoResponse
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        recordedActions.append("operation:\(operation):\(modelID)")
        if let modelOperationError {
            throw modelOperationError
        }
        let hasNamedOverride = modelOperationResponsesByName[operation] != nil
        var response = modelOperationResponsesByName[operation] ?? modelOperationResponse
        response.operation = operation
        if !hasNamedOverride, !outputDir.isEmpty {
            response.outputPath = outputDir + "/" + operation + ".artifact"
        }
        if !weightQuant.isEmpty || !kvQuant.isEmpty || !ext.isEmpty {
            response.stage = response.stage.isEmpty ? "write_artifact" : response.stage
        }
        return response
    }

    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        recordedActions.append("image.generate:\(request.modelID)")
        if let imageGenerateError {
            throw imageGenerateError
        }
        var response = imageGenerateResponse
        response.modelID = request.modelID
        if response.requestID.isEmpty {
            response.requestID = "image-generate-1"
        }
        return response
    }

    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        recordedActions.append("image.edit:\(request.modelID)")
        if let imageEditError {
            throw imageEditError
        }
        var response = imageEditResponse
        response.modelID = request.modelID
        if response.requestID.isEmpty {
            response.requestID = "image-edit-1"
        }
        return response
    }

    func cancelRequest(requestID: String) async throws -> Bool {
        recordedActions.append("cancel:\(requestID)")
        if let cancelError {
            throw cancelError
        }
        return true
    }

    func runDoctor() async throws -> String {
        recordedActions.append("doctor")
        if let doctorError {
            throw doctorError
        }
        return doctorResponse
    }

    func runBench() async throws -> ControlPlaneBenchResult {
        recordedActions.append("bench")
        if let benchError {
            throw benchError
        }
        return benchResponse
    }

    func sendModelStateChanged(state: Melix_Controlplane_V1_ModelState) {
        modelState = state
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = "melix-dev-text"
        event.modelState.state = state
        emit(event)
    }

    func sendLog(level: String, message: String) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "log"
        event.log = Melix_Controlplane_V1_LogEvent()
        event.log.level = level
        event.log.message = message
        emit(event)
    }

    func sendServerStateChanged(state: Melix_Controlplane_V1_ServerState) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "server.state_changed"
        event.serverState = Melix_Controlplane_V1_ServerStateChanged()
        event.serverState.state = state
        emit(event)
    }

    func sendSessionStateChanged(
        sessionID: String,
        branchCount: Int = 1,
        latestRequestID: String = "request-1",
        latestSnapshotID: String = "snapshot-1"
    ) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "session.state_changed"
        event.sessionState = Melix_Controlplane_V1_SessionStateChanged()
        event.sessionState.state.sessionID = sessionID
        event.sessionState.state.activeBranchID = "branch-main"
        event.sessionState.state.latestRequestID = latestRequestID
        event.sessionState.state.latestSnapshotID = latestSnapshotID
        event.sessionState.state.branches = (0..<branchCount).map { index in
            var branch = Melix_Controlplane_V1_BranchState()
            branch.branchID = "branch-\(index)"
            return branch
        }
        emit(event)
    }

    func sendCacheStats(l1Bytes: UInt64, l2Bytes: UInt64) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "cache.stats"
        event.cacheStats = Melix_Controlplane_V1_CacheStatsEvent()
        event.cacheStats.summary.l1Bytes = l1Bytes
        event.cacheStats.summary.l2Bytes = l2Bytes
        emit(event)
    }

    func sendResourcePressure(scope: String, usedBytes: UInt64, totalBytes: UInt64) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "resource.pressure"
        event.resourcePressure = Melix_Controlplane_V1_ResourcePressureEvent()
        event.resourcePressure.scope = scope
        event.resourcePressure.resources.memoryUsedBytes = usedBytes
        event.resourcePressure.resources.memoryTotalBytes = totalBytes
        emit(event)
    }

    func sendRequestProgress(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        prefillProcessedTokens: UInt32 = 0,
        prefillTotalTokens: UInt32 = 0,
        activeRequests: UInt32 = 0,
        waitingRequests: UInt32 = 0,
        restoreStage: String = "",
        cachePressure: Double = 0
    ) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "request.progress"
        event.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        event.requestProgress.requestID = requestID
        event.requestProgress.phase = phase
        event.requestProgress.prefillProcessedTokens = prefillProcessedTokens
        event.requestProgress.prefillTotalTokens = prefillTotalTokens
        event.requestProgress.prefillProgressPct = prefillTotalTokens == 0
            ? 0
            : Double(prefillProcessedTokens) / Double(prefillTotalTokens) * 100
        event.requestProgress.activeRequests = activeRequests
        event.requestProgress.waitingRequests = waitingRequests
        event.requestProgress.restoreStage = restoreStage
        event.requestProgress.cachePressure = cachePressure
        emit(event)
    }

    func sendHeartbeat() {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "heartbeat"
        event.heartbeat = Melix_Controlplane_V1_Heartbeat()
        emit(event)
    }

    func sendImageJobStateChanged(_ job: Melix_Controlplane_V1_ImageJobSummary) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "image.job.state_changed"
        event.imageJob = Melix_Controlplane_V1_ImageJobStateChanged()
        event.imageJob.job = job
        emit(event)
    }

    func finishLatestSubscription() {
        guard let continuation = streamContinuations.last else {
            return
        }
        continuation.finish()
        streamContinuations.removeLast()
    }

    func configureSnapshot(_ snapshot: Melix_Controlplane_V1_ServerSnapshot?) {
        snapshotOverride = snapshot
    }

    func makeSnapshot(state: Melix_Controlplane_V1_ModelState) -> Melix_Controlplane_V1_ServerSnapshot {
        if var snapshotOverride {
            if snapshotOverride.models.isEmpty {
                snapshotOverride.models = [makeModelSummary(state: state)]
            }
            return snapshotOverride
        }

        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeModelSummary(state: state)]
        snapshot.queues = makeQueueSummary()
        snapshot.cache = makeCacheSummary()
        snapshot.metrics = makeMetricsSummary()
        return snapshot
    }

    private func makeModelSummary(
        state: Melix_Controlplane_V1_ModelState
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = state
        model.features = responseFeatures
        model.maxContext = 8192
        model.settings = modelSettings
        return model
    }

    private func makeQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.queuedRequests = 1
        queue.activeRequests = 1
        queue.backpressure = 0.12

        var decode = Melix_Controlplane_V1_QueueLaneSummary()
        decode.laneID = "text.decode.interactive"
        decode.laneClass = "interactive-decode"
        decode.activeRequests = 1
        decode.priorityScore = 100

        var prefill = Melix_Controlplane_V1_QueueLaneSummary()
        prefill.laneID = "text.prefill.hot"
        prefill.laneClass = "hot-prefill"
        prefill.queuedRequests = 1
        prefill.priorityScore = 120

        queue.lanes = [decode, prefill]
        return queue
    }

    private static func defaultChatEvents() -> [ControlPlaneChatStreamEvent] {
        [
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .tokenDelta("Assistant response"),
            .reasoningDelta("Reasoning trace"),
            .toolCallDelta(callID: "tool-1", toolName: "search", argumentsFragment: #"{"q":"melix"}"#),
            .usage(promptTokens: 12, completionTokens: 24),
            .completed(finishReason: "stop", assistantText: "Assistant response", reasoningText: "Reasoning trace"),
        ]
    }

    private func makeCacheSummary() -> Melix_Controlplane_V1_CacheSummary {
        var cache = Melix_Controlplane_V1_CacheSummary()
        cache.l1Bytes = 16 * 1024 * 1024
        cache.l2Bytes = 64 * 1024 * 1024
        cache.l1HitRate = 0.72
        cache.l2HitRate = 0.35
        return cache
    }

    private func makeMetricsSummary() -> Melix_Controlplane_V1_MetricsSummary {
        var metrics = Melix_Controlplane_V1_MetricsSummary()
        metrics.values = [
            "http.translation_ms": 2.4,
            "http.stream_first_event_ms": 18.8,
            "requests.inflight": 1,
        ]
        return metrics
    }

    private static func defaultModelSettings() -> Melix_Controlplane_V1_ModelSettings {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.alias = "Melix Dev Text"
        settings.memoryPolicy = .memoryResidencyEvictable
        settings.defaultAccelerationMode = .baseline
        return settings
    }

    private static func defaultModelInfo() -> Melix_Controlplane_V1_ModelInfo {
        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 8192
        info.supportedParsers = ["text", "json"]
        info.supportedModalities = ["text"]
        return info
    }

    private static func defaultModelOperation() -> Melix_Controlplane_V1_ModelOperationResult {
        var result = Melix_Controlplane_V1_ModelOperationResult()
        result.ok = true
        result.jobID = "job-fake"
        result.stage = "write_artifact"
        result.pct = 0.75
        result.manifestJson = #"{"operation":"quantize"}"#
        result.outputPath = "/tmp/melix-fake/quantize.artifact"
        return result
    }

    private func emit(_ event: Melix_Controlplane_V1_ControlPlaneEvent) {
        guard streamContinuations.isEmpty == false else {
            return
        }
        var sequenced = event
        sequenced.seq = nextEventSequence
        nextEventSequence += 1
        streamContinuations[streamContinuations.count - 1].yield(sequenced)
    }
}

struct MenuBarTestError: Error, CustomStringConvertible {
    let description: String
}

func makeMenuBarImageModelSummary(
    modelID: String = "melix-dev-image",
    state: Melix_Controlplane_V1_ModelState = .modelWarm
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "image"
    model.state = state
    model.features = ["image_generate", "image_edit", "artifact_jobs"]
    model.maxContext = 0
    model.settings.alias = "Melix Dev Image"
    return model
}

func makeMenuBarImageArtifact(
    jobID: String,
    role: Melix_Controlplane_V1_ImageArtifactRole = .imageArtifactGenerated,
    storageURI: String = "/tmp/output.png"
) -> Melix_Controlplane_V1_ImageArtifactRef {
    var artifact = Melix_Controlplane_V1_ImageArtifactRef()
    artifact.artifactID = "\(jobID)::artifact"
    artifact.jobID = jobID
    artifact.role = role
    artifact.mimeType = "image/png"
    artifact.format = "png"
    artifact.width = 512
    artifact.height = 512
    artifact.byteLength = 128
    artifact.storageUri = storageURI
    artifact.sha256 = "sha256-artifact"
    artifact.variantIndex = 0
    return artifact
}

func makeMenuBarImageJobSummary(
    jobID: String,
    requestID: String,
    modelID: String = "melix-dev-image",
    operation: String,
    state: Melix_Controlplane_V1_ImageJobState = .imageJobCompleted,
    artifacts: [Melix_Controlplane_V1_ImageArtifactRef] = []
) -> Melix_Controlplane_V1_ImageJobSummary {
    var job = Melix_Controlplane_V1_ImageJobSummary()
    job.jobID = jobID
    job.requestID = requestID
    job.modelID = modelID
    job.operation = operation
    job.state = state
    job.lane = operation == "image_edit" ? "image.edit.background" : "image.generate.background"
    job.workerID = "python-image-worker"
    job.progress.stage = state == .imageJobCompleted ? "completed" : "running"
    job.progress.pct = state == .imageJobCompleted ? 1 : 0.5
    job.artifacts = artifacts
    job.cancelable = state == .imageJobRunning || state == .imageJobQueued
    job.createdAtUnixMs = 1_710_000_000_000
    job.updatedAtUnixMs = 1_710_000_000_500
    return job
}
