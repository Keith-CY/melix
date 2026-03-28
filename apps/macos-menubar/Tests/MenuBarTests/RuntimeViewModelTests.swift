import Foundation
import Testing

@testable import AppMain
import MelixControlPlaneProtocol

@Suite("Runtime View Model")
struct RuntimeViewModelTests {
    @Test("start hydrates the initial snapshot into app state")
    @MainActor
    func startHydratesInitialSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()

        #expect(viewModel.statusTitle == "Melix Ready")
        #expect(viewModel.primaryModel?.modelID == "melix-dev-text")
        #expect(viewModel.primaryModel?.stateText == "Discovered")
        #expect(viewModel.primaryModel?.actionTitle == "Load")
        #expect(await metrics.snapshot()["menu.handshake_ms"] != nil)
        #expect(await metrics.snapshot()["menu.hydration_ms"] != nil)
    }

    @Test("load and unload actions dispatch through the client and refresh app state")
    @MainActor
    func loadAndUnloadDispatchThroughClient() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.loadPrimaryModel()
        #expect(await client.recordedActions == ["load:melix-dev-text"])
        #expect(viewModel.primaryModel?.stateText == "Warm")
        #expect(viewModel.primaryModel?.actionTitle == "Unload")

        await viewModel.unloadPrimaryModel()
        #expect(await client.recordedActions == ["load:melix-dev-text", "unload:melix-dev-text"])
        #expect(viewModel.primaryModel?.stateText == "Unloaded")
        #expect(viewModel.primaryModel?.actionTitle == "Load")
        #expect(await metrics.snapshot()["menu.model_load_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_unload_ms"] != nil)
    }

    @Test("model-state events update runtime state after hydration")
    @MainActor
    func modelStateEventsUpdateRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendModelStateChanged(state: .modelPinned)

        try await Task.sleep(for: .milliseconds(20))

        #expect(viewModel.primaryModel?.stateText == "Pinned")
        #expect(viewModel.primaryModel?.actionTitle == "Unload")
    }

    @Test("start records an error state when handshake fails")
    @MainActor
    func startRecordsHandshakeFailure() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(handshake: MenuBarTestError(description: "handshake failed"))
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.statusTitle == "Melix Error")
        #expect(viewModel.lastError?.contains("handshake failed") == true)
    }

    @Test("load and unload surface client failures in app state")
    @MainActor
    func loadAndUnloadFailuresSurfaceErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(
            load: MenuBarTestError(description: "load failed"),
            unload: MenuBarTestError(description: "unload failed")
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.loadPrimaryModel()
        #expect(viewModel.lastError?.contains("load failed") == true)

        await client.configureErrors(load: nil, unload: MenuBarTestError(description: "unload failed"))
        await viewModel.unloadPrimaryModel()
        #expect(viewModel.lastError?.contains("unload failed") == true)
    }

    @Test("load and unload no-op when there is no primary model")
    @MainActor
    func loadAndUnloadNoopWithoutPrimaryModel() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.loadPrimaryModel()
        await viewModel.unloadPrimaryModel()

        #expect(viewModel.primaryModel == nil)
        #expect(await client.recordedActions.isEmpty)
        #expect(await metrics.snapshot()["menu.model_load_ms"] == nil)
        #expect(await metrics.snapshot()["menu.model_unload_ms"] == nil)
    }

    @Test("snapshot server and model states map to user-facing labels")
    @MainActor
    func snapshotStatesMapToUserFacingLabels() async throws {
        let serverCases: [(Melix_Controlplane_V1_ServerState, String)] = [
            (.serverBooting, "Melix Booting"),
            (.serverDegraded, "Melix Degraded"),
            (.serverDraining, "Melix Draining"),
            (.serverStopped, "Melix Stopped"),
            (.serverFailed, "Melix Failed"),
            (.UNRECOGNIZED(-1), "Melix Unknown"),
        ]

        for (serverState, expectedTitle) in serverCases {
            let client = SnapshotControlPlaneXPCClient(
                snapshot: makeSnapshot(
                    serverState: serverState,
                    models: [makeModelSummary(state: .modelLoading)]
                )
            )
            let viewModel = RuntimeViewModel(client: client)
            await viewModel.start()

            #expect(viewModel.statusTitle == expectedTitle)
            #expect(viewModel.primaryModel?.stateText == "Loading")
            #expect(viewModel.primaryModel?.actionTitle == "Load")
        }

        let failedClient = SnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .modelFailed)]
            )
        )
        let failedViewModel = RuntimeViewModel(client: failedClient)
        await failedViewModel.start()
        #expect(failedViewModel.primaryModel?.stateText == "Failed")

        let unknownClient = SnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .UNRECOGNIZED(-1))]
            )
        )
        let unknownViewModel = RuntimeViewModel(client: unknownClient)
        await unknownViewModel.start()
        #expect(unknownViewModel.primaryModel?.stateText == "Unknown")
    }

    @Test("unknown model events append new models and ignore unrelated payloads")
    @MainActor
    func unknownModelEventsAppendModelsAndIgnoreOtherPayloads() async throws {
        let client = EventingSnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(serverState: .serverReady, models: [])
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendQueueSummary()
        await client.sendModelStateChanged(modelID: "secondary-model", state: .modelWarm)
        try await Task.sleep(for: .milliseconds(20))

        #expect(viewModel.models.count == 1)
        #expect(viewModel.primaryModel?.modelID == "secondary-model")
        #expect(viewModel.primaryModel?.stateText == "Warm")
        #expect(viewModel.primaryModel?.actionTitle == "Unload")
    }

    @Test("runtime model row reports loaded states for warm and pinned models")
    func runtimeModelRowReportsLoadedStates() {
        #expect(makeRuntimeModelRow(state: .modelWarm).isLoaded)
        #expect(makeRuntimeModelRow(state: .modelPinned).isLoaded)
        #expect(makeRuntimeModelRow(state: .modelDiscovered).isLoaded == false)
    }

    @Test("desktop foundation derives dashboard settings bench and api state from control-plane truth")
    @MainActor
    func desktopFoundationDerivesOperatorPanelsFromSnapshotTruth() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        #expect(foundation.title == "Melix Ready")
        #expect(foundation.dashboardCards.contains(where: { $0.id == "server" && $0.value == "Ready" }))
        #expect(foundation.queueLanes.contains(where: { $0.id == "text.decode.interactive" }))
        #expect(foundation.models.contains(where: { $0.modelID == "melix-dev-text" }))
        #expect(foundation.settings.contains(where: { $0.key == "Protocol" && $0.value == "melix.controlplane.v1" }))
        #expect(foundation.benchMetrics.contains(where: { $0.name == "http.translation_ms" }))
        #expect(foundation.apiReference.contains(where: { $0.path == "/v1/responses" }))
    }

    @Test("desktop foundation refresh pulls a fresh server snapshot and records metrics")
    @MainActor
    func desktopFoundationRefreshPullsFreshSnapshotAndRecordsMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await viewModel.start()

        var refreshedSnapshot = makeSnapshot(
            serverState: .serverDegraded,
            models: [makeModelSummary(state: .modelWarm)]
        )
        refreshedSnapshot.sessions = {
            var summary = Melix_Controlplane_V1_SessionSummary()
            summary.sessionID = "session-1"
            summary.activeBranchID = "branch-main"
            summary.branchCount = 1
            return [summary]
        }()
        refreshedSnapshot.metrics.values["http.stream_first_event_ms"] = 12.5
        await client.configureSnapshot(refreshedSnapshot)

        await viewModel.refreshDesktopFoundation()

        let foundation = viewModel.desktopFoundationState
        #expect(viewModel.statusTitle == "Melix Degraded")
        #expect(foundation.dashboardCards.contains(where: { $0.id == "sessions" && $0.value == "1" }))
        #expect(foundation.models.contains(where: { $0.modelID == "melix-dev-text" && $0.stateText == "Warm" }))
        #expect(await metrics.snapshot()["menu.foundation_refresh_ms"] != nil)
        #expect(await client.recordedActions.contains("snapshot"))
    }

    @Test("desktop foundation refresh records local snapshot errors")
    @MainActor
    func desktopFoundationRefreshRecordsSnapshotErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await client.configureErrors(snapshot: MenuBarTestError(description: "snapshot failed"))

        await viewModel.refreshDesktopFoundation()

        let foundation = viewModel.desktopFoundationState
        #expect(viewModel.lastError?.contains("snapshot failed") == true)
        #expect(foundation.logs.first?.message.contains("snapshot failed") == true)
        #expect(await metrics.snapshot()["menu.foundation_refresh_ms"] == nil)
    }

    @Test("event log records streamed control-plane events for the desktop foundation")
    @MainActor
    func eventLogRecordsStreamedControlPlaneEvents() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendLog(level: "warning", message: "queue pressure rising")
        try await Task.sleep(for: .milliseconds(20))

        let foundation = viewModel.desktopFoundationState
        #expect(foundation.logs.contains(where: { $0.message == "queue pressure rising" }))
    }

    @Test("streamed control-plane events update dashboard state")
    @MainActor
    func streamedEventsUpdateDashboardState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendServerStateChanged(state: .serverDraining)
        await client.sendSessionStateChanged(sessionID: "session-42", branchCount: 2)
        await client.sendCacheStats(l1Bytes: 32 * 1024 * 1024, l2Bytes: 128 * 1024 * 1024)
        await client.sendResourcePressure(scope: "metal", usedBytes: 4 * 1024 * 1024 * 1024, totalBytes: 8 * 1024 * 1024 * 1024)
        await client.sendRequestProgress(requestID: "request-42", phase: .requestDecoding)
        await client.sendHeartbeat()
        await client.sendLog(level: "error", message: "thermal pressure")
        try await Task.sleep(for: .milliseconds(30))

        let foundation = viewModel.desktopFoundationState
        #expect(viewModel.statusTitle == "Melix Draining")
        #expect(viewModel.lastError == "thermal pressure")
        #expect(foundation.dashboardCards.contains(where: { $0.id == "sessions" && $0.value == "1" }))
        #expect(foundation.dashboardCards.contains(where: { $0.id == "cache" && $0.detail == "L1 / L2" }))
        #expect(foundation.dashboardCards.contains(where: { $0.id == "memory" && $0.detail.contains("8") }))
        #expect(foundation.logs.contains(where: { $0.message == "Session session-42 updated" }))
        #expect(foundation.logs.contains(where: { $0.message == "Cache summary updated" }))
        #expect(foundation.logs.contains(where: { $0.message == "Resource pressure in metal" && $0.level == "warning" }))
        #expect(foundation.logs.contains(where: { $0.message.contains("request-42") }))
        #expect(foundation.logs.contains(where: { $0.message == "Heartbeat" }))
    }

    @Test("recent logs are trimmed to the last forty entries")
    @MainActor
    func recentLogsAreTrimmedToFortyEntries() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        for index in 0..<45 {
            await client.sendLog(level: "info", message: "log-\(index)")
        }
        try await Task.sleep(for: .milliseconds(30))

        let foundation = viewModel.desktopFoundationState
        #expect(foundation.logs.count == 40)
        #expect(foundation.logs.first?.message == "log-44")
        #expect(foundation.logs.contains(where: { $0.message == "log-5" }))
        #expect(foundation.logs.contains(where: { $0.message == "log-4" }) == false)
    }

    @Test("featureless model responses still hydrate model rows")
    @MainActor
    func featurelessModelResponsesStillHydrateModelRows() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.configureModelResponseFeatures([])

        await viewModel.loadModel(modelID: "melix-dev-text")

        #expect(viewModel.primaryModel?.modelID == "melix-dev-text")
        #expect(viewModel.primaryModel?.stateText == "Warm")
        #expect(viewModel.desktopFoundationState.models.contains(where: { $0.modelID == "melix-dev-text" }))
    }

    @Test("model settings dispatch through the client and hydrate typed row settings")
    @MainActor
    func modelSettingsDispatchThroughClientAndHydrateRows() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.updatePrimaryModelForLatency()

        #expect(await client.recordedActions.contains("settings:melix-dev-text"))
        #expect(viewModel.primaryModel?.memoryPolicyText == "Pinned")
        #expect(viewModel.primaryModel?.accelerationModeText == "Speculative Decode")
        #expect(viewModel.primaryModel?.accelerationProfileID == "draft-q4")
        #expect(await metrics.snapshot()["menu.model_settings_ms"] != nil)
    }

    @Test("model info and operations dispatch through the client and populate tool state")
    @MainActor
    func modelInfoAndOperationsPopulateToolState() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        await viewModel.quantizePrimaryModel()
        await viewModel.uploadPrimaryModel()

        #expect(await client.recordedActions.contains("info:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:quantize:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
        #expect(viewModel.selectedModelInfo?.modelKind == "text")
        #expect(viewModel.selectedModelInfo?.supportedParsers == ["text", "json"])
        #expect(viewModel.lastModelOperation?.operation == "upload")
        #expect(viewModel.lastModelOperation?.outputPath.contains("/tmp/melix-upload") == true)
        #expect(await metrics.snapshot()["menu.model_info_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_operation_ms"] != nil)
    }

    @Test("model tool actions no-op when there is no primary model")
    @MainActor
    func modelToolActionsNoopWithoutPrimaryModel() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.updatePrimaryModelForLatency()
        await viewModel.inspectPrimaryModel()
        await viewModel.quantizePrimaryModel()
        await viewModel.downloadPrimaryModel()
        await viewModel.uploadPrimaryModel()

        #expect(viewModel.primaryModel == nil)
        #expect(await client.recordedActions.isEmpty)
        let snapshot = await metrics.snapshot()
        #expect(snapshot["menu.model_settings_ms"] == nil)
        #expect(snapshot["menu.model_info_ms"] == nil)
        #expect(snapshot["menu.model_operation_ms"] == nil)
    }

    @Test("model tool failures surface local errors")
    @MainActor
    func modelToolFailuresSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.configureErrors(
            modelSettings: MenuBarTestError(description: "settings failed"),
            modelInfo: MenuBarTestError(description: "inspect failed"),
            modelOperation: MenuBarTestError(description: "operation failed")
        )

        await viewModel.updatePrimaryModelForLatency()
        #expect(viewModel.lastError?.contains("settings failed") == true)

        await viewModel.inspectPrimaryModel()
        #expect(viewModel.lastError?.contains("inspect failed") == true)

        await viewModel.quantizePrimaryModel()
        #expect(viewModel.lastError?.contains("operation failed") == true)
    }

    @Test("model settings support ttl and advanced acceleration labels")
    @MainActor
    func modelSettingsSupportAdvancedLabels() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.updateModelSettings(
            modelID: "melix-dev-text",
            alias: "Melix Warm Cache",
            pinOnLoad: false,
            memoryPolicy: "ttl",
            accelerationMode: "accelerated_prefill",
            accelerationProfileID: "prefill-hot"
        )
        #expect(viewModel.primaryModel?.memoryPolicyText == "TTL")
        #expect(viewModel.primaryModel?.accelerationModeText == "Accelerated Prefill")

        await viewModel.updateModelSettings(
            modelID: "melix-dev-text",
            alias: "Melix Quantized",
            pinOnLoad: false,
            memoryPolicy: "evictable",
            accelerationMode: "active_kv_quantized",
            accelerationProfileID: "kv-q8"
        )
        #expect(viewModel.primaryModel?.memoryPolicyText == "Evictable")
        #expect(viewModel.primaryModel?.accelerationModeText == "Active KV Quantized")
        #expect(viewModel.primaryModel?.accelerationProfileID == "kv-q8")
    }
}

