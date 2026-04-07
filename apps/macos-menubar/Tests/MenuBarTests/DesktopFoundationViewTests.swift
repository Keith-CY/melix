import AppKit
import SwiftUI
import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Desktop Foundation View", .serialized)
struct DesktopFoundationViewTests {
    @Test("root view renders the desktop foundation shell")
    @MainActor
    func rootViewRendersDesktopFoundationShell() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopFoundationRootView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .chat)
    }

    @Test("title-bar tabs fit a compact height budget")
    @MainActor
    func titleBarTabsFitACompactHeightBudget() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()

        let hosted = hostView(DesktopWorkspaceTitleBarTabsView(viewModel: viewModel))

        #expect(hosted.fittingSize.height <= DesktopShellChromeMetrics.titleBarTabHeightBudget)
        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .chat)
    }

    @Test("root view renders workspace content without in-content shell chrome")
    @MainActor
    func rootViewRendersWorkspaceContentWithoutInContentShellChrome() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopFoundationRootView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Melix") == false)
    }

    @Test("workspace server surface renders projected gateway config state")
    @MainActor
    func workspaceServerSurfaceRendersProjectedGatewayConfigState() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
        runtimeSession.serverSessionID = "server-session-1"
        runtimeSession.lifecycleState = .ready
        runtimeSession.powerState = .active
        runtimeSession.wakeReason = .initialBoot
        snapshot.runtimeSessions = [runtimeSession]
        var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
        listener.serverSessionID = "server-session-1"
        listener.requestedHost = "0.0.0.0"
        listener.requestedPort = 18080
        listener.effectiveHost = "127.0.0.1"
        listener.effectivePort = 11_434
        listener.servedModelID = "melix-dev-text"
        listener.rateLimitPerMinute = 240
        listener.timeoutSeconds = 90
        listener.source = .operatorOverride
        listener.activeBinding = true
        listener.requiresRestart = true
        snapshot.gatewayConfig.listeners = [listener]
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.servedModelID = "melix-dev-text"
        servingDefaults.requestedTemperature = 0.33
        servingDefaults.requestedTopP = 0.92
        servingDefaults.requestedMaxTokens = 384
        servingDefaults.requestedStreamIntervalTokens = 3
        servingDefaults.requestedMaxConcurrentRequests = 5
        servingDefaults.requestedConcurrentProcessingEnabled = true
        servingDefaults.requestedPrefillBatchSize = 3
        servingDefaults.requestedCompletionBatchSize = 2
        servingDefaults.effectiveTemperature = 0.2
        servingDefaults.effectiveTopP = 0.88
        servingDefaults.effectiveMaxTokens = 512
        servingDefaults.effectiveStreamIntervalTokens = 3
        servingDefaults.effectiveMaxConcurrentRequests = 5
        servingDefaults.effectiveConcurrentProcessingEnabled = true
        servingDefaults.effectivePrefillBatchSize = 3
        servingDefaults.effectiveCompletionBatchSize = 2
        servingDefaults.source = .operatorOverride
        servingDefaults.modelOverrideApplied = true
        snapshot.servingDefaults.sessions = [servingDefaults]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .server)
        #expect(renderedTexts.contains("0.0.0.0"))
        #expect(renderedTexts.contains("18,080"))
        #expect(renderedTexts.contains("240"))
        #expect(renderedTexts.contains("90"))
        #expect(viewModel.selectedServerSession?.effectiveBaseURL == "http://127.0.0.1:11434/v1")
        #expect(viewModel.selectedServerSession?.gatewayConfigRequiresRestart == true)
        #expect(viewModel.selectedServerSession?.gatewayConfigSourceText == "Operator Override")
        #expect(viewModel.selectedServerSession?.servingDefaults.streamIntervalTokens == 3)
        #expect(viewModel.selectedServerSession?.servingDefaults.effectiveMaxTokens == 512)
        #expect(viewModel.selectedServerSession?.servingDefaults.modelOverrideApplied == true)
    }

    @Test("workspace server surface renders projected serving defaults values")
    @MainActor
    func workspaceServerSurfaceRendersProjectedServingDefaultsValues() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.servedModelID = "melix-dev-text"
        servingDefaults.requestedTemperature = 0.44
        servingDefaults.requestedTopP = 0.91
        servingDefaults.requestedMaxTokens = 320
        servingDefaults.requestedStreamIntervalTokens = 2
        servingDefaults.requestedMaxConcurrentRequests = 6
        servingDefaults.requestedConcurrentProcessingEnabled = false
        servingDefaults.requestedPrefillBatchSize = 4
        servingDefaults.requestedCompletionBatchSize = 3
        servingDefaults.effectiveTemperature = 0.25
        servingDefaults.effectiveTopP = 0.85
        servingDefaults.effectiveMaxTokens = 512
        servingDefaults.effectiveStreamIntervalTokens = 2
        servingDefaults.effectiveMaxConcurrentRequests = 1
        servingDefaults.effectiveConcurrentProcessingEnabled = false
        servingDefaults.effectivePrefillBatchSize = 1
        servingDefaults.effectiveCompletionBatchSize = 1
        servingDefaults.source = .environmentDefaults
        snapshot.servingDefaults.sessions = [servingDefaults]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("0.44"))
        #expect(renderedTexts.contains("0.91"))
        #expect(renderedTexts.contains("320"))
        #expect(renderedTexts.contains("2"))
        #expect(renderedTexts.contains("6"))
        #expect(viewModel.selectedServerSession?.servingDefaults.sourceText == "Environment Defaults")
    }

    @Test("command center view renders global operator summaries")
    @MainActor
    func commandCenterViewRendersGlobalOperatorSummaries() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopCommandCenterView(
                foundation: viewModel.desktopFoundationState,
                chatSessions: viewModel.chatSessions,
                serverSessions: viewModel.serverSessions
            )
        )

        #expect(view.subviews.isEmpty == false)
    }

    @Test("workspace shell renders dismissible update banners from shared signal state")
    @MainActor
    func workspaceShellRendersDismissibleUpdateBanner() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            productInstallStateProvider: StubProductInstallStateProvider(
                updateStatusResponse: ProductUpdateStatus(
                    summary: "Update available: 0.2.0",
                    detail: "Current 0.1.0 on stable",
                    isAvailable: true,
                    checkSucceeded: true
                ),
                startupDiagnosticResponse: nil
            )
        )

        await viewModel.start()

        let initialView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let banner = try #require(viewModel.desktopBannerState)

        #expect(initialView.subviews.isEmpty == false)
        #expect(banner.isDismissible)
        #expect(banner.title == "Update available: 0.2.0")
        #expect(banner.detail == "Current 0.1.0 on stable")

        viewModel.dismissDesktopBanner(id: banner.id)

        let dismissedView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let dismissedTexts = renderedTextValues(in: dismissedView)
        #expect(dismissedTexts.contains("Update available: 0.2.0") == false)
    }

    @Test("settings tab renders typed tooling settings rows")
    @MainActor
    func settingsTabRendersTypedToolingSettingsRows() async throws {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel(), ModelCatalog.devEmbeddingModel()]
        snapshot.toolingSettings.embedding.modelID = "melix-dev-embed"
        snapshot.toolingSettings.embedding.backendID = "bert-v1"
        snapshot.toolingSettings.embedding.familyID = "bert"
        snapshot.toolingSettings.embedding.modelState = .modelWarm
        snapshot.toolingSettings.embedding.loaded = true
        snapshot.toolingSettings.embedding.preloaded = true
        snapshot.toolingSettings.builtinToolParserModes = ["text", "json", "qwen"]
        snapshot.toolingSettings.mcpDefaultParserMode = "json"
        snapshot.toolingSettings.mcpConfigPath = "/tmp/mcp-tools.json"
        snapshot.toolingSettings.mcpEnabledSourceCount = 1
        snapshot.toolingSettings.mcpResolvedToolCount = 2
        var gatewayConfigPath = Melix_Controlplane_V1_ToolingConfigPathSummary()
        gatewayConfigPath.pathID = "gateway_config_store_path"
        gatewayConfigPath.path = "/tmp/gateway-config.json"
        var servingDefaultsPath = Melix_Controlplane_V1_ToolingConfigPathSummary()
        servingDefaultsPath.pathID = "gateway_serving_defaults_store_path"
        servingDefaultsPath.path = "/tmp/gateway-serving-defaults.json"
        snapshot.toolingSettings.configPaths = [gatewayConfigPath, servingDefaultsPath]
        snapshot.toolingSettings.additionalArguments = ["--config", "/tmp/melix.json"]

        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-settings",
            features: ["xpc", "mcp-tools"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let view = hostView(DesktopSettingsTabView(foundation: foundation))

        #expect(view.subviews.isEmpty == false)
        #expect(foundation.settings.contains { $0.key == "Embedding Model" && $0.value == "melix-dev-embed" })
        #expect(foundation.settings.contains { $0.key == "MCP Config" && $0.value == "/tmp/mcp-tools.json" })
        #expect(foundation.settings.contains { $0.key == "Gateway Config Store" && $0.value == "/tmp/gateway-config.json" })
        #expect(foundation.settings.contains { $0.key == "Built-in Tool Parsers" && $0.value == "text, json, qwen" })
        #expect(foundation.settings.contains { $0.key == "Boot Arguments" && $0.value == "--config /tmp/melix.json" })
    }

    @Test("settings tab normalizes tooling state labels across model states and config paths")
    @MainActor
    func settingsTabNormalizesToolingStateLabelsAcrossModelStatesAndConfigPaths() async throws {
        let expectedStateDetails: [(Melix_Controlplane_V1_ModelState, String)] = [
            (.modelDiscovered, "Discovered"),
            (.modelWarm, "Warm"),
            (.modelPinned, "Pinned"),
            (.modelLoading, "Loading"),
            (.modelEvicting, "Evicting"),
            (.modelUnloaded, "Unloaded"),
            (.modelFailed, "Failed"),
            (.UNRECOGNIZED(-1), "Unknown"),
        ]

        for (state, expectedPrefix) in expectedStateDetails {
            var snapshot = Melix_Controlplane_V1_ServerSnapshot()
            snapshot.serverState = .serverReady
            snapshot.models = [ModelCatalog.devEmbeddingModel()]
            snapshot.toolingSettings.embedding.modelID = "melix-dev-embed"
            snapshot.toolingSettings.embedding.modelState = state
            snapshot.toolingSettings.embedding.preloaded = false
            var metricsPath = Melix_Controlplane_V1_ToolingConfigPathSummary()
            metricsPath.pathID = "control_plane_metrics_path"
            metricsPath.path = "/tmp/control-plane-metrics.prom"
            var customPath = Melix_Controlplane_V1_ToolingConfigPathSummary()
            customPath.pathID = "custom_runtime_path"
            customPath.path = "/tmp/runtime"
            snapshot.toolingSettings.configPaths = [metricsPath, customPath]

            let foundation = DesktopFoundationState.build(
                statusTitle: "Melix Ready",
                serverStateText: "Ready",
                connectionStateText: "Connected",
                connectionDetailText: "Snapshot hydrated",
                snapshot: snapshot,
                protocolVersion: "melix.controlplane.v1",
                serverVersion: "0.1.0",
                daemonInstanceID: "daemon-settings-variants",
                features: ["xpc"],
                productUpdateSummary: nil,
                productUpdateDetail: nil,
                lastError: nil,
                recentEvents: []
            )

            #expect(
                foundation.settings.contains {
                    $0.key == "Embedding Preload"
                        && $0.value.hasPrefix(expectedPrefix + " • not preloaded")
                }
            )
            #expect(
                foundation.settings.contains {
                    $0.key == "Control Plane Metrics"
                        && $0.value == "/tmp/control-plane-metrics.prom"
                }
            )
            #expect(
                foundation.settings.contains {
                    $0.key == "custom runtime path" && $0.value == "/tmp/runtime"
                }
            )
        }
    }

    @Test("models tab renders model actions and settings")
    @MainActor
    func modelsTabRendersModelActionsAndSettings() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            )
        )

        #expect(view.subviews.isEmpty == false)
    }

    @Test("models tab exposes explicit disk streaming picker options")
    @MainActor
    func modelsTabExposesExplicitDiskStreamingPickerOptions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        let mirror = Mirror(reflecting: tab)
        let options = try #require(mirror.descendant("diskStreamingModeOptions") as? [(String, String)])

        #expect(options.map(\.0) == ["Disabled", "Prefer Disk", "Require Disk"])
        #expect(options.map(\.1) == ["disabled", "prefer_disk", "require_disk"])
    }

    @Test("models tab exposes explicit cache mode picker options")
    @MainActor
    func modelsTabExposesExplicitCacheModePickerOptions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        let mirror = Mirror(reflecting: tab)
        let options = try #require(mirror.descendant("cacheModeOptions") as? [(String, String)])

        #expect(options.map(\.0) == ["Tiered", "Rotating", "Hybrid"])
        #expect(options.map(\.1) == ["tiered", "rotating", "hybrid"])
    }

    @Test("models tab renders residency memory alerts when a model is guard-blocked")
    @MainActor
    func modelsTabRendersResidencyMemoryAlerts() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeMenuBarModelSummary(
                modelID: "melix-dev-guarded",
                state: .modelFailed,
                transitionReason: "memory_budget_exceeded",
                estimatedBytes: 512 * 1024 * 1024,
                inflightRequests: 2
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let guardedModel = try #require(foundation.models.first)
        let view = hostView(
            DesktopModelsTabView(
                foundation: foundation,
                viewModel: viewModel
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(guardedModel.memoryAlertText == "Memory protection • Memory budget exceeded")
        #expect(guardedModel.memoryText.contains("2 inflight"))
    }

    @Test("models tab buttons dispatch latency profile and load actions")
    @MainActor
    func modelsTabButtonsDispatchActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        let model = try #require(viewModel.primaryModel)
        await tab.applyLatencyProfile(to: model)
        await tab.toggleModelLoad(for: model)

        let actions = await client.recordedActions
        #expect(actions.contains("settings:melix-dev-text"))
        #expect(actions.contains("load:melix-dev-text"))
    }

    @Test("models tab renders registry root management without crashing")
    @MainActor
    func modelsTabRendersRegistryRootManagement() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [
                        MenuBarRegistryRootFixture(
                            id: "root-a",
                            path: "/tmp/root-a",
                            order: 1,
                            discoveredModelIDs: ["registry-model-a"]
                        ),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let view = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.registryRoots.first?.rootPath == "/tmp/root-a")
        #expect(viewModel.registryRootSummaryText.contains("environment roots"))
    }

    @Test("models tab registry root actions dispatch add move remove and rescan requests")
    @MainActor
    func modelsTabRegistryRootActionsDispatchAddMoveRemoveAndRescanRequests() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [
                        MenuBarRegistryRootFixture(id: "root-a", path: "/tmp/root-a", order: 1),
                        MenuBarRegistryRootFixture(id: "root-b", path: "/tmp/root-b", order: 2),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        viewModel.registryRootPathDraft = "/tmp/root-c"

        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        await tab.addRegistryRoot()
        await tab.moveRegistryRootUp(RuntimeRegistryRootState(
            id: "root-b",
            rootPath: "/tmp/root-b",
            rootOrder: 2,
            accessible: true,
            errorCode: "",
            errorMessage: "",
            discoveredModelIDs: []
        ))
        await tab.removeRegistryRoot(RuntimeRegistryRootState(
            id: "root-a",
            rootPath: "/tmp/root-a",
            rootOrder: 1,
            accessible: true,
            errorCode: "",
            errorMessage: "",
            discoveredModelIDs: []
        ))
        await tab.rescanRegistryRoots()

        let requests = await client.recordedModelOperationRequests.filter { $0.operation == "registry_snapshot" }
        #expect(requests.count == 5)
        #expect(requests[1].ext["melix.registry_roots_json"] == #"["/tmp/root-a","/tmp/root-b","/tmp/root-c"]"#)
        #expect(requests[2].ext["melix.registry_roots_json"] == #"["/tmp/root-b","/tmp/root-a","/tmp/root-c"]"#)
        #expect(requests[3].ext["melix.registry_roots_json"] == #"["/tmp/root-b","/tmp/root-c"]"#)
        #expect(requests[4].ext["melix.registry_roots_json"] == #"["/tmp/root-b","/tmp/root-c"]"#)
        #expect(requests[4].ext["melix.registry_rescan"] == "true")
    }

    @Test("models tab form buttons dispatch apply reset inspect and load actions")
    @MainActor
    func modelsTabFormButtonsDispatchActions() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var snapshotModel = Melix_Controlplane_V1_ModelSummary()
        snapshotModel.modelID = "melix-dev-ocr"
        snapshotModel.kind = "ocr"
        snapshotModel.state = .modelDiscovered
        snapshotModel.features = ["ocr", "vision"]
        snapshotModel.maxContext = 4096
        snapshotModel.settings.alias = "Melix Dev OCR"
        snapshot.models = [snapshotModel]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.modelSettingsAliasDraft = "Melix Form Alias"
        viewModel.modelSettingsTypeOverrideDraft = "mlx-form"
        viewModel.modelSettingsTTLDraft = "321"
        viewModel.modelSettingsMemoryBudgetDraft = "65536"
        viewModel.modelSettingsAdaptiveThinkingModeDraft = "adaptive"
        viewModel.modelSettingsAdaptiveThinkingBudgetDraft = "64"
        viewModel.modelSettingsToolParserXMLFallbackDraft = true
        viewModel.modelSettingsOCRSamplingProfileDraft = "ocr-operator"
        viewModel.modelSettingsOCRTemperatureDraft = "0.05"
        viewModel.modelSettingsOCRTopPDraft = "0.82"
        viewModel.modelSettingsOCRMaxTokensDraft = "192"

        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        let model = try #require(viewModel.primaryModel)

        tab.latencyProfileAction(for: model)()
        tab.applyPrimaryModelSettingsAction()()
        tab.resetPrimaryModelSettingsAction()()
        tab.inspectPrimaryModelAction()()
        tab.toggleModelLoadAction(for: model)()

        try await Task.sleep(for: .milliseconds(50))

        let actions = await client.recordedActions
        #expect(actions.contains("settings:melix-dev-ocr"))
        #expect(actions.contains("info:melix-dev-ocr"))
        #expect(actions.contains("load:melix-dev-ocr"))
        #expect(viewModel.modelSettingsAliasDraft == viewModel.primaryModel?.alias)
    }

    @Test("models tab renders OCR sampling controls when the primary model is OCR")
    @MainActor
    func modelsTabRendersOCRSamplingControlsForOCRModels() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var snapshotModel = Melix_Controlplane_V1_ModelSummary()
        snapshotModel.modelID = "melix-dev-ocr"
        snapshotModel.kind = "ocr"
        snapshotModel.state = .modelDiscovered
        snapshotModel.features = ["ocr", "vision"]
        snapshotModel.maxContext = 4096
        snapshotModel.settings.alias = "Melix Dev OCR"
        snapshot.models = [snapshotModel]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.modelSettingsOCRSamplingProfileDraft = "ocr-operator"
        viewModel.modelSettingsOCRTemperatureDraft = "0.05"
        viewModel.modelSettingsOCRTopPDraft = "0.82"
        viewModel.modelSettingsOCRMaxTokensDraft = "192"

        let view = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            )
        )
        let values = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(values.contains("ocr-operator"))
        #expect(values.contains("0.05"))
        #expect(values.contains("0.82"))
        #expect(values.contains("192"))
    }

    @Test("agent integration exports panel renders populated and empty states")
    @MainActor
    func agentIntegrationExportsPanelRendersPopulatedAndEmptyStates() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        _ = hostView(
            DesktopAgentIntegrationExportsPanel(
                exports: viewModel.agentIntegrationExports,
                selectedTarget: Binding(
                    get: { viewModel.selectedAgentIntegrationTarget },
                    set: { viewModel.selectAgentIntegrationTarget($0) }
                )
            )
        )
        _ = hostView(
            DesktopAgentIntegrationExportsPanel(
                exports: [],
                selectedTarget: .constant(.openAICompatible)
            )
        )

        #expect(viewModel.agentIntegrationExports.isEmpty == false)
        #expect(viewModel.selectedAgentIntegrationExport?.target == .openAICompatible)
    }

    @Test("server workspace renders the bound integration export panel")
    @MainActor
    func serverWorkspaceRendersTheBoundIntegrationExportPanel() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let selectedExport = try #require(viewModel.selectedAgentIntegrationExport)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.agentIntegrationExports.isEmpty == false)
        #expect(selectedExport.target == .openAICompatible)
    }

    @Test("server workspace renders lifecycle controls and idle policy details")
    @MainActor
    func serverWorkspaceRendersLifecycleControlsAndIdlePolicyDetails() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
        snapshot.runtimeSessions = [
            makeDesktopRuntimeSession(
                lifecycleState: .paused,
                powerState: .active,
                wakeReason: .policyApply,
                idleTimerSeconds: 180,
                autoSleepEnabled: true,
                lightSleepAfterSeconds: 300,
                deepSleepAfterSeconds: 900
            )
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let values = renderedTextValues(in: view)
        let notice = try #require(viewModel.selectedServerSession?.lifecycleBannerState)
        let session = try #require(viewModel.selectedServerSession)

        #expect(view.subviews.isEmpty == false)
        #expect(values.contains("300"))
        #expect(values.contains("900"))
        #expect(session.canPause == false)
        #expect(session.canResume)
        #expect(session.canWake == false)
        #expect(session.canStop)
        #expect(notice.title.contains("Paused"))
        #expect(notice.severity == .warning)
        #expect(viewModel.selectedServerSession?.idlePolicySummaryText == "Auto sleep enabled • light after 300s • deep after 900s")
    }

    @Test("server workspace renders stopped lifecycle banner and start control")
    @MainActor
    func serverWorkspaceRendersStoppedLifecycleBannerAndStartControl() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
        snapshot.runtimeSessions = [
            makeDesktopRuntimeSession(
                lifecycleState: .stopped,
                powerState: .stopped,
                wakeReason: .policyApply,
                idleTimerSeconds: 0,
                autoSleepEnabled: false,
                lightSleepAfterSeconds: 0,
                deepSleepAfterSeconds: 0
            )
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let notice = try #require(viewModel.selectedServerSession?.lifecycleBannerState)
        let session = try #require(viewModel.selectedServerSession)

        #expect(view.subviews.isEmpty == false)
        #expect(session.canStart)
        #expect(session.canPause == false)
        #expect(session.canResume == false)
        #expect(session.canWake == false)
        #expect(session.canStop == false)
        #expect(notice.title.contains("Stopped"))
        #expect(notice.detail.contains("serve melix-dev-text"))
    }

    @Test("tools workspace renders lora training controls for local and Hugging Face datasets")
    @MainActor
    func toolsWorkspaceRendersLoRATrainingControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.training)
        viewModel.loraDatasetSourceKind = .localPackage
        _ = hostView(DesktopWorkspaceShellView(viewModel: viewModel))

        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        let hfView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))

        #expect(hfView.subviews.isEmpty == false)
        #expect(viewModel.selectedToolSection == .training)
    }

    @Test("training tool section renders populated adapter activation state and dispatches actions")
    @MainActor
    func trainingToolSectionRendersPopulatedActivationState() async throws {
        let client = FakeControlPlaneXPCClient()
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
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let section = DesktopTrainingToolSectionView(viewModel: viewModel)
        let hosted = hostView(section)

        await section.trainLoRA()
        await section.activateAdapter()
        await section.publishAdapter()

        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.selectedAdapterPackage?.derivedModelID == "melix-dev-text-lora-adapter")
        #expect(await client.recordedActions.contains("operation:train_lora:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:activate_adapter:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
    }

    @Test("api workspace renders authentication and quick-start integration references")
    @MainActor
    func apiWorkspaceRendersAuthenticationAndQuickStartIntegrationReferences() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        let foundation = viewModel.desktopFoundationState

        let authentication = hostView(
            DesktopAPIWorkspaceView(
                viewModel: viewModel,
                foundation: foundation,
                initialSection: .authentication
            )
        )
        let quickStarts = hostView(
            DesktopAPIWorkspaceView(
                viewModel: viewModel,
                foundation: foundation,
                initialSection: .quickStarts
            )
        )

        #expect(authentication.subviews.isEmpty == false)
        #expect(quickStarts.subviews.isEmpty == false)
        #expect(
            desktopAPIAuthenticationReferenceText(
                selectedExport: viewModel.selectedAgentIntegrationExport
            ).contains("Selected target:")
        )
    }

    @Test("api reference tab projects typed onboarding surfaces and endpoints")
    @MainActor
    func apiReferenceTabProjectsTypedOnboardingSurfacesAndEndpoints() throws {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        snapshot.apiOnboarding = makeAPIOnboardingSummary()

        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-api-onboarding",
            features: ["xpc", "api-onboarding"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let view = hostView(DesktopAPIReferenceTabView(foundation: foundation))

        #expect(view.subviews.isEmpty == false)
        #expect(foundation.apiSurfaces.count == 4)
        #expect(foundation.apiSurfaces.contains { $0.id == "openai_compatible" && $0.statusText == "Shipped" })
        #expect(foundation.apiSurfaces.contains { $0.id == "ollama_compatibility" && $0.statusText == "Compatibility Only" })
        #expect(foundation.apiReference.contains { $0.id == "health" && $0.path == "/health" })
        #expect(foundation.apiReference.contains { $0.id == "responses" && $0.path == "/v1/responses" && $0.streaming })
        #expect(foundation.apiReference.contains { $0.id == "messages" && $0.surfaceID == "anthropic_messages" })
    }

    @Test("api quick-start groups use the effective listener URL and compatibility notes")
    @MainActor
    func apiQuickStartGroupsUseTheEffectiveListenerURLAndCompatibilityNotes() throws {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        snapshot.apiOnboarding = makeAPIOnboardingSummary()

        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-api-quick-starts",
            features: ["xpc", "api-onboarding"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let session = DesktopServerSessionState(
            id: "server-session-1",
            title: "Primary Session",
            modelID: "melix-dev-text",
            effectiveHost: "127.0.0.1",
            effectivePort: 11_434,
            authMode: .apiKeys,
            authTokenHint: "desktop-agent",
            sharedAccessState: .enabled,
            accessKeyCount: 1,
            accessKeyHints: ["desktop-agent"],
            lifecycle: .running
        )

        let groups = desktopAPIQuickStartGroups(
            foundation: foundation,
            selectedSession: session
        )
        let groupByID = Dictionary(uniqueKeysWithValues: groups.map { ($0.id, $0) })
        let openAIGroup = try #require(groupByID["openai_compatible"])
        let anthropicGroup = try #require(groupByID["anthropic_messages"])
        let ollamaGroup = try #require(groupByID["ollama_compatibility"])

        #expect(groups.count == 3)
        #expect(openAIGroup.snippets.contains { $0.body.contains("http://127.0.0.1:11434/v1") })
        #expect(openAIGroup.snippets.contains { $0.body.contains("<desktop-agent>") })
        #expect(openAIGroup.snippets.contains { $0.body.contains("\"stream\":true") || $0.body.contains("\"stream\": True") || $0.body.contains("stream: true") })
        #expect(openAIGroup.snippets.contains { $0.body.contains("client.responses.stream") || $0.body.contains("response.iter_lines()") || $0.body.contains("TextDecoderStream") })
        #expect(anthropicGroup.snippets.contains { $0.body.contains("/messages") })
        #expect(anthropicGroup.snippets.contains { $0.body.contains("anthropic-version") })
        #expect(anthropicGroup.snippets.contains { $0.body.contains("\"stream\":true") || $0.body.contains("\"stream\": True") || $0.body.contains("stream: true") })
        #expect(ollamaGroup.note.contains("Native /api/chat"))
        #expect(ollamaGroup.snippets.contains { $0.body.contains("/health") })
        #expect(ollamaGroup.snippets.contains { $0.body.contains("x-api-key") })
    }

    @Test("api onboarding state normalizes unknown surface status text")
    @MainActor
    func apiOnboardingStateNormalizesUnknownSurfaceStatusText() {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        var unknownSurface = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
        unknownSurface.surfaceID = "experimental"
        unknownSurface.title = "Experimental"
        unknownSurface.summary = "Preview-only surface."
        unknownSurface.status = .UNRECOGNIZED(-1)
        snapshot.apiOnboarding.surfaces = [unknownSurface]

        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-api-unknown",
            features: ["xpc", "api-onboarding"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )

        #expect(foundation.apiSurfaces.first?.statusText == "Unknown")
    }

    @Test("api quick-start panel covers empty-surface and missing-session states")
    @MainActor
    func apiQuickStartPanelCoversEmptySurfaceAndMissingSessionStates() throws {
        let emptyFoundation = DesktopFoundationState(
            title: "Melix Ready",
            dashboardCards: [],
            queueLanes: [],
            models: [],
            settings: [],
            logs: [],
            benchMetrics: [],
            apiSurfaces: [],
            apiReference: []
        )
        let session = DesktopServerSessionState(
            id: "server-session-empty-api",
            title: "Primary Session",
            modelID: "melix-dev-text",
            effectiveHost: "127.0.0.1",
            effectivePort: 11_434,
            authMode: .none,
            sharedAccessState: .localOnly,
            lifecycle: .running
        )

        let missingSessionView = hostView(
            DesktopAPIQuickStartPanel(
                foundation: emptyFoundation,
                selectedSession: nil
            )
        )
        let emptySurfaceView = hostView(
            DesktopAPIQuickStartPanel(
                foundation: emptyFoundation,
                selectedSession: session
            )
        )

        #expect(missingSessionView.subviews.isEmpty == false)
        #expect(emptySurfaceView.subviews.isEmpty == false)
        #expect(
            desktopAPIQuickStartGroups(
                foundation: emptyFoundation,
                selectedSession: session
            ).isEmpty
        )
    }

    @Test("api quick-start groups cover bearer disabled and unauthenticated gateway headers")
    @MainActor
    func apiQuickStartGroupsCoverBearerDisabledAndUnauthenticatedGatewayHeaders() {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        snapshot.apiOnboarding = makeAPIOnboardingSummary()

        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-api-auth-branches",
            features: ["xpc", "api-onboarding"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )

        let disabledSession = DesktopServerSessionState(
            id: "disabled-session",
            title: "Disabled Session",
            modelID: "melix-dev-text",
            effectiveHost: "127.0.0.1",
            effectivePort: 11_434,
            authMode: .apiKeys,
            authTokenHint: "desktop-agent",
            sharedAccessState: .configuredDisabled,
            accessKeyHints: ["desktop-agent"],
            lifecycle: .running
        )
        let unauthenticatedSession = DesktopServerSessionState(
            id: "none-session",
            title: "Unauthenticated Session",
            modelID: "melix-dev-text",
            effectiveHost: "127.0.0.1",
            effectivePort: 11_434,
            authMode: .none,
            sharedAccessState: .enabled,
            lifecycle: .running
        )
        let bearerSession = DesktopServerSessionState(
            id: "bearer-session",
            title: "Bearer Session",
            modelID: "melix-dev-text",
            effectiveHost: "127.0.0.1",
            effectivePort: 11_434,
            authMode: .bearerToken,
            authTokenHint: "desktop-agent",
            sharedAccessState: .enabled,
            lifecycle: .running
        )

        let disabledGroups = desktopAPIQuickStartGroups(
            foundation: foundation,
            selectedSession: disabledSession
        )
        let unauthenticatedGroups = desktopAPIQuickStartGroups(
            foundation: foundation,
            selectedSession: unauthenticatedSession
        )
        let bearerGroups = desktopAPIQuickStartGroups(
            foundation: foundation,
            selectedSession: bearerSession
        )

        #expect(
            disabledGroups.first(where: { $0.id == "openai_compatible" })?.snippets.contains {
                $0.body.contains("x-api-key")
            } == false
        )
        #expect(
            disabledGroups.first(where: { $0.id == "ollama_compatibility" })?.snippets.contains {
                $0.body.contains("x-api-key")
            } == false
        )
        #expect(
            unauthenticatedGroups.first(where: { $0.id == "openai_compatible" })?.snippets.contains {
                $0.body.contains("Authorization")
            } == false
        )
        #expect(
            unauthenticatedGroups.first(where: { $0.id == "ollama_compatibility" })?.snippets.contains {
                $0.body.contains("Authorization")
            } == false
        )
        #expect(
            bearerGroups.first(where: { $0.id == "openai_compatible" })?.snippets.contains {
                $0.body.contains("Authorization: Bearer <desktop-agent>")
            } == true
        )
        #expect(
            bearerGroups.first(where: { $0.id == "ollama_compatibility" })?.snippets.contains {
                $0.body.contains("Authorization: Bearer <desktop-agent>")
            } == true
        )
    }

    @Test("agent integration copy helper views render canonical actions")
    @MainActor
    func agentIntegrationCopyHelperViewsRenderCanonicalActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        let selectedExport = try #require(viewModel.selectedAgentIntegrationExport)

        _ = hostView(DesktopAgentIntegrationCopyButtons(export: selectedExport))
        _ = hostView(DesktopAPISelectedExportCopyButton(export: selectedExport))
        _ = hostView(
            DesktopAPIAuthenticationReferenceView(
                referenceText: desktopAPIAuthenticationReferenceText(selectedExport: selectedExport)
            )
        )

        #expect(selectedExport.configFragment.isEmpty == false)
        #expect(selectedExport.shellSnippet.isEmpty == false)
        #expect(
            desktopAPIAuthenticationReferenceText(selectedExport: selectedExport)
                .contains("Selected target:")
        )
    }

    @Test("gateway access summary and auth guidance cover bearer disabled and enabled shared access")
    @MainActor
    func gatewayAccessSummaryAndAuthGuidanceCoverBearerDisabledAndEnabledStates() throws {
        let bearerSession = DesktopServerSessionState(
            id: "bearer-session",
            title: "Bearer Session",
            modelID: "melix-dev-text",
            authMode: .bearerToken,
            authTokenHint: "desktop-agent",
            sharedAccessState: .localOnly,
            accessKeyCount: 1,
            accessKeyHints: ["desktop-agent"],
            lifecycle: .running
        )
        let configuredDisabledSession = DesktopServerSessionState(
            id: "disabled-session",
            title: "Disabled Session",
            modelID: "melix-dev-text",
            sharedAccessState: .configuredDisabled,
            accessKeyCount: 2,
            accessKeyHints: ["desktop-agent", "codex"],
            lifecycle: .running
        )
        let enabledSession = DesktopServerSessionState(
            id: "enabled-session",
            title: "Enabled Session",
            modelID: "melix-dev-text",
            authMode: .apiKeys,
            authTokenHint: "desktop-agent",
            sharedAccessState: .enabled,
            accessKeyCount: 2,
            accessKeyHints: ["desktop-agent", "codex"],
            lifecycle: .running
        )

        _ = hostView(DesktopServerGatewayAccessSummaryView(session: bearerSession))
        _ = hostView(DesktopServerGatewayAccessSummaryView(session: configuredDisabledSession))
        _ = hostView(DesktopServerGatewayAccessSummaryView(session: enabledSession))

        #expect(
            desktopAPIAuthenticationReferenceText(selectedSession: nil, selectedExport: nil)
                == "Select a server session to render auth guidance."
        )
        #expect(
            desktopAPIAuthenticationReferenceText(selectedSession: bearerSession, selectedExport: nil)
                .contains("Authorization: Bearer <desktop-agent>")
        )
        #expect(
            desktopAPIAuthenticationReferenceText(selectedSession: configuredDisabledSession, selectedExport: nil)
                .contains("configured but disabled")
        )
        #expect(
            desktopAPIAuthenticationReferenceText(selectedSession: enabledSession, selectedExport: nil)
                .contains("x-api-key or Authorization: Bearer")
        )
    }

    @Test("gateway access summary renders persistent session summary and sign-out latency")
    @MainActor
    func gatewayAccessSummaryRendersPersistentSessionSummaryAndSignOutLatency() throws {
        let session = DesktopServerSessionState(
            id: "persistent-session",
            title: "Persistent Session",
            modelID: "melix-dev-text",
            authMode: .apiKeys,
            authTokenHint: "desktop-agent",
            sharedAccessState: .enabled,
            accessKeyCount: 1,
            accessKeyHints: ["desktop-agent"],
            lifecycle: .running,
            activeAuthSessionCount: 3,
            rememberedAuthSessionCount: 2,
            expiredRememberedSessionCount: 1,
            authSessionRetentionSeconds: 86_400,
            lastAuthSessionSignOutLatencyMs: 14
        )

        let view = hostView(DesktopServerGatewayAccessSummaryView(session: session))

        #expect(view.subviews.isEmpty == false)
        #expect(session.persistentSessionSummaryText.contains("2 remembered sessions active"))
    }

    @Test("tools tab renders model information and operations state")
    @MainActor
    func toolsTabRendersModelInformationAndOperationsState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        await viewModel.runDoctor()
        await viewModel.runBench()
        await viewModel.quantizePrimaryModel()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("tools tab renders OCR profile metadata when selected model info includes OCR defaults")
    @MainActor
    func toolsTabRendersOCRProfileMetadata() async throws {
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

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedModelInfo?.ocrPromptProfileText == "ocr-default-v1")
        #expect(viewModel.selectedModelInfo?.ocrSamplingProfileText == "ocr-deterministic")
        #expect(viewModel.selectedModelInfo?.ocrStopSequencesText == "<ocr:end>")
    }

    @Test("models workspace renders expanded model settings metadata")
    @MainActor
    func modelsWorkspaceRendersExpandedModelSettingsMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = .modelWarm
        model.features = ["chat", "adaptive_thinking"]
        model.maxContext = 8192
        model.settings.alias = "Melix Text Turbo"
        model.settings.typeOverride = "mlx-text"
        model.settings.ttlSeconds = 600
        model.settings.pinOnLoad = true
        model.settings.memoryPolicy = .memoryResidencyTtl
        model.settings.defaultAccelerationMode = .activeKvQuantized
        model.settings.accelerationProfileID = "kv-q8"
        model.settings.adaptiveThinking.mode = "adaptive"
        model.settings.adaptiveThinking.budgetTokens = 192
        model.settings.ext["tool_parser_xml_fallback"] = "true"
        model.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.settings.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.settings.ext["ocr_default_temperature"] = "0.05"
        model.settings.ext["ocr_default_top_p"] = "0.82"
        model.settings.ext["ocr_default_max_tokens"] = "192"
        model.settings.ext["melix.generation_config.source"] = "/tmp/melix-dev-text/generation_config.json"
        model.settings.ext["melix.generation_config.temperature"] = "0.12"
        model.settings.ext["melix.generation_config.top_p"] = "0.9"
        model.settings.ext["melix.generation_config.max_tokens"] = "320"
        model.settings.ext["ocr_stop_sequences"] = "<ocr:end>"
        model.cachePolicy.effectiveMode = .hybrid
        model.cachePolicy.compatibility = .cacheCompatibilityLimited
        model.cachePolicy.compatibilityReason = "requested cache mode is not advertised by the worker"
        model.cachePolicy.requestedDirectory = "/tmp/requested-cache"
        model.cachePolicy.effectiveDirectory = "/var/melix/cache"
        model.cachePolicy.requestedBlockSizeTokens = 32
        model.cachePolicy.effectiveBlockSizeTokens = 64
        model.cachePolicy.requestedCacheMemoryBudgetBytes = 4_096
        model.cachePolicy.effectiveCacheMemoryBudgetBytes = 8_192
        model.cachePolicy.requestedMultimodalCacheBudgetBytes = 2_048
        model.cachePolicy.effectiveMultimodalCacheBudgetBytes = 4_096
        model.cachePolicy.initialCacheBlocks = 4
        snapshot.models = [model]

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 8192
        info.supportedParsers = ["text", "json"]
        info.supportedModalities = ["text"]

        await client.configureSnapshot(snapshot)
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        let modelRow = try #require(viewModel.desktopFoundationState.models.first)
        let view = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            )
        )
        let values = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(values.contains("Melix Text Turbo"))
        #expect(values.contains("mlx-text"))
        #expect(values.contains("600"))
        #expect(values.contains("Active KV Quantized"))
        #expect(values.contains("Adaptive"))
        #expect(values.contains("192"))
        #expect(modelRow.cachePolicyText == "Limited • Hybrid")
        #expect(modelRow.cacheSettingsText == "/var/melix/cache • block 64 • cache 8 KB • multimodal 4 KB")
        #expect(viewModel.selectedModelInfo?.toolParserFallbackText == "XML")
        #expect(viewModel.selectedModelInfo?.ocrSamplingProfileText == "ocr-deterministic")
        #expect(viewModel.selectedModelInfo?.ocrTemperatureText == "0.05")
        #expect(viewModel.selectedModelInfo?.generationConfigTemperatureText == "0.12")
    }

    @Test("model info summary view renders typed settings and merged defaults")
    @MainActor
    func modelInfoSummaryViewRendersTypedSettingsAndMergedDefaults() {
        let info = RuntimeModelInfoState(
            modelID: "melix-dev-text",
            modelKind: "text",
            maxContext: 8192,
            supportedParsers: ["text", "json"],
            supportedModalities: ["text", "image"],
            supportedTasks: ["generate", "chat"],
            backendID: "mlx_lm",
            familyID: "llama-v1",
            modelPath: "/tmp/melix-dev-text",
            modelRevision: "dev",
            defaultWorkflowRole: "chat",
            detectedIdentitySource: "explicit_override",
            aliasText: "Melix Text Turbo",
            typeOverrideText: "mlx-text",
            ttlSeconds: 600,
            pinOnLoad: true,
            memoryPolicyText: "TTL",
            memoryBudgetText: "32 KB",
            diskStreamingModeText: "Prefer Disk",
            adaptiveThinkingText: "Adaptive • 192 tok",
            accelerationModeText: "Active KV Quantized",
            accelerationProfileID: "kv-q8",
            toolParserFallbackText: "XML",
            ocrPromptProfileText: "ocr-default-v1",
            ocrSamplingProfileText: "ocr-deterministic",
            ocrTemperatureText: "0.05",
            ocrTopPText: "0.82",
            ocrMaxTokensText: "192",
            cacheModeText: "Hybrid",
            cacheCompatibilityText: "Limited",
            cacheCompatibilityReasonText: "requested cache mode is not advertised by the worker",
            cacheDirectoryText: "/tmp/requested-cache -> /var/melix/cache",
            cacheBlockSizeText: "32 -> 64 tokens",
            cacheBudgetText: "4 KB -> 8 KB",
            multimodalCacheBudgetText: "2 KB -> 4 KB",
            cacheRootText: "/var/melix/cache",
            initialCacheBlocksText: "4",
            generationConfigSourceText: "/tmp/melix-dev-text/generation_config.json",
            generationConfigTemperatureText: "0.12",
            generationConfigTopPText: "0.9",
            generationConfigMaxTokensText: "320",
            ocrStopSequencesText: "<ocr:end>"
        )

        let content = desktopModelInfoSummaryContent(info)

        #expect(content.headline == "melix-dev-text • text")
        #expect(content.maxContext == "max context 8192")
        #expect(content.detailLines.contains("alias: Melix Text Turbo"))
        #expect(content.detailLines.contains("type override: mlx-text"))
        #expect(content.detailLines.contains("memory policy: TTL"))
        #expect(content.detailLines.contains("memory budget: 32 KB"))
        #expect(content.detailLines.contains("cache mode: Hybrid"))
        #expect(content.detailLines.contains("cache compatibility: Limited"))
        #expect(content.detailLines.contains("cache detail: requested cache mode is not advertised by the worker"))
        #expect(content.detailLines.contains("cache directory: /tmp/requested-cache -> /var/melix/cache"))
        #expect(content.detailLines.contains("cache root: /var/melix/cache"))
        #expect(content.detailLines.contains("cache block size: 32 -> 64 tokens"))
        #expect(content.detailLines.contains("cache budget: 4 KB -> 8 KB"))
        #expect(content.detailLines.contains("multimodal cache budget: 2 KB -> 4 KB"))
        #expect(content.detailLines.contains("initial cache blocks: 4"))
        #expect(content.detailLines.contains("adaptive thinking: Adaptive • 192 tok"))
        #expect(content.detailLines.contains("acceleration: Active KV Quantized • kv-q8"))
        #expect(content.detailLines.contains("parser fallback: XML"))
        #expect(content.detailLines.contains("pin on load: yes"))
        #expect(content.detailLines.contains("ttl seconds: 600"))
        #expect(content.detailLines.contains("parsers: text, json"))
        #expect(content.detailLines.contains("modalities: text, image"))
        #expect(content.detailLines.contains("backend: mlx_lm"))
        #expect(content.detailLines.contains("family: llama-v1"))
        #expect(content.detailLines.contains("default workflow: chat"))
        #expect(content.detailLines.contains("identity source: explicit_override"))
        #expect(content.detailLines.contains("tasks: generate, chat"))
        #expect(content.detailLines.contains("revision: dev"))
        #expect(content.detailLines.contains("source path: /tmp/melix-dev-text"))
        #expect(content.detailLines.contains("generation config: /tmp/melix-dev-text/generation_config.json"))
        #expect(content.detailLines.contains("generation defaults: temp 0.12 • top-p 0.9 • max 320"))
        #expect(content.detailLines.contains("ocr sampling defaults: ocr-deterministic • temp 0.05 • top-p 0.82 • max 192"))
    }

    @Test("speech model info summary view renders voice catalog details")
    @MainActor
    func speechModelInfoSummaryViewRendersVoiceCatalogDetails() {
        let info = RuntimeModelInfoState(
            modelID: "melix-qwen3-tts-mlx",
            modelKind: "speech",
            maxContext: 4096,
            supportedParsers: ["text"],
            supportedModalities: ["text", "audio"],
            supportedTasks: ["speak"],
            backendID: "mlx_audio.tts",
            familyID: "qwen3-tts",
            audioInstallProfileText: "audio-tts",
            audioLanguagesText: "zh,en",
            audioVoiceModeText: "hybrid",
            audioOutputFormatsText: "wav",
            audioSupportsInstructionsText: "Yes",
            audioVoiceCatalogSummaryText: "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis.",
            audioVoiceLocalesText: "zh,en",
            audioDefaultLocaleText: "zh",
            audioPackagedDefaultLocaleText: "zh",
            audioLocalePolicyText: "request>model_default>packaged_default",
            audioRuntimePackStateText: "installed",
            audioRuntimePackIDText: "melix-audio-runtime-pack",
            audioModelStateText: "managed_local",
            modelPath: "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit",
            modelRevision: "mlx-audio"
        )

        let content = desktopModelInfoSummaryContent(info)

        #expect(content.headline == "melix-qwen3-tts-mlx • speech")
        #expect(content.detailLines.contains("audio install profile: audio-tts"))
        #expect(content.detailLines.contains("audio languages: zh,en"))
        #expect(content.detailLines.contains("voice mode: hybrid"))
        #expect(content.detailLines.contains("audio formats: wav"))
        #expect(content.detailLines.contains("instruction support: Yes"))
        #expect(content.detailLines.contains("voice locales: zh,en"))
        #expect(content.detailLines.contains("default locale: zh"))
        #expect(content.detailLines.contains("packaged default locale: zh"))
        #expect(content.detailLines.contains("locale policy: request>model_default>packaged_default"))
        #expect(
            content.detailLines.contains(
                "voice catalog: Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
            )
        )
        #expect(content.detailLines.contains("runtime pack state: installed"))
        #expect(content.detailLines.contains("runtime pack id: melix-audio-runtime-pack"))
        #expect(content.detailLines.contains("audio model state: managed_local"))
    }

    @Test("doctor report summary view renders health and finding detail")
    @MainActor
    func doctorReportSummaryViewRendersHealthAndFindingDetail() async throws {
        let report = RuntimeDoctorReportState(
            markdown: "# Melix Doctor\n\n- worker_state: warning\n",
            healthStatusText: "Warning",
            findings: [
                RuntimeDoctorFindingState(
                    code: "cache_unavailable",
                    severityText: "Warning",
                    summary: "Cache metrics unavailable",
                    detail: "Resident cache bytes were reported as zero."
                ),
            ]
        )

        let view = hostView(DesktopDoctorReportSummaryView(report: report))

        #expect(view.subviews.isEmpty == false)
        #expect(report.findings.first?.id == "cache_unavailable")
    }

    @Test("tools tab buttons dispatch inspect diagnostics bench and model operations")
    @MainActor
    func toolsTabButtonsDispatchActions() async throws {
        let client = FakeControlPlaneXPCClient()
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
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopToolsTabView(viewModel: viewModel)
        await tab.inspectPrimaryModel()
        await tab.refreshModelOpsProductState()
        await tab.runDoctor()
        await tab.runBench()
        await tab.convertPrimaryModel()
        await tab.quantizePrimaryModel()
        await tab.trainPrimaryModel()
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
        await tab.activateLatestAdapter()
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
        await tab.publishLatestAdapter()
        await tab.downloadPrimaryModel()
        await tab.uploadPrimaryModel()

        let actions = await client.recordedActions
        #expect(actions.contains("info:melix-dev-text"))
        #expect(actions.contains("operation:registry_snapshot:melix-dev-text"))
        #expect(actions.contains("doctor"))
        #expect(actions.contains("bench"))
        #expect(actions.contains("operation:convert:melix-dev-text"))
        #expect(actions.contains("operation:quantize:melix-dev-text"))
        #expect(actions.contains("operation:train_lora:melix-dev-text"))
        #expect(actions.contains("operation:activate_adapter:melix-dev-text"))
        #expect(actions.contains("operation:download:melix-dev-text"))
        #expect(actions.contains("operation:upload:melix-dev-text"))
        #expect(viewModel.selectedModelInfo?.modelID == "melix-dev-text")
        #expect(viewModel.lastDoctorReport?.markdown.contains("Melix Doctor") == true)
        #expect(viewModel.lastBenchReport?.markdown.contains("Melix Bench") == true)
        #expect(viewModel.lastModelOperation?.operation == "upload")
        #expect(viewModel.adapterPackages.first?.adapterName == "melix-dev-adapter")
        #expect(viewModel.adapterPackages.first?.activationStatusText == "Activated")
        #expect(viewModel.trainingHistory.first?.jobID == "model-ops-0001")
    }

    @Test("workspace diagnostics renders benchmark configuration history and charts")
    @MainActor
    func workspaceDiagnosticsRendersBenchmarkConfigurationHistoryAndCharts() async throws {
        let client = FakeControlPlaneXPCClient()
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = "melix-dev-text-lora"
        await client.configureSnapshot(
            makeAudioSetupSnapshot(
                models: [
                    ModelCatalog.devTextModel(),
                    derivedModel,
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        await viewModel.refreshBenchmarkHistory()
        viewModel.selectBenchmarkMetric("bench.smoke.tokens_per_second")

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.benchmarkHistory.count == 3)
        #expect(viewModel.benchmarkMetricCards.isEmpty == false)
        #expect(viewModel.benchmarkChartPoints.count == 2)
    }

    @Test("workspace diagnostics renders matrix benchmark controls history and charts")
    @MainActor
    func workspaceDiagnosticsRendersMatrixBenchmarkControlsHistoryAndCharts() async throws {
        let client = FakeControlPlaneXPCClient()
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = "melix-dev-text-lora"
        await client.configureSnapshot(
            makeAudioSetupSnapshot(
                models: [
                    ModelCatalog.devTextModel(),
                    derivedModel,
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        await viewModel.refreshBenchmarkHistory()

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Matrix"))
        #expect(renderedTexts.contains("Requests"))
        #expect(renderedTexts.contains("Duration"))
        #expect(viewModel.benchmarkMatrixHistory.count == 2)
        #expect(viewModel.benchmarkMatrixSummaryRows.count == 2)
        #expect(viewModel.benchmarkMatrixContextChartPoints.count == 2)
        #expect(viewModel.benchmarkMatrixThroughputChartPoints.count == 2)
    }

    @Test("diagnostics tool section action helpers dispatch benchmark operations and render exported state")
    @MainActor
    func diagnosticsToolSectionActionHelpersDispatchBenchmarkOperations() async throws {
        let client = FakeControlPlaneXPCClient()
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
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        await section.inspectPrimaryModel()
        await section.runDoctor()
        await section.runBenchmark()
        await section.refreshBenchmarkResults()
        await section.runEvaluation()
        await section.refreshEvaluationResults()
        section.toggleBenchmarkSuiteSelection("latency")
        await section.exportBenchmarkCSV()
        await section.exportEvaluationSummaryCSV()
        await section.exportEvaluationSamplesCSV()
        await section.exportEvaluationSamplesJSONL()
        await section.refreshTooling()
        section.selectBenchmarkHistory(jobID: "bench-older")
        section.selectEvaluationHistory(jobID: "eval-newer")

        let view = hostView(section)
        let actions = await client.recordedActions

        #expect(view.subviews.isEmpty == false)
        #expect(actions.contains("info:melix-dev-text"))
        #expect(actions.contains("doctor"))
        #expect(actions.contains("bench"))
        #expect(actions.contains("eval"))
        #expect(actions.contains("bench.export"))
        #expect(actions.contains("operation:registry_snapshot:melix-dev-text"))
        #expect(viewModel.lastBenchmarkCSVExport?.rowCount == 3)
        #expect(viewModel.lastEvaluationExport?.rowCount == 2)
        #expect(viewModel.selectedBenchmarkHistoryJobID == "bench-older")
        #expect(viewModel.selectedEvaluationHistoryJobID == "eval-newer")
        #expect(viewModel.selectedBenchmarkSuiteIDs.contains("latency"))
    }

    @Test("diagnostics tool section action helpers dispatch matrix benchmark operations and exports")
    @MainActor
    func diagnosticsToolSectionActionHelpersDispatchMatrixBenchmarkOperations() async throws {
        let client = FakeControlPlaneXPCClient()
        var matrixJob = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
        matrixJob.jobID = "matrix-newer"
        matrixJob.modelID = "melix-dev-text"
        matrixJob.taskKind = "text-generation"
        matrixJob.sourceRepo = "databricks/databricks-dolly-15k"
        matrixJob.suiteIds = ["smoke", "latency"]
        matrixJob.benchmarkMode = "matrix"
        matrixJob.status = "completed"
        matrixJob.outputDir = "/tmp/melix/bench/matrix-runs/matrix-newer"
        matrixJob.createdAtUnixMs = 1_712_250_000_000
        matrixJob.updatedAtUnixMs = 1_712_250_000_500
        var summaryRow = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
        summaryRow.jobID = "matrix-newer"
        summaryRow.taskKind = "text-generation"
        summaryRow.sourceRepo = "databricks/databricks-dolly-15k"
        summaryRow.modelID = "melix-dev-text"
        summaryRow.suiteID = "smoke"
        summaryRow.contextLength = 1024
        summaryRow.generationLength = 128
        summaryRow.batchSize = 2
        summaryRow.cacheProfile = "warm"
        summaryRow.reasoningMode = "enabled"
        summaryRow.structuredOutputMode = "json_schema"
        summaryRow.concurrencyLevel = 1
        summaryRow.repeats = 3
        summaryRow.requests = 8
        summaryRow.ttftMeanMs = 24.4
        summaryRow.requestLatencyMeanMs = 33.8
        summaryRow.prefillTokensPerSecondMean = 310
        summaryRow.decodeTokensPerSecondMean = 62
        summaryRow.throughputRequestsPerSecond = 4.8
        summaryRow.throughputTokensPerSecond = 256
        summaryRow.successRate = 1
        summaryRow.peakMemoryBytesMax = 2_048_000_000
        summaryRow.queueWaitMeanMs = 2.3
        summaryRow.queueWaitP95Ms = 3.1
        summaryRow.createdAtUnixMs = 1_712_250_000_000
        await client.configureBenchMatrixResponse(
            ControlPlaneBenchMatrixResult(job: matrixJob, summaryRows: [summaryRow])
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        await section.runBenchmarkMatrix()
        await section.refreshBenchmarkMatrixResults()
        await section.exportBenchmarkMatrixSummaryCSV()
        await section.exportBenchmarkMatrixRequestsCSV()
        section.selectBenchmarkMatrixHistory(jobID: "matrix-newer")

        let view = hostView(section)
        let actions = await client.recordedActions

        #expect(view.subviews.isEmpty == false)
        #expect(actions.contains("bench.matrix"))
        #expect(actions.contains("bench.export"))
        #expect(viewModel.lastBenchmarkMatrixExport?.formatTitle == "requests.csv")
        #expect(viewModel.selectedBenchmarkMatrixHistoryJobID == "matrix-newer")
        #expect(viewModel.benchmarkMatrixHistory.isEmpty == false)
    }

    @Test("diagnostics tool section renders empty benchmark states and refreshes persisted history when needed")
    @MainActor
    func diagnosticsToolSectionRendersEmptyBenchmarkStates() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeAudioSetupSnapshot(models: [makeMenuBarImageModelSummary()])
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        await section.refreshDiagnosticsHistoryIfNeeded()
        let view = hostView(section)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.benchmarkModels.isEmpty == false)
        #expect(viewModel.benchmarkModels.first?.modelID == "melix-dev-image")
        #expect(viewModel.benchmarkHistory.isEmpty)
        #expect(await client.recordedActions.contains("bench.export"))
    }

    @Test("diagnostics tool section renders the empty catalog benchmark message when no benchmark models are available")
    @MainActor
    func diagnosticsToolSectionRendersEmptyCatalogBenchmarkMessage() async throws {
        let client = FakeControlPlaneXPCClient()
        var audioOnlyModel = Melix_Controlplane_V1_ModelSummary()
        audioOnlyModel.modelID = "melix-dev-audio"
        audioOnlyModel.kind = "audio"
        audioOnlyModel.state = .modelWarm
        audioOnlyModel.features = ["transcribe"]
        await client.configureSnapshot(makeAudioSetupSnapshot(models: [audioOnlyModel]))
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        let view = hostView(section)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.benchmarkModels.isEmpty)
    }

    @Test("diagnostics tool section renders the direct Hugging Face repo benchmark target input")
    @MainActor
    func diagnosticsToolSectionRendersDirectHFRepoBenchmarkInput() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkTargetMode = .huggingFaceRepo
        viewModel.benchmarkHFRepoID = "unsloth/gemma-4-E4B-it-MLX-8bit"

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        let view = hostView(section)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.benchmarkTargetSummaryText.contains("unsloth/gemma-4-E4B-it-MLX-8bit"))
    }

    @Test("workspace diagnostics renders canonical benchmark and evaluation controls")
    @MainActor
    func workspaceDiagnosticsRendersCanonicalBenchmarkAndEvaluationControls() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeAudioSetupSnapshot(models: [ModelCatalog.devTextModel()])
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Catalog Model"))
        #expect(renderedTexts.contains("Hugging Face Repo"))
        #expect(renderedTexts.contains("Melix Dev Text • melix-dev-text"))
        #expect(renderedTexts.contains("3"))
        #expect(renderedTexts.contains("Partial Prefix"))
        #expect(renderedTexts.contains("Enabled"))
        #expect(renderedTexts.contains("Json Schema"))
        #expect(renderedTexts.contains("multiple_choice_accuracy"))
        #expect(renderedTexts.contains("sandboxed"))

    }

    @Test("workspace diagnostics renders evaluation configuration history and sample previews")
    @MainActor
    func workspaceDiagnosticsRendersEvaluationConfigurationHistoryAndSamples() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        await viewModel.refreshEvaluationHistory()

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.evaluationHistory.count == 1)
        #expect(viewModel.evaluationMetricCards.count == 1)
        #expect(viewModel.evaluationSamplePreview.count == 2)
    }

    @Test("workspace diagnostics covers evaluation helper actions and direct repo configuration")
    @MainActor
    func workspaceDiagnosticsCoversEvaluationHelperActionsAndDirectRepoConfiguration() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )

        section.toggleEvaluationSuiteSelection("gsm8k")
        #expect(viewModel.selectedEvaluationSuiteIDs.contains("gsm8k"))

        await section.refreshDiagnosticsHistoryIfNeeded()
        #expect(viewModel.evaluationHistory.isEmpty == false)

        section.selectEvaluationHistory(jobID: "eval-newer")
        #expect(viewModel.selectedEvaluationHistoryEntry?.jobID == "eval-newer")

        viewModel.selectedEvaluationTargetMode = .huggingFaceRepo
        viewModel.evaluationHFRepoID = "unsloth/gemma-4-E4B-it-MLX-8bit"
        let hosted = hostView(DesktopWorkspaceShellView(viewModel: viewModel))

        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.evaluationTargetSummaryText.contains("unsloth/gemma-4-E4B-it-MLX-8bit"))
    }

    @Test("tools tab renders pending adapter registry and history rows")
    @MainActor
    func toolsTabRendersPendingAdapterRegistryRows() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makePendingRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))
        let adapter = try #require(viewModel.adapterPackages.first)
        let trainingJob = try #require(viewModel.trainingHistory.first)

        #expect(view.subviews.isEmpty == false)
        #expect(adapter.statusText == "Queued for publish")
        #expect(adapter.activationStatusText == "Pending activation")
        #expect(adapter.responseOnlyEnabled)
        #expect(adapter.gradientCheckpointingEnabled)
        #expect(adapter.publishedRepo.isEmpty)
        #expect(trainingJob.statusText == "Unknown")
        #expect(trainingJob.stageText == "write_manifest • 42%")
    }

    @Test("tools tab renders empty tooling state without a primary model")
    @MainActor
    func toolsTabRendersWithoutPrimaryModel() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        _ = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(viewModel.primaryModel == nil)
        #expect(viewModel.adapterPackages.isEmpty)
        #expect(viewModel.trainingHistory.isEmpty)
        #expect(viewModel.selectedModelInfo == nil)
        #expect(viewModel.lastModelOperation == nil)
    }

    @Test("downloads section renders audio setup actions and dispatches first-use remediation buttons")
    @MainActor
    func downloadsSectionRendersAudioSetupActionsAndDispatchesButtons() async throws {
        let client = FakeControlPlaneXPCClient()

        var missingRuntime = ModelCatalog.mlxWhisperModel()
        missingRuntime.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        missingRuntime.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
        missingRuntime.settings.ext["melix.audio.model_state"] = "catalog_default"

        var runtimeInstalled = missingRuntime
        runtimeInstalled.settings.ext["melix.audio.runtime_pack_state"] = "installed"

        var managedLocal = runtimeInstalled
        managedLocal.settings.ext["melix.audio.model_state"] = "managed_local"
        managedLocal.settings.ext["melix.model_path"] = "/Users/test/Library/Application Support/Melix/models/default-managed/hf/mlx-community/whisper-large-v3-turbo-asr-fp16/mlx-audio"

        await client.configureSnapshot(
            makeAudioSetupSnapshot(models: [ModelCatalog.devTextModel(), missingRuntime])
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
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)

        let initialView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(initialView.subviews.isEmpty == false)
        #expect(viewModel.audioSetupActions.first?.actionTitle == "Install Audio Support")

        await client.configureSnapshot(makeAudioSetupSnapshot(models: [ModelCatalog.devTextModel(), runtimeInstalled]))
        await viewModel.installAudioRuntime(modelID: "melix-whisper-mlx")

        let runtimeInstalledView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(runtimeInstalledView.subviews.isEmpty == false)
        #expect(viewModel.audioSetupActions.first?.actionTitle == "Download Audio Model")

        await client.configureSnapshot(makeAudioSetupSnapshot(models: [ModelCatalog.devTextModel(), managedLocal]))
        await viewModel.downloadAudioModel(modelID: "melix-whisper-mlx")

        let managedLocalView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(managedLocalView.subviews.isEmpty == false)
        #expect(viewModel.audioSetupActions.isEmpty)

        let requests = await client.recordedModelOperationRequests
        #expect(requests.count == 3)
        #expect(requests[0].operation == "install_audio_runtime")
        #expect(requests[1].operation == "download")
        #expect(requests[2].operation == "registry_snapshot")
    }

    @Test("downloads section renders audio setup notice as a compact single row")
    @MainActor
    func downloadsSectionRendersCompactAudioSetupNotice() async throws {
        let action = RuntimeAudioSetupActionState(
            modelID: "melix-whisper-mlx",
            alias: "Melix Whisper MLX",
            detail: "Install melix-audio-runtime-pack to enable audio requests for Melix Whisper MLX.",
            actionTitle: "Install Audio Support",
            kind: .installRuntime
        )
        let hosted = hostView(
            DesktopAudioSetupNoticeRow(action: action, performAction: {})
        )

        #expect(hosted.subviews.isEmpty == false)
        #expect(hosted.fittingSize.height <= DesktopDownloadsLayoutMetrics.compactAudioNoticeHeightBudget)
        #expect(action.detail.contains("melix-audio-runtime-pack"))
    }

    @Test("tools tab renders typed convert operation metadata")
    @MainActor
    func toolsTabRendersTypedConvertOperationMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "convert",
                outputPath: "/tmp/melix-convert/job-1/convert.artifact",
                manifestJSON: #"""
                {
                  "operation": "convert",
                  "target_format": "melix_model_bundle",
                  "compatibility": {
                    "runtime": "mlx_text",
                    "serving_compatible": true,
                    "smoke_test_requested": true,
                    "smoke_test_passed": true
                  }
                }
                """#,
                artifactKind: "converted_model_bundle",
                manifestPath: "/tmp/melix-convert/job-1/convert.artifact/manifest.json",
                artifactBytes: 512,
                smokeTestPassed: true
            ),
            forNamedOperation: "convert"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.convertPrimaryModel()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))
        let operation = try #require(viewModel.lastModelOperation)

        #expect(view.subviews.isEmpty == false)
        #expect(operation.operation == "convert")
        #expect(operation.conversionTargetFormat == "melix_model_bundle")
        #expect(operation.artifactRuntime == "mlx_text")
        #expect(operation.servingCompatible == true)
    }

    @Test("tools tab evaluates typed upload summary branches")
    @MainActor
    func toolsTabEvaluatesTypedUploadSummaryBranches() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "upload",
                outputPath: "/tmp/melix-upload/job-1/upload.receipt.json",
                manifestJSON: #"""
                {
                  "operation": "upload",
                  "target_repo": "melix/models/melix-dev-text-q6",
                  "source_artifact_kind": "quantized_model_bundle",
                  "linked_quantization": {
                    "quant_profile_id": "q6"
                  }
                }
                """#,
                artifactKind: "upload_receipt",
                manifestPath: "/tmp/melix-upload/job-1/upload.receipt.json",
                artifactBytes: 192,
                smokeTestPassed: false
            ),
            forNamedOperation: "upload"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.uploadPrimaryModel()

        _ = DesktopToolsTabView(viewModel: viewModel).body
        let operation = try #require(viewModel.lastModelOperation)

        #expect(operation.targetRepo == "melix/models/melix-dev-text-q6")
        #expect(operation.sourceArtifactKind == "quantized_model_bundle")
        #expect(operation.linkedQuantizationProfileID == "q6")
    }

    @Test("downloads section renders recent transfer metadata for packaged artifacts")
    @MainActor
    func downloadsSectionRendersRecentTransferMetadataForPackagedArtifacts() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "upload",
                outputPath: "/tmp/melix-upload/job-1/upload.receipt.json",
                manifestJSON: #"""
                {
                  "operation": "upload",
                  "target_repo": "melix/models/melix-dev-text-converted",
                  "source_artifact_kind": "converted_model_bundle"
                }
                """#,
                artifactKind: "upload_receipt",
                manifestPath: "/tmp/melix-upload/job-1/upload.receipt.json",
                artifactBytes: 192,
                smokeTestPassed: false
            ),
            forNamedOperation: "upload"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)
        await viewModel.uploadPrimaryModel()

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let operation = try #require(viewModel.lastModelOperation)

        #expect(view.subviews.isEmpty == false)
        #expect(operation.operation == "upload")
        #expect(operation.targetRepo == "melix/models/melix-dev-text-converted")
        #expect(operation.sourceArtifactKind == "converted_model_bundle")
    }

    @Test("downloads section evaluates typed transfer summary branches")
    @MainActor
    func downloadsSectionEvaluatesTypedTransferSummaryBranches() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "upload",
                outputPath: "/tmp/melix-upload/job-2/upload.receipt.json",
                manifestJSON: #"""
                {
                  "operation": "upload",
                  "target_repo": "melix/models/melix-dev-text-converted",
                  "source_artifact_kind": "converted_model_bundle",
                  "target_format": "melix_model_bundle"
                }
                """#,
                artifactKind: "upload_receipt",
                manifestPath: "/tmp/melix-upload/job-2/upload.receipt.json",
                artifactBytes: 192,
                smokeTestPassed: false
            ),
            forNamedOperation: "upload"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)
        await viewModel.uploadPrimaryModel()

        _ = DesktopDownloadsToolSectionView(viewModel: viewModel).body
        let operation = try #require(viewModel.lastModelOperation)

        #expect(operation.targetRepo == "melix/models/melix-dev-text-converted")
        #expect(operation.sourceArtifactKind == "converted_model_bundle")
        #expect(operation.conversionTargetFormat == "melix_model_bundle")
    }

    @Test("downloads section renders queue recovery rows and resume actions")
    @MainActor
    func downloadsSectionRendersQueueRecoveryRowsAndResumeActions() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "model-ops-0099",
                            sourceModel: "melix-dev-text",
                            status: "stalled",
                            stage: "download",
                            pct: 0.42,
                            outputDir: "/tmp/melix-downloads/melix-dev-text",
                            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
                            selectedMirror: "https://mirror.example/recovery",
                            downloadedBytes: 1536,
                            totalBytes: 4096,
                            resumeUsed: true,
                            resumeFromBytes: 1024,
                            retryCount: 1,
                            stallDetectionCount: 1,
                            stallReason: "no_progress_timeout",
                            resumeReady: true
                        )
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)
        await viewModel.refreshDownloadQueueState()

        let view = hostView(DesktopDownloadsToolSectionView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.downloadQueue.first?.statusText == "Stalled")
        #expect(viewModel.downloadQueue.first?.resumeReady == true)
        #expect(viewModel.desktopSignalStates.contains(where: { $0.title == "Download Recovery Available" }))
    }

    @Test("dashboard settings logs bench and api tabs render from foundation state")
    @MainActor
    func supportingTabsRenderFromFoundationState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await client.sendLog(level: "info", message: "operator-log")
        try await Task.sleep(for: .milliseconds(20))

        let foundation = viewModel.desktopFoundationState
        let dashboard = hostView(DesktopDashboardTabView(foundation: foundation))
        let settings = hostView(DesktopSettingsTabView(foundation: foundation))
        let logs = hostView(DesktopLogsTabView(foundation: foundation))
        let bench = hostView(DesktopBenchTabView(foundation: foundation))
        let chat = hostView(DesktopChatTabView(viewModel: viewModel))
        let api = hostView(DesktopAPIReferenceTabView(foundation: foundation))
        let hasConnectionCard = foundation.dashboardCards.contains { row in
            row.id == "connection" && row.value == "Connected"
        }
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency"
        }
        let hasEvictionsCard = foundation.dashboardCards.contains { row in
            row.id == "evictions"
        }
        let hasGuardCard = foundation.dashboardCards.contains { row in
            row.id == "guards"
        }
        let hasConnectionSetting = foundation.settings.contains { row in
            row.key == "Connection" && row.value == "Connected"
        }

        #expect(dashboard.subviews.isEmpty == false)
        #expect(hasConnectionCard)
        #expect(hasResidencyCard)
        #expect(hasEvictionsCard)
        #expect(hasGuardCard)
        #expect(hasConnectionSetting)
        #expect(settings.subviews.isEmpty == false)
        #expect(logs.subviews.isEmpty == false)
        #expect(bench.subviews.isEmpty == false)
        #expect(chat.subviews.isEmpty == false)
        #expect(api.subviews.isEmpty == false)
    }

    @Test("chat tab submit and clear actions dispatch through the view model")
    @MainActor
    func chatTabDispatchesViewModelActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopChatTabView(viewModel: viewModel)
        viewModel.chatComposerText = "Hello from SwiftUI"
        await viewModel.submitChatPrompt()
        viewModel.clearChatTranscript()

        let view = hostView(tab)

        #expect(await client.recordedActions.contains("chat:melix-dev-text"))
        #expect(viewModel.chatTranscript.isEmpty)
        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat tab renders populated transcript rows and runtime metadata")
    @MainActor
    func chatTabRendersPopulatedTranscriptRowsAndRuntimeMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.chatComposerText = "Render the transcript"

        await viewModel.submitChatPrompt()

        let view = hostView(DesktopChatTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .user }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .assistant }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .reasoning }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .tool }))
        #expect(viewModel.lastChatRequestID == "chat-request-1")
        #expect(viewModel.lastChatUsageText == "12 prompt • 24 completion")
    }

    @Test("chat tab renders terminal error entries")
    @MainActor
    func chatTabRendersTerminalErrorEntries() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .failed(code: "runtime_error", message: "worker failed"),
        ])
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.chatComposerText = "Render the error path"

        await viewModel.submitChatPrompt()

        let view = hostView(DesktopChatTabView(viewModel: viewModel))
        let renderedErrorEntry = viewModel.chatTranscript.contains { entry in
            entry.kind == .error && entry.body == "worker failed"
        }

        #expect(view.subviews.isEmpty == false)
        #expect(renderedErrorEntry)
        #expect(viewModel.chatStatusText == "Failed • runtime_error")
    }

    @Test("chat session sidebar renders the empty state when no chat sessions exist")
    @MainActor
    func chatSessionSidebarRendersTheEmptyStateWhenNoChatSessionsExist() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let view = hostView(DesktopChatSessionSidebar(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.chatSessions.isEmpty)
    }

    @Test("chat workspace uses compact layout metrics")
    @MainActor
    func chatWorkspaceUsesCompactLayoutMetrics() {
        #expect(DesktopChatLayoutMetrics.sidebarIdealWidth <= 230)
        #expect(DesktopChatLayoutMetrics.inspectorIdealWidth <= 240)
        #expect(DesktopChatLayoutMetrics.composerMinHeight <= 84)
        #expect(DesktopChatLayoutMetrics.collapsedRailWidth <= 32)
    }

    @Test("chat collapsed rails render compact restore affordances")
    @MainActor
    func chatCollapsedRailsRenderCompactRestoreAffordances() {
        let leadingRail = hostView(DesktopChatPaneRail(edge: .leading, action: {}))
        let trailingRail = hostView(DesktopChatPaneRail(edge: .trailing, action: {}))

        #expect(leadingRail.fittingSize.width <= DesktopChatLayoutMetrics.collapsedRailWidth + 4)
        #expect(trailingRail.fittingSize.width <= DesktopChatLayoutMetrics.collapsedRailWidth + 4)
    }

    @Test("chat tab renders collapsed rails when both side panes start hidden")
    @MainActor
    func chatTabRendersCollapsedRailsWhenBothSidePanesStartHidden() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let hosted = hostView(
            DesktopChatTabView(
                viewModel: viewModel,
                initiallyShowsSidebar: false,
                initiallyShowsInspector: false
            )
        )
        let renderedTexts = renderedTextValues(in: hosted)

        #expect(hosted.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Chat Sessions") == false)
        #expect(renderedTexts.contains("Inspector") == false)
    }

    @Test("chat session workspace renders the server required state when no server is running")
    @MainActor
    func chatSessionWorkspaceRendersTheServerRequiredStateWhenNoServerIsRunning() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.stopSelectedServerSession()
        viewModel.chatComposerText = "Need a running server"
        await viewModel.submitChatPrompt()

        let view = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedChatServerSession?.isRunning == false)
        #expect(viewModel.chatStatusText == "Stopped")
    }

    @Test("chat workspace hides header fork and export buttons")
    @MainActor
    func chatWorkspaceHidesHeaderForkAndExportButtons() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let hosted = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )
        let renderedTexts = renderedTextValues(in: hosted)

        #expect(renderedTexts.contains("Fork") == false)
        #expect(renderedTexts.contains("Export") == false)
    }

    @Test("chat session workspace renders lifecycle notices for paused and sleeping servers")
    @MainActor
    func chatSessionWorkspaceRendersLifecycleNoticesForPausedAndSleepingServers() async throws {
        let client = FakeControlPlaneXPCClient()
        var pausedSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        pausedSnapshot.serverState = .serverReady
        pausedSnapshot.models = [makeMenuBarModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
        pausedSnapshot.runtimeSessions = [
            makeDesktopRuntimeSession(
                lifecycleState: .paused,
                powerState: .active,
                wakeReason: .policyApply,
                idleTimerSeconds: 60,
                autoSleepEnabled: true,
                lightSleepAfterSeconds: 300,
                deepSleepAfterSeconds: 900
            )
        ]
        await client.configureSnapshot(pausedSnapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let pausedView = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )
        let pausedNotice = try #require(viewModel.selectedChatServerSession?.chatWorkspaceNoticeState)

        #expect(pausedView.subviews.isEmpty == false)
        #expect(pausedNotice.title.contains("Paused"))
        #expect(pausedNotice.severity == .warning)
        #expect(viewModel.selectedChatServerSession?.isInteractiveReady == false)

        let serverSessionID = try #require(viewModel.selectedServerSession?.id)
        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeDesktopRuntimeSession(
                    serverSessionID: serverSessionID,
                    lifecycleState: .sleeping,
                    powerState: .deepSleep,
                    wakeReason: .requestActivity,
                    idleTimerSeconds: 240,
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 300,
                    deepSleepAfterSeconds: 900
                )
            ]
        )
        try await waitForDesktopFoundationCondition("expected chat-bound server session to enter sleeping state") {
            viewModel.selectedChatServerSession?.lifecycle == .sleeping
        }

        let sleepingView = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )
        let sleepingNotice = try #require(viewModel.selectedChatServerSession?.chatWorkspaceNoticeState)

        #expect(sleepingView.subviews.isEmpty == false)
        #expect(sleepingNotice.title.contains("Will Wake On Demand"))
        #expect(sleepingNotice.severity == .info)
        #expect(viewModel.selectedChatServerSession?.isInteractiveReady == true)
    }

    @Test("image tab renders image jobs and artifact previews")
    @MainActor
    func imageTabRendersImageJobsAndArtifacts() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-preview",
                requestID: "req-image-preview",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-preview", storageURI: "/tmp/preview.png")]
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.imageJobs.count == 1)
        #expect(viewModel.selectedImageJob?.artifacts.first?.storageUri == "/tmp/preview.png")
    }

    @Test("chat session inspector renders export metadata when a session has been exported")
    @MainActor
    func chatSessionInspectorRendersExportMetadataWhenASessionHasBeenExported() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Export the transcript"
        await viewModel.submitChatPrompt()
        let exportPath = try #require(viewModel.exportSelectedChatSession())

        _ = hostView(DesktopChatSessionInspector(viewModel: viewModel))

        #expect(FileManager.default.fileExists(atPath: exportPath))
        #expect(viewModel.selectedChatSession?.exportPath == exportPath)
    }

    @Test("image workspace renders edit mode fields directly")
    @MainActor
    func imageWorkspaceRendersEditModeFieldsDirectly() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.imagePromptText = "Edit a cover"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        viewModel.imageEditMaskURL = "file:///tmp/mask.png"

        let view = hostView(
            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: .constant(.edit),
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.imageEditSourceURL == "file:///tmp/source.png")
        #expect(viewModel.imageEditMaskURL == "file:///tmp/mask.png")
    }

    @Test("image inspector renders timeout redo and reiterate branches")
    @MainActor
    func imageInspectorRendersTimeoutRedoAndReiterateBranches() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeMenuBarImageModelSummary(),
        ]
        var timedOutError = Melix_Controlplane_V1_ErrorStatus()
        timedOutError.code = "deadline_exceeded"
        timedOutError.message = "Image request exceeded the 600-second creative workflow deadline."
        let generatedArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-timeout",
            role: .imageArtifactGenerated,
            storageURI: "/tmp/timeout-output.png"
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-timeout",
                requestID: "req-image-timeout",
                operation: "image_edit",
                state: .imageJobFailed,
                artifacts: [generatedArtifact],
                timeoutSeconds: 600,
                sourceArtifactID: "artifact-source",
                editMode: .iterate,
                error: timedOutError
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopImageInspector(
                viewModel: viewModel,
                cancelSelectedJob: {},
                redoSelectedJob: {},
                prepareReiterateFromSelectedJob: {}
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.canRedoSelectedImageJob == true)
        #expect(viewModel.canPrepareReiterateFromSelectedImageJob == true)
        #expect(viewModel.selectedImageJobTimeoutText == "Timed out • 10-minute deadline")
    }

    @Test("image workspace renders source artifact summaries and variation or iterate disabled branches")
    @MainActor
    func imageWorkspaceRendersSourceArtifactSummariesAndVariationOrIterateDisabledBranches() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarImageModelSummary()]
        var generatedArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-workspace-summary",
            role: .imageArtifactGenerated,
            storageURI: "/tmp/workspace-generated.png"
        )
        generatedArtifact.artifactID = "artifact-workspace-generated"
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-workspace-summary",
                requestID: "req-image-workspace-summary",
                operation: "image_edit",
                artifacts: [generatedArtifact]
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.imageEditMode = .variation
        viewModel.imageEditSourceArtifactID = ""
        let variationView = hostView(
            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: .constant(.edit),
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        viewModel.imageEditMode = .iterate
        viewModel.imageEditSourceArtifactID = "artifact-workspace-generated"
        viewModel.imagePromptText = ""
        let iterateDisabledView = hostView(
            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: .constant(.edit),
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        viewModel.imagePromptText = "Push the lighting"
        let iterateEnabledView = hostView(
            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: .constant(.edit),
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        #expect(variationView.subviews.isEmpty == false)
        #expect(iterateDisabledView.subviews.isEmpty == false)
        #expect(iterateEnabledView.subviews.isEmpty == false)
        #expect(viewModel.imageEditSourceArtifactSummaryText == "artifact-workspace-generated • /tmp/workspace-generated.png")
    }

    @Test("image tab dispatches generate and edit actions through the view model")
    @MainActor
    func imageTabDispatchesGenerateAndEditActions() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopImageTabView(viewModel: viewModel)
        viewModel.imagePromptText = "Generate a cover"
        await viewModel.submitImageGeneration()
        viewModel.imagePromptText = "Edit the cover"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        await viewModel.submitImageEdit()

        let view = hostView(tab)

        #expect(await client.recordedActions.contains("image.generate:melix-dev-image"))
        #expect(await client.recordedActions.contains("image.edit:melix-dev-image"))
        #expect(view.subviews.isEmpty == false)
    }

    @Test("image tab dispatches cancel for the selected cancelable job")
    @MainActor
    func imageTabDispatchesCancelForSelectedJob() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-running",
                requestID: "req-image-running",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopImageTabView(viewModel: viewModel)
        tab.cancelSelectedJob()
        try await Task.sleep(for: .milliseconds(20))
        let view = hostView(tab)

        #expect(await client.recordedActions.contains("cancel:req-image-running"))
        #expect(view.subviews.isEmpty == false)
    }

    @Test("image tab helper actions dispatch redo and prepare reiterate through the view model")
    @MainActor
    func imageTabHelperActionsDispatchRedoAndPrepareReiterateThroughViewModel() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarImageModelSummary()]
        let generatedArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-tab-helper",
            role: .imageArtifactGenerated,
            storageURI: "/tmp/tab-helper-generated.png"
        )
        var recipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        recipe.prompt = "Redo this poster"
        recipe.steps = 24
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-tab-helper",
                requestID: "req-image-tab-helper",
                operation: "image_generate",
                artifacts: [generatedArtifact],
                recipe: recipe
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureImageResponses(
            generation: makeMenuBarImageJobSummary(
                jobID: "job-image-tab-helper-redo",
                requestID: "req-image-tab-helper-redo",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-tab-helper-redo")]
            )
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopImageTabView(viewModel: viewModel)
        tab.redoSelectedJob()
        try await Task.sleep(for: .milliseconds(20))
        tab.prepareReiterateFromSelectedJob()

        let request = try #require(await client.recordedImageGenerateRequests.last)
        #expect(request.prompt == "Redo this poster")
        #expect(viewModel.imageEditMode == .iterate)
        #expect(viewModel.imageEditSourceArtifactID == "job-image-tab-helper-redo::artifact")
    }

    @Test("image tab renders completed jobs without dispatching cancel")
    @MainActor
    func imageTabRendersCompletedJobsWithoutCancelDispatch() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-complete",
                requestID: "req-image-complete",
                operation: "image_generate",
                state: .imageJobCompleted
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))
        await viewModel.cancelSelectedImageJob()

        #expect(view.subviews.isEmpty == false)
        #expect(await client.recordedActions.contains("cancel:req-image-complete") == false)
        #expect(viewModel.imageStatusText != "Canceling")
        #expect(viewModel.imageStatusText != "Failed")
    }

    @Test("image tab renders empty-state placeholders when no jobs are available")
    @MainActor
    func imageTabRendersEmptyStatePlaceholders() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = []
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.imageJobs.isEmpty)
        #expect(viewModel.selectedImageJob == nil)
    }

    @Test("image tab renders timed out image rows through the sidebar")
    @MainActor
    func imageTabRendersTimedOutImageRowsThroughTheSidebar() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarImageModelSummary()]
        var timedOutError = Melix_Controlplane_V1_ErrorStatus()
        timedOutError.code = "deadline_exceeded"
        timedOutError.message = "Image request exceeded the 600-second creative workflow deadline."
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-row-timeout",
                requestID: "req-image-row-timeout",
                operation: "image_generate",
                state: .imageJobFailed,
                timeoutSeconds: 600,
                error: timedOutError
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))
        viewModel.selectImageJob(jobID: "job-image-row-timeout")

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedImageJobTimeoutText == "Timed out • 10-minute deadline")
    }

    @Test("dashboard renders residency and memory protection summaries from control-plane truth")
    @MainActor
    func dashboardRendersResidencyAndMemoryProtectionSummaries() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeMenuBarModelSummary(
                modelID: "melix-dev-text",
                state: .modelPinned,
                pinRequested: true,
                pinned: true,
                ttlSeconds: 900,
                estimatedBytes: 768 * 1024 * 1024,
                memoryPolicy: .memoryResidencyPinned
            ),
            makeMenuBarModelSummary(
                modelID: "melix-dev-guarded",
                state: .modelFailed,
                transitionReason: "memory_budget_exceeded",
                estimatedBytes: 512 * 1024 * 1024,
                inflightRequests: 1
            ),
        ]
        snapshot.metrics.values = [
            "control_plane.model_eviction_ttl_count": 1,
            "control_plane.model_eviction_lru_same_capability_count": 1,
            "control_plane.model_eviction_last_pinned_protected_count": 1,
        ]
        snapshot.recentErrors = [
            {
                var error = Melix_Controlplane_V1_RecentError()
                error.code = "memory_budget_exceeded"
                error.message = "Model load rejected by memory budget headroom."
                return error
            }(),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let view = hostView(DesktopDashboardTabView(foundation: foundation))
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency" && row.value == "1 pinned"
        }
        let hasGuardCard = foundation.dashboardCards.contains { row in
            row.id == "guards" && row.value == "1"
        }
        let hasGuardedModel = foundation.models.contains { row in
            row.modelID == "melix-dev-guarded" && row.memoryAlertText.contains("Memory protection")
        }

        #expect(view.subviews.isEmpty == false)
        #expect(hasResidencyCard)
        #expect(hasGuardCard)
        #expect(hasGuardedModel)
    }

    @Test("dashboard renders an empty residency section when no models are discovered")
    @MainActor
    func dashboardRendersEmptyResidencySection() async throws {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = []
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Empty snapshot",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-empty",
            features: ["xpc", "models"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let view = hostView(DesktopDashboardTabView(foundation: foundation))
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency" && row.value == "0 pinned"
        }

        #expect(view.subviews.isEmpty == false)
        #expect(foundation.models.isEmpty)
        #expect(hasResidencyCard)
    }
}

@MainActor
private func hostView<Content: View>(_ rootView: Content) -> NSView {
    let controller = NSHostingController(rootView: rootView)
    let view = controller.view
    view.frame = NSRect(x: 0, y: 0, width: 1200, height: 800)
    view.layoutSubtreeIfNeeded()
    return view
}

@MainActor
private func renderedTextValues(in rootView: NSView) -> [String] {
    var values: [String] = []

    func appendValue(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty == false {
            values.append(trimmed)
        }
    }

    func visit(_ view: NSView) {
        if let textField = view as? NSTextField {
            appendValue(textField.stringValue)
        }
        if let button = view as? NSButton {
            appendValue(button.title)
        }
        if let popup = view as? NSPopUpButton {
            appendValue(popup.title)
        }
        if let segmented = view as? NSSegmentedControl {
            for index in 0..<segmented.segmentCount {
                appendValue(segmented.label(forSegment: index) ?? "")
            }
        }
        for subview in view.subviews {
            visit(subview)
        }
    }

    visit(rootView)
    return values
}

private func waitForDesktopFoundationCondition(
    _ description: String,
    timeout: Duration = .seconds(2),
    pollInterval: Duration = .milliseconds(10),
    condition: @escaping @MainActor () -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }

    throw MenuBarTestError(description: description)
}

private func makeDesktopRuntimeSession(
    serverSessionID: String = "server-session-1",
    lifecycleState: Melix_Controlplane_V1_ServerSessionLifecycleState = .ready,
    powerState: Melix_Controlplane_V1_ServerSessionPowerState = .active,
    wakeReason: Melix_Controlplane_V1_ServerWakeReason = .initialBoot,
    idleTimerSeconds: UInt32 = 0,
    autoSleepEnabled: Bool = false,
    lightSleepAfterSeconds: UInt32 = 300,
    deepSleepAfterSeconds: UInt32 = 1800
) -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
    runtimeSession.serverSessionID = serverSessionID
    runtimeSession.lifecycleState = lifecycleState
    runtimeSession.powerState = powerState
    runtimeSession.wakeReason = wakeReason
    runtimeSession.idleTimerSeconds = idleTimerSeconds
    runtimeSession.autoSleepEnabled = autoSleepEnabled
    runtimeSession.lightSleepAfterSeconds = lightSleepAfterSeconds
    runtimeSession.deepSleepAfterSeconds = deepSleepAfterSeconds
    runtimeSession.updatedAtUnixMs = 1_717_171_717
    return runtimeSession
}

private func makeAudioSetupSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary]
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = .serverReady
    snapshot.models = models
    return snapshot
}

private func makeAPIOnboardingSummary() -> Melix_Controlplane_V1_APIOnboardingSummary {
    var summary = Melix_Controlplane_V1_APIOnboardingSummary()

    var localSurface = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
    localSurface.surfaceID = "local_service"
    localSurface.title = "Local Service"
    localSurface.summary = "Readiness and operational inspection routes for same-host automation."
    localSurface.status = .shipped
    localSurface.endpointIds = ["health", "cache_stats"]

    var openAISurface = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
    openAISurface.surfaceID = "openai_compatible"
    openAISurface.title = "OpenAI-Compatible"
    openAISurface.summary = "The primary local API surface for text, embeddings, rerank, audio, and image workflows."
    openAISurface.status = .shipped
    openAISurface.endpointIds = [
        "models",
        "responses",
        "images_generations",
    ]

    var anthropicSurface = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
    anthropicSurface.surfaceID = "anthropic_messages"
    anthropicSurface.title = "Anthropic Messages"
    anthropicSurface.summary = "Anthropic-style message execution over the shared local text runtime."
    anthropicSurface.status = .shipped
    anthropicSurface.endpointIds = ["messages"]

    var ollamaSurface = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
    ollamaSurface.surfaceID = "ollama_compatibility"
    ollamaSurface.title = "Ollama Compatibility"
    ollamaSurface.summary = "Compatibility guidance for clients that can target Melix through a custom provider bridge."
    ollamaSurface.status = .compatibilityOnly
    ollamaSurface.compatibilityNote = "Native /api/chat, /api/generate, /api/tags, /api/show, and /api/embeddings routes are not shipped yet."

    var health = Melix_Controlplane_V1_APIReferenceEndpointSummary()
    health.endpointID = "health"
    health.surfaceID = "local_service"
    health.method = "GET"
    health.path = "/health"
    health.summary = "Probe process readiness."

    var cacheStats = Melix_Controlplane_V1_APIReferenceEndpointSummary()
    cacheStats.endpointID = "cache_stats"
    cacheStats.surfaceID = "local_service"
    cacheStats.method = "GET"
    cacheStats.path = "/v1/cache/stats"
    cacheStats.summary = "Inspect cache usage."

    var responses = Melix_Controlplane_V1_APIReferenceEndpointSummary()
    responses.endpointID = "responses"
    responses.surfaceID = "openai_compatible"
    responses.method = "POST"
    responses.path = "/v1/responses"
    responses.summary = "Run Responses-style generation."
    responses.streaming = true

    var models = Melix_Controlplane_V1_APIReferenceEndpointSummary()
    models.endpointID = "models"
    models.surfaceID = "openai_compatible"
    models.method = "GET"
    models.path = "/v1/models"
    models.summary = "List local models."

    var imageGeneration = Melix_Controlplane_V1_APIReferenceEndpointSummary()
    imageGeneration.endpointID = "images_generations"
    imageGeneration.surfaceID = "openai_compatible"
    imageGeneration.method = "POST"
    imageGeneration.path = "/v1/images/generations"
    imageGeneration.summary = "Submit local image-generation jobs."

    var messages = Melix_Controlplane_V1_APIReferenceEndpointSummary()
    messages.endpointID = "messages"
    messages.surfaceID = "anthropic_messages"
    messages.method = "POST"
    messages.path = "/v1/messages"
    messages.summary = "Run Anthropic-style messages requests."
    messages.streaming = true

    summary.surfaces = [localSurface, openAISurface, anthropicSurface, ollamaSurface]
    summary.endpoints = [health, cacheStats, models, responses, imageGeneration, messages]
    return summary
}

private func makeNamedModelOperationResult(
    operation: String,
    outputPath: String,
    manifestJSON: String,
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
    if !artifactKind.isEmpty {
        result.artifact = Melix_Controlplane_V1_ModelOperationArtifact()
        result.artifact.schemaVersion = "melix.artifact.v1"
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

private func makeMenuBarModelSummary(
    modelID: String,
    state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = "",
    pinRequested: Bool = false,
    pinned: Bool = false,
    ttlSeconds: UInt32 = 0,
    estimatedBytes: UInt64 = 0,
    inflightRequests: UInt64 = 0,
    memoryPolicy: Melix_Controlplane_V1_MemoryResidencyPolicy = .memoryResidencyEvictable
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
    model.settings.alias = "Melix \(modelID)"
    model.settings.pinOnLoad = pinRequested
    model.settings.ttlSeconds = ttlSeconds
    model.settings.memoryPolicy = memoryPolicy
    model.settings.defaultAccelerationMode = .baseline
    model.residency.pinRequested = pinRequested
    model.residency.pinned = pinned
    model.residency.ttlSeconds = ttlSeconds
    model.residency.policy = memoryPolicy
    model.residency.transitionReason = transitionReason
    return model
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

private actor EmptyToolsSnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-empty-tools"
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
