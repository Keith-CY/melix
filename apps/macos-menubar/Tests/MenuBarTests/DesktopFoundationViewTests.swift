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
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.modelsLibrary)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let values = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(values.contains("Melix Text Turbo"))
        #expect(values.contains("mlx-text"))
        #expect(values.contains("600"))
        #expect(values.contains("Active KV Quantized"))
        #expect(values.contains("Adaptive"))
        #expect(values.contains("192"))
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
            aliasText: "Melix Text Turbo",
            typeOverrideText: "mlx-text",
            ttlSeconds: 600,
            pinOnLoad: true,
            memoryPolicyText: "TTL",
            adaptiveThinkingText: "Adaptive • 192 tok",
            accelerationModeText: "Active KV Quantized",
            accelerationProfileID: "kv-q8",
            toolParserFallbackText: "XML",
            ocrPromptProfileText: "ocr-default-v1",
            ocrSamplingProfileText: "ocr-deterministic",
            ocrTemperatureText: "0.05",
            ocrTopPText: "0.82",
            ocrMaxTokensText: "192",
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
        #expect(content.detailLines.contains("adaptive thinking: Adaptive • 192 tok"))
        #expect(content.detailLines.contains("acceleration: Active KV Quantized • kv-q8"))
        #expect(content.detailLines.contains("parser fallback: XML"))
        #expect(content.detailLines.contains("pin on load: yes"))
        #expect(content.detailLines.contains("ttl seconds: 600"))
        #expect(content.detailLines.contains("parsers: text, json"))
        #expect(content.detailLines.contains("modalities: text, image"))
        #expect(content.detailLines.contains("generation config: /tmp/melix-dev-text/generation_config.json"))
        #expect(content.detailLines.contains("generation defaults: temp 0.12 • top-p 0.9 • max 320"))
        #expect(content.detailLines.contains("ocr sampling defaults: ocr-deterministic • temp 0.05 • top-p 0.82 • max 192"))
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
        #expect(requests.count == 2)
        #expect(requests[0].operation == "install_audio_runtime")
        #expect(requests[1].operation == "download")
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