private actor EmptySnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    private(set) var recordedActions: [String] = []

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-empty"
        response.snapshot = Melix_Controlplane_V1_ServerSnapshot()
        response.snapshot.serverState = .serverReady
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        return snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("load:\(modelID)")
        return Melix_Controlplane_V1_ModelSummary()
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("unload:\(modelID)")
        return Melix_Controlplane_V1_ModelSummary()
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("settings:\(modelID)")
        _ = values
        return Melix_Controlplane_V1_ModelSummary()
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = weightQuant
        _ = kvQuant
        _ = ext
        return Melix_Controlplane_V1_ModelOperationResult()
    }
}

private actor SnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    private let snapshot: Melix_Controlplane_V1_ServerSnapshot

    init(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-snapshot"
        response.snapshot = snapshot
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        _ = values
        return Melix_Controlplane_V1_ModelSummary()
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = weightQuant
        _ = kvQuant
        _ = ext
        return Melix_Controlplane_V1_ModelOperationResult()
    }
}

private actor EventingSnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    private let snapshot: Melix_Controlplane_V1_ServerSnapshot
    private let stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    private let continuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation

    init(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot

        var capturedContinuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation?
        self.stream = AsyncStream { continuation in
            capturedContinuation = continuation
        }
        self.continuation = capturedContinuation!
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-eventing"
        response.snapshot = snapshot
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return stream
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        _ = values
        return Melix_Controlplane_V1_ModelSummary()
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = weightQuant
        _ = kvQuant
        _ = ext
        return Melix_Controlplane_V1_ModelOperationResult()
    }

    func sendQueueSummary() {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "heartbeat"
        event.heartbeat = Melix_Controlplane_V1_Heartbeat()
        continuation.yield(event)
    }

    func sendModelStateChanged(modelID: String, state: Melix_Controlplane_V1_ModelState) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = modelID
        event.modelState.state = state
        continuation.yield(event)
    }
}

private func makeSnapshot(
    serverState: Melix_Controlplane_V1_ServerState,
    models: [Melix_Controlplane_V1_ModelSummary]
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = serverState
    snapshot.models = models
    return snapshot
}

private func makeModelSummary(
    modelID: String = "melix-dev-text",
    state: Melix_Controlplane_V1_ModelState
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    model.state = state
    model.features = ["chat"]
    model.maxContext = 8192
    return model
}

private func makeRuntimeModelRow(state: Melix_Controlplane_V1_ModelState) -> RuntimeModelRow {
    RuntimeModelRow(
        modelID: "melix-dev-text",
        kind: "text",
        state: state,
        stateText: "state",
        actionTitle: "action",
        maxContext: 8192,
        alias: "Melix Dev Text",
        memoryPolicyText: "Evictable",
        accelerationModeText: "Baseline",
        accelerationProfileID: ""
    )
}
