import Foundation
import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Runtime View Model", .serialized)
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
        #expect(viewModel.selectedSurface == .chat)
        #expect(viewModel.selectedToolSection == .modelsLibrary)
        #expect(viewModel.serverSessions.isEmpty == false)
        #expect(viewModel.selectedServerSession?.modelID == "melix-dev-text")
        #expect(await metrics.snapshot()["menu.handshake_ms"] != nil)
        #expect(await metrics.snapshot()["menu.hydration_ms"] != nil)
    }

    @Test("restoresSelectedSurfaceAndServerSession from operator-session state")
    @MainActor
    func restoresSelectedSurfaceAndServerSessionFromOperatorSessionState() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-restore-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let restoredServerSession = DesktopServerSessionState(
            id: "server-session-restored",
            title: "Restored Server",
            modelID: "melix-dev-text",
            lifecycle: .running
        )
        try operatorSessionStore.save(
            OperatorSessionState(
                selectedSurface: .api,
                selectedServerSessionID: restoredServerSession.id,
                serverSessions: [restoredServerSession]
            )
        )

        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()

        #expect(viewModel.selectedSurface == .api)
        #expect(viewModel.selectedServerSession?.id == restoredServerSession.id)
    }

    @Test("generatesPrimaryAPIKeyForSelectedServerSession and forces api key auth mode")
    @MainActor
    func generatesPrimaryAPIKeyForSelectedServerSessionAndForcesAPIKeyAuthMode() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-generate-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        let generatedPrimaryKey = try #require(await viewModel.generatePrimaryAPIKeyForSelectedServerSession())
        let persistedPrimaryKey = try #require(try apiKeyStore.loadPrimaryKey(serverSessionID: selectedServerSessionID))

        #expect(generatedPrimaryKey.hasPrefix("melix_sk_"))
        #expect(persistedPrimaryKey.primaryKey == generatedPrimaryKey)
        #expect(viewModel.selectedServerSession?.authMode == .apiKeys)

        var persistMetricFound = false
        for _ in 0..<100 {
            let metricValues = await metrics.snapshot()
            if metricValues["operator.session_persist_write_ms"] != nil {
                persistMetricFound = true
                break
            }
            try await Task.sleep(for: .milliseconds(10))
        }

        let metricValues = await metrics.snapshot()
        #expect(metricValues["operator.session_restore_ms"] != nil)
        #expect(persistMetricFound)
        #expect(metricValues["gateway.api_key_persist_failures"] == 0)
    }

    @Test("defers gateway apply when selected server session is not running")
    @MainActor
    func defersGatewayApplyWhenSelectedServerSessionIsNotRunning() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-defer-apply-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        viewModel.createServerSession()
        #expect(viewModel.selectedServerSession?.isRunning == false)

        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()

        #expect(await client.recordedGatewayAccessApplyRequests.isEmpty)
    }

    @Test("appliesStoredKeyWhenSelectedRunningServerSessionBecomesActive")
    @MainActor
    func appliesStoredKeyWhenSelectedRunningServerSessionBecomesActive() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-apply-stored-key-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        viewModel.createServerSession()
        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        let primaryKey = try #require(await viewModel.generatePrimaryAPIKeyForSelectedServerSession())
        #expect(await client.recordedGatewayAccessApplyRequests.isEmpty)

        await viewModel.startSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.isEmpty, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.isEmpty == false)

        let appliedRequest = try #require(await client.recordedGatewayAccessApplyRequests.last)
        #expect(appliedRequest.serverSessionID == selectedServerSessionID)
        #expect(appliedRequest.primaryKey == primaryKey)
    }

    @Test("selecting a keyless server session clears previously applied gateway access")
    @MainActor
    func selectingAKeylessServerSessionClearsPreviouslyAppliedGatewayAccess() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-clear-keyless-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.isEmpty, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        viewModel.createServerSession()

        var clearAttempts = 0
        while await client.recordedGatewayAccessClearRequests.isEmpty, clearAttempts < 200 {
            clearAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessClearRequests == [try #require(viewModel.selectedServerSession?.id)])
    }

    @Test("stopping a keyed server session clears previously applied gateway access")
    @MainActor
    func stoppingAKeyedServerSessionClearsPreviouslyAppliedGatewayAccess() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-clear-stopped-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.isEmpty, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        await viewModel.stopSelectedServerSession()

        var clearAttempts = 0
        while await client.recordedGatewayAccessClearRequests.isEmpty, clearAttempts < 200 {
            clearAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessClearRequests == [selectedServerSessionID])
    }

    @Test("gateway access clear failures surface as recoverable local errors")
    @MainActor
    func gatewayAccessClearFailuresSurfaceAsRecoverableLocalErrors() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-clear-error-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.count < 1, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        await client.configureGatewayAccessClearError(MenuBarTestError(description: "clear failed"))
        viewModel.createServerSession()

        try await waitForRuntimeViewModelCondition("expected gateway access clear failure to surface") {
            viewModel.lastError?.contains("Gateway access clear failed") == true
        }
    }

    @Test("generate primary key returns nil when no server session exists")
    @MainActor
    func generatePrimaryKeyReturnsNilWhenNoServerSessionExists() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        let generatedPrimaryKey = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()

        #expect(generatedPrimaryKey == nil)
    }

    @Test("generate primary key records persistence failures when the store write fails")
    @MainActor
    func generatePrimaryKeyRecordsPersistenceFailuresWhenStoreWriteFails() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: true,
                loadPrimaryKeyValue: nil
            )
        )

        await viewModel.start()
        let generatedPrimaryKey = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()

        #expect(generatedPrimaryKey == nil)
        var metricValues = await metrics.snapshot()
        if metricValues["gateway.api_key_persist_failures"] != 1 {
            try await Task.sleep(for: .milliseconds(20))
            metricValues = await metrics.snapshot()
        }
        #expect(metricValues["gateway.api_key_persist_failures"] == 1)
    }

    @Test("start captures operator-session restore failures as local errors")
    @MainActor
    func startCapturesOperatorSessionRestoreFailuresAsLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: ThrowingOperatorSessionStore(throwOnLoad: true, throwOnSave: false),
            serverSessionAPIKeyStore: NullServerSessionAPIKeyStore()
        )

        await viewModel.start()

        #expect(viewModel.lastError?.contains("Operator session restore failed") == true)
    }

    @Test("persist operator-session failures are isolated to local error state")
    @MainActor
    func persistOperatorSessionFailuresAreIsolatedToLocalErrorState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: ThrowingOperatorSessionStore(throwOnLoad: false, throwOnSave: true),
            serverSessionAPIKeyStore: NullServerSessionAPIKeyStore()
        )

        await viewModel.start()
        viewModel.selectSurface(.server)

        #expect(viewModel.lastError?.contains("Operator session persistence failed") == true)
    }

    @Test("stored gateway key load and apply failures surface as recoverable local errors")
    @MainActor
    func storedGatewayKeyLoadAndApplyFailuresSurfaceAsRecoverableLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(applyGatewayAccess: MenuBarTestError(description: "apply failed"))
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: true,
                throwOnSave: false,
                loadPrimaryKeyValue: nil
            )
        )

        await viewModel.start()
        viewModel.selectServerSession(id: viewModel.selectedServerSession?.id ?? "")
        #expect(viewModel.lastError?.contains("Gateway API key restore failed") == true)

        let applyFailureViewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: "melix_sk_apply_failure"
            )
        )

        await applyFailureViewModel.start()
        applyFailureViewModel.selectServerSession(id: applyFailureViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        #expect(applyFailureViewModel.lastError?.contains("Gateway access apply failed") == true)
    }

    @Test("stored gateway apply skips empty keys and dedupes already-applied keys")
    @MainActor
    func storedGatewayApplySkipsEmptyKeysAndDedupesAlreadyAppliedKeys() async throws {
        let emptyKeyClient = FakeControlPlaneXPCClient()
        let emptyKeyViewModel = RuntimeViewModel(
            client: emptyKeyClient,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: ""
            )
        )

        await emptyKeyViewModel.start()
        emptyKeyViewModel.selectServerSession(id: emptyKeyViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        #expect(await emptyKeyClient.recordedGatewayAccessApplyRequests.isEmpty)

        let dedupeClient = FakeControlPlaneXPCClient()
        let dedupeViewModel = RuntimeViewModel(
            client: dedupeClient,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: "melix_sk_dedupe"
            )
        )

        await dedupeViewModel.start()
        dedupeViewModel.selectServerSession(id: dedupeViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        dedupeViewModel.selectServerSession(id: dedupeViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        #expect(await dedupeClient.recordedGatewayAccessApplyRequests.count == 1)
    }

    @Test("chat requires a running server session before sending prompts")
    @MainActor
    func chatRequiresRunningServerSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "hello"
        await viewModel.stopSelectedServerSession()
        await viewModel.submitChatPrompt()

        let actions = await client.recordedActions
        #expect(actions.contains(where: { $0.hasPrefix("chat:") }) == false)
        #expect(viewModel.chatStatusText == "No Server Session")
        #expect(viewModel.lastError?.contains("Server Session") == true)
    }

    @Test("creating a chat session binds it to the selected server session")
    @MainActor
    func creatingChatSessionBindsSelectedServerSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        let originalServerID = try #require(viewModel.selectedServerSession?.id)

        viewModel.createChatSession()

        #expect(viewModel.chatSessions.count == 2)
        #expect(viewModel.selectedChatSession?.serverSessionID == originalServerID)
    }

    @Test("surface selection command center and server session controls update shell state")
    @MainActor
    func shellStateSelectionAndServerSessionControlsUpdateState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        var stateChangeCount = 0
        var commandCenterOpenCount = 0
        viewModel.onStateChanged = { stateChangeCount += 1 }
        viewModel.openCommandCenterAction = { commandCenterOpenCount += 1 }

        await viewModel.start()

        viewModel.selectSurface(.api)
        #expect(viewModel.selectedSurface == .api)

        viewModel.selectToolSection(.diagnostics)
        #expect(viewModel.selectedSurface == .tools)
        #expect(viewModel.selectedToolSection == .diagnostics)

        viewModel.openCommandCenter()
        #expect(commandCenterOpenCount == 1)

        let originalServerID = try #require(viewModel.selectedServerSession?.id)
        viewModel.createServerSession()

        let createdServer = try #require(viewModel.selectedServerSession)
        #expect(createdServer.id != originalServerID)
        #expect(createdServer.title == "Server 2")
        #expect(createdServer.lifecycle == .draft)
        #expect(viewModel.selectedSurface == .server)

        viewModel.selectServerSession(id: "missing-server")
        #expect(viewModel.selectedServerSession?.id == createdServer.id)

        viewModel.selectServerSession(id: originalServerID)
        #expect(viewModel.selectedServerSession?.id == originalServerID)

        viewModel.selectServerSession(id: createdServer.id)
        viewModel.updateSelectedServerSessionModelID("melix-dev-text")
        viewModel.updateSelectedServerSessionHost("0.0.0.0")
        viewModel.updateSelectedServerSessionPort(0)
        viewModel.updateSelectedServerSessionAuthMode(.bearerToken)
        viewModel.updateSelectedServerSessionAuthTokenHint("dev-token")
        viewModel.updateSelectedServerSessionRateLimit(0)
        viewModel.updateSelectedServerSessionTimeout(0)
        viewModel.updateSelectedServerSessionTemperature(-1)
        viewModel.updateSelectedServerSessionTopP(5)
        viewModel.updateSelectedServerSessionMaxTokens(0)
        viewModel.updateSelectedServerSessionMaxConcurrentRequests(0)

        let configuredServer = try #require(viewModel.selectedServerSession)
        #expect(configuredServer.host == "0.0.0.0")
        #expect(configuredServer.port == 1)
        #expect(configuredServer.authMode == .bearerToken)
        #expect(configuredServer.authTokenHint == "dev-token")
        #expect(configuredServer.rateLimitPerMinute == 1)
        #expect(configuredServer.timeoutSeconds == 1)
        #expect(configuredServer.servingDefaults.temperature == 0)
        #expect(configuredServer.servingDefaults.topP == 1)
        #expect(configuredServer.servingDefaults.maxTokens == 1)
        #expect(configuredServer.servingDefaults.maxConcurrentRequests == 1)

        await viewModel.startSelectedServerSession()
        #expect(await client.recordedActions.contains("load:melix-dev-text"))
        #expect(viewModel.selectedServerSession?.lifecycle == .running)

        await viewModel.stopSelectedServerSession()
        #expect(await client.recordedActions.contains("unload:melix-dev-text"))
        #expect(viewModel.selectedServerSession?.lifecycle == .stopped)
        #expect(stateChangeCount > 0)
    }

    @Test("agent integration exports mirror the selected server session and record metrics")
    @MainActor
    func agentIntegrationExportsMirrorTheSelectedServerSessionAndRecordMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        try await waitForRuntimeViewModelCondition("expected agent exports to be generated") {
            viewModel.agentIntegrationExports.count == AgentIntegrationExportTarget.allCases.count
        }

        let selectedExport = try #require(viewModel.selectedAgentIntegrationExport)
        let metricValues = await metrics.snapshot()

        #expect(viewModel.agentIntegrationExports.map(\.target) == AgentIntegrationExportTarget.allCases)
        #expect(selectedExport.target == .openAICompatible)
        #expect(selectedExport.baseURL == "http://127.0.0.1:8080/v1")
        #expect(selectedExport.modelID == "melix-dev-text")
        #expect(selectedExport.shellSnippet.contains("curl http://127.0.0.1:8080/v1/responses"))
        #expect(metricValues["integration.export_generation_ms"] != nil)
        #expect(metricValues["integration.export_target_count"] == Double(AgentIntegrationExportTarget.allCases.count))
    }

    @Test("agent integration exports render auth placeholders and rebind when the selected server changes")
    @MainActor
    func agentIntegrationExportsRenderAuthPlaceholdersAndRebindWhenTheSelectedServerChanges() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.updateSelectedServerSessionAuthMode(.bearerToken)
        viewModel.updateSelectedServerSessionAuthTokenHint("dev-token")
        viewModel.selectAgentIntegrationTarget(.codex)

        let codexExport = try #require(viewModel.selectedAgentIntegrationExport)
        #expect(codexExport.configFragment.contains("<dev-token>"))
        #expect(codexExport.shellSnippet.contains("OPENAI_API_KEY=<dev-token>"))

        viewModel.createServerSession()
        viewModel.updateSelectedServerSessionHost("0.0.0.0")
        viewModel.updateSelectedServerSessionPort(9090)
        viewModel.updateSelectedServerSessionAuthMode(.none)
        viewModel.selectAgentIntegrationTarget(.openClaw)

        let reboundServer = try #require(viewModel.selectedServerSession)
        let reboundExport = try #require(viewModel.selectedAgentIntegrationExport)
        #expect(reboundServer.port == 9090)
        #expect(reboundExport.baseURL == "http://0.0.0.0:9090/v1")
        #expect(reboundExport.configFragment.contains("http://0.0.0.0:9090/v1"))
        #expect(reboundExport.configFragment.contains("not-required"))
    }

    @Test("shared-access snapshot hydrates server-session state and agent exports")
    @MainActor
    func sharedAccessSnapshotHydratesServerSessionStateAndAgentExports() async throws {
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                acceptedApiKeyCount: 2,
                keyHints: ["desktop-agent", "codex"]
            )
        )
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        let export = try #require(viewModel.selectedAgentIntegrationExport)

        #expect(session.authMode == .apiKeys)
        #expect(session.sharedAccessState == .enabled)
        #expect(session.accessKeyCount == 2)
        #expect(session.accessKeyHints == ["desktop-agent", "codex"])
        #expect(export.configFragment.contains("<desktop-agent>"))
        #expect(export.shellSnippet.contains("x-api-key: <desktop-agent>"))
    }

    @Test("configured-but-disabled shared access stays local trust while surfacing key hints")
    @MainActor
    func configuredButDisabledSharedAccessStaysLocalTrustWhileSurfacingKeyHints() async throws {
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .apiKeys,
                sharedAccessEnabled: false,
                acceptedApiKeyCount: 2,
                keyHints: ["desktop-agent", "codex"]
            )
        )
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        let export = try #require(viewModel.selectedAgentIntegrationExport)
        let authReference = desktopAPIAuthenticationReferenceText(
            selectedSession: session,
            selectedExport: export
        )

        #expect(session.authMode == .none)
        #expect(session.sharedAccessState == .configuredDisabled)
        #expect(session.accessKeyCount == 2)
        #expect(session.accessKeyHints == ["desktop-agent", "codex"])
        #expect(export.configFragment.contains("not-required"))
        #expect(export.shellSnippet.contains("x-api-key") == false)
        #expect(authReference.contains("configured but disabled"))
        #expect(authReference.contains("desktop-agent, codex"))
    }

    @Test("switching auth mode away from shared access restores local-only trust state")
    @MainActor
    func switchingAuthModeAwayFromSharedAccessRestoresLocalOnlyTrustState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.updateSelectedServerSessionAuthMode(.apiKeys)
        #expect(viewModel.selectedServerSession?.sharedAccessState == .enabled)

        viewModel.updateSelectedServerSessionAuthMode(.bearerToken)

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.authMode == .bearerToken)
        #expect(session.sharedAccessState == .localOnly)
    }

    @Test("gateway access projection covers none bearer and unknown modes")
    @MainActor
    func gatewayAccessProjectionCoversNoneBearerAndUnknownModes() async throws {
        let noneSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .none,
                sharedAccessEnabled: false,
                acceptedApiKeyCount: 0,
                keyHints: []
            )
        )
        let bearerSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .bearerToken,
                sharedAccessEnabled: false,
                acceptedApiKeyCount: 0,
                keyHints: ["desktop-agent"]
            )
        )
        var unknownGatewayAccess = makeGatewayAccessSummary(
            mode: .none,
            sharedAccessEnabled: false,
            acceptedApiKeyCount: 0,
            keyHints: []
        )
        unknownGatewayAccess.mode = .UNRECOGNIZED(99)
        let unknownSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: unknownGatewayAccess
        )

        let noneViewModel = RuntimeViewModel(client: SnapshotControlPlaneXPCClient(snapshot: noneSnapshot))
        await noneViewModel.start()
        let noneSession = try #require(noneViewModel.selectedServerSession)
        #expect(noneSession.authMode == .none)
        #expect(noneSession.sharedAccessState == .localOnly)
        #expect(noneSession.accessKeyCount == 0)

        let bearerViewModel = RuntimeViewModel(client: SnapshotControlPlaneXPCClient(snapshot: bearerSnapshot))
        await bearerViewModel.start()
        let bearerSession = try #require(bearerViewModel.selectedServerSession)
        #expect(bearerSession.authMode == .bearerToken)
        #expect(bearerSession.authTokenHint == "desktop-agent")
        #expect(bearerSession.sharedAccessState == .localOnly)
        #expect(bearerSession.accessKeyCount == 1)
        #expect(bearerSession.accessKeyHints == ["desktop-agent"])

        let unknownViewModel = RuntimeViewModel(client: SnapshotControlPlaneXPCClient(snapshot: unknownSnapshot))
        await unknownViewModel.start()
        let unknownSession = try #require(unknownViewModel.selectedServerSession)
        #expect(unknownSession.authMode == .none)
        #expect(unknownSession.sharedAccessState == .localOnly)
        #expect(unknownSession.accessKeyCount == 0)
        #expect(unknownSession.authTokenHint.isEmpty)
    }

    @Test("server session shared-access summary text covers configured disabled and enabled states")
    func serverSessionSharedAccessSummaryTextCoversConfiguredDisabledAndEnabledStates() {
        let configuredDisabled = DesktopServerSessionState(
            id: "configured-disabled",
            title: "Configured Disabled",
            modelID: "melix-dev-text",
            sharedAccessState: .configuredDisabled
        )
        let enabledSingleKey = DesktopServerSessionState(
            id: "enabled-single",
            title: "Enabled Single",
            modelID: "melix-dev-text",
            sharedAccessState: .enabled,
            accessKeyCount: 1
        )
        let enabledMultipleKeys = DesktopServerSessionState(
            id: "enabled-multi",
            title: "Enabled Multiple",
            modelID: "melix-dev-text",
            sharedAccessState: .enabled,
            accessKeyCount: 2
        )

        #expect(configuredDisabled.sharedAccessSummaryText == "Shared access is configured but disabled.")
        #expect(enabledSingleKey.sharedAccessSummaryText == "Shared access is enabled for 1 key.")
        #expect(enabledMultipleKeys.sharedAccessSummaryText == "Shared access is enabled for 2 keys.")
    }

    @Test("agent integration exports stay empty when no server session is available")
    @MainActor
    func agentIntegrationExportsStayEmptyWhenNoServerSessionIsAvailable() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.serverSessions.isEmpty)
        #expect(viewModel.agentIntegrationExports.isEmpty)
        #expect(viewModel.selectedAgentIntegrationExport == nil)
    }

    @Test("empty workspace routes chat creation to server and server creation seeds the first chat session")
    @MainActor
    func emptyWorkspaceRoutesChatCreationToServerAndSeedsServerBoundChat() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        #expect(viewModel.serverSessions.isEmpty)
        #expect(viewModel.chatSessions.isEmpty)

        viewModel.createChatSession()
        #expect(viewModel.chatStatusText == "No Server Session")
        #expect(viewModel.lastError == "Create a Server Session before opening chat.")
        #expect(viewModel.selectedSurface == .server)

        viewModel.createServerSession()

        let seededServer = try #require(viewModel.selectedServerSession)
        let seededChat = try #require(viewModel.selectedChatSession)
        #expect(viewModel.serverSessions.count == 1)
        #expect(viewModel.chatSessions.count == 1)
        #expect(seededServer.title == "Primary Server")
        #expect(seededServer.modelID == "melix-dev-text")
        #expect(seededServer.port == 8080)
        #expect(seededChat.serverSessionID == seededServer.id)
        #expect(viewModel.selectedSurface == .chat)
    }

    @Test("chat sessions can be exported forked and reselected without losing server bindings")
    @MainActor
    func chatSessionsCanBeExportedForkedAndReselected() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Export this chat session"
        await viewModel.submitChatPrompt()

        let originalSession = try #require(viewModel.selectedChatSession)
        let exportPath = try #require(viewModel.exportSelectedChatSession())
        #expect(FileManager.default.fileExists(atPath: exportPath))
        #expect(viewModel.selectedChatSession?.exportPath == exportPath)

        viewModel.forkSelectedChatSession()

        let forkedSession = try #require(viewModel.selectedChatSession)
        #expect(viewModel.chatSessions.count == 2)
        #expect(forkedSession.title == "\(originalSession.title) Fork")
        #expect(forkedSession.serverSessionID == originalSession.serverSessionID)
        #expect(forkedSession.branchID == "branch-2")
        #expect(forkedSession.branchTitle == "Branch 2")
        #expect(forkedSession.transcript == originalSession.transcript)
        #expect(forkedSession.exportPath == exportPath)

        viewModel.selectChatSession(id: originalSession.id)
        #expect(viewModel.selectedChatSession?.id == originalSession.id)

        viewModel.selectChatSession(id: "missing-chat-session")
        #expect(viewModel.selectedChatSession?.id == originalSession.id)
    }

    @Test("guarded server and chat actions no-op safely before hydration")
    @MainActor
    func guardedServerAndChatActionsNoOpSafelyBeforeHydration() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        viewModel.chatComposerText = "hello from a cold start"
        await viewModel.startSelectedServerSession()
        await viewModel.stopSelectedServerSession()
        viewModel.clearChatTranscript()
        viewModel.forkSelectedChatSession()
        let exportPath = viewModel.exportSelectedChatSession()
        await viewModel.submitChatPrompt()

        #expect(exportPath == nil)
        #expect(await client.recordedActions.isEmpty)
        #expect(viewModel.chatStatusText == "No Server Session")
        #expect(viewModel.lastError?.contains("Server Session") == true)
        #expect(viewModel.selectedSurface == .server)
    }

    @Test("server session sync and banner state cover fallback unavailable warning and recovery paths")
    @MainActor
    func serverSessionSyncAndBannerStateCoverFallbackAndRecoveryPaths() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.updateSelectedServerSessionModelID("missing-model")

        let alternateTextSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(modelID: "melix-alt-text", state: .modelWarm)]
        )
        await client.configureSnapshot(alternateTextSnapshot)
        await viewModel.refreshDesktopFoundation()

        #expect(viewModel.selectedServerSession?.modelID == "melix-alt-text")
        #expect(viewModel.selectedServerSession?.lastKnownModelStateText == "Warm")
        #expect(viewModel.selectedChatServerSession?.modelID == "melix-alt-text")

        var drainingEvent = Melix_Controlplane_V1_ServerStateChanged()
        drainingEvent.state = .serverDraining
        await client.sendServerStateChanged(state: .serverDraining)
        try await waitForRuntimeViewModelCondition("warning banner should surface draining runtime state") {
            viewModel.desktopBannerState?.severity == .warning
        }
        #expect(viewModel.desktopBannerState?.title == "Runtime Needs Monitoring")

        let imageOnlySnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeCapabilityModelSummary(
                modelID: "melix-dev-image",
                kind: "image",
                state: .modelWarm,
                features: ["image_generate"]
            )]
        )
        await client.configureSnapshot(imageOnlySnapshot)
        await viewModel.refreshDesktopFoundation()

        #expect(viewModel.selectedServerSession?.lifecycle == .unavailable)
        #expect(viewModel.selectedServerSession?.lastKnownModelStateText == "Unavailable")

        let failingClient = FakeControlPlaneXPCClient()
        await failingClient.configureErrors(load: MenuBarTestError(description: "load failed"))
        let failingViewModel = RuntimeViewModel(client: failingClient)
        await failingViewModel.start()
        failingViewModel.createServerSession()
        await failingViewModel.startSelectedServerSession()

        let failingBanner = try #require(failingViewModel.desktopBannerState)
        #expect(failingBanner.severity == .critical)
        #expect(failingBanner.title.contains("Needs Recovery"))
        #expect(failingBanner.detail.contains("load failed"))
    }

    @Test("critical banner surfaces failed runtime state")
    @MainActor
    func criticalBannerSurfacesFailedRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendServerStateChanged(state: .serverFailed)

        try await waitForRuntimeViewModelCondition("critical banner should surface failed runtime state") {
            viewModel.desktopBannerState?.severity == .critical
        }

        let banner = try #require(viewModel.desktopBannerState)
        #expect(banner.title == "Operator Attention Required")
        #expect(banner.detail == viewModel.connectionDetailText)
    }

    @Test("audio setup banner and download actions surface missing audio assets")
    @MainActor
    func audioSetupBannerAndDownloadActionsSurfaceMissingAudioAssets() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        whisper.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        whisper.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
        whisper.settings.ext["melix.audio.model_state"] = "catalog_default"
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [ModelCatalog.devTextModel(), whisper]
        )
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let banner = try #require(viewModel.desktopBannerState)
        let action = try #require(viewModel.audioSetupActions.first)

        #expect(banner.severity == .warning)
        #expect(banner.title == "Audio Setup Required")
        #expect(action.modelID == "melix-whisper-mlx")
        #expect(action.actionTitle == "Install Audio Support")
        #expect(action.detail.contains("melix-audio-runtime-pack"))
    }

    @Test("audio setup actions dispatch install and download operations then refresh snapshot")
    @MainActor
    func audioSetupActionsDispatchInstallAndDownloadOperationsThenRefreshSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()

        var missingRuntime = ModelCatalog.mlxWhisperModel()
        missingRuntime.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        missingRuntime.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
        missingRuntime.settings.ext["melix.audio.model_state"] = "catalog_default"

        var runtimeInstalled = missingRuntime
        runtimeInstalled.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        runtimeInstalled.settings.ext["melix.audio.model_state"] = "catalog_default"

        var managedLocal = runtimeInstalled
        managedLocal.settings.ext["melix.audio.model_state"] = "managed_local"
        managedLocal.settings.ext["melix.model_path"] = "/Users/test/Library/Application Support/Melix/models/default-managed/hf/mlx-community/whisper-large-v3-turbo-asr-fp16/mlx-audio"

        await client.configureSnapshot(
            makeSnapshot(serverState: .serverReady, models: [ModelCatalog.devTextModel(), missingRuntime])
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "install_audio_runtime",
                outputPath: "/Users/test/Library/Application Support/Melix/runtime-packs/audio/melix-audio-runtime-pack/0.3.0",
                manifestJSON: "{}"
            ),
            forNamedOperation: "install_audio_runtime"
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "download",
                outputPath: managedLocal.settings.ext["melix.model_path"] ?? "",
                manifestJSON: "{}"
            ),
            forNamedOperation: "download"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        await client.configureSnapshot(
            makeSnapshot(serverState: .serverReady, models: [ModelCatalog.devTextModel(), runtimeInstalled])
        )
        await viewModel.installAudioRuntime(modelID: "melix-whisper-mlx")

        let installRequest = try #require(await client.recordedModelOperationRequests.first)
        #expect(installRequest.operation == "install_audio_runtime")
        #expect(installRequest.modelID == "melix-whisper-mlx")
        #expect(viewModel.audioSetupActions.first?.actionTitle == "Download Audio Model")

        await client.configureSnapshot(
            makeSnapshot(serverState: .serverReady, models: [ModelCatalog.devTextModel(), managedLocal])
        )
        await viewModel.downloadAudioModel(modelID: "melix-whisper-mlx")

        let requests = await client.recordedModelOperationRequests
        #expect(requests.count == 2)
        #expect(requests[1].operation == "download")
        #expect(requests[1].modelID == "melix-whisper-mlx")
        #expect(viewModel.audioSetupActions.isEmpty)
        #expect(viewModel.lastModelOperation?.operation == "download")
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
        #expect(viewModel.connectionDetailText == "Handshake failed")
        #expect(viewModel.lastError?.contains("Startup failed:") == true)
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

    @Test("runtime model row surfaces residency memory and guard descriptors")
    func runtimeModelRowSurfacesResidencyMemoryAndGuardDescriptors() {
        let guarded = makeModelSummary(
            state: .modelFailed,
            transitionReason: "memory_budget_exceeded",
            pinRequested: true,
            pinned: false,
            ttlSeconds: 600,
            estimatedBytes: 512 * 1024 * 1024,
            inflightRequests: 3,
            memoryPolicy: .memoryResidencyPinned
        )

        let row = makeRuntimeModelRow(guarded)

        #expect(row.residencyText.contains("Failed"))
        #expect(row.residencyText.contains("Pinned"))
        #expect(row.residencyText.contains("TTL 600s"))
        #expect(row.residencyText.contains("Pin requested"))
        #expect(row.memoryText.contains("estimated"))
        #expect(row.memoryText.contains("3 inflight"))
        #expect(row.memoryAlertText == "Memory protection • Memory budget exceeded")
    }

    @Test("runtime model row surfaces adaptive thinking policy")
    func runtimeModelRowSurfacesAdaptiveThinkingPolicy() {
        let adaptive = makeModelSummary(
            state: .modelWarm,
            adaptiveThinkingMode: "adaptive",
            adaptiveThinkingBudgetTokens: 192
        )
        let off = makeModelSummary(
            state: .modelWarm,
            adaptiveThinkingMode: "off"
        )

        #expect(makeRuntimeModelRow(adaptive).adaptiveThinkingText == "Adaptive • 192 tok")
        #expect(makeRuntimeModelRow(off).adaptiveThinkingText == "Off")
    }

    @Test("runtime model row falls back across residency states policies and ttl descriptors")
    func runtimeModelRowFallsBackAcrossResidencyStateBranches() {
        var explicitResidency = makeModelSummary(
            state: .modelDiscovered,
            memoryPolicy: .unspecified
        )
        explicitResidency.residency.state = .loading

        let loadingFallback = makeModelSummary(
            state: .modelLoading,
            memoryPolicy: .unspecified
        )
        let evictingFallback = makeModelSummary(
            state: .modelEvicting,
            memoryPolicy: .unspecified
        )
        let unloadedFallback = makeModelSummary(
            state: .modelUnloaded,
            memoryPolicy: .unspecified
        )
        let ttlFallback = makeModelSummary(
            state: .modelDiscovered,
            ttlSeconds: 30,
            memoryPolicy: .unspecified
        )
        let unknownFallback = makeModelSummary(
            state: .UNRECOGNIZED(-1),
            memoryPolicy: .unspecified
        )

        #expect(makeRuntimeModelRow(explicitResidency).residencyText.contains("Loading"))
        #expect(makeRuntimeModelRow(loadingFallback).residencyText.contains("Loading"))
        #expect(makeRuntimeModelRow(evictingFallback).residencyText.contains("Evicting"))
        #expect(makeRuntimeModelRow(unloadedFallback).residencyText.contains("Unloaded"))
        #expect(makeRuntimeModelRow(ttlFallback).residencyText.contains("TTL 30s"))
        #expect(makeRuntimeModelRow(unknownFallback).residencyText.contains("Unknown"))
    }

    @Test("desktop foundation derives dashboard settings bench and api state from control-plane truth")
    @MainActor
    func desktopFoundationDerivesOperatorPanelsFromSnapshotTruth() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let hasReadyServerCard = foundation.dashboardCards.contains { $0.id == "server" && $0.value == "Ready" }
        let hasConnectedCard = foundation.dashboardCards.contains { $0.id == "connection" && $0.value == "Connected" }
        let hasDecodeLane = foundation.queueLanes.contains { $0.id == "text.decode.interactive" }
        let hasPrimaryModel = foundation.models.contains { $0.modelID == "melix-dev-text" }
        let hasProtocolSetting = foundation.settings.contains { $0.key == "Protocol" && $0.value == "melix.controlplane.v1" }
        let hasConnectionSetting = foundation.settings.contains { $0.key == "Connection" && $0.value == "Connected" }
        let hasTranslationMetric = foundation.benchMetrics.contains { $0.name == "http.translation_ms" }
        let hasResponsesEndpoint = foundation.apiReference.contains { $0.path == "/v1/responses" }
        #expect(foundation.title == "Melix Ready")
        #expect(hasReadyServerCard)
        #expect(hasConnectedCard)
        #expect(hasDecodeLane)
        #expect(hasPrimaryModel)
        #expect(hasProtocolSetting)
        #expect(hasConnectionSetting)
        #expect(hasTranslationMetric)
        #expect(hasResponsesEndpoint)
    }

    @Test("desktop foundation surfaces residency eviction and memory guard summaries")
    @MainActor
    func desktopFoundationSurfacesResidencyEvictionAndMemoryGuardSummaries() async throws {
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(
                    modelID: "melix-dev-text",
                    state: .modelPinned,
                    pinRequested: true,
                    pinned: true,
                    ttlSeconds: 900,
                    estimatedBytes: 768 * 1024 * 1024,
                    memoryPolicy: .memoryResidencyPinned
                ),
                makeModelSummary(
                    modelID: "melix-dev-evicting",
                    state: .modelEvicting,
                    transitionReason: "ttl_expired",
                    ttlSeconds: 120,
                    estimatedBytes: 256 * 1024 * 1024,
                    memoryPolicy: .memoryResidencyTtl
                ),
                makeModelSummary(
                    modelID: "melix-dev-guarded",
                    state: .modelFailed,
                    transitionReason: "prefill_memory_guard_exceeded",
                    estimatedBytes: 512 * 1024 * 1024,
                    inflightRequests: 1
                ),
            ]
        )
        snapshot.metrics.values = [
            "control_plane.model_eviction_ttl_count": 2,
            "control_plane.model_eviction_lru_same_capability_count": 1,
            "control_plane.model_eviction_last_pinned_protected_count": 1,
        ]
        snapshot.recentErrors = [
            {
                var error = Melix_Controlplane_V1_RecentError()
                error.code = "prefill_memory_guard_exceeded"
                error.message = "Prefill memory guard exceeded for melix-dev-guarded"
                return error
            }(),
        ]
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency" && row.value == "1 pinned"
        }
        let hasEvictionsCard = foundation.dashboardCards.contains { row in
            row.id == "evictions" && row.value == "3"
        }
        let hasGuardCard = foundation.dashboardCards.contains { row in
            row.id == "guards" && row.value == "1"
        }
        let hasGuardedModel = foundation.models.contains { row in
            row.modelID == "melix-dev-guarded" && row.memoryAlertText.contains("Memory protection")
        }
        let hasEvictingModel = foundation.models.contains { row in
            row.modelID == "melix-dev-evicting" && row.stateText == "Evicting • Ttl expired"
        }

        #expect(hasResidencyCard)
        #expect(hasEvictionsCard)
        #expect(hasGuardCard)
        #expect(hasGuardedModel)
        #expect(hasEvictingModel)
    }

    @Test("desktop foundation formats guard details from model transitions when recent errors are absent")
    @MainActor
    func desktopFoundationFormatsGuardDetailFromModelTransitionFallback() async throws {
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(
                    modelID: "melix-dev-guarded",
                    state: .modelFailed,
                    transitionReason: "quadratic_prefill_guard_exceeded",
                    estimatedBytes: 128 * 1024 * 1024
                ),
            ]
        )
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let guardCard = try #require(foundation.dashboardCards.first(where: { $0.id == "guards" }))

        #expect(guardCard.value == "1")
        #expect(guardCard.detail == "Quadratic prefill guard exceeded")
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
        let hasConnectedSetting = foundation.settings.contains { $0.key == "Connection" && $0.value == "Connected" }
        let hasReconnectLog = foundation.logs.contains { $0.message.contains("Reconnected event stream") }
        #expect(requests.count == 2)
        if requests.count >= 2 {
            #expect(requests[0] == 0)
            #expect(requests[1] == 1)
        }
        #expect(hasConnectedSetting)
        #expect(hasReconnectLog)
        #expect(await metrics.snapshot()["desktop.reconnect_success_ms"] != nil)
    }

    @Test("subscription reconnect reapplies stored gateway access for the selected running server session")
    @MainActor
    func subscriptionReconnectReappliesStoredGatewayAccessForSelectedRunningServerSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: "melix_sk_reconnect"
            )
        )

        await viewModel.start()
        var initialApplyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.count < 1, initialApplyAttempts < 200 {
            initialApplyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        await client.finishLatestSubscription()

        var reconnectApplyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.count < 2, reconnectApplyAttempts < 200 {
            reconnectApplyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 2)
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
        let hasSessionsCard = foundation.dashboardCards.contains { card in
            card.id == "sessions" && card.value == "1"
        }
        let hasWarmTextModel = foundation.models.contains { model in
            model.modelID == "melix-dev-text" && model.stateText == "Warm"
        }
        #expect(viewModel.statusTitle == "Melix Degraded")
        #expect(hasSessionsCard)
        #expect(hasWarmTextModel)
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
        await client.sendRequestProgress(
            requestID: "request-42",
            phase: .requestPrefilling,
            prefillProcessedTokens: 12,
            prefillTotalTokens: 24,
            activeRequests: 2,
            waitingRequests: 1,
            restoreStage: "partial",
            cachePressure: 0.25
        )
        await client.sendHeartbeat()
        await client.sendLog(level: "error", message: "thermal pressure")
        try await waitForRuntimeViewModelCondition("streamed events should update dashboard state") {
            let foundation = viewModel.desktopFoundationState
            return viewModel.lastError == "thermal pressure"
                && foundation.logs.contains(where: { $0.message == "Heartbeat" })
                && foundation.logs.contains(where: { $0.message == "thermal pressure" })
        }

        let foundation = viewModel.desktopFoundationState
        let hasSessionsCard = foundation.dashboardCards.contains { card in
            card.id == "sessions" && card.value == "1"
        }
        let hasCacheCard = foundation.dashboardCards.contains { card in
            card.id == "cache" && card.detail == "L1 / L2"
        }
        let hasMemoryCard = foundation.dashboardCards.contains { card in
            card.id == "memory" && card.detail.contains("8")
        }
        let hasSessionUpdateLog = foundation.logs.contains { $0.message == "Session session-42 updated" }
        let hasCacheLog = foundation.logs.contains { $0.message == "Cache summary updated" }
        let hasResourcePressureLog = foundation.logs.contains {
            $0.message == "Resource pressure in metal" && $0.level == "warning"
        }
        let hasPrefillLog = foundation.logs.contains {
            $0.message == "request-42 prefilling • 50% 12/24 • active 2 • waiting 1 • restore partial • pressure 0.25"
        }
        let hasHeartbeatLog = foundation.logs.contains { $0.message == "Heartbeat" }
        let hasPrefillMetric = foundation.benchMetrics.contains {
            $0.name == "scheduler.prefill_progress_pct" && $0.value == "50.00"
        }
        let hasCachePressureMetric = foundation.benchMetrics.contains {
            $0.name == "scheduler.cache_pressure" && $0.value == "0.25"
        }
        #expect(viewModel.statusTitle == "Melix Draining")
        #expect(viewModel.lastError == "thermal pressure")
        #expect(hasSessionsCard)
        #expect(hasCacheCard)
        #expect(hasMemoryCard)
        #expect(hasSessionUpdateLog)
        #expect(hasCacheLog)
        #expect(hasResourcePressureLog)
        #expect(hasPrefillLog)
        #expect(hasHeartbeatLog)
        #expect(hasPrefillMetric)
        #expect(hasCachePressureMetric)
    }

    @Test("request progress events map all operator-facing phase labels")
    @MainActor
    func requestProgressEventsMapAllOperatorFacingPhaseLabels() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendRequestProgress(
            requestID: "request-queue",
            phase: .requestQueued,
            restoreStage: "restored"
        )
        await client.sendRequestProgress(
            requestID: "request-admitted",
            phase: .requestAdmitted
        )
        await client.sendRequestProgress(
            requestID: "request-decode",
            phase: .requestDecoding
        )
        await client.sendRequestProgress(
            requestID: "request-complete",
            phase: .requestCompleted
        )
        await client.sendRequestProgress(
            requestID: "request-abort",
            phase: .requestAborted
        )
        await client.sendRequestProgress(
            requestID: "request-fail",
            phase: .requestFailed
        )
        await client.sendRequestProgress(
            requestID: "request-reject",
            phase: .requestRejected
        )
        await client.sendRequestProgress(
            requestID: "request-unknown",
            phase: .UNRECOGNIZED(-1),
            restoreStage: "none"
        )

        try await waitForRuntimeViewModelCondition("all request progress labels should be logged") {
            let messages = viewModel.desktopFoundationState.logs.map(\.message)
            return messages.contains("request-queue queued • restore restored")
                && messages.contains("request-admitted admitted")
                && messages.contains("request-decode decoding")
                && messages.contains("request-complete completed")
                && messages.contains("request-abort aborted")
                && messages.contains("request-fail failed")
                && messages.contains("request-reject rejected")
                && messages.contains("request-unknown unknown • restore none")
        }

        let foundation = viewModel.desktopFoundationState
        let hasRestoreStageMetric = foundation.benchMetrics.contains {
            $0.name == "scheduler.restore_stage_code" && $0.value == "0.00"
        }
        #expect(hasRestoreStageMetric)
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
                    publishedRepo: "",
                    targetRepo: "melix/adapters/melix-dev-adapter",
                    activationStatus: "activated",
                    derivedModelID: "melix-dev-text-lora-adapter",
                    derivedModelPath: "/tmp/melix-derived/model"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await viewModel.activateLatestAdapter()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "melix/adapters/melix-dev-adapter",
                    targetRepo: "melix/adapters/melix-dev-adapter",
                    activationStatus: "activated",
                    derivedModelID: "melix-dev-text-lora-adapter",
                    derivedModelPath: "/tmp/melix-derived/model"
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
        #expect(await client.recordedActions.contains("operation:activate_adapter:melix-dev-text"))
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
        #expect(viewModel.adapterPackages.first?.statusText == "Published")
        #expect(viewModel.adapterPackages.first?.activationStatusText == "Activated")
        #expect(viewModel.adapterPackages.first?.derivedModelID == "melix-dev-text-lora-adapter")
        #expect(viewModel.adapterPackages.first?.responseOnlyEnabled == true)
        #expect(viewModel.adapterPackages.first?.publishedRepo == "melix/adapters/melix-dev-adapter")
        #expect(viewModel.trainingHistory.first?.datasetURI == "datasets/melix-dev")
        #expect(await metrics.snapshot()["menu.model_info_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_doctor_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_bench_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_operation_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_ops_refresh_ms"] != nil)
    }

    @Test("fetch model info surfaces OCR profile defaults from the active snapshot")
    @MainActor
    func fetchModelInfoSurfacesOCRProfileDefaultsFromActiveSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-ocr"
        model.kind = "ocr"
        model.state = .modelDiscovered
        model.settings.alias = "Melix Dev OCR"
        model.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.settings.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.settings.ext["ocr_stop_sequences"] = "<ocr:end>"
        snapshot.models = [model]

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "ocr"
        info.maxContext = 4096
        info.supportedParsers = ["text"]
        info.supportedModalities = ["image"]

        await client.configureSnapshot(snapshot)
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.fetchModelInfo(modelID: "melix-dev-ocr")

        #expect(viewModel.selectedModelInfo?.modelID == "melix-dev-ocr")
        #expect(viewModel.selectedModelInfo?.ocrPromptProfileText == "ocr-default-v1")
        #expect(viewModel.selectedModelInfo?.ocrSamplingProfileText == "ocr-deterministic")
        #expect(viewModel.selectedModelInfo?.ocrStopSequencesText == "<ocr:end>")
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

    @Test("quantize action stores typed quantization summary")
    @MainActor
    func quantizeActionStoresTypedQuantizationSummary() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "quantize",
                outputPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact",
                manifestJSON: #"""
                {
                  "operation": "quantize",
                  "calibration": {
                    "sample_count": 32
                  }
                }
                """#,
                quantProfileID: "q6",
                artifactKind: "quantized_model_bundle",
                manifestPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json",
                artifactBytes: 256,
                smokeTestPassed: true
            ),
            forNamedOperation: "quantize"
        )

        await viewModel.start()
        viewModel.selectedQuantizationProfileID = "q6"
        await viewModel.quantizePrimaryModel()

        #expect(viewModel.lastModelOperation?.operation == "quantize")
        #expect(viewModel.lastModelOperation?.quantProfileID == "q6")
        #expect(viewModel.lastModelOperation?.artifactKind == "quantized_model_bundle")
        #expect(viewModel.lastModelOperation?.manifestPath == "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json")
        #expect(viewModel.lastModelOperation?.artifactBytes == 256)
        #expect(viewModel.lastModelOperation?.smokeTestPassed == true)
        #expect(viewModel.lastModelOperation?.calibrationSampleCount == 32)
    }

    @Test("upload action links the latest quantized artifact when available")
    @MainActor
    func uploadActionLinksLatestQuantizedArtifact() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "quantize",
                outputPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact",
                manifestJSON: #"""
                {
                  "operation": "quantize",
                  "calibration": {
                    "sample_count": 48
                  }
                }
                """#,
                quantProfileID: "q5",
                artifactKind: "quantized_model_bundle",
                manifestPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json",
                artifactBytes: 256,
                smokeTestPassed: true
            ),
            forNamedOperation: "quantize"
        )

        await viewModel.start()
        await viewModel.quantizePrimaryModel()
        await viewModel.uploadPrimaryModel()

        let uploadRequest = try #require(await client.recordedModelOperationRequests.last)
        #expect(uploadRequest.operation == "upload")
        #expect(uploadRequest.ext["artifact_kind"] == "model")
        #expect(uploadRequest.ext["artifact_path"] == "/tmp/melix-quantize/model-ops-0001/quantize.artifact")
        #expect(uploadRequest.ext["quantization_manifest_path"] == "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json")
        #expect(uploadRequest.ext["quant_profile_id"] == "q5")
        #expect(uploadRequest.ext["target_repo"] == "melix/upload-target")
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
        #expect(adapter.activationStatusText == "Pending activation")
        #expect(adapter.targetRepo.isEmpty)
        #expect(adapter.responseOnlyEnabled)
        #expect(adapter.gradientCheckpointingEnabled)
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

        let hasReadyTextCapability = viewModel.chatCapabilities.contains { $0.id == "text" && $0.isReady }
        let hasReadyOCRCapability = viewModel.chatCapabilities.contains { $0.id == "ocr" && $0.isReady }
        let hasPendingVLMBinding = viewModel.chatCapabilities.contains { $0.id == "vlm" && $0.isReady == false }
        let hasReadyTranscriptionCapability = viewModel.chatCapabilities.contains { $0.id == "transcription" && $0.isReady }
        let hasPendingSpeechCapability = viewModel.chatCapabilities.contains { $0.id == "speech" && $0.isReady == false }
        #expect(hasReadyTextCapability)
        #expect(hasReadyOCRCapability)
        #expect(hasPendingVLMBinding)
        #expect(hasReadyTranscriptionCapability)
        #expect(hasPendingSpeechCapability)
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
    timeout: Duration = .seconds(2),
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
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = quantProfileID
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
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = quantProfileID
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
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = quantProfileID
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

private struct ThrowingOperatorSessionStore: OperatorSessionStoring {
    let throwOnLoad: Bool
    let throwOnSave: Bool

    func load() throws -> OperatorSessionState? {
        if throwOnLoad {
            throw MenuBarTestError(description: "restore-failed")
        }
        return nil
    }

    func save(_ state: OperatorSessionState) throws {
        _ = state
        if throwOnSave {
            throw MenuBarTestError(description: "persist-failed")
        }
    }
}

private struct ThrowingServerSessionAPIKeyStore: ServerSessionAPIKeyStoring {
    let throwOnLoad: Bool
    let throwOnSave: Bool
    let loadPrimaryKeyValue: String?

    func loadPrimaryKey(serverSessionID: String) throws -> ServerSessionPrimaryAPIKeyRecord? {
        if throwOnLoad {
            throw MenuBarTestError(description: "load-key-failed")
        }
        guard let loadPrimaryKeyValue else {
            return nil
        }
        return ServerSessionPrimaryAPIKeyRecord(
            serverSessionID: serverSessionID,
            keyID: "primary",
            primaryKey: loadPrimaryKeyValue,
            updatedAt: Date()
        )
    }

    func savePrimaryKey(
        serverSessionID: String,
        primaryKey: String,
        keyID: String
    ) throws -> ServerSessionPrimaryAPIKeyRecord {
        if throwOnSave {
            throw MenuBarTestError(description: "save-key-failed")
        }
        return ServerSessionPrimaryAPIKeyRecord(
            serverSessionID: serverSessionID,
            keyID: keyID,
            primaryKey: primaryKey,
            updatedAt: Date()
        )
    }
}

private func makeSnapshot(
    serverState: Melix_Controlplane_V1_ServerState,
    models: [Melix_Controlplane_V1_ModelSummary],
    gatewayAccess: Melix_Controlplane_V1_GatewayAccessSummary? = nil
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = serverState
    snapshot.models = models
    if let gatewayAccess {
        snapshot.gatewayAccess = gatewayAccess
    }
    return snapshot
}

private func makeGatewayAccessSummary(
    mode: Melix_Controlplane_V1_GatewayAccessMode,
    sharedAccessEnabled: Bool,
    acceptedApiKeyCount: UInt32,
    keyHints: [String]
) -> Melix_Controlplane_V1_GatewayAccessSummary {
    var summary = Melix_Controlplane_V1_GatewayAccessSummary()
    summary.mode = mode
    summary.sharedAccessEnabled = sharedAccessEnabled
    summary.sharedAccessReady = keyHints.isEmpty == false
    summary.requiredHeader = mode == .apiKeys ? .xApiKey : .none
    summary.acceptedApiKeyCount = acceptedApiKeyCount
    summary.keys = keyHints.enumerated().map { offset, hint in
        var key = Melix_Controlplane_V1_GatewayAccessKeySummary()
        key.keyID = "key-\(offset + 1)"
        key.label = hint
        key.tokenHint = hint
        return key
    }
    return summary
}

private func makeModelSummary(
    modelID: String = "melix-dev-text",
    state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = "",
    pinRequested: Bool = false,
    pinned: Bool = false,
    ttlSeconds: UInt32 = 0,
    estimatedBytes: UInt64 = 0,
    inflightRequests: UInt64 = 0,
    memoryPolicy: Melix_Controlplane_V1_MemoryResidencyPolicy = .memoryResidencyEvictable,
    adaptiveThinkingMode: String = "",
    adaptiveThinkingBudgetTokens: UInt32 = 0
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    model.state = state
    model.features = ["chat"]
    model.maxContext = 8192
    model.pinned = pinned
    model.inflightRequests = inflightRequests
    model.estimatedBytes = estimatedBytes
    model.settings.pinOnLoad = pinRequested
    model.settings.ttlSeconds = ttlSeconds
    model.settings.memoryPolicy = memoryPolicy
    model.settings.adaptiveThinking.mode = adaptiveThinkingMode
    model.settings.adaptiveThinking.budgetTokens = adaptiveThinkingBudgetTokens
    model.residency.pinRequested = pinRequested
    model.residency.pinned = pinned
    model.residency.ttlSeconds = ttlSeconds
    model.residency.policy = memoryPolicy
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
        adaptiveThinkingText: "Adaptive • 192 tok",
        accelerationModeText: "Baseline",
        accelerationProfileID: "",
        residencyText: "Warm • Evictable",
        memoryText: "No live footprint reported",
        memoryAlertText: ""
    )
}

private func makeNamedModelOperationResult(
    operation: String,
    outputPath: String,
    manifestJSON: String,
    quantProfileID: String = "",
    artifactKind: String = "",
    manifestPath: String = "",
    artifactBytes: UInt64 = 0,
    smokeTestPassed: Bool = false
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.ok = true
    result.operation = operation
    result.jobID = "job-\(operation)"
    result.stage = "completed"
    result.pct = 1
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    if !quantProfileID.isEmpty {
        result.quantProfile = Melix_Controlplane_V1_QuantizationProfile()
        result.quantProfile.algorithm = "oq"
        result.quantProfile.schemaVersion = "melix.quant_profile.v1"
        result.quantProfile.quantProfileID = quantProfileID
        result.quantProfile.weightQuant = quantProfileID
        result.quantProfile.kvQuant = "q8"
    }
    if !artifactKind.isEmpty {
        result.artifact = Melix_Controlplane_V1_ModelOperationArtifact()
        result.artifact.schemaVersion = "melix.quantized_bundle.v1"
        result.artifact.artifactKind = artifactKind
        result.artifact.bundlePath = outputPath
        result.artifact.manifestPath = manifestPath
        result.artifact.artifactBytes = artifactBytes
        result.artifact.manifestBytes = UInt64(manifestJSON.utf8.count)
        result.artifact.servingCompatible = true
        result.artifact.smokeTestRequested = true
        result.artifact.smokeTestPassed = smokeTestPassed
        result.artifact.runtime = "mlx_text"
    }
    return result
}

private func makeRegistrySnapshotManifest(
    publishedRepo: String,
    targetRepo: String,
    activationStatus: String = "pending_activation",
    derivedModelID: String = "",
    derivedModelPath: String = "",
    status: String? = nil
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
          "activation_status": "\#(activationStatus)",
          "derived_model_id": "\#(derivedModelID)",
          "derived_model_path": "\#(derivedModelPath)",
          "exportable_state": "ready",
          "published_state": "\#(publishedRepo.isEmpty ? "not_published" : "published")",
          "target_repo": "\#(targetRepo)",
          "published_repo": "\#(publishedRepo)",
          "status": "\#(status ?? (publishedRepo.isEmpty ? (activationStatus == "activated" ? "activated" : "completed") : "published"))",
          "response_only": true,
          "gradient_checkpointing": false,
          "training_duration_ms": 1420.0,
          "activation_duration_ms": \#(derivedModelID.isEmpty ? "0.0" : "321.0"),
          "adapter_publish_ms": 118.0
        }
      ],
      "derived_models": [
        {
          "model_id": "\#(derivedModelID)",
          "model_path": "\#(derivedModelPath)",
          "adapter_set_hash": "\#(derivedModelID.isEmpty ? "" : "adapter-alpha")",
          "source_model": "melix-dev-text",
          "activation_mode": "\#(derivedModelID.isEmpty ? "" : "fused_derived_model")",
          "status": "\#(derivedModelID.isEmpty ? "" : "activated")"
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
          "activation_status": "pending_activation",
          "derived_model_id": "",
          "derived_model_path": "",
          "exportable_state": "ready",
          "published_state": "not_published",
          "target_repo": "",
          "published_repo": "",
          "status": "queued_for_publish",
          "response_only": true,
          "gradient_checkpointing": true,
          "training_duration_ms": 950,
          "activation_duration_ms": 0,
          "adapter_publish_ms": 0
        }
      ],
      "derived_models": []
    }
    """#
}
