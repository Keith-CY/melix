import Foundation
import Testing

@testable import AppMain
import MelixControlPlaneCore
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

        let evictingClient = SnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .modelEvicting)]
            )
        )
        let evictingViewModel = RuntimeViewModel(client: evictingClient)
        await evictingViewModel.start()
        #expect(evictingViewModel.primaryModel?.stateText == "Evicting")

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

    @Test("runtime model row surfaces eviction transition reasons for operator visibility")
    func runtimeModelRowSurfacesEvictionTransitionReasons() {
        let evicting = makeModelSummary(
            state: .modelEvicting,
            transitionReason: "ttl_expired"
        )
        let unloaded = makeModelSummary(
            state: .modelUnloaded,
            transitionReason: "lru_same_capability"
        )
        let failed = makeModelSummary(
            state: .modelFailed,
            transitionReason: "operator_unload_failed"
        )

        #expect(makeRuntimeModelRow(evicting).stateText == "Evicting • Ttl expired")
        #expect(makeRuntimeModelRow(unloaded).stateText == "Unloaded • Lru same capability")
        #expect(makeRuntimeModelRow(failed).stateText == "Failed • Operator unload failed")
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
        #expect(foundation.dashboardCards.contains(where: { $0.id == "connection" && $0.value == "Connected" }))
        #expect(foundation.queueLanes.contains(where: { $0.id == "text.decode.interactive" }))
        #expect(foundation.models.contains(where: { $0.modelID == "melix-dev-text" }))
        #expect(foundation.settings.contains(where: { $0.key == "Protocol" && $0.value == "melix.controlplane.v1" }))
        #expect(foundation.settings.contains(where: { $0.key == "Connection" && $0.value == "Connected" }))
        #expect(foundation.benchMetrics.contains(where: { $0.name == "http.translation_ms" }))
        #expect(foundation.apiReference.contains(where: { $0.path == "/v1/responses" }))
    }

    @Test("subscription termination triggers bounded reconnect and records recovery metrics")
    @MainActor
    func subscriptionTerminationTriggersReconnect() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await client.sendHeartbeat()
        await client.finishLatestSubscription()

        try await waitForRuntimeViewModelCondition("subscription termination should reconnect") {
            let foundation = viewModel.desktopFoundationState
            return foundation.settings.contains(where: { $0.key == "Connection" && $0.value == "Connected" })
                && foundation.logs.contains(where: { $0.message.contains("Reconnected event stream") })
        }

        let foundation = viewModel.desktopFoundationState
        let requests = await client.subscriptionRequests
        #expect(requests.count == 2)
        if requests.count >= 2 {
            #expect(requests[0] == 0)
            #expect(requests[1] == 1)
        }
        #expect(foundation.settings.contains(where: { $0.key == "Connection" && $0.value == "Connected" }))
        #expect(foundation.logs.contains(where: { $0.message.contains("Reconnected event stream") }))
        #expect(await metrics.snapshot()["desktop.reconnect_success_ms"] != nil)
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
        try await waitForRuntimeViewModelCondition("streamed events should update dashboard state") {
            let foundation = viewModel.desktopFoundationState
            return viewModel.lastError == "thermal pressure"
                && foundation.logs.contains(where: { $0.message == "Heartbeat" })
                && foundation.logs.contains(where: { $0.message == "thermal pressure" })
        }

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

    @Test("model info ops doctor and bench dispatch through the client and populate tool state")
    @MainActor
    func modelInfoOpsDoctorAndBenchPopulateToolState() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/melix-dev-adapter"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        await viewModel.runDoctor()
        await viewModel.runBench()
        await viewModel.quantizePrimaryModel()
        await viewModel.trainPrimaryModel()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "melix/adapters/melix-dev-adapter",
                    targetRepo: "melix/adapters/melix-dev-adapter"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await viewModel.publishLatestAdapter()

        #expect(await client.recordedActions.contains("info:melix-dev-text"))
        #expect(await client.recordedActions.contains("doctor"))
        #expect(await client.recordedActions.contains("bench"))
        #expect(await client.recordedActions.contains("operation:quantize:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:train_lora:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:registry_snapshot:melix-dev-text"))
        #expect(viewModel.selectedModelInfo?.modelKind == "text")
        #expect(viewModel.selectedModelInfo?.supportedParsers == ["text", "json"])
        #expect(viewModel.lastDoctorReport?.markdown.contains("Melix Doctor") == true)
        #expect(viewModel.lastBenchReport?.reportPath.contains("bench-report") == true)
        #expect(viewModel.desktopFoundationState.benchMetrics.contains(where: { $0.name == "bench.smoke.ttft_ms" }))
        #expect(viewModel.lastModelOperation?.operation == "upload")
        #expect(viewModel.lastModelOperation?.outputPath.contains("/tmp/melix-upload-adapter") == true)
        #expect(viewModel.adapterPackages.first?.adapterName == "melix-dev-adapter")
        #expect(viewModel.adapterPackages.first?.publishedRepo == "melix/adapters/melix-dev-adapter")
        #expect(viewModel.trainingHistory.first?.datasetURI == "datasets/melix-dev")
        #expect(await metrics.snapshot()["menu.model_info_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_doctor_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_bench_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_operation_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_ops_refresh_ms"] != nil)
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
        await viewModel.trainPrimaryModel()
        await viewModel.refreshModelOpsProductState()
        await viewModel.publishLatestAdapter()
        await viewModel.downloadPrimaryModel()
        await viewModel.uploadPrimaryModel()

        #expect(viewModel.primaryModel == nil)
        #expect(await client.recordedActions.isEmpty)
        let snapshot = await metrics.snapshot()
        #expect(snapshot["menu.model_settings_ms"] == nil)
        #expect(snapshot["menu.model_info_ms"] == nil)
        #expect(snapshot["menu.model_operation_ms"] == nil)
        #expect(snapshot["menu.model_ops_refresh_ms"] == nil)
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
            modelOperation: MenuBarTestError(description: "operation failed"),
            doctor: MenuBarTestError(description: "doctor failed"),
            bench: MenuBarTestError(description: "bench failed")
        )

        await viewModel.updatePrimaryModelForLatency()
        #expect(viewModel.lastError?.contains("settings failed") == true)

        await viewModel.inspectPrimaryModel()
        #expect(viewModel.lastError?.contains("inspect failed") == true)

        await viewModel.runDoctor()
        #expect(viewModel.lastError?.contains("doctor failed") == true)

        await viewModel.runBench()
        #expect(viewModel.lastError?.contains("bench failed") == true)

        await viewModel.quantizePrimaryModel()
        #expect(viewModel.lastError?.contains("operation failed") == true)

        await viewModel.refreshModelOpsProductState()
        #expect(viewModel.lastError?.contains("operation failed") == true)
    }

    @Test("model tooling refresh surfaces parse failures and publish no-ops without adapters")
    @MainActor
    func modelToolingRefreshSurfacesParseFailuresAndPublishNoopsWithoutAdapters() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: "{not-json"
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        await viewModel.publishLatestAdapter()

        #expect(viewModel.lastError?.contains("registry snapshot") == true)
        #expect(viewModel.adapterPackages.isEmpty)
        #expect(viewModel.trainingHistory.isEmpty)
    }

    @Test("model tooling snapshot normalizes pending adapter payloads and fallback publish flows")
    @MainActor
    func modelToolingSnapshotNormalizesPendingAdapterPayloads() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makePendingRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let adapter = try #require(viewModel.adapterPackages.first)
        let trainingJob = try #require(viewModel.trainingHistory.first)

        #expect(adapter.adapterName == "pending-adapter")
        #expect(adapter.statusText == "Queued for publish")
        #expect(adapter.targetRepo.isEmpty)
        #expect(adapter.trainingDurationText == "950ms")
        #expect(adapter.publishDurationText == "n/a")
        #expect(trainingJob.adapterName == "pending-adapter")
        #expect(trainingJob.datasetURI == "datasets/pending")
        #expect(trainingJob.statusText == "Unknown")
        #expect(trainingJob.stageText == "write_manifest • 42%")

        await viewModel.publishLatestAdapter()

        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
        #expect(await metrics.snapshot()["menu.model_ops_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_operation_ms"] != nil)
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

    @Test("chat prompt streams assistant reasoning and tool deltas into the transcript")
    @MainActor
    func chatPromptStreamsAssistantReasoningAndToolDeltas() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.chatComposerText = "Explain Melix"

        await viewModel.submitChatPrompt()

        #expect(await client.recordedActions.contains("chat:melix-dev-text"))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .user && $0.body == "Explain Melix" }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .assistant && $0.body.contains("Assistant response") }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .reasoning && $0.body.contains("Reasoning trace") }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .tool && $0.body.contains(#""q":"melix""#) }))
        #expect(viewModel.chatStatusText.contains("Completed"))
        #expect(viewModel.lastChatUsageText == "12 prompt • 24 completion")
        #expect(await metrics.snapshot()["menu.chat_submit_ms"] != nil)
        #expect(await metrics.snapshot()["menu.chat_first_delta_ms"] != nil)
        #expect(await metrics.snapshot()["menu.chat_stream_ms"] != nil)
    }

    @Test("chat prompt merges repeated deltas into shared transcript entries")
    @MainActor
    func chatPromptMergesRepeatedDeltasIntoSharedEntries() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .tokenDelta("Assistant "),
            .tokenDelta("response"),
            .reasoningDelta("Reasoning "),
            .reasoningDelta("trace"),
            .toolCallDelta(callID: "tool-1", toolName: "search", argumentsFragment: ""),
            .toolCallDelta(callID: "tool-1", toolName: "search", argumentsFragment: #"{"q":"melix"}"#),
            .completed(finishReason: "stop", assistantText: "Assistant response", reasoningText: "Reasoning trace"),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Merge deltas"

        await viewModel.submitChatPrompt()

        let assistantEntries = viewModel.chatTranscript.filter { $0.kind == .assistant }
        let reasoningEntries = viewModel.chatTranscript.filter { $0.kind == .reasoning }
        let toolEntries = viewModel.chatTranscript.filter { $0.kind == .tool }

        #expect(assistantEntries.count == 1)
        #expect(assistantEntries.first?.body == "Assistant response")
        #expect(reasoningEntries.count == 1)
        #expect(reasoningEntries.first?.body == "Reasoning trace")
        #expect(toolEntries.count == 1)
        #expect(toolEntries.first?.body == #"{"q":"melix"}"#)
    }

    @Test("chat completion can synthesize transcript entries without prior deltas")
    @MainActor
    func chatCompletionSynthesizesTranscriptEntriesWithoutPriorDeltas() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .completed(finishReason: "stop", assistantText: "Assistant final", reasoningText: "Reasoning final"),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Completion only"

        await viewModel.submitChatPrompt()

        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .assistant && $0.body == "Assistant final" }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .reasoning && $0.body == "Reasoning final" }))
        #expect(viewModel.chatStatusText == "Completed • stop")
    }

    @Test("chat prompt records phase transitions and terminal worker failures")
    @MainActor
    func chatPromptRecordsPhaseTransitionsAndWorkerFailures() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .queued(lane: "text.prefill.hot", queuePosition: 1, backpressure: 0.15),
            .admitted(lane: "text.prefill.hot", workerID: "swift-text-worker", queueDelayMs: 1.2),
            .prefillStarted(inputTokens: 64),
            .decodeStarted(decodeHandle: "decode-hot-1", maxOutputTokens: 96),
            .heartbeat,
            .failed(code: "runtime_error", message: "worker failed"),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Diagnose runtime phases"

        await viewModel.submitChatPrompt()

        #expect(viewModel.lastChatRequestID == "chat-request-1")
        #expect(viewModel.chatStatusText == "Failed • runtime_error")
        #expect(viewModel.lastError == "worker failed")
        #expect(viewModel.isChatStreaming == false)
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .error && $0.body == "worker failed" }))
    }

    @Test("chat transport failures surface local error rows and reset streaming state")
    @MainActor
    func chatTransportFailuresSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(chat: MenuBarTestError(description: "chat transport failed"))
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Diagnose transport"

        await viewModel.submitChatPrompt()

        #expect(viewModel.chatStatusText == "Failed")
        #expect(viewModel.lastError?.contains("chat transport failed") == true)
        #expect(viewModel.isChatStreaming == false)
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .error && $0.body.contains("chat transport failed") }))
    }

    @Test("chat route readiness reflects multimodal model availability from the snapshot")
    @MainActor
    func chatRouteReadinessReflectsMultimodalAvailability() async throws {
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeCapabilityModelSummary(modelID: "melix-dev-ocr", kind: "ocr", state: .modelWarm, features: ["ocr"]),
                makeCapabilityModelSummary(modelID: "melix-dev-vlm", kind: "vlm", state: .modelDiscovered, features: ["vlm", "vision"]),
                makeCapabilityModelSummary(modelID: "melix-dev-transcription", kind: "transcription", state: .modelWarm, features: ["audio", "transcription"]),
                makeCapabilityModelSummary(modelID: "melix-dev-speech", kind: "speech", state: .modelDiscovered, features: ["audio", "speech"]),
            ]
        )
        snapshot.metrics.values["http.translation_ms"] = 4.2
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.chatCapabilities.contains(where: { $0.id == "text" && $0.isReady }))
        #expect(viewModel.chatCapabilities.contains(where: { $0.id == "ocr" && $0.isReady }))
        #expect(viewModel.chatCapabilities.contains(where: { $0.id == "vlm" && $0.isReady == false }))
        #expect(viewModel.chatCapabilities.contains(where: { $0.id == "transcription" && $0.isReady }))
        #expect(viewModel.chatCapabilities.contains(where: { $0.id == "speech" && $0.isReady == false }))
    }

    @Test("image snapshot hydrates image panel state from control-plane truth")
    @MainActor
    func imageSnapshotHydratesImagePanelState() async throws {
        let artifact = makeMenuBarImageArtifact(
            jobID: "job-image-1",
            storageURI: "/tmp/melix-image-preview.png"
        )
        let imageJob = makeMenuBarImageJobSummary(
            jobID: "job-image-1",
            requestID: "req-image-1",
            operation: "image_generate",
            artifacts: [artifact]
        )
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [imageJob]
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.selectedImageModelID == "melix-dev-image")
        #expect(viewModel.imageJobs.count == 1)
        #expect(viewModel.selectedImageJobID == "job-image-1")
        #expect(viewModel.selectedImageJob?.operation == "image_generate")
        #expect(viewModel.selectedImageJob?.artifacts.first?.storageUri == "/tmp/melix-image-preview.png")
    }

    @Test("image generate and edit actions dispatch through the client and update runtime state")
    @MainActor
    func imageActionsDispatchThroughClientAndUpdateRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        await client.configureSnapshot(snapshot)
        await client.configureImageResponses(
            generation: makeMenuBarImageJobSummary(
                jobID: "job-image-generate",
                requestID: "req-image-generate",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-generate")]
            ),
            edit: makeMenuBarImageJobSummary(
                jobID: "job-image-edit",
                requestID: "req-image-edit",
                operation: "image_edit",
                artifacts: [
                    makeMenuBarImageArtifact(jobID: "job-image-edit", role: .imageArtifactEditSource, storageURI: "/tmp/source.png"),
                    makeMenuBarImageArtifact(jobID: "job-image-edit", role: .imageArtifactGenerated, storageURI: "/tmp/output.png"),
                ]
            )
        )
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.imagePromptText = "Generate a poster"
        await viewModel.submitImageGeneration()

        #expect(await client.recordedActions.contains("image.generate:melix-dev-image"))
        #expect(viewModel.imageStatusText == "Completed • image_generate")
        #expect(viewModel.imageJobs.contains(where: { $0.jobID == "job-image-generate" }))
        #expect(await metrics.snapshot()["desktop.image_action_latency_ms"] != nil)

        viewModel.imagePromptText = "Edit the poster"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        viewModel.imageEditMaskURL = "file:///tmp/mask.png"
        await viewModel.submitImageEdit()

        #expect(await client.recordedActions.contains("image.edit:melix-dev-image"))
        #expect(viewModel.imageJobs.contains(where: { $0.jobID == "job-image-edit" }))
        #expect(viewModel.selectedImageJob?.artifacts.contains(where: { $0.storageUri == "/tmp/output.png" }) == true)
    }

    @Test("image cancel action dispatches through the client and records cancel latency")
    @MainActor
    func imageCancelActionDispatchesThroughClient() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-live",
                requestID: "req-image-live",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(snapshot)
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.cancelSelectedImageJob()

        #expect(await client.recordedActions.contains("cancel:req-image-live"))
        #expect(viewModel.imageStatusText == "Canceling")
        #expect(await metrics.snapshot()["desktop.image_cancel_latency_ms"] != nil)
    }

    @Test("image cancel action is a no-op for non-cancelable jobs")
    @MainActor
    func imageCancelActionNoopsForNonCancelableJobs() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-complete",
                requestID: "req-image-complete",
                operation: "image_generate",
                state: .imageJobCompleted
            ),
        ]
        await client.configureSnapshot(snapshot)
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        let initialStatus = viewModel.imageStatusText
        await viewModel.cancelSelectedImageJob()

        #expect(await client.recordedActions.contains("cancel:req-image-complete") == false)
        #expect(viewModel.imageStatusText == initialStatus)
        #expect(await metrics.snapshot()["desktop.image_cancel_latency_ms"] == nil)
    }

    @Test("image cancel action surfaces client failures")
    @MainActor
    func imageCancelActionSurfacesClientFailures() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-failing-cancel",
                requestID: "req-image-failing-cancel",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureErrors(cancel: MenuBarTestError(description: "cancel failed"))
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.cancelSelectedImageJob()

        #expect(await client.recordedActions.contains("cancel:req-image-failing-cancel"))
        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError?.contains("cancel failed") == true)
        #expect(await metrics.snapshot()["desktop.image_cancel_latency_ms"] == nil)
    }

    @Test("image job events refresh selected job progress and terminal state")
    @MainActor
    func imageJobEventsRefreshSelectedJobProgressAndTerminalState() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = []
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        var runningJob = makeMenuBarImageJobSummary(
            jobID: "job-image-live",
            requestID: "req-image-live",
            operation: "image_generate",
            state: .imageJobRunning
        )
        runningJob.progress.stage = "sampling"
        runningJob.progress.pct = 0.5
        await client.sendImageJobStateChanged(runningJob)

        try await waitForRuntimeViewModelCondition("expected running image job to appear") {
            viewModel.imageJobs.contains(where: { $0.jobID == "job-image-live" })
        }

        #expect(viewModel.imageStatusText == "Running • image_generate")

        var completedJob = runningJob
        completedJob.state = .imageJobCompleted
        completedJob.progress.stage = "completed"
        completedJob.progress.pct = 1
        completedJob.artifacts = [makeMenuBarImageArtifact(jobID: "job-image-live", storageURI: "/tmp/live-output.png")]
        await client.sendImageJobStateChanged(completedJob)

        try await waitForRuntimeViewModelCondition("expected completed image job artifact") {
            viewModel.selectedImageJob?.artifacts.contains(where: { $0.storageUri == "/tmp/live-output.png" }) == true
        }

        #expect(viewModel.imageStatusText == "Completed • image_generate")
    }

    @Test("image edit requires a source URL before dispatch")
    @MainActor
    func imageEditRequiresASourceURLBeforeDispatch() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.imagePromptText = "Edit the skyline"
        await viewModel.submitImageEdit()

        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError == "Image edit source is required.")
        #expect(await client.recordedActions.contains("image.edit:melix-dev-image") == false)
        #expect(await metrics.snapshot()["desktop.image_action_latency_ms"] == nil)
    }

    @Test("image edit surfaces client failures")
    @MainActor
    func imageEditSurfacesClientFailures() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(imageEdit: MenuBarTestError(description: "edit failed"))
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.imagePromptText = "Edit the skyline"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"

        await viewModel.submitImageEdit()

        #expect(await client.recordedActions.contains("image.edit:melix-dev-image"))
        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError?.contains("edit failed") == true)
        #expect(await metrics.snapshot()["desktop.image_action_latency_ms"] == nil)
    }

    @Test("desktop foundation refresh records image refresh latency when image jobs are present")
    @MainActor
    func desktopFoundationRefreshRecordsImageRefreshLatency() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()

        var refreshedSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        refreshedSnapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-refresh",
                requestID: "req-image-refresh",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(refreshedSnapshot)

        await viewModel.refreshDesktopFoundation()

        #expect(await metrics.snapshot()["menu.foundation_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["desktop.image_refresh_ms"] != nil)
    }
}

