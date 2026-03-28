import Foundation

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

actor FakeControlPlaneXPCClient: ControlPlaneXPCClient {
    private let stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    private let continuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation

    private(set) var recordedActions: [String] = []
    private(set) var handshakeCount = 0
    private var modelState: Melix_Controlplane_V1_ModelState = .modelDiscovered
    private var handshakeError: Error?
    private var loadError: Error?
    private var unloadError: Error?
    private var snapshotError: Error?
    private var modelSettingsError: Error?
    private var modelInfoError: Error?
    private var modelOperationError: Error?
    private var chatError: Error?
    private var snapshotOverride: Melix_Controlplane_V1_ServerSnapshot?
    private var responseFeatures: [String] = ["chat"]
    private var modelSettings = FakeControlPlaneXPCClient.defaultModelSettings()
    private var modelInfoResponse = FakeControlPlaneXPCClient.defaultModelInfo()
    private var modelOperationResponse = FakeControlPlaneXPCClient.defaultModelOperation()
    private var chatEvents = FakeControlPlaneXPCClient.defaultChatEvents()

    init() {
        var capturedContinuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation?
        stream = AsyncStream { continuation in
            capturedContinuation = continuation
        }
        continuation = capturedContinuation!
    }

    func configureErrors(
        handshake: Error? = nil,
        load: Error? = nil,
        unload: Error? = nil,
        snapshot: Error? = nil,
        modelSettings: Error? = nil,
        modelInfo: Error? = nil,
        modelOperation: Error? = nil,
        chat: Error? = nil
    ) {
        handshakeError = handshake
        loadError = load
        unloadError = unload
        snapshotError = snapshot
        modelSettingsError = modelSettings
        modelInfoError = modelInfo
        modelOperationError = modelOperation
        chatError = chat
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

    func configureChatEvents(_ events: [ControlPlaneChatStreamEvent]) {
        chatEvents = events
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
        response.features = ["xpc", "models", "metrics", "cache-metadata", "session-graph"]
        response.snapshot = makeSnapshot(state: modelState)
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return stream
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
        var response = modelOperationResponse
        response.operation = operation
        if !outputDir.isEmpty {
            response.outputPath = outputDir + "/" + operation + ".artifact"
        }
        if !weightQuant.isEmpty || !kvQuant.isEmpty || !ext.isEmpty {
            response.stage = response.stage.isEmpty ? "write_artifact" : response.stage
        }
        return response
    }

    func sendModelStateChanged(state: Melix_Controlplane_V1_ModelState) {
        modelState = state
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = "melix-dev-text"
        event.modelState.state = state
        continuation.yield(event)
    }

    func sendLog(level: String, message: String) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "log"
        event.log = Melix_Controlplane_V1_LogEvent()
        event.log.level = level
        event.log.message = message
        continuation.yield(event)
    }

    func sendServerStateChanged(state: Melix_Controlplane_V1_ServerState) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "server.state_changed"
        event.serverState = Melix_Controlplane_V1_ServerStateChanged()
        event.serverState.state = state
        continuation.yield(event)
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
        continuation.yield(event)
    }

    func sendCacheStats(l1Bytes: UInt64, l2Bytes: UInt64) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "cache.stats"
        event.cacheStats = Melix_Controlplane_V1_CacheStatsEvent()
        event.cacheStats.summary.l1Bytes = l1Bytes
        event.cacheStats.summary.l2Bytes = l2Bytes
        continuation.yield(event)
    }

    func sendResourcePressure(scope: String, usedBytes: UInt64, totalBytes: UInt64) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "resource.pressure"
        event.resourcePressure = Melix_Controlplane_V1_ResourcePressureEvent()
        event.resourcePressure.scope = scope
        event.resourcePressure.resources.memoryUsedBytes = usedBytes
        event.resourcePressure.resources.memoryTotalBytes = totalBytes
        continuation.yield(event)
    }

    func sendRequestProgress(requestID: String, phase: Melix_Controlplane_V1_RequestPhase) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "request.progress"
        event.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        event.requestProgress.requestID = requestID
        event.requestProgress.phase = phase
        continuation.yield(event)
    }

    func sendHeartbeat() {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "heartbeat"
        event.heartbeat = Melix_Controlplane_V1_Heartbeat()
        continuation.yield(event)
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
}

struct MenuBarTestError: Error, CustomStringConvertible {
    let description: String
}