@MainActor
private func waitForRuntimeViewModelCondition(
    _ description: String,
    timeout: Duration = .milliseconds(500),
    pollInterval: Duration = .milliseconds(10),
    condition: @escaping @MainActor () -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }

    throw MenuBarTestError(description: description)
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

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
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

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
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

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
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
    state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = ""
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    model.state = state
    model.features = ["chat"]
    model.maxContext = 8192
    model.residency.transitionReason = transitionReason
    return model
}

private func makeCapabilityModelSummary(
    modelID: String,
    kind: String,
    state: Melix_Controlplane_V1_ModelState,
    features: [String]
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = kind
    model.state = state
    model.features = features
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

private func makeNamedModelOperationResult(
    operation: String,
    outputPath: String,
    manifestJSON: String
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.ok = true
    result.operation = operation
    result.jobID = "job-\(operation)"
    result.stage = "completed"
    result.pct = 1
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    return result
}

private func makeRegistrySnapshotManifest(
    publishedRepo: String,
    targetRepo: String
) -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [
        {
          "job_id": "model-ops-0001",
          "operation": "train_lora",
          "source_model": "melix-dev-text",
          "status": "completed",
          "stage": "write_artifact",
          "pct": 1.0,
          "output_path": "/tmp/melix-train-lora/train_lora.adapter.json",
          "manifest": {
            "adapter_name": "melix-dev-adapter",
            "dataset_uri": "datasets/melix-dev",
            "target_repo": "\#(targetRepo)"
          }
        }
      ],
      "adapters": [
        {
          "adapter_id": "melix-dev-adapter@model-ops-0001",
          "job_id": "model-ops-0001",
          "adapter_name": "melix-dev-adapter",
          "source_model": "melix-dev-text",
          "dataset_uri": "datasets/melix-dev",
          "output_path": "/tmp/melix-train-lora/train_lora.adapter.json",
          "target_repo": "\#(targetRepo)",
          "published_repo": "\#(publishedRepo)",
          "status": "\#(publishedRepo.isEmpty ? "completed" : "published")",
          "training_duration_ms": 1420.0,
          "adapter_publish_ms": 118.0
        }
      ]
    }
    """#
}

private func makePendingRegistrySnapshotManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [
        {
          "job_id": "model-ops-0009",
          "operation": "quantize",
          "source_model": "melix-dev-text",
          "status": "completed",
          "stage": "write_artifact",
          "pct": 1.0,
          "output_path": "/tmp/melix-quantize/quantize.artifact",
          "manifest": {}
        },
        {
          "job_id": "model-ops-0008",
          "operation": "train_lora",
          "source_model": "melix-dev-text",
          "status": "",
          "stage": "write_manifest",
          "pct": 0.42,
          "output_path": "/tmp/melix-train-lora/pending.adapter.json",
          "manifest": {
            "adapter_name": "pending-adapter",
            "dataset_uri": "datasets/pending",
            "target_repo": ""
          }
        }
      ],
      "adapters": [
        {
          "adapter_id": "pending-adapter@model-ops-0008",
          "job_id": "model-ops-0008",
          "adapter_name": "pending-adapter",
          "source_model": "melix-dev-text",
          "dataset_uri": "datasets/pending",
          "output_path": "/tmp/melix-train-lora/pending.adapter.json",
          "target_repo": "",
          "published_repo": "",
          "status": "queued_for_publish",
          "training_duration_ms": 950,
          "adapter_publish_ms": 0
        }
      ]
    }
    """#
}
