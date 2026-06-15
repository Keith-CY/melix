import AppKit
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

private let desktopTestReadyModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
private let desktopTestReadyLoRAModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit-lora"

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

    @Test("shared pane chrome exposes labeled icon controls")
    @MainActor
    func sharedPaneChromeExposesLabeledIconControls() {
        let hideSidebar = hostView(
            DesktopPaneToggleButton(role: .sidebar, isVisible: true, action: {})
        )
        let showInspector = hostView(
            DesktopPaneToggleButton(role: .inspector, isVisible: false, action: {})
        )

        #expect(hideSidebar.fittingSize.width <= DesktopShellChromeMetrics.paneToggleButtonWidth + 8)
        #expect(showInspector.fittingSize.width <= DesktopShellChromeMetrics.paneToggleButtonWidth + 8)
        #expect(DesktopPaneRole.sidebar.symbolName == "sidebar.left")
        #expect(DesktopPaneRole.inspector.symbolName == "sidebar.right")
        #expect(DesktopPaneRole.sidebar.accessibilityLabel(isVisible: true) == "Hide Sidebar")
        #expect(DesktopPaneRole.inspector.accessibilityLabel(isVisible: false) == "Show Inspector")
    }

    @Test("design tokens keep semantic opacity roles explicit")
    func designTokensKeepSemanticOpacityRolesExplicit() {
        _ = MelixDesignTokens.brandAccent
        _ = MelixDesignTokens.BubbleTint.user
        _ = MelixDesignTokens.BubbleTint.assistant
        _ = MelixDesignTokens.BubbleTint.reasoning
        _ = MelixDesignTokens.BubbleTint.tool
        _ = MelixDesignTokens.BubbleTint.error

        #expect(MelixDesignTokens.StrokeOpacity.hairline == MelixDesignTokens.SurfaceOpacity.card)
        #expect(MelixDesignTokens.StrokeOpacity.interactive == 0.08)
        #expect(MelixDesignTokens.StrokeOpacity.input == 0.18)
        #expect(MelixDesignTokens.StrokeOpacity.focusedInput == 0.72)
        #expect(MelixDesignTokens.AccentOpacity.medium == 0.32)
        #expect(MelixDesignTokens.AccentOpacity.weak == 0.12)
        #expect(MelixDesignTokens.AccentOpacity.selected == 0.12)
        #expect(MelixDesignTokens.AccentOpacity.capsule == 0.12)
        #expect(MelixDesignTokens.AccentOpacity.faint == 0.06)
        #expect(MelixDesignTokens.BubbleOpacity.user == 0.10)
        #expect(MelixDesignTokens.BubbleOpacity.assistant == 0.09)
        #expect(MelixDesignTokens.BubbleOpacity.reasoning == 0.09)
        #expect(MelixDesignTokens.BubbleOpacity.tool == 0.09)
        #expect(MelixDesignTokens.BubbleOpacity.error == 0.09)
        #expect(MelixDesignTokens.StateOpacity.background == 0.09)
    }

    @Test("design color palette matches the design system css tokens")
    func designColorPaletteMatchesDesignSystemCSSTokens() {
        typealias DesignColor = MelixDesignTokens.DesignColor
        typealias Components = DesignColor.Components

        #expect(MelixDesignTokens.Palette.accent == MelixDesignTokens.DesignColor(red: 0x0F, green: 0x76, blue: 0x6E))
        #expect(MelixDesignTokens.Palette.foregroundPrimary == DesignColor(light: Components(red: 0x0A, green: 0x0A, blue: 0x0A), dark: Components(red: 0xFD, green: 0xFD, blue: 0xFD)))
        #expect(MelixDesignTokens.Palette.foregroundSecondary == DesignColor(light: Components(red: 0x3A, green: 0x3A, blue: 0x3A), dark: Components(red: 0xC8, green: 0xC8, blue: 0xC8)))
        #expect(MelixDesignTokens.Palette.foregroundTertiary == DesignColor(light: Components(red: 0x6B, green: 0x6B, blue: 0x6B), dark: Components(red: 0x8A, green: 0x8A, blue: 0x8A)))
        #expect(MelixDesignTokens.Palette.foregroundQuaternary == DesignColor(light: Components(red: 0x9A, green: 0x9A, blue: 0x9A), dark: Components(red: 0x5A, green: 0x5A, blue: 0x5A)))
        #expect(MelixDesignTokens.Palette.foregroundInverse == DesignColor(light: Components(red: 0xFD, green: 0xFD, blue: 0xFD), dark: Components(red: 0x0A, green: 0x0A, blue: 0x0A)))
        #expect(MelixDesignTokens.Palette.backgroundBase == DesignColor(light: Components(red: 0xFA, green: 0xFA, blue: 0xFA), dark: Components(red: 0x1A, green: 0x1A, blue: 0x1A)))
        #expect(MelixDesignTokens.Palette.backgroundSurface == DesignColor(light: Components(red: 0xFF, green: 0xFF, blue: 0xFF), dark: Components(red: 0x22, green: 0x22, blue: 0x22)))
        #expect(MelixDesignTokens.Palette.backgroundElevated == DesignColor(light: Components(red: 0xF5, green: 0xF5, blue: 0xF5), dark: Components(red: 0x2A, green: 0x2A, blue: 0x2A)))
        #expect(MelixDesignTokens.Palette.backgroundSunken == DesignColor(light: Components(red: 0xF0, green: 0xF0, blue: 0xF0), dark: Components(red: 0x16, green: 0x16, blue: 0x16)))
        #expect(MelixDesignTokens.Palette.success == MelixDesignTokens.DesignColor(red: 0x14, green: 0xA0, blue: 0x5A))
        #expect(MelixDesignTokens.Palette.warning == MelixDesignTokens.DesignColor(red: 0xD9, green: 0x77, blue: 0x06))
        #expect(MelixDesignTokens.Palette.error == MelixDesignTokens.DesignColor(red: 0xDC, green: 0x26, blue: 0x26))
        #expect(MelixDesignTokens.Palette.userBubble == MelixDesignTokens.DesignColor(red: 0x00, green: 0x64, blue: 0xDC))
        #expect(MelixDesignTokens.Palette.assistantBubble == MelixDesignTokens.DesignColor(red: 0x14, green: 0xA0, blue: 0x50))
        #expect(MelixDesignTokens.Palette.reasoningBubble == MelixDesignTokens.DesignColor(red: 0xDC, green: 0x6E, blue: 0x14))
        #expect(MelixDesignTokens.Palette.toolBubble == MelixDesignTokens.DesignColor(red: 0x78, green: 0x3C, blue: 0xC8))
        #expect(MelixDesignTokens.Palette.errorBubble == MelixDesignTokens.DesignColor(red: 0xD2, green: 0x28, blue: 0x28))
    }

    @Test("lora visual polish tokens use the design system base background with clearer hierarchy")
    func loraVisualPolishTokensUseDesignSystemBaseBackground() {
        #expect(DesktopLoRAVisualPolish.pageBackgroundColorSpec == MelixDesignTokens.Palette.backgroundBase)
        #expect(DesktopLoRAVisualPolish.sectionSurfaceOpacity == 0.04)
        #expect(DesktopLoRAVisualPolish.metricSurfaceOpacity == 0.032)
        #expect(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity == MelixDesignTokens.AccentOpacity.selected)
        #expect(DesktopLoRAVisualPolish.chartFillOpacity == 0.24)
    }

    @Test("diagnostics throughput bars declare a fixed mark width")
    func diagnosticsThroughputBarsDeclareFixedMarkWidth() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let shellSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift"
        )
        let shellSource = try String(contentsOf: shellSourceURL, encoding: .utf8)
        let throughputChartSource = try #require(
            shellSource.slice(
                from: "Chart(viewModel.benchmarkMatrixThroughputChartPoints)",
                to: ".chartLegend(.hidden)"
            )
        )

        #expect(throughputChartSource.contains("width: .fixed(12)"))
    }

    @Test("menubar swift verification disables noisy debug info")
    func menubarSwiftVerificationDisablesNoisyDebugInfo() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let makefileURL = root.appendingPathComponent("Makefile")
        let makefile = try String(contentsOf: makefileURL, encoding: .utf8)
        let menubarTestTarget = try #require(
            makefile.slice(from: "swift-test-menubar:", to: "py-test:")
        )
        let menubarCoverageCommand = try #require(
            makefile.slice(from: "swift-coverage:", to: "py-coverage:")
        )

        #expect(makefile.contains("MENUBAR_SWIFT_TEST_FLAGS := --no-parallel -Xswiftc -gnone"))
        #expect(menubarTestTarget.contains("$(MENUBAR_SWIFT_TEST_FLAGS)"))
        #expect(menubarCoverageCommand.contains("$(MENUBAR_SWIFT_TEST_FLAGS)"))
    }

    @Test("command center visuals track design-system and Apple-style inputs")
    func commandCenterVisualsTrackDesignInputs() {
        #expect(DesktopCommandCenterVisuals.visualDirection == "Digital Broadsheet Command Center")
        #expect(DesktopCommandCenterVisuals.operatorLabel == "Melix Operator")
        #expect(DesktopCommandCenterVisuals.windowTitle == "Command Center")
        #expect(DesktopCommandCenterVisuals.runtimeSectionTitle == "Providers")
        #expect(DesktopCommandCenterVisuals.pressureSectionTitle == "Resource And Queue Pressure")
        #expect(DesktopCommandCenterVisuals.recoverySectionTitle == "Recovery")
        #expect(DesktopCommandCenterVisuals.workflowSectionTitle == "Workflow")
        #expect(DesktopCommandCenterVisuals.activitySectionTitle == "Recent Activity")
        #expect(DesktopCommandCenterVisuals.sessionSummarySectionTitle == "Session Summary")
        #expect(DesktopCommandCenterVisuals.primaryModelTitle == "Primary Model")
        #expect(DesktopCommandCenterVisuals.repositoryDesignSystemPath == "docs/design-system/README.md")
        #expect(DesktopCommandCenterVisuals.appleLayoutGuidanceURL.contains("human-interface-guidelines/layout"))
        #expect(DesktopCommandCenterVisuals.maxContentWidth == 1180)
        #expect(DesktopCommandCenterVisuals.secondaryColumnWidth == 340)
        #expect(DesktopCommandCenterVisuals.maxContentWidth > DesktopCommandCenterVisuals.secondaryColumnWidth * 2)
        #expect(DesktopCommandCenterVisuals.panelCornerRadius == MelixDesignTokens.Radius.xl)
        #expect(DesktopCommandCenterVisuals.statusSymbolName == "command.circle")
        #expect(DesktopCommandCenterVisuals.recoverySymbolName == "arrow.clockwise.circle")
    }

    @Test("command center health is derived from foundation state semantics")
    func commandCenterHealthUsesSemanticFoundationState() {
        func foundation(
            serverState: Melix_Controlplane_V1_ServerState,
            lastError: String? = nil
        ) -> DesktopFoundationState {
            var snapshot = Melix_Controlplane_V1_ServerSnapshot()
            snapshot.serverState = serverState
            return DesktopFoundationState.build(
                statusTitle: "Melix Ready",
                serverStateText: "Localized server copy",
                connectionStateText: "Localized connection copy",
                connectionDetailText: "Snapshot hydrated",
                snapshot: snapshot,
                protocolVersion: "melix.controlplane.v1",
                serverVersion: "0.1.0",
                daemonInstanceID: "daemon-command-center-health",
                features: ["xpc"],
                productUpdateSummary: nil,
                productUpdateDetail: nil,
                lastError: lastError,
                recentEvents: []
            )
        }

        #expect(foundation(serverState: .serverReady).healthState == .runtimeReady)
        #expect(foundation(serverState: .serverDegraded).healthState == .runtimeWarning)
        #expect(foundation(serverState: .serverDraining).healthState == .runtimeWarning)
        #expect(foundation(serverState: .serverStopped).healthState == .recoveryAvailable)
        #expect(foundation(serverState: .serverFailed).healthState == .needsAttention)
        #expect(foundation(serverState: .serverReady, lastError: "Handshake failed").healthState == .needsAttention)
    }

    @Test("logo svg resource mirrors the design system asset")
    func logoSVGResourceMirrorsDesignSystemAsset() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let designSystemLogo = root.appendingPathComponent("docs/design-system/assets/melix_logo.svg")
        let appLogo = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Resources/Branding/melix_logo.svg"
        )

        #expect(try Data(contentsOf: appLogo) == Data(contentsOf: designSystemLogo))
    }

    @Test("repository root helper rejects unrelated roots")
    func repositoryRootHelperRejectsUnrelatedRoots() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        #expect(throws: DesktopFoundationTestError.repositoryRootNotFound) {
            try repositoryRootForDesktopFoundationTests(startingAt: root)
        }
    }

    @Test("desktop banner recovery priority is explicit")
    func desktopBannerRecoveryPriorityIsExplicit() {
        let recoverableWarning = DesktopBannerState(
            id: "arbitrary-recovery-id",
            title: "Recoverable",
            detail: "Can resume",
            severity: .warning,
            isRecoverable: true
        )
        let regularWarning = DesktopBannerState(
            id: "download-recovery",
            title: "Regular Warning",
            detail: "Not recoverable",
            severity: .warning
        )

        #expect(recoverableWarning.priority == .recovery)
        #expect(regularWarning.priority == .warning)
    }

    @Test("workspace commands update surface selection and command center")
    @MainActor
    func workspaceCommandsUpdateSurfaceSelectionAndCommandCenter() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let commandCenter = CommandCenterOpenRecorder()
        viewModel.openCommandCenterAction = { commandCenter.open() }
        await viewModel.start()

        DesktopWorkspaceCommand.selectSurface(.image).perform(on: viewModel)
        #expect(viewModel.selectedSurface == .image)

        DesktopWorkspaceCommand.selectToolSection(.downloads).perform(on: viewModel)
        #expect(viewModel.selectedSurface == .models)
        #expect(viewModel.selectedToolSection == .downloads)

        DesktopWorkspaceCommand.openCommandCenter.perform(on: viewModel)
        #expect(commandCenter.wasOpened)
    }

    @Test("titlebar exposes only primary navigation entries")
    @MainActor
    func titlebarExposesOnlyPrimaryNavigationEntries() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()

        let hosted = hostView(DesktopWorkspaceTitleBarTabsView(viewModel: viewModel))
        let root = try repositoryRootForDesktopFoundationTests()
        let rootSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift"
        )
        let chromeSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift"
        )
        let rootSource = try String(contentsOf: rootSourceURL, encoding: .utf8)
        let chromeSource = try String(contentsOf: chromeSourceURL, encoding: .utf8)

        #expect(hosted.subviews.isEmpty == false)
        #expect(DesktopSurface.visibleNavigationCases.map(\.rawValue) == ["Chat", "Providers", "Models", "Workflows"])
        #expect(chromeSource.contains("ForEach(DesktopSurface.visibleNavigationCases)"))
        #expect(rootSource.contains("ToolbarItem(placement: .principal)"))
        #expect(rootSource.contains("ToolbarItem(placement: .primaryAction)") == false)
    }

    @Test("titlebar pane toggles use the shared pane animation contract")
    @MainActor
    func titlebarPaneTogglesUseSharedPaneAnimationContract() {
        #expect(DesktopWorkspacePaneAnimation.durationSeconds >= 0.16)
        #expect(DesktopWorkspacePaneAnimation.durationSeconds <= 0.24)
        #expect(DesktopWorkspacePaneTransition.edge(for: .sidebar) == .leading)
        #expect(DesktopWorkspacePaneTransition.edge(for: .inspector) == .trailing)
    }

    @Test("workspace panes collapse by animating their owning edge slot")
    @MainActor
    func workspacePanesCollapseByAnimatingTheirOwningEdgeSlot() {
        #expect(DesktopWorkspacePaneSlotMetrics.width(isVisible: false, idealWidth: 220) == 0)
        #expect(DesktopWorkspacePaneSlotMetrics.width(isVisible: true, idealWidth: 220) == 220)
        #expect(DesktopWorkspacePaneSlotMetrics.alignment(for: .sidebar) == .leading)
        #expect(DesktopWorkspacePaneSlotMetrics.alignment(for: .inspector) == .trailing)
    }

    @Test("workspace pane dividers are clipped by the owning pane slot")
    func workspacePaneDividersAreClippedByTheOwningPaneSlot() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let shellChrome = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift"
        )
        let shellSource = try String(contentsOf: shellChrome, encoding: .utf8)

        #expect(shellSource.contains("struct DesktopWorkspacePaneBoundary"))
        #expect(DesktopWorkspacePaneSlotMetrics.boundaryAlignment(for: .sidebar) == .trailing)
        #expect(DesktopWorkspacePaneSlotMetrics.boundaryAlignment(for: .inspector) == .leading)

        let workspaceSources = [
            "apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift",
            "apps/macos-menubar/Sources/AppMain/Image/DesktopImageView.swift",
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift",
        ]

        for relativePath in workspaceSources {
            let sourceURL = root.appendingPathComponent(relativePath)
            let source = try String(contentsOf: sourceURL, encoding: .utf8)

            #expect(source.contains("if showsSidebar {\n                Divider()") == false)
            #expect(source.contains("if showsInspector {\n                Divider()") == false)
        }
    }

    @Test("chat submit shortcut is not double-owned by the SwiftUI send button")
    func chatSubmitShortcutIsNotDoubleOwnedByTheSwiftUISendButton() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let chatView = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"
        )
        let source = try String(contentsOf: chatView, encoding: .utf8)

        #expect(source.contains(".keyboardShortcut(.return, modifiers: .command)") == false)
    }

    @Test("tools categories map sections into staged workflow groups")
    @MainActor
    func toolsCategoriesMapSectionsIntoStagedWorkflowGroups() {
        #expect(DesktopToolCategory.models.sections == [.modelsLibrary, .downloads])
        #expect(DesktopToolCategory.workflows.sections == [.training, .workflowRecipes, .syntheticDatasets, .batchRuns])
        #expect(DesktopToolCategory.jobs.sections == [.jobs])
        #expect(DesktopToolCategory.diagnostics.sections == [.diagnostics, .logs])
        #expect(DesktopToolCategory.system.sections == [.settings])
    }

    @Test("tool categories cover every tool section exactly once")
    @MainActor
    func toolCategoriesCoverEveryToolSectionExactlyOnce() {
        let categorizedSections = DesktopToolCategory.allCases.flatMap(\.sections)
        let missingSections = DesktopToolSection.allCases.filter { section in
            categorizedSections.contains(section) == false
        }
        let duplicateSections = DesktopToolSection.allCases.filter { section in
            categorizedSections.filter { $0 == section }.count > 1
        }

        #expect(missingSections.isEmpty)
        #expect(duplicateSections.isEmpty)
        #expect(categorizedSections.count == DesktopToolSection.allCases.count)
    }

    @Test("workspace surfaces use shared icon pane controls")
    @MainActor
    func workspaceSurfacesUseSharedIconPaneControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        for surface in [DesktopSurface.server, .jobs, .image, .tools, .api] {
            viewModel.selectSurface(surface)
            let hosted = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
            let renderedTexts = renderedTextValues(in: hosted)

            #expect(hosted.subviews.isEmpty == false)
            #expect(renderedTexts.contains("Hide List") == false)
            #expect(renderedTexts.contains("Hide Inspector") == false)
            #expect(DesktopPaneRole.sidebar.accessibilityLabel(isVisible: true) == "Hide Sidebar")
            #expect(DesktopPaneRole.inspector.accessibilityLabel(isVisible: false) == "Show Inspector")
            #expect(viewModel.isDesktopPaneVisible(.inspector, for: surface) == false)
        }
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
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
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
        listener.effectivePort = UInt32(MelixGatewayDefaults.port)
        listener.defaultModelID = desktopTestReadyModelID
        listener.servedModelIds = [desktopTestReadyModelID]
        listener.rateLimitPerMinute = 240
        listener.timeoutSeconds = 90
        listener.source = .operatorOverride
        listener.activeBinding = true
        listener.requiresRestart = true
        snapshot.gatewayConfig.listeners = [listener]
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.defaultModelID = desktopTestReadyModelID
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
        view.frame = NSRect(x: 0, y: 0, width: 1200, height: 2400)
        view.layoutSubtreeIfNeeded()
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .server)
        #expect(renderedTexts.contains("0.0.0.0"))
        #expect(renderedTexts.contains("18,080"))
        #expect(renderedTexts.contains("240"))
        #expect(renderedTexts.contains("90"))
        #expect(viewModel.selectedServerSession?.effectiveBaseURL == "http://127.0.0.1:12436/v1")
        #expect(viewModel.selectedServerSession?.gatewayConfigRequiresRestart == true)
        #expect(viewModel.selectedServerSession?.gatewayConfigSourceText == "Operator Override")
        #expect(viewModel.selectedServerSession?.servingDefaults.streamIntervalTokens == 3)
        #expect(viewModel.selectedServerSession?.servingDefaults.effectiveMaxTokens == 512)
        #expect(viewModel.selectedServerSession?.servingDefaults.modelOverrideApplied == true)
    }

    @Test("workspace server surface renders projected serving defaults profile metadata")
    @MainActor
    func workspaceServerSurfaceRendersProjectedServingDefaultsProfileMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.defaultModelID = desktopTestReadyModelID
        servingDefaults.requestedTemperature = 0.44
        servingDefaults.requestedTopP = 0.91
        servingDefaults.requestedMaxTokens = 320
        servingDefaults.requestedStreamIntervalTokens = 2
        servingDefaults.requestedMaxConcurrentRequests = 6
        servingDefaults.requestedConcurrentProcessingEnabled = false
        servingDefaults.requestedPrefillBatchSize = 4
        servingDefaults.requestedCompletionBatchSize = 3
        servingDefaults.requestedAccelerationProfile = "low-memory"
        servingDefaults.effectiveTemperature = 0.25
        servingDefaults.effectiveTopP = 0.85
        servingDefaults.effectiveMaxTokens = 512
        servingDefaults.effectiveStreamIntervalTokens = 2
        servingDefaults.effectiveMaxConcurrentRequests = 1
        servingDefaults.effectiveConcurrentProcessingEnabled = false
        servingDefaults.effectivePrefillBatchSize = 1
        servingDefaults.effectiveCompletionBatchSize = 1
        servingDefaults.effectiveAccelerationProfile = "low-memory"
        servingDefaults.accelerationProfileIntent = "Conservative single-request serving for constrained local memory."
        servingDefaults.source = .environmentDefaults
        snapshot.servingDefaults.sessions = [servingDefaults]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Profile"))
        #expect(renderedTexts.contains("Low Memory"))
        #expect(viewModel.selectedServerSession?.servingDefaults.temperature == 0.44)
        #expect(viewModel.selectedServerSession?.servingDefaults.topP == 0.91)
        #expect(viewModel.selectedServerSession?.servingDefaults.maxTokens == 320)
        #expect(viewModel.selectedServerSession?.servingDefaults.streamIntervalTokens == 2)
        #expect(viewModel.selectedServerSession?.servingDefaults.maxConcurrentRequests == 6)
        #expect(viewModel.selectedServerSession?.servingDefaults.sourceText == "Environment Defaults")
    }

    @Test("workspace server surface renders acceleration profile picker")
    @MainActor
    func workspaceServerSurfaceRendersAccelerationProfilePicker() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(
            DesktopWorkspaceShellView(viewModel: viewModel),
            size: CGSize(width: 1_280, height: 1_400)
        )
        let renderedTexts = renderedTextValues(in: view)
        let pickerView = hostView(
            DesktopServingAccelerationProfilePicker(viewModel: viewModel),
            size: CGSize(width: 320, height: 120)
        )
        let pickerTexts = renderedTextValues(in: pickerView)

        #expect(viewModel.servingAccelerationProfileOptions.map(\.id) == [
            "balanced",
            "throughput",
            "low-memory",
            "long-session",
        ])
        #expect(renderedTexts.contains("Acceleration Profile"))
        #expect(renderedTexts.contains("Balanced"))
        #expect(pickerTexts.contains("Acceleration Profile"))
        #expect(pickerTexts.contains("Balanced"))

        viewModel.updateSelectedServerSessionAccelerationProfile("LOW_MEMORY")

        #expect(viewModel.selectedServerSession?.servingDefaults.accelerationProfile == "low-memory")
    }

    @Test("workspace server surface renders requested and effective acceleration profile receipts")
    @MainActor
    func workspaceServerSurfaceRendersRequestedAndEffectiveAccelerationProfileReceipts() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.defaultModelID = desktopTestReadyModelID
        servingDefaults.requestedTemperature = 0.4
        servingDefaults.requestedTopP = 0.9
        servingDefaults.requestedMaxTokens = 512
        servingDefaults.requestedStreamIntervalTokens = 2
        servingDefaults.requestedMaxConcurrentRequests = 8
        servingDefaults.requestedConcurrentProcessingEnabled = true
        servingDefaults.requestedPrefillBatchSize = 4
        servingDefaults.requestedCompletionBatchSize = 4
        servingDefaults.requestedAccelerationMode = .speculativeDecode
        servingDefaults.requestedNumDraftTokens = 6
        servingDefaults.requestedAccelerationProfile = "throughput"
        servingDefaults.effectiveTemperature = 0.4
        servingDefaults.effectiveTopP = 0.9
        servingDefaults.effectiveMaxTokens = 512
        servingDefaults.effectiveStreamIntervalTokens = 2
        servingDefaults.effectiveMaxConcurrentRequests = 1
        servingDefaults.effectiveConcurrentProcessingEnabled = false
        servingDefaults.effectivePrefillBatchSize = 1
        servingDefaults.effectiveCompletionBatchSize = 1
        servingDefaults.effectiveAccelerationMode = .baseline
        servingDefaults.effectiveAccelerationProfile = "low-memory"
        servingDefaults.accelerationProfileIntent = "Conservative single-request serving for constrained local memory."
        servingDefaults.source = .operatorOverride
        snapshot.servingDefaults.sessions = [servingDefaults]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(
            DesktopWorkspaceShellView(viewModel: viewModel),
            size: CGSize(width: 1_280, height: 1_400)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Requested profile: Throughput"))
        #expect(renderedTexts.contains("Effective profile: Low Memory"))
        #expect(renderedTexts.contains("Intent: Conservative single-request serving for constrained local memory."))
        #expect(renderedTexts.contains("Resolved defaults: None • sequences 1 • prefill 1 • completion 1"))
    }

    @Test("profile regression renders requested effective and resolved serving receipts")
    @MainActor
    func profileRegressionRendersRequestedEffectiveAndResolvedServingReceipts() throws {
        let servingDefaults = DesktopServerServingDefaultsState(
            maxConcurrentRequests: 2,
            concurrentProcessingEnabled: true,
            prefillBatchSize: 2,
            completionBatchSize: 1,
            accelerationProfile: "long-session",
            accelerationMode: "sparse_prefill",
            effectiveMaxConcurrentRequests: 1,
            effectiveConcurrentProcessingEnabled: false,
            effectivePrefillBatchSize: 1,
            effectiveCompletionBatchSize: 1,
            effectiveAccelerationProfile: "low-memory",
            accelerationProfileIntent: "Runtime selected low-memory after model constraints.",
            effectiveAccelerationMode: "baseline"
        )
        let view = hostView(
            DesktopServingAccelerationProfileSummary(servingDefaults: servingDefaults),
            size: CGSize(width: 520, height: 160)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Requested profile: Long Session"))
        #expect(renderedTexts.contains("Effective profile: Low Memory"))
        #expect(renderedTexts.contains("Intent: Runtime selected low-memory after model constraints."))
        #expect(renderedTexts.contains("Resolved defaults: None • sequences 1 • prefill 1 • completion 1"))
    }

    @Test("workspace server surface renders remote server picker and editor")
    @MainActor
    func workspaceServerSurfaceRendersRemoteServerPickerAndEditor() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let store = FakeRemoteServerStore(servers: [
            RemoteServer(
                id: "kimi",
                title: "Kimi",
                providerPreset: .kimi,
                providerKind: "openai-compatible",
                baseURL: "https://api.kimi.com/coding",
                defaultModelID: "kimi-2.6",
                timeoutSeconds: 60,
                rateLimitPerMinute: 0,
                credentialRef: RemoteServerStore.credentialRef(for: "kimi"),
                apiKeyHint: "sk-k...7890",
                healthStatus: "healthy"
            ),
            RemoteServer(
                id: "gemini",
                title: "Gemini",
                providerPreset: .gemini,
                providerKind: "gemini-generative-language",
                baseURL: "https://generativelanguage.googleapis.com/v1beta",
                defaultModelID: "gemini-2.5-flash",
                timeoutSeconds: 90,
                rateLimitPerMinute: 3,
                credentialRef: RemoteServerStore.credentialRef(for: "gemini"),
                apiKeyHint: "AIza...cret",
                healthStatus: "unknown"
            ),
        ])
        let viewModel = RuntimeViewModel(client: client, remoteServerStore: store)
        await viewModel.start()
        viewModel.selectSurface(.server)
        viewModel.selectRemoteServer(id: "gemini")

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        view.frame = NSRect(x: 0, y: 0, width: 1200, height: 2600)
        view.layoutSubtreeIfNeeded()
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Gemini"))
        #expect(renderedTexts.contains("gemini-2.5-flash"))
        #expect(renderedTexts.contains("https://generativelanguage.googleapis.com/v1beta"))
        #expect(renderedTexts.contains("90"))
        #expect(renderedTexts.contains("3"))
        #expect(viewModel.selectedRemoteServerID == "gemini")
        #expect(viewModel.remoteServerProviderPresetDraft == .gemini)
        #expect(viewModel.isRemoteServerBaseURLEditable == false)
    }

    @Test("server workspace folds advanced serving defaults by default")
    @MainActor
    func serverWorkspaceFoldsAdvancedServingDefaultsByDefault() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.server)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopServerWorkspaceDefaults.showsAdvancedServingDefaults == false)
        #expect(DesktopServerWorkspaceDefaults.advancedServingDefaultsTitle == "Advanced Serving Defaults")
        #expect(renderedTexts.contains("Apply Serving Defaults") == false)
        #expect(renderedTexts.contains("Temperature") == false)
        #expect(renderedTexts.contains("Top P") == false)
    }

    @Test("server empty states dispatch local and remote creation actions")
    @MainActor
    func serverEmptyStatesDispatchCreationActions() async throws {
        let localViewModel = RuntimeViewModel(client: EmptyToolsSnapshotControlPlaneXPCClient())
        await localViewModel.start()
        localViewModel.selectSurface(.server)

        let localView = hostView(
            DesktopWorkspaceShellView(viewModel: localViewModel),
            size: CGSize(width: 1280, height: 1200)
        )
        DesktopServerCreationActions.addLocalServer(viewModel: localViewModel)

        #expect(localView.subviews.isEmpty == false)
        #expect(localViewModel.isCreatingServerTarget)
        #expect(localViewModel.selectedServerCreationKind == .localServer)
        #expect(localViewModel.selectedSurface == .server)

        let remoteViewModel = RuntimeViewModel(client: EmptyToolsSnapshotControlPlaneXPCClient())
        await remoteViewModel.start()
        remoteViewModel.selectSurface(.server)

        let remoteView = hostView(
            DesktopWorkspaceShellView(viewModel: remoteViewModel),
            size: CGSize(width: 1280, height: 1200)
        )
        DesktopServerCreationActions.addRemoteServer(viewModel: remoteViewModel)

        #expect(remoteView.subviews.isEmpty == false)
        #expect(remoteViewModel.isCreatingServerTarget)
        #expect(remoteViewModel.selectedServerCreationKind == .remoteServer)
        #expect(remoteViewModel.selectedSurface == .server)
    }

    @Test("server creation editor renders local input fields with ready models")
    @MainActor
    func serverCreationEditorRendersLocalInputFieldsWithReadyModels() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.beginServerCreation(kind: .localServer)

        let view = hostView(
            DesktopWorkspaceShellView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1200)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.isCreatingServerTarget)
        #expect(viewModel.selectedServerCreationKind == .localServer)
        #expect(viewModel.serverModelOptions.isEmpty == false)
        #expect(renderedTexts.contains(where: { $0.contains(desktopTestReadyModelID) }))
        #expect(renderedTexts.contains("127.0.0.1"))
        #expect(renderedTexts.contains("12,436") || renderedTexts.contains("12436"))
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
        #expect(DesktopCommandCenterVisuals.operatorLabel == "Melix Operator")
        #expect(DesktopCommandCenterVisuals.windowTitle == "Command Center")
        #expect(DesktopCommandCenterVisuals.runtimeSectionTitle == "Providers")
        #expect(DesktopCommandCenterVisuals.pressureSectionTitle == "Resource And Queue Pressure")
        #expect(DesktopCommandCenterVisuals.recoverySectionTitle == "Recovery")
        #expect(DesktopCommandCenterVisuals.activitySectionTitle == "Recent Activity")
        #expect(DesktopCommandCenterVisuals.sessionSummarySectionTitle == "Session Summary")
    }

    @Test("command center renders state-first recovery and workflow summaries")
    @MainActor
    func commandCenterRendersStateFirstRecoveryAndWorkflowSummaries() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "model-ops-command-center",
                            sourceModel: "melix-dev-text",
                            status: "stalled",
                            stage: "download",
                            pct: 0.5,
                            outputDir: "/tmp/melix-downloads/melix-dev-text",
                            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
                            selectedMirror: "https://mirror.example/command-center",
                            downloadedBytes: 1024,
                            totalBytes: 2048,
                            resumeReady: true
                        ),
                        MenuBarDownloadFixture(
                            jobID: "model-ops-command-center-2",
                            sourceModel: "melix-dev-vision",
                            status: "stalled",
                            stage: "download",
                            pct: 0.25,
                            outputDir: "/tmp/melix-downloads/melix-dev-vision",
                            outputPath: "/tmp/melix-downloads/melix-dev-vision/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-vision/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-vision/download.state.json",
                            selectedMirror: "https://mirror.example/command-center-2",
                            downloadedBytes: 512,
                            totalBytes: 2048,
                            resumeReady: true
                        ),
                        MenuBarDownloadFixture(
                            jobID: "model-ops-command-center-3",
                            sourceModel: "melix-dev-audio",
                            status: "stalled",
                            stage: "download",
                            pct: 0.75,
                            outputDir: "/tmp/melix-downloads/melix-dev-audio",
                            outputPath: "/tmp/melix-downloads/melix-dev-audio/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-audio/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-audio/download.state.json",
                            selectedMirror: "https://mirror.example/command-center-3",
                            downloadedBytes: 1536,
                            totalBytes: 2048,
                            resumeReady: true
                        )
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshDownloadQueueState()

        let view = hostView(DesktopCommandCenterView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.desktopFoundationState.models.isEmpty == false)
        #expect(viewModel.recoverableDownloads.count == 3)
        #expect(viewModel.desktopSignalStates.contains { $0.title == "Download Recovery Available" })
        #expect(DesktopCommandCenterVisuals.recoverySectionTitle == "Recovery")
        #expect(viewModel.recoverableDownloads.first?.resumeActionTitle == "Resume Download")
        #expect(DesktopCommandCenterView.downloadRecoveryOverflowActionTitle == "View All Downloads")
        #expect(DesktopCommandCenterVisuals.workflowSectionTitle == "Workflow")
        #expect(DesktopCommandCenterView.downloadRecoveryOverflowText(totalCount: 2) == nil)
        #expect(DesktopCommandCenterView.downloadRecoveryOverflowText(totalCount: 3) == "+1 more stalled download")
        #expect(DesktopCommandCenterView.downloadRecoveryOverflowActionTitle == "View All Downloads")
    }

    @Test("workspace shell keeps dismissible update signals out of the top banner")
    @MainActor
    func workspaceShellKeepsDismissibleUpdateSignalsOutOfTopBanner() async throws {
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
        let signal = try #require(viewModel.desktopSignalStates.first { $0.title == "Update available: 0.2.0" })
        let initialTexts = renderedTextValues(in: initialView)

        #expect(initialView.subviews.isEmpty == false)
        #expect(viewModel.desktopBannerState == nil)
        #expect(signal.isDismissible)
        #expect(signal.detail == "Current 0.1.0 on stable")
        #expect(initialTexts.contains("Update available: 0.2.0") == false)

        viewModel.dismissDesktopBanner(id: signal.id)

        let dismissedView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let dismissedTexts = renderedTextValues(in: dismissedView)
        #expect(viewModel.desktopSignalStates.contains { $0.title == "Update available: 0.2.0" } == false)
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
        let summary = DesktopSettingsTabView(foundation: foundation).accessibilitySummary

        #expect(summary.contains("Embedding Model"))
        #expect(summary.contains("melix-dev-embed"))
        #expect(summary.contains("MCP Config"))
        #expect(summary.contains("/tmp/mcp-tools.json"))
        #expect(foundation.settings.contains { $0.key == "Embedding Model" && $0.value == "melix-dev-embed" })
        #expect(foundation.settings.contains { $0.key == "MCP Config" && $0.value == "/tmp/mcp-tools.json" })
        #expect(foundation.settings.contains { $0.key == "Gateway Config Store" && $0.value == "/tmp/gateway-config.json" })
        #expect(foundation.settings.contains { $0.key == "Built-in Tool Parsers" && $0.value == "text, json, qwen" })
        #expect(foundation.settings.contains { $0.key == "Boot Arguments" && $0.value == "--config /tmp/melix.json" })
    }

    @Test("settings tab renders runtime settings rows with source and validation state")
    @MainActor
    func settingsTabRendersRuntimeSettingsRowsWithSourceAndValidationState() async throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-settings",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.applyRuntimeSettings(
            RuntimeSettingsSnapshotState(
                schemaVersion: "melix.runtime_settings.effective.v1",
                rows: [
                    RuntimeSettingRowState(
                        key: "model_cache_path",
                        currentValueText: "/tmp/melix/models",
                        source: "environment",
                        sourceDetail: "MELIX_MODEL_CACHE_PATH"
                    ),
                    RuntimeSettingRowState(
                        key: "memory_pressure_threshold",
                        currentValueText: "1.25",
                        source: "user_settings",
                        sourceDetail: "/tmp/melix-home/runtime_settings.json",
                        validationState: .invalid,
                        validationMessage: "must be <= 1.0"
                    ),
                    RuntimeSettingRowState(
                        key: "max_workers",
                        currentValueText: "4",
                        source: "default",
                        sourceDetail: "runtime defaults",
                        validationState: .valid
                    ),
                ],
                sources: [
                    RuntimeSettingSourceState(key: "user_settings", path: "/tmp/melix-home/runtime_settings.json"),
                ],
                metrics: [
                    RuntimeSettingMetricState(name: "settings_resolve_ms", valueText: "3"),
                ]
            )
        )

        let tab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        let view = hostView(tab)
        let values = tab.accessibilitySummary
        #expect(view.subviews.isEmpty == false)
        #expect(values.contains("Provider Settings"))
        #expect(values.contains("model_cache_path"))
        #expect(values.contains("/tmp/melix/models"))
        #expect(values.contains("environment"))
        #expect(values.contains("MELIX_MODEL_CACHE_PATH"))
        #expect(values.contains("Not validated"))
        #expect(values.contains("memory_pressure_threshold"))
        #expect(values.contains("1.25"))
        #expect(values.contains("Invalid"))
        #expect(values.contains("must be <= 1.0"))
        #expect(values.contains("max_workers"))
        #expect(values.contains("Valid"))
        #expect(values.contains("Resolved Sources"))
        #expect(values.contains("/tmp/melix-home/runtime_settings.json"))
        #expect(values.contains("settings_resolve_ms"))

        viewModel.selectToolSection(.settings)
        let shellView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(shellView.subviews.isEmpty == false)
    }

    @Test("settings tab renders runtime settings operation controls")
    @MainActor
    func settingsTabRendersRuntimeSettingsOperationControls() async throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-settings-controls",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.applyRuntimeSettings(
            RuntimeSettingsSnapshotState(
                schemaVersion: "melix.runtime_settings.effective.v1",
                rows: [
                    RuntimeSettingRowState(
                        key: "max_concurrent_jobs",
                        currentValueText: "4",
                        source: "default",
                        sourceDetail: "builtin"
                    ),
                ],
                sources: [],
                metrics: []
            )
        )
        viewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "8")
        viewModel.applyRuntimeSettingsOperationMessage("Updated max_concurrent_jobs.")

        let tab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        let view = hostView(tab)
        let values = tab.accessibilitySummary
        _ = renderedTextValues(in: view)

        #expect(values.contains("Setting key"))
        #expect(values.contains("Setting value"))
        #expect(values.contains("Set Setting"))
        #expect(values.contains("Reset Setting"))
        #expect(values.contains("Validate Settings"))
        #expect(values.contains("Updated max_concurrent_jobs."))
    }

    @Test("settings tab drives runtime settings operation buttons and renders failures")
    @MainActor
    func settingsTabDrivesRuntimeSettingsOperationButtonsAndRendersFailures() async throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-settings-actions",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            """
            {
              "key": "max_concurrent_jobs",
              "value": 8,
              "source": "user_settings"
            }
            """,
            for: .settingsSet(.init(key: "max_concurrent_jobs", value: "8", json: true))
        )
        await runner.configureOutput(Self.runtimeSettingsOperationSnapshotJSON, for: .settingsShow(.init(json: true)))
        await runner.configureOutput(
            """
            {
              "valid": false,
              "errors": [
                {
                  "key": "max_concurrent_jobs",
                  "message": "expected int",
                  "source": "user_settings"
                }
              ],
              "metrics": {}
            }
            """,
            for: .settingsValidate(.init(json: true))
        )
        await runner.configureOutput(
            """
            {
              "key": "max_concurrent_jobs",
              "removed": true
            }
            """,
            for: .settingsReset(.init(key: "max_concurrent_jobs", json: true))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyRuntimeSettings(try RuntimeSettingsPayloadDecoder.decodeShow(Self.runtimeSettingsOperationSnapshotJSON))
        viewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "8")

        await viewModel.setRuntimeSetting()
        try await waitForDesktopFoundationCondition("settings set completes") {
            viewModel.runtimeSettingsOperationMessage == "Updated max_concurrent_jobs."
        }

        await viewModel.validateRuntimeSettings()
        try await waitForDesktopFoundationCondition("settings validation completes") {
            viewModel.runtimeSettingsOperationMessage == "1 validation issue."
        }
        let validationTab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        _ = hostView(validationTab)
        #expect(validationTab.accessibilitySummary.contains("expected int"))
        #expect(validationTab.accessibilitySummary.contains("user_settings"))

        await viewModel.resetRuntimeSetting()
        try await waitForDesktopFoundationCondition("settings reset completes") {
            viewModel.runtimeSettingsOperationMessage == "Reset max_concurrent_jobs."
        }

        #expect(
            await runner.snapshotRecordedCommands() == [
                .settingsSet(.init(key: "max_concurrent_jobs", value: "8", json: true)),
                .settingsShow(.init(json: true)),
                .settingsValidate(.init(json: true)),
                .settingsReset(.init(key: "max_concurrent_jobs", json: true)),
                .settingsShow(.init(json: true)),
            ]
        )

        let localErrorViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        localErrorViewModel.applyRuntimeSettings(try RuntimeSettingsPayloadDecoder.decodeShow(Self.runtimeSettingsOperationSnapshotJSON))
        localErrorViewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "8")
        await localErrorViewModel.setRuntimeSetting()
        let errorTab = DesktopSettingsTabView(foundation: foundation, viewModel: localErrorViewModel)
        _ = hostView(errorTab)
        #expect(errorTab.accessibilitySummary.contains("Settings CLI runner is unavailable."))

        let legacyTab = DesktopSettingsTabView(
            foundation: foundation,
            viewModel: RuntimeViewModel(client: FakeControlPlaneXPCClient())
        )
        _ = hostView(legacyTab)
        #expect(legacyTab.accessibilitySummary.contains("Protocol"))
    }

    @Test("settings tab renders runtime discovery inspector payloads")
    @MainActor
    func settingsTabRendersRuntimeDiscoveryInspectorPayloads() async throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-discovery",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.applyRuntimeDiscovery(
            try RuntimeDiscoveryPayloadDecoder.decodeSnapshot([
                (.info, RuntimeDiscoveryStateTests.infoJSON),
                (.capabilities, RuntimeDiscoveryStateTests.capabilitiesJSON),
                (.instructions, RuntimeDiscoveryStateTests.instructionsJSON),
                (.schema, RuntimeDiscoveryStateTests.schemaJSON),
                (.configMetadata, RuntimeDiscoveryStateTests.configMetadataJSON),
            ])
        )

        let tab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        let view = hostView(tab)
        let values = tab.accessibilitySummary
        _ = renderedTextValues(in: view)

        #expect(values.contains("Refresh Discovery"))
        #expect(values.contains("Discovery Inspector"))
        #expect(values.contains("Info"))
        #expect(values.contains("Capabilities"))
        #expect(values.contains("Instructions"))
        #expect(values.contains("Schema"))
        #expect(values.contains("Config Metadata"))
        #expect(values.contains("melix.discovery.info.v1"))
        #expect(values.contains("runtime_settings"))
        #expect(values.contains("/api/config-metadata"))
        #expect(values.contains("mlx-community/Qwen3.5-9B-MLX-4bit"))
        #expect(values.contains("qwen35_9b_mlx_4bit"))
        #expect(values.contains("/repo/packages/protocol/schema"))
        #expect(values.contains("max_concurrent_jobs"))
        #expect(values.contains("MELIX_MAX_CONCURRENT_JOBS"))
    }

    @Test("settings tab renders model alias lookup suggestions and no match states")
    @MainActor
    func settingsTabRendersModelAliasLookupSuggestionsAndNoMatchStates() async throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-discovery-alias",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            RuntimeDiscoveryStateTests.noMatchCapabilitiesJSON,
            for: .capabilities(.init(json: true, modelQuery: "not a/model id"))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyRuntimeDiscovery(
            try RuntimeDiscoveryPayloadDecoder.decodeSnapshot([
                (.capabilities, RuntimeDiscoveryStateTests.capabilitiesJSON),
            ])
        )
        viewModel.updateRuntimeDiscoveryAliasQuery("not a/model id")

        let initialTab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        let initialView = hostView(initialTab)
        let initialValues = initialTab.accessibilitySummary
        _ = renderedTextValues(in: initialView)

        #expect(initialValues.contains("Model alias query"))
        #expect(initialValues.contains("Lookup Alias"))
        #expect(initialValues.contains("Model Alias Suggestions"))
        #expect(initialValues.contains("Suggestions available"))
        #expect(initialValues.contains("mlx-community/Qwen3.5-9B-MLX-4bit"))

        await viewModel.lookupRuntimeDiscoveryModelAlias()
        try await waitForDesktopFoundationCondition("alias lookup completes") {
            viewModel.runtimeDiscoveryOperationMessage == "Model alias lookup refreshed."
        }

        let noMatchTab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        _ = hostView(noMatchTab)
        #expect(noMatchTab.accessibilitySummary.contains("No match"))
        #expect(noMatchTab.accessibilitySummary.contains("No model alias matches not a/model id."))
        #expect(
            await runner.snapshotRecordedCommands() == [
                .capabilities(.init(json: true, modelQuery: "not a/model id")),
            ]
        )
    }

    @Test("settings tab renders discovery copy and open affordances")
    @MainActor
    func settingsTabRendersDiscoveryCopyAndOpenAffordances() throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-discovery-affordances",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.applyRuntimeDiscovery(
            try RuntimeDiscoveryPayloadDecoder.decodeSnapshot([
                (.info, RuntimeDiscoveryStateTests.infoJSON),
                (.schema, RuntimeDiscoveryStateTests.schemaJSON),
            ])
        )

        let pasteboard = RecordingPasteboard()
        #expect(RuntimeDiscoveryClipboard.copy("/repo/docs/plans", to: pasteboard))
        #expect(pasteboard.string == "/repo/docs/plans")
        #expect(RuntimeDiscoveryClipboard.copy("   ", to: pasteboard) == false)

        var openedURL: URL?
        #expect(RuntimeDiscoveryClipboard.open("/repo/docs/plans") { url in
            openedURL = url
            return true
        })
        #expect(openedURL?.path == "/repo/docs/plans")
        #expect(RuntimeDiscoveryClipboard.open("   ") { _ in true } == false)

        var expandedHomeURL: URL?
        #expect(RuntimeDiscoveryClipboard.open("~/Documents") { url in
            expandedHomeURL = url
            return true
        })
        #expect(expandedHomeURL?.path == "\(NSHomeDirectory())/Documents")

        let tab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        let view = hostView(tab)
        let buttons = renderedButtons(in: view)
        let values = tab.accessibilitySummary

        #expect(buttons.count >= 4)
        #expect(values.contains("Copy Schema Version"))
        #expect(values.contains("Copy Endpoint"))
        #expect(values.contains("Copy Schema Path"))
        #expect(values.contains("Open Schema Path"))
    }

    @Test("settings tab refreshes runtime discovery and renders status states")
    @MainActor
    func settingsTabRefreshesRuntimeDiscoveryAndRendersStatusStates() async throws {
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: Melix_Controlplane_V1_ServerSnapshot(),
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-discovery-status",
            features: [],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(RuntimeDiscoveryStateTests.infoJSON, for: .info(.init(json: true)))
        await runner.configureOutput(RuntimeDiscoveryStateTests.capabilitiesJSON, for: .capabilities(.init(json: true)))
        await runner.configureOutput(RuntimeDiscoveryStateTests.instructionsJSON, for: .instructions(.init(json: true)))
        await runner.configureOutput(RuntimeDiscoveryStateTests.schemaJSON, for: .schema(.init(json: true)))
        await runner.configureOutput(RuntimeDiscoveryStateTests.configMetadataJSON, for: .configMetadata(.init(json: true)))
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        let refreshView = hostView(DesktopSettingsTabView(foundation: foundation, viewModel: viewModel))
        #expect(DesktopSettingsTabView(foundation: foundation, viewModel: viewModel).accessibilitySummary.contains("Discovery metadata unavailable."))
        _ = renderedTextValues(in: refreshView)
        #expect(DesktopSettingsTabView(foundation: foundation, viewModel: viewModel).accessibilitySummary.contains("Refresh Discovery"))
        await viewModel.refreshRuntimeDiscovery()
        try await waitForDesktopFoundationCondition("discovery refresh completes") {
            viewModel.runtimeDiscoveryOperationMessage == "Provider discovery refreshed."
        }
        let refreshedTab = DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
        _ = hostView(refreshedTab)
        #expect(refreshedTab.accessibilitySummary.contains("Provider discovery refreshed."))
        #expect(refreshedTab.accessibilitySummary.contains("melix.discovery.config_metadata.v1"))

        let errorViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await errorViewModel.refreshRuntimeDiscovery()
        let errorTab = DesktopSettingsTabView(foundation: foundation, viewModel: errorViewModel)
        _ = hostView(errorTab)
        #expect(errorTab.accessibilitySummary.contains("Discovery CLI runner is unavailable."))

        let settingsViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        settingsViewModel.applyRuntimeSettings(
            RuntimeSettingsSnapshotState(
                schemaVersion: "melix.runtime_settings.effective.v1",
                rows: [
                    RuntimeSettingRowState(
                        key: "max_concurrent_jobs",
                        currentValueText: "4",
                        source: "default",
                        sourceDetail: "builtin"
                    ),
                ],
                sources: [],
                metrics: []
            )
        )
        settingsViewModel.applyRuntimeDiscovery(viewModel.runtimeDiscoverySnapshot)
        let settingsTab = DesktopSettingsTabView(foundation: foundation, viewModel: settingsViewModel)
        _ = hostView(settingsTab)
        #expect(settingsTab.accessibilitySummary.contains("Provider Settings"))
        #expect(settingsTab.accessibilitySummary.contains("Discovery Inspector"))
        #expect(settingsTab.accessibilitySummary.contains("melix.discovery.info.v1"))
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
            ),
            size: CGSize(width: 1_200, height: 1_600)
        )

        #expect(view.subviews.isEmpty == false)
    }

    @Test("capability disabled explanations render in model settings and server defaults")
    @MainActor
    func capabilityDisabledExplanationsRenderInSettingsAndServerDefaults() async throws {
        var model = makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)
        var capabilityReceipt = Melix_Controlplane_V1_ModelCapabilityReceipt()
        var tools = Melix_Controlplane_V1_TaskCapabilityReceipt()
        tools.capability = "tools"
        tools.state = .capabilityUnsupported
        tools.unsupportedReason = .unsupportedReasonUnsupportedTask
        tools.recoveryHint = "Select a tool-capable model."
        tools.provenance = "tool parser metadata"
        var completion = Melix_Controlplane_V1_TaskCapabilityReceipt()
        completion.capability = "completion"
        completion.state = .capabilitySupported
        completion.provenance = "model catalog"
        var acceleration = Melix_Controlplane_V1_AccelerationCapabilityReceipt()
        acceleration.requestedAccelerationMode = .speculativeDecode
        acceleration.supportedModes = [.baseline]
        acceleration.state = .capabilityUnsupported
        acceleration.unsupportedReason = .unsupportedReasonUnsupportedMode
        acceleration.recoveryHint = "Switch to baseline or pick a compatible draft model."
        capabilityReceipt.tasks = [completion, tools]
        capabilityReceipt.acceleration = acceleration
        model.capabilityReceipt = capabilityReceipt

        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [model]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.modelSettingsToolParserXMLFallbackDraft = true
        viewModel.modelSettingsAccelerationModeDraft = "speculative_decode"
        let modelsView = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            ),
            size: CGSize(width: 1_200, height: 1_800)
        )

        #expect(modelsView.subviews.isEmpty == false)
        #expect(viewModel.modelSettingsToolParserXMLFallbackDisabledReason == "Tool parser XML fallback is unavailable for \(desktopTestReadyModelID): tools capability is unsupported • reason unsupported task • recovery Select a tool-capable model.")
        #expect(viewModel.modelSettingsAccelerationModeDisabledReason == "Model settings acceleration is unavailable for \(desktopTestReadyModelID): Speculative Decode acceleration is unsupported • reason unsupported mode • recovery Switch to baseline or pick a compatible draft model.")

        viewModel.selectSurface(.server)
        viewModel.updateSelectedServerSessionAccelerationMode("speculative_decode")
        let serverView = hostView(
            DesktopWorkspaceShellView(viewModel: viewModel),
            size: CGSize(width: 1_400, height: 1_100)
        )

        #expect(serverView.subviews.isEmpty == false)
        #expect(viewModel.selectedServerAccelerationModeDisabledReason == "Serving acceleration is unavailable for \(desktopTestReadyModelID): Speculative Decode acceleration is unsupported • reason unsupported mode • recovery Switch to baseline or pick a compatible draft model.")
    }

    @Test("models registry uses design-system workspace primitives")
    func modelsRegistryUsesDesignSystemWorkspacePrimitives() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let modelsSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift"
        )
        let shellSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift"
        )
        let modelsSource = try String(contentsOf: modelsSourceURL, encoding: .utf8)
        let shellSource = try String(contentsOf: shellSourceURL, encoding: .utf8)
        let modelsTabSource = try #require(
            modelsSource.slice(
                from: "struct DesktopModelsTabView: View",
                to: "struct DesktopModelRegistryEntriesView: View"
            )
        )
        let registrySource = try #require(
            modelsSource.slice(
                from: "struct DesktopModelRegistryEntriesView: View",
                to: "private struct DesktopRegistryRootsSectionView: View"
            )
        )
        let serverSidebarSource = try #require(
            shellSource.slice(
                from: "private struct DesktopServerSessionSidebar: View",
                to: "private struct DesktopRemoteServerEditor: View"
            )
        )
        let serverEditorSource = try #require(
            shellSource.slice(
                from: "private struct DesktopServerLoRAAdapterSection: View",
                to: "private struct DesktopServerSessionInspector: View"
            )
        )

        #expect(modelsTabSource.contains("List(") == false)
        #expect(modelsTabSource.contains("GroupBox(") == false)
        #expect(shellSource.contains("DisclosureGroup(\"Models Library\")") == false)
        #expect(modelsTabSource.contains("MelixSectionCard(\"Model Registry\")") == false)
        #expect(modelsTabSource.contains("MelixSectionCard(\"Model Settings\")") == false)
        #expect(registrySource.contains("MelixSectionCard(\"Unified Model List\")") == false)
        #expect(registrySource.contains("MelixSectionCard(\"Model Card\")") == false)
        #expect(shellSource.contains("ForEach(workflowModeBadges, id: \\.self) { badge in\n                    Text(badge)"))
        #expect(shellSource.contains(".accessibilityLabel(badge)"))
        #expect(shellSource.contains("Benchmark Target") == false)
        #expect(shellSource.contains("Evaluation Target") == false)
        #expect(shellSource.contains("\"Running Provider\""))
        #expect(shellSource.contains("Text(\"Providers\")"))
        #expect(shellSource.contains("routeTarget: DesktopRouteActionTarget?"))
        #expect(shellSource.contains("title: \"Open Detail\""))
        #expect(shellSource.contains("selectedObject: .init(kind: .provider, objectID: session.id)"))
        #expect(shellSource.contains("LoRA Adapter"))
        #expect(shellSource.contains("Color.accentColor") == false)
        #expect(shellSource.contains("selectedServerCreationKind"))
        #expect(shellSource.contains("\"Session Name\""))
        #expect(shellSource.contains("Button(\"Add Local Provider\", action:"))
        #expect(shellSource.contains("Button(\"Add Remote Provider\", action:"))
        #expect(shellSource.contains("DesktopServerCreationStepperHeader"))
        #expect(shellSource.contains("\"Local Provider Setup\""))
        #expect(shellSource.contains("\"Remote Provider Setup\""))
        #expect(shellSource.contains("MelixSectionCard(\"Provider\")"))
        #expect(shellSource.contains("\"Server Type\"") == false)
        #expect(shellSource.contains("Button(\"Create Local Server\")") == false)
        #expect(shellSource.contains("Text(\"Servers\")") == false)
        #expect(shellSource.contains("\"Running Server\"") == false)
        #expect(shellSource.contains(".disabled(viewModel.canCreateLocalServerFromDraft == false)"))
        #expect(shellSource.contains(".disabled(viewModel.canSaveRemoteServerDraft == false)"))
        #expect(shellSource.contains("Scanning Ready to Run Models"))
        #expect(serverSidebarSource.contains("Text(target.title)"))
        #expect(serverSidebarSource.contains("Text(target.detailText)"))
        #expect(serverSidebarSource.contains("Text(target.statusText)"))
        #expect(serverSidebarSource.components(separatedBy: ".lineLimit(1)").count >= 4)
        #expect(serverSidebarSource.contains(".lineLimit(2)") == false)
        #expect(serverEditorSource.contains("(\"None\", \"baseline\")"))
        #expect(serverEditorSource.contains("(\"Sparse Prefill\", \"sparse_prefill\")"))
        #expect(serverEditorSource.contains("\"Acceleration Mode\""))
        #expect(serverEditorSource.contains("\"Baseline\"") == false)
        #expect(modelsSource.contains("MelixSectionCard(\"Registry Roots\")") == false)
        #expect(modelsTabSource.contains("DesktopRegistryBroadsheetSection(\"Model Registry\")"))
        #expect(modelsTabSource.contains("DesktopRegistryBroadsheetSection(\"Model Settings\")"))
        #expect(registrySource.contains("registryGroup(.readyToRun, title: \"Ready to Run\")"))
        #expect(registrySource.contains("registryGroup(.discoverAndDownload, title: \"Discover & Download\")"))
        #expect(registrySource.contains("DesktopRegistryInspectorPane(\"Model Card\")"))
        #expect(modelsSource.contains("DesktopRegistryBroadsheetSection(\"Registry Roots\")"))
        #expect(registrySource.contains("DesktopRegistryRowBackground"))
        #expect(registrySource.contains("Run Suitability"))
    }

    @Test("desktop workspace keeps titlebar chrome compact")
    func desktopWorkspaceKeepsTitlebarChromeCompact() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let chromeSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift"
        )
        let shellSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift"
        )
        let chromeSource = try String(contentsOf: chromeSourceURL, encoding: .utf8)
        let shellSource = try String(contentsOf: shellSourceURL, encoding: .utf8)

        #expect(chromeSource.contains("workspaceTitleBarContentTopInset"))
        #expect(shellSource.contains(".padding(.top, DesktopShellChromeMetrics.workspaceTitleBarContentTopInset)"))
        #expect(
            DesktopShellChromeMetrics.workspaceTitleBarContentTopInset
            == DesktopShellChromeMetrics.titleBarTabHeightBudget + 14
        )
    }

    @Test("server sidebar rows opt out of appkit focus rings")
    func serverSidebarRowsOptOutOfAppKitFocusRings() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let shellSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift"
        )
        let shellSource = try String(contentsOf: shellSourceURL, encoding: .utf8)

        #expect(shellSource.contains(".buttonStyle(.plain)\n                            .focusable(false)"))
    }

    @Test("models tab renders Hugging Face hub ingress state")
    @MainActor
    func modelsTabRendersHuggingFaceHubIngressState() async throws {
        let client = FakeControlPlaneXPCClient()
        var searchResult = Melix_Controlplane_V1_HubSearchResult()
        var model = Melix_Controlplane_V1_HubModelSummary()
        model.repoID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        model.author = "mlx-community"
        model.modelName = "Qwen3.5-0.8B-OptiQ-4bit"
        model.pipelineTag = "text-generation"
        model.mlxCompatible = true
        model.localFitStatus = "good"
        model.localFitReasons = ["Estimated resident bytes are within the memory comfort budget."]
        model.estimatedArtifactBytes = 4_200_000_000
        model.estimatedResidentBytes = 5_670_000_000
        model.parameterCount = 7_000_000_000
        model.quantizationSummary = "4-bit"
        model.recommendedAction = "download"
        searchResult.models = [model]
        await client.configureHubSearchResult(searchResult)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.modelHubSearchQuery = "qwen3.5"
        await viewModel.searchModelHub()

        let view = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            ),
            size: CGSize(width: 1_200, height: 1_600)
        )
        let renderedTexts = renderedTextValues(in: view)
        let registryView = DesktopModelRegistryEntriesView(viewModel: viewModel)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("qwen3.5"))
        #expect(renderedTexts.contains("main"))
        #expect(registryView.entries.contains(where: {
            $0.repoID == model.repoID && $0.runSuitabilityText == "Good"
        }))
        #expect(viewModel.modelHubSearchResults.count == 1)
    }

    @Test("models tab renders Hub model card run suitability evidence")
    @MainActor
    func modelsTabRendersHubModelCardRunSuitabilityEvidence() async throws {
        let client = FakeControlPlaneXPCClient()
        var searchResult = Melix_Controlplane_V1_HubSearchResult()
        var model = Melix_Controlplane_V1_HubModelSummary()
        model.repoID = "mlx-community/Qwen3.5-72B-4bit"
        model.author = "mlx-community"
        model.modelName = "Qwen3.5-72B-4bit"
        model.pipelineTag = "text-generation"
        model.mlxCompatible = true
        model.localFitStatus = "heavy"
        model.localFitReasons = ["Estimated resident bytes exceed the memory comfort budget."]
        model.estimatedArtifactBytes = 52_000_000_000
        model.estimatedResidentBytes = 70_200_000_000
        model.parameterCount = 72_000_000_000
        model.quantizationSummary = "4-bit"
        model.recommendedAction = "review_risk"
        searchResult.models = [model]
        await client.configureHubSearchResult(searchResult)

        var card = Melix_Controlplane_V1_HubModelCard()
        card.repoID = model.repoID
        card.author = model.author
        card.modelName = model.modelName
        card.summary = "Large MLX model card"
        card.pipelineTag = model.pipelineTag
        card.mlxCompatible = true
        card.tags = ["mlx", "4-bit"]
        card.baseModels = ["Qwen/Qwen3.5-72B"]
        card.localFitStatus = model.localFitStatus
        card.localFitReasons = model.localFitReasons
        card.estimatedArtifactBytes = model.estimatedArtifactBytes
        card.estimatedResidentBytes = model.estimatedResidentBytes
        card.parameterCount = model.parameterCount
        card.quantizationSummary = model.quantizationSummary
        card.recommendedAction = model.recommendedAction
        await client.configureHubModelCard(card)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.modelHubSearchQuery = "qwen72"
        await viewModel.searchModelHub()
        await viewModel.inspectHubModel(repoID: model.repoID)

        let registryView = DesktopModelRegistryEntriesView(viewModel: viewModel)
        let hosted = hostView(registryView)
        let selectedCard = try #require(registryView.selectedCard)

        #expect(hosted.subviews.isEmpty == false || registryView.entries.isEmpty == false)
        #expect(registryView.entries.contains(where: {
            $0.repoID == model.repoID && $0.runSuitabilityText == "Heavy" && $0.canDownload
        }))
        #expect(selectedCard.runSuitabilityText == "Heavy")
        #expect(selectedCard.localFitReasons == ["Estimated resident bytes exceed the memory comfort budget."])
        #expect(selectedCard.estimatedArtifactBytesText != "0 B")
        #expect(selectedCard.estimatedResidentBytesText != "0 B")
        #expect(selectedCard.parameterCountText == "72.0B params")
        #expect(selectedCard.quantizationSummary == "4-bit")
    }

    @Test("model registry renders empty state and placeholder card")
    @MainActor
    func modelRegistryRendersEmptyStateAndPlaceholderCard() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        let registryView = DesktopModelRegistryEntriesView(viewModel: viewModel)
        _ = hostView(registryView)

        #expect(registryView.entries.isEmpty)
        #expect(registryView.selectedCard == nil)
        #expect(viewModel.modelRegistryEntries.isEmpty)
        #expect(viewModel.selectedHubModelCard == nil)
    }

    @Test("model registry local card does not label model state as a recommendation")
    @MainActor
    func modelRegistryLocalCardDoesNotLabelModelStateAsRecommendation() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeMenuBarModelSummary(modelID: "melix-local-warm", state: .modelWarm),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopModelRegistryEntriesView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Recommended action: Warm") == false)
        #expect(renderedTexts.contains("Recommended action: warm") == false)
    }

    @Test("model registry local card renders memory fit receipt rows")
    @MainActor
    func modelRegistryLocalCardRendersMemoryFitReceiptRows() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var model = makeMenuBarModelSummary(modelID: "melix-local-fit", state: .modelWarm)
        model.settings.ext["melix.memory_fit.import.status"] = "blocked"
        model.settings.ext["melix.memory_fit.import.reason"] = "Import requires 42 GB active memory."
        model.settings.ext["melix.memory_fit.benchmark.status"] = "heavy"
        model.settings.ext["melix.memory_fit.benchmark.reason"] = "Benchmark KV cache may exceed comfort budget."
        model.settings.ext["melix.memory_fit.eval.status"] = "good"
        model.settings.ext["melix.memory_fit.eval.reason"] = "Eval sample size fits available memory."
        model.settings.ext["melix.memory_fit.train.status"] = "unknown"
        model.settings.ext["melix.memory_fit.train.reason"] = "Training optimizer estimate is unavailable."
        snapshot.models = [model]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let rows = try #require(viewModel.primaryModel?.memoryFitReceiptRows)
        let localEntry = try #require(viewModel.modelRegistryEntries.first)
        _ = hostView(DesktopRegistryEntryCardContent(entry: localEntry, localModel: viewModel.primaryModel))
        let displayTexts = rows.map(DesktopMemoryFitReceiptRowsView.displayText(for:))
        let summary = desktopModelInfoSummaryContent(RuntimeModelInfoState(
            modelID: "melix-local-fit",
            modelKind: "text",
            maxContext: 8_192,
            supportedParsers: ["text"],
            supportedModalities: ["text"],
            memoryFitReceiptRows: rows
        ))

        #expect(displayTexts == [
            "Fit Import: Blocked • Import requires 42 GB active memory.",
            "Fit Benchmark: Heavy • Benchmark KV cache may exceed comfort budget.",
            "Fit Eval: Good • Eval sample size fits available memory.",
            "Fit Train: Unknown • Training optimizer estimate is unavailable.",
        ])
        #expect(summary.detailLines.contains("memory fit import: Blocked • Import requires 42 GB active memory."))
    }

    @Test("model registry local card renders memory fit resource summaries")
    @MainActor
    func modelRegistryLocalCardRendersMemoryFitResourceSummaries() async throws {
        let row = RuntimeMemoryFitReceiptRow(
            target: "benchmark",
            title: "Benchmark",
            status: "heavy",
            statusText: "Heavy",
            reasonText: "Benchmark KV cache may exceed comfort budget.",
            detailRows: [
                "active memory 32.00 GB",
                "disk 8.00 GB required • 16.00 GB available • Good",
                "unified memory 64.00 GB",
                "threshold 85%",
                "unknown fields kv_cache, dataset_cache",
            ]
        )
        let displayTexts = DesktopMemoryFitReceiptRowsView.displayTexts(for: row)
        let summary = desktopModelInfoSummaryContent(RuntimeModelInfoState(
            modelID: "melix-local-fit",
            modelKind: "text",
            maxContext: 8_192,
            supportedParsers: ["text"],
            supportedModalities: ["text"],
            memoryFitReceiptRows: [row]
        ))

        #expect(displayTexts == [
            "Fit Benchmark: Heavy • Benchmark KV cache may exceed comfort budget.",
            "active memory 32.00 GB",
            "disk 8.00 GB required • 16.00 GB available • Good",
            "unified memory 64.00 GB",
            "threshold 85%",
            "unknown fields kv_cache, dataset_cache",
        ])
        #expect(summary.detailLines.contains("memory fit benchmark detail: active memory 32.00 GB"))
        #expect(summary.detailLines.contains("memory fit benchmark detail: unknown fields kv_cache, dataset_cache"))
    }

    @Test("model registry memory fit receipt rows expose visual states")
    @MainActor
    func modelRegistryMemoryFitReceiptRowsExposeVisualStates() async throws {
        let rows = [
            RuntimeMemoryFitReceiptRow(
                target: "import",
                title: "Import",
                status: "blocked",
                statusText: "Blocked",
                reasonText: "Import exceeds unified memory."
            ),
            RuntimeMemoryFitReceiptRow(
                target: "benchmark",
                title: "Benchmark",
                status: "heavy",
                statusText: "Heavy",
                reasonText: "Benchmark may need swap."
            ),
            RuntimeMemoryFitReceiptRow(
                target: "eval",
                title: "Eval",
                status: "good",
                statusText: "Good",
                reasonText: "Eval fits the memory budget."
            ),
            RuntimeMemoryFitReceiptRow(
                target: "train",
                title: "Train",
                status: "unexpected-state",
                statusText: "Unknown",
                reasonText: "Training estimate is missing."
            ),
        ]
        let visualStates = rows.map(DesktopMemoryFitReceiptRowsView.visualState(for:))
        let accessibilityLabels = rows.map(DesktopMemoryFitReceiptRowsView.accessibilityLabel(for:))

        #expect(visualStates == [.blocked, .heavy, .good, .unknown])
        #expect(visualStates.map(\.badgeTitle) == ["Blocked", "Heavy", "Good", "Unknown"])
        #expect(accessibilityLabels == [
            "Memory fit Import: Blocked, Import exceeds unified memory.",
            "Memory fit Benchmark: Heavy, Benchmark may need swap.",
            "Memory fit Eval: Good, Eval fits the memory budget.",
            "Memory fit Train: Unknown, Training estimate is missing.",
        ])
    }

    @Test("model registry covers cache missing managed blocked unknown and gated branches")
    @MainActor
    func modelRegistryCoversCacheMissingManagedBlockedUnknownAndGatedBranches() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var missingModel = makeMenuBarModelSummary(modelID: "mlx-community/Qwen3", state: .modelDiscovered)
        missingModel.settings.ext["melix.model_path_missing"] = "true"
        missingModel.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        missingModel.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3"
        missingModel.settings.ext["melix.hf_revision"] = "refs/pr/7"
        let warmModel = makeMenuBarModelSummary(modelID: "melix-warm", state: .modelWarm)
        let discoveredModel = makeMenuBarModelSummary(modelID: "melix-discovered", state: .modelDiscovered)
        snapshot.models = [missingModel, warmModel, discoveredModel]
        await client.configureSnapshot(snapshot)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "managed-download-a",
                            sourceModel: "mlx-community/Qwen3-managed",
                            status: "downloading",
                            stage: "download",
                            pct: 0.4,
                            outputDir: "/tmp/melix-downloads/qwen3",
                            outputPath: "/tmp/melix-downloads/qwen3/model.safetensors",
                            partialPath: "/tmp/melix-downloads/qwen3/model.safetensors.partial",
                            statePath: "/tmp/melix-downloads/qwen3/download.state.json",
                            selectedMirror: "https://huggingface.co",
                            downloadedBytes: 400,
                            totalBytes: 1_000,
                            resumeReady: false
                        ),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        var unknown = Melix_Controlplane_V1_HubModelSummary()
        unknown.repoID = "mlx-community/Unknown-Fit"
        unknown.author = "mlx-community"
        unknown.modelName = "Unknown-Fit"
        unknown.pipelineTag = "text-generation"
        unknown.mlxCompatible = true
        unknown.localFitStatus = "unknown"
        unknown.recommendedAction = "inspect_metadata"
        var blocked = Melix_Controlplane_V1_HubModelSummary()
        blocked.repoID = "generic/Blocked"
        blocked.author = "generic"
        blocked.modelName = "Blocked"
        blocked.pipelineTag = "text-generation"
        blocked.mlxCompatible = false
        blocked.localFitStatus = "blocked"
        blocked.recommendedAction = "unsupported_runtime"
        var searchResult = Melix_Controlplane_V1_HubSearchResult()
        searchResult.models = [unknown, blocked]
        await client.configureHubSearchResult(searchResult)
        var card = Melix_Controlplane_V1_HubModelCard()
        card.repoID = unknown.repoID
        card.author = unknown.author
        card.modelName = unknown.modelName
        card.pipelineTag = unknown.pipelineTag
        card.mlxCompatible = true
        card.localFitStatus = "unknown"
        card.localFitReasons = [
            "MLX-compatible Hub metadata found.",
            "No artifact size metadata",
            "Local memory probe is unavailable.",
            "Quantization metadata is missing.",
            "Sibling file sizes are incomplete.",
            "README size hint was not model-specific.",
        ]
        card.gated = true
        card.recommendedAction = "inspect_metadata"
        await client.configureHubModelCard(card)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshDownloadQueueState()
        viewModel.modelHubSearchQuery = "unknown blocked"
        await viewModel.searchModelHub()
        let registryView = DesktopModelRegistryEntriesView(viewModel: viewModel)
        let localView = hostView(registryView)
        let entries = viewModel.modelRegistryEntries

        #expect(localView.subviews.isEmpty == false)
        #expect(entries.contains { entry in
            entry.id == "local:mlx-community/Qwen3"
                && entry.sourceText == "Local"
                && entry.runSuitabilityText == "Installed"
        })
        #expect(entries.contains { entry in
            entry.id == "managed-download:managed-download-a"
                && entry.sourceText == "Managed Download"
                && entry.runSuitabilityText == "Pending"
                && entry.sizeText == "400 bytes / 1,000 bytes • 40%"
        })
        #expect(entries.contains { entry in
            entry.repoID == unknown.repoID
                && entry.sourceText == "Hugging Face"
                && entry.runSuitabilityText == "Unknown"
                && entry.canDownload
        })
        #expect(entries.contains { entry in
            entry.repoID == blocked.repoID
                && entry.sourceText == "Hugging Face"
                && entry.runSuitabilityText == "Blocked"
                && entry.canDownload == false
        })

        await viewModel.inspectHubModel(repoID: unknown.repoID)
        let gatedView = hostView(DesktopModelRegistryEntriesView(viewModel: viewModel))
        #expect(gatedView.subviews.isEmpty == false)
        #expect(viewModel.selectedHubModelCard?.gated == true)
        #expect(viewModel.selectedHubModelCard?.runSuitabilityText == "Unknown")
        #expect(viewModel.selectedHubModelCard?.localFitReasons.count == 6)

        let rows = viewModel.desktopFoundationState.models
        await registryView.applyLatencyProfile(to: rows.first { $0.modelID == "melix-warm" })
        await registryView.toggleModelLoad(for: rows.first { $0.modelID == "melix-warm" })
        await registryView.toggleModelLoad(for: rows.first { $0.modelID == "melix-discovered" })
        await registryView.toggleModelLoad(for: rows.first { $0.modelID == "mlx-community/Qwen3" })
        await registryView.applyLatencyProfile(to: nil)
        await registryView.toggleModelLoad(for: nil)

        let actions = await client.recordedActions
        let modelOps = await client.recordedModelOperationRequests
        #expect(actions.contains("settings:melix-warm"))
        #expect(actions.contains("unload:melix-warm"))
        #expect(actions.contains("load:melix-discovered"))
        #expect(modelOps.contains { $0.operation == "download" && $0.modelID == "mlx-community/Qwen3" })
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

    @Test("models tab restore action re-downloads a missing managed Hugging Face cache")
    @MainActor
    func modelsTabRestoreActionRedownloadsMissingManagedHuggingFaceCache() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var snapshotModel = Melix_Controlplane_V1_ModelSummary()
        snapshotModel.modelID = "mlx-community/Qwen3"
        snapshotModel.kind = "text"
        snapshotModel.state = .modelDiscovered
        snapshotModel.features = ["chat"]
        snapshotModel.maxContext = 8192
        snapshotModel.settings.ext["melix.model_path_missing"] = "true"
        snapshotModel.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        snapshotModel.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3"
        snapshotModel.settings.ext["melix.hf_revision"] = "refs/pr/7"
        snapshot.models = [snapshotModel]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        let model = try #require(viewModel.primaryModel)
        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )

        #expect(model.actionTitle == "Restore Download")
        tab.toggleModelLoadAction(for: model)()

        try await Task.sleep(for: .milliseconds(50))
        let calls = await client.recordedModelOperationRequests
        let downloadCall = try #require(calls.first { $0.operation == "download" })
        let actions = await client.recordedActions
        #expect(actions.contains("load:mlx-community/Qwen3") == false)
        #expect(downloadCall.modelID == "mlx-community/Qwen3")
        #expect(downloadCall.ext["melix.hf_repo_id"] == "mlx-community/Qwen3")
        #expect(downloadCall.ext["melix.hf_revision"] == "refs/pr/7")
        #expect(downloadCall.ext["melix.managed_import"] == "true")
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
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
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
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
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
        #expect(notice.detail.contains("serve \(desktopTestReadyModelID)"))
    }

    @Test("tools workspace renders lora training controls for local and Hugging Face datasets")
    @MainActor
    func toolsWorkspaceRendersLoRATrainingControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.selectToolSection(.training)
        viewModel.loraDatasetSourceKind = .localPackage
        let localView = hostView(DesktopWorkspaceShellView(viewModel: viewModel), size: CGSize(width: 1200, height: 1400))
        let localTexts = renderedTextValues(in: localView)

        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraTrainingMode = .qlora
        let hfView = hostView(
            DesktopWorkspaceShellView(viewModel: viewModel),
            size: CGSize(width: 1200, height: 1400)
        )
        let renderedTexts = renderedTextValues(in: hfView)

        #expect(hfView.subviews.isEmpty == false)
        #expect(viewModel.selectedToolSection == .training)
        #expect(renderedTexts.contains("Local Package"))
        #expect(renderedTexts.contains("Hugging Face"))
        #expect(renderedTexts.contains("QLoRA"))
        #expect(localTexts.contains("LoRA"))
        #expect(DesktopTrainingWorkspaceDefaults.showsAdvancedParameters == false)
        #expect(DesktopTrainingWorkspaceDefaults.advancedParametersTitle == "Advanced Training Parameters")
    }

    @Test("tools workspace renders category-first navigation")
    @MainActor
    func toolsWorkspaceRendersCategoryFirstNavigation() async throws {
        let view = hostView(
            DesktopDomainSidebarView(
                domain: .workflows,
                selectedToolSection: .training,
                selectToolSection: { _ in }
            )
        )

        #expect(view.subviews.isEmpty == false)
        for section in DesktopSurfaceDomain.workflows.sections {
            #expect(section.breadcrumbTitle == "Workflows / \(section.domainTitle)")
        }
        for section in DesktopSurfaceDomain.jobs.sections {
            #expect(section.breadcrumbTitle == "Jobs / \(section.domainTitle)")
        }
    }

    @Test("jobs tool section renders navigation list selection and empty state")
    @MainActor
    func jobsToolSectionRendersNavigationListSelectionAndEmptyState() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.jobs)

        let emptyView = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let emptyTexts = renderedTextValues(in: emptyView)

        #expect(viewModel.selectedSurface == .jobs)
        #expect(viewModel.selectedToolSection == .jobs)
        #expect(DesktopJobsToolSectionView.emptyStateTitle == "No Jobs Yet")
        #expect(emptyTexts.contains(DesktopJobsToolSectionView.emptyStateTitle))
        #expect(emptyTexts.contains(DesktopJobsToolSectionView.emptyStateDetail))

        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-20260516-1027",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "updated_at_unix_ms": 1778908099000,
            "cancelable": true
          },
          {
            "job_id": "eval-20260516-1044",
            "run_kind": "evaluation",
            "status": "completed",
            "phase": "complete",
            "model_id": "melix-dev-text",
            "task_kind": "mmlu",
            "updated_at_unix_ms": 1778909101000
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)
        viewModel.selectRuntimeJob(id: "eval-20260516-1044")

        let populatedView = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let populatedTexts = renderedTextValues(in: populatedView)

        #expect(populatedTexts.contains(where: { $0.contains("bench-20260516-1027") }))
        #expect(populatedTexts.contains("eval-20260516-1044"))
        #expect(populatedTexts.contains("evaluation"))
        #expect(populatedTexts.contains("completed"))

        let shellView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(shellView.subviews.isEmpty == false)
    }

    @Test("jobs inspector evidence maps every fetched artifact path")
    @MainActor
    func jobsInspectorEvidenceMapsEveryFetchedArtifactPath() {
        let evidence = DesktopInspectorEvidenceBuilder.jobsEvidence(
            artifactRoot: "/tmp/melix/jobs/eval-1808",
            detailLogPath: "/tmp/melix/jobs/eval-1808/detail.log",
            logSnapshotPath: "/tmp/melix/jobs/eval-1808/live.log",
            artifactPaths: [
                "/tmp/melix/jobs/eval-1808/manifest.json",
                "/tmp/melix/jobs/eval-1808/metrics.json",
                "",
                "/tmp/melix/jobs/eval-1808/report.md",
            ]
        )

        #expect(evidence == [
            "/tmp/melix/jobs/eval-1808",
            "/tmp/melix/jobs/eval-1808/detail.log",
            "/tmp/melix/jobs/eval-1808/live.log",
            "/tmp/melix/jobs/eval-1808/manifest.json",
            "/tmp/melix/jobs/eval-1808/metrics.json",
            "/tmp/melix/jobs/eval-1808/report.md",
        ])
    }

    @Test("batch runs tool section renders model config inputs and validation messages")
    @MainActor
    func batchRunsToolSectionRendersModelConfigInputsAndValidationMessages() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.batchRuns)
        viewModel.updateBatchRunModelListText("")
        viewModel.updateBatchRunConfigText(
            """
            unknown_key: value
            broken line
            """
        )

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: view)
        let buttons = renderedButtons(in: view)
        let preflightButton = try #require(buttons.first { $0.title == "Run Preflight" })

        #expect(viewModel.selectedSurface == .workflows)
        #expect(viewModel.selectedToolSection == .batchRuns)
        #expect(preflightButton.isEnabled == false)
        #expect(values.contains("0 models • 0 config values"))
        #expect(values.contains("Add at least one model repository."))
        #expect(values.contains(where: { $0.contains("unknown_key") }))
        #expect(values.contains(where: { $0.contains("line 2") }))

        let shellView = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(shellView.subviews.isEmpty == false)

        viewModel.updateBatchRunModelListText("mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")
        let readyView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let readyValues = renderedTextValues(in: readyView)
        let readyPreflightButton = try #require(renderedButtons(in: readyView).first { $0.title == "Run Preflight" })
        #expect(readyPreflightButton.isEnabled)
        #expect(readyValues.contains("Batch input is ready for preflight."))
    }

    @Test("batch runs tool section preflight button dispatches and selects report")
    @MainActor
    func batchRunsToolSectionPreflightButtonDispatchesAndSelectsReport() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            guard case .batchRun = command else {
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
            return .success(
                """
                {
                  "schema_version": "melix.batch.effective_config.v1",
                  "run_id": "smoke-batch",
                  "model_list": "/tmp/models.txt",
                  "config_path": "/tmp/config.txt",
                  "output_root": "/tmp/melix-batch-output",
                  "temp_root": "/tmp/melix-batch-temp",
                  "melix_home": "/tmp/melix-home",
                  "runtime_dir": "/tmp/melix-runtime",
                  "http_port": "12434",
                  "service_instance_name": "window-ui",
                  "selected_model_count": 1,
                  "total_model_count": 1,
                  "dry_run": true,
                  "preflight": true,
                  "continue_on_failure": true,
                  "restart_stack_per_model": true,
                  "preflight_report": "/tmp/melix-batch-output/preflight-report.json",
                  "isolation_policy": {
                    "schema_version": "melix.batch.isolation_policy.v1",
                    "best_effort_unload_previous_model": true,
                    "best_effort_unload_after_model": true,
                    "restart_stack_per_model": true,
                    "force_clean_stack_after_runtime_failure": true,
                    "cleanup_failures_preserve_artifacts": true
                  },
                  "judge": {
                    "remote_server_id": "judge-local",
                    "model": "judge-model"
                  },
                  "benchmark": {
                    "suite": "latency",
                    "context_length": 2048,
                    "generation_length": 128,
                    "batch_size": 2,
                    "repeats": 1,
                    "sample_size": 8,
                    "batch_factor": 1
                  },
                  "evaluation": {
                    "suite": "mt-bench",
                    "dataset_id": "smoke",
                    "scoring_mode": "exact",
                    "sample_size": 8,
                    "batch_factor": 1
                  },
                  "models": [
                    {
                      "index": "01",
                      "repo_id": "mlx-community/Qwen3-8B",
                      "source_line": 1,
                      "slug": "01-mlx-community-qwen3-8b"
                    }
                  ],
                  "preflight_result": {
                    "schema_version": "melix.batch.preflight_report.v1",
                    "run_id": "smoke-batch",
                    "status": "ready",
                    "blocker_count": 0,
                    "model_count": 1,
                    "runtime": {
                      "repo_root": "/tmp/melix",
                      "melix_home": "/tmp/melix-home",
                      "runtime_dir": "/tmp/melix-runtime",
                      "http_port": "12434",
                      "service_instance_name": "window-ui",
                      "melix_cli": "/tmp/melix"
                    },
                    "judge": {
                      "remote_server_id": "judge-local",
                      "model": "judge-model"
                    },
                    "checks": [
                      {
                        "name": "output_root",
                        "status": "ready",
                        "detail": "output root writable",
                        "actionable": "",
                        "category": "filesystem",
                        "metadata": {
                          "path": "/tmp/melix-batch-output"
                        }
                      }
                    ]
                  }
                }
                """
            )
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let preflightButton = try #require(renderedButtons(in: view).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected selected batch preflight report") {
            viewModel.selectedBatchRunReport?.preflightStatus == "ready"
        }

        let updatedView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: updatedView)
        #expect(values.contains("smoke-batch"))
        #expect(values.contains("Preflight ready"))
        #expect(values.contains("output_root"))
        #expect(values.contains("Effective Config"))
        #expect(values.contains("Output Root"))
        #expect(values.contains("/tmp/melix-batch-output"))
        #expect(values.contains("Isolation Summary"))
        #expect(values.contains("Restart Stack Per Model"))
        #expect(values.contains("enabled"))
        #expect(await runner.snapshotRecordedCommands().count == 1)
    }

    @Test("batch runs tool section renders preflight readiness categories and blockers")
    @MainActor
    func batchRunsToolSectionRendersPreflightReadinessCategoriesAndBlockers() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            guard case .batchRun = command else {
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
            return .success(Self.batchRunsBlockedPreflightJSON)
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: blocked-batch")

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let preflightButton = try #require(renderedButtons(in: view).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected blocked batch preflight report") {
            viewModel.selectedBatchRunReport?.preflightStatus == "blocked"
        }

        let updatedView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: updatedView)
        #expect(values.contains("Preflight Readiness"))
        #expect(values.contains("filesystem"))
        #expect(values.contains("1/1 ready • 0 blockers"))
        #expect(values.contains("runtime"))
        #expect(values.contains("0/1 ready • 1 blocker"))
        #expect(values.contains("Set a free MELIX_HTTP_PORT before running the batch."))
        #expect(values.contains("Select a judge remote server."))
    }

    @Test("batch runs tool section renders manifest status rows with failure attribution")
    @MainActor
    func batchRunsToolSectionRendersManifestStatusRowsWithFailureAttribution() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            switch command {
            case .batchRun:
                return .success(Self.batchRunsPreflightJSON)
            case .batchStatus:
                return .success(Self.batchRunsStatusJSON)
            default:
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let preflightButton = try #require(renderedButtons(in: view).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected selected batch preflight report") {
            viewModel.selectedBatchRunReport?.preflightStatus == "ready"
        }

        let reportView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let statusButton = try #require(renderedButtons(in: reportView).first { $0.title == "Refresh Status" })
        #expect(statusButton.isEnabled)
        statusButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected batch manifest status rows") {
            viewModel.selectedBatchRunReport?.statusSummary?.status == "partial_success"
        }

        let updatedView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: updatedView)
        #expect(values.contains("Batch Status"))
        #expect(values.contains("2 succeeded, 1 partial, 1 failed, 0 running, 0 planned / 4 total"))
        #expect(values.contains("mlx-community/Mistral-7B"))
        #expect(values.contains("partial_success"))
        #expect(values.contains("artifact_export"))
        #expect(values.contains("retry_same_model"))
        #expect(values.contains("model_load"))
        #expect(await runner.snapshotRecordedCommands().count == 2)
    }

    @Test("batch runs tool section renders resume missing-only controls and disabled states")
    @MainActor
    func batchRunsToolSectionRendersResumeMissingOnlyControlsAndDisabledStates() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            switch command {
            case .batchRun:
                return .success(Self.batchRunsPreflightJSON)
            case .batchStatus, .batchResume:
                return .success(Self.batchRunsStatusJSON)
            default:
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")

        let initialView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let initialResumeButton = try #require(renderedButtons(in: initialView).first { $0.title == "Resume Batch" })
        #expect(initialResumeButton.isEnabled == false)
        #expect(renderedTextValues(in: initialView).contains("Run or select a batch report before resuming."))

        let preflightButton = try #require(renderedButtons(in: initialView).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected selected batch preflight report") {
            viewModel.selectedBatchRunReport?.preflightStatus == "ready"
        }

        let reportView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let statusButton = try #require(renderedButtons(in: reportView).first { $0.title == "Refresh Status" })
        statusButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected batch manifest status rows") {
            viewModel.selectedBatchRunReport?.statusSummary?.status == "partial_success"
        }

        let statusView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let statusValues = renderedTextValues(in: statusView)
        let missingOnlyToggle = try #require(renderedButtons(in: statusView).first {
            $0.title == "Missing Only" || $0.accessibilityLabel() == "Missing Only"
        })
        let resumeButton = try #require(renderedButtons(in: statusView).first { $0.title == "Resume Batch" })
        #expect(missingOnlyToggle.state == .on)
        #expect(resumeButton.isEnabled)
        #expect(statusValues.contains("2 incomplete rows available for missing-only resume."))

        resumeButton.performClick(nil)

        try await waitForRecordedCLICommandCount(3, runner: runner, description: "expected missing-only resume command")
        var recordedCommands = await runner.snapshotRecordedCommands()
        guard case .batchResume(let missingOnlyOptions) = try #require(recordedCommands.last) else {
            Issue.record("expected batch.resume command")
            return
        }
        #expect(missingOnlyOptions.missingOnly)

        missingOnlyToggle.performClick(nil)
        try await waitForDesktopFoundationCondition("expected missing-only toggle to clear") {
            viewModel.batchRunResumeMissingOnly == false
        }

        let allRowsView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        #expect(renderedTextValues(in: allRowsView).contains("Resume will rerun all 4 manifest rows."))
        let allRowsResumeButton = try #require(renderedButtons(in: allRowsView).first { $0.title == "Resume Batch" })
        allRowsResumeButton.performClick(nil)

        try await waitForRecordedCLICommandCount(4, runner: runner, description: "expected all-rows resume command")
        recordedCommands = await runner.snapshotRecordedCommands()
        guard case .batchResume(let allRowsOptions) = try #require(recordedCommands.last) else {
            Issue.record("expected second batch.resume command")
            return
        }
        #expect(allRowsOptions.missingOnly == false)
    }

    @Test("batch runs tool section renders status refresh errors")
    @MainActor
    func batchRunsToolSectionRendersStatusRefreshErrors() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            switch command {
            case .batchRun:
                return .success(Self.batchRunsPreflightJSON)
            case .batchStatus:
                return .failure(
                    .processFailed(
                        commandID: "batch.status",
                        surface: .subprocess,
                        exitCode: 2,
                        stderr: "status manifest missing"
                    )
                )
            default:
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let preflightButton = try #require(renderedButtons(in: view).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected selected batch preflight report") {
            viewModel.selectedBatchRunReport?.preflightStatus == "ready"
        }

        let reportView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let statusButton = try #require(renderedButtons(in: reportView).first { $0.title == "Refresh Status" })
        statusButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected status refresh error") {
            viewModel.batchRunStatusErrorMessage.contains("status manifest missing")
        }

        let updatedView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        #expect(renderedTextValues(in: updatedView).contains(where: { $0.contains("status manifest missing") }))
    }

    @Test("batch runs tool section renders resume errors")
    @MainActor
    func batchRunsToolSectionRendersResumeErrors() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            switch command {
            case .batchRun:
                return .success(Self.batchRunsPreflightJSON)
            case .batchStatus:
                return .success(Self.batchRunsStatusJSON)
            case .batchResume:
                return .failure(
                    .processFailed(
                        commandID: "batch.resume",
                        surface: .subprocess,
                        exitCode: 2,
                        stderr: "resume failed"
                    )
                )
            default:
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let preflightButton = try #require(renderedButtons(in: view).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected selected batch preflight report") {
            viewModel.selectedBatchRunReport?.preflightStatus == "ready"
        }

        let reportView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let statusButton = try #require(renderedButtons(in: reportView).first { $0.title == "Refresh Status" })
        statusButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected batch status before resume") {
            viewModel.selectedBatchRunReport?.statusSummary?.status == "partial_success"
        }

        let statusView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let resumeButton = try #require(renderedButtons(in: statusView).first { $0.title == "Resume Batch" })
        resumeButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected resume error") {
            viewModel.batchRunResumeErrorMessage.contains("resume failed")
        }

        let updatedView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        #expect(renderedTextValues(in: updatedView).contains(where: { $0.contains("resume failed") }))
    }

    private static let batchRunsPreflightJSON = #"""
    {
      "schema_version": "melix.batch.effective_config.v1",
      "run_id": "smoke-batch",
      "model_list": "/tmp/models.txt",
      "config_path": "/tmp/config.txt",
      "output_root": "/tmp/melix-batch-output",
      "temp_root": "/tmp/melix-batch-temp",
      "selected_model_count": 1,
      "total_model_count": 4,
      "preflight_report": "/tmp/melix-batch-output/preflight-report.json",
      "preflight_result": {
        "schema_version": "melix.batch.preflight_report.v1",
        "run_id": "smoke-batch",
        "status": "ready",
        "blocker_count": 0,
        "model_count": 1,
        "checks": [
          {
            "name": "output_root",
            "status": "ready",
            "detail": "output root writable",
            "actionable": "",
            "category": "filesystem",
            "metadata": {
              "path": "/tmp/melix-batch-output"
            }
          }
        ]
      }
    }
    """#

    private static let runtimeSettingsOperationSnapshotJSON = #"""
    {
      "schema_version": "melix.runtime_settings.effective.v1",
      "settings": {
        "max_concurrent_jobs": {
          "value": 4,
          "source": "default",
          "source_detail": "builtin"
        }
      },
      "sources": {
        "user_settings": "/tmp/melix-home/runtime_settings.json"
      },
      "metrics": {
        "settings_resolve_ms": 3
      }
    }
    """#

    private static let batchRunsBlockedPreflightJSON = #"""
    {
      "schema_version": "melix.batch.effective_config.v1",
      "run_id": "blocked-batch",
      "model_list": "/tmp/models.txt",
      "config_path": "/tmp/config.txt",
      "output_root": "/tmp/melix-batch-output",
      "temp_root": "/tmp/melix-batch-temp",
      "selected_model_count": 1,
      "total_model_count": 1,
      "preflight_report": "/tmp/melix-batch-output/preflight-report.json",
      "preflight_result": {
        "schema_version": "melix.batch.preflight_report.v1",
        "run_id": "blocked-batch",
        "status": "blocked",
        "blocker_count": 2,
        "model_count": 1,
        "checks": [
          {
            "name": "output_root",
            "status": "ready",
            "detail": "output root writable",
            "actionable": "",
            "category": "filesystem",
            "metadata": {
              "path": "/tmp/melix-batch-output"
            }
          },
          {
            "name": "http_port",
            "status": "blocked",
            "detail": "HTTP port is already in use",
            "actionable": "Set a free MELIX_HTTP_PORT before running the batch.",
            "category": "runtime",
            "metadata": {
              "port": "12434"
            }
          },
          {
            "name": "judge_remote",
            "status": "blocked",
            "detail": "judge remote server is missing",
            "actionable": "Select a judge remote server.",
            "category": "judge",
            "metadata": {}
          }
        ]
      }
    }
    """#

    private static let batchRunsStatusJSON = #"""
    {
      "schema_version": "melix.batch.run_summary.v1",
      "run_id": "smoke-batch",
      "status": "partial_success",
      "total_models": 4,
      "succeeded_models": 2,
      "partial_success_models": 1,
      "failed_models": 1,
      "running_models": 0,
      "planned_models": 0,
      "temp_root": "/tmp/melix-batch-temp",
      "output_root": "/tmp/melix-batch-output",
      "manifest_path": "/tmp/melix-batch-temp/manifest.jsonl",
      "models": [
        {
          "model_index": "01",
          "repo_id": "mlx-community/Qwen3-8B",
          "status": "succeeded",
          "benchmark_job_id": "bench-01",
          "evaluation_job_id": "eval-01",
          "failure_category": "",
          "recoverability": "",
          "duration_seconds": 12.5,
          "metric_fields": {
            "latency_ms": 42.0
          }
        },
        {
          "model_index": "02",
          "repo_id": "mlx-community/Mistral-7B",
          "status": "partial_success",
          "benchmark_job_id": "bench-02",
          "evaluation_job_id": "",
          "failure_category": "artifact_export",
          "recoverability": "retry_same_model",
          "duration_seconds": 21.0,
          "metric_fields": {}
        },
        {
          "model_index": "03",
          "repo_id": "mlx-community/Llama-3.2-3B",
          "status": "failed",
          "benchmark_job_id": "",
          "evaluation_job_id": "",
          "failure_category": "model_load",
          "recoverability": "operator_action_required",
          "duration_seconds": 3.25,
          "metric_fields": {}
        },
        {
          "model_index": "04",
          "repo_id": "mlx-community/Phi-3.5",
          "status": "succeeded",
          "benchmark_job_id": "bench-04",
          "evaluation_job_id": "eval-04",
          "failure_category": "",
          "recoverability": "",
          "duration_seconds": 9.75,
          "metric_fields": {
            "accuracy": 0.88
          }
        }
      ]
    }
    """#

    @Test("batch runs tool section renders preflight runner error")
    @MainActor
    func batchRunsToolSectionRendersPreflightRunnerError() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.updateBatchRunModelListText("mlx-community/Qwen3-8B")

        let view = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        let preflightButton = try #require(renderedButtons(in: view).first { $0.title == "Run Preflight" })
        preflightButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected missing batch runner error") {
            viewModel.batchRunPreflightErrorMessage == "Batch Runs CLI runner is unavailable."
        }

        let updatedView = hostView(DesktopBatchRunsToolSectionView(viewModel: viewModel))
        #expect(renderedTextValues(in: updatedView).contains("Batch Runs CLI runner is unavailable."))
    }

    @Test("jobs tool section renders selected job detail summary")
    @MainActor
    func jobsToolSectionRendersSelectedJobDetailSummary() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.jobs)
        let detail = try RuntimeJobsPayloadDecoder.decodeDetail(Data("""
        {
          "job_id": "training-queue-0001",
          "run_kind": "training",
          "operation": "train_lora",
          "status": "failed",
          "phase": "preflight",
          "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
          "task_kind": "train_lora",
          "dataset_id": "support-chat",
          "artifact_root": "/tmp/melix/jobs/training-queue-0001",
          "record_path": "/tmp/melix/state/local-training-queue.json",
          "cancelable": false,
          "timestamps": {
            "started_at_unix_ms": 1778911200000,
            "updated_at_unix_ms": 1778911210000,
            "ended_at_unix_ms": 1778911215000,
            "duration_ms": 15000
          },
          "error": {
            "code": "insufficient_training_samples",
            "message": "LoRA training requires at least one training sample.",
            "retriable": false,
            "remediation": "Add more accepted training samples before starting training."
          },
          "training_queue": {
            "schema_version": "melix.local_training_queue.v1",
            "resource_class": "exclusive_local_training",
            "recovery_policy": "fix_preflight_and_retry",
            "queue_path": "/tmp/melix/state/local-training-queue.json",
            "workspace_manifest_path": "/tmp/workspace/workspace-manifest.json",
            "dataset_version_id": "support-chat-v2",
            "preflight_receipt_path": "/tmp/melix/jobs/training-queue-0001/trainability-preflight.json"
          },
          "trainability_preflight": {
            "schema_version": "melix.trainability_preflight.v1",
            "status": "blocked",
            "receipt_path": "/tmp/melix/jobs/training-queue-0001/trainability-preflight.json",
            "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "model_family": "qwen3",
            "dataset_format": "chat_messages",
            "training_mode": "qlora",
            "sample_count": 0,
            "validation_sample_count": 0,
            "checks": [
              {
                "code": "insufficient_training_samples",
                "status": "blocked",
                "severity": "error",
                "operator_message": "LoRA training requires at least one training sample.",
                "remediation": "Add more accepted training samples before starting training."
              }
            ],
            "operator_errors": [
              {
                "code": "insufficient_training_samples",
                "severity": "error",
                "operator_message": "LoRA training requires at least one training sample.",
                "retriable": false,
                "remediation": "Add more accepted training samples before starting training."
              },
              {
                "code": "workspace_manifest_unreadable",
                "severity": "error",
                "operator_message": "",
                "retriable": true,
                "remediation": "   "
              }
            ]
          },
          "logs": {
            "available": true,
            "path": "/tmp/melix/jobs/training-queue-0001/job.log",
            "command": "melix jobs logs training-queue-0001"
          },
          "artifacts": [
            {
              "kind": "manifest",
              "path": "/tmp/melix/jobs/training-queue-0001/manifest.json",
              "relative_path": "manifest.json",
              "exists": true
            }
          ]
        }
        """.utf8))
        viewModel.applyRuntimeJobDetail(detail)

        let view = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: view)

        #expect(values.contains("training-queue-0001"))
        #expect(values.contains("failed"))
        #expect(values.contains("preflight"))
        #expect(values.contains(expectedDesktopJobTimestampText(1_778_911_200_000)))
        #expect(values.contains("raw 1778911200000 ms"))
        #expect(values.contains(expectedDesktopJobTimestampText(1_778_911_215_000)))
        #expect(values.contains("raw 1778911215000 ms"))
        #expect(values.contains("15000 ms"))
        #expect(values.contains("insufficient_training_samples"))
        #expect(values.contains("LoRA training requires at least one training sample."))
        #expect(values.contains("not retriable"))
        #expect(values.contains("Add more accepted training samples before starting training."))
        #expect(values.contains("workspace_manifest_unreadable"))
        #expect(values.contains("retriable"))
        #expect(values.allSatisfy { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false })
        #expect(values.contains("fix_preflight_and_retry"))
        #expect(values.contains("exclusive_local_training"))
        #expect(values.contains("support-chat-v2"))
        #expect(values.contains("/tmp/melix/state/local-training-queue.json"))
        #expect(values.contains("/tmp/melix/jobs/training-queue-0001/trainability-preflight.json"))
        #expect(values.contains("blocked"))
        #expect(values.contains("qlora"))
        #expect(values.contains("/tmp/melix/jobs/training-queue-0001/job.log"))
        #expect(values.contains("melix jobs logs training-queue-0001"))
        #expect(values.contains("manifest"))
        #expect(values.contains("/tmp/melix/jobs/training-queue-0001/manifest.json"))
    }

    @Test("jobs tool section renders CLI operation controls")
    @MainActor
    func jobsToolSectionRendersCLIOperationControls() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.jobs)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-20260516-1027",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "updated_at_unix_ms": 1778908099000,
            "cancelable": true
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        let view = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: view)

        #expect(values.contains("Refresh Jobs"))
        #expect(values.contains("Refresh Detail"))
        #expect(values.contains("Fetch Logs"))
        #expect(values.contains("Refresh Artifacts"))
    }

    @Test("jobs tool section operation buttons dispatch and render fetched results")
    @MainActor
    func jobsToolSectionOperationButtonsDispatchAndRenderFetchedResults() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            """
            [
              {
                "job_id": "bench-cli-1",
                "run_kind": "benchmark",
                "status": "running",
                "phase": "sampling",
                "model_id": "mlx-community/Qwen3-8B",
                "task_kind": "text-generation",
                "updated_at_unix_ms": 1778912044000,
                "cancelable": true
              }
            ]
            """,
            for: .jobsList(.init(json: true))
        )
        await runner.configureOutput(
            """
            {
              "job_id": "bench-cli-1",
              "run_kind": "benchmark",
              "status": "running",
              "phase": "export",
              "model_id": "mlx-community/Qwen3-8B",
              "task_kind": "text-generation",
              "logs": {
                "available": true,
                "path": "/tmp/melix/jobs/bench-cli-1/job.log",
                "command": "melix jobs logs bench-cli-1"
              },
              "artifacts": []
            }
            """,
            for: .jobsShow(.init(jobID: "bench-cli-1", json: true))
        )
        await runner.configureOutput(
            """
            {
              "schema_version": "melix.logs.v1",
              "run_id": "bench-cli-1",
              "source_path": "/tmp/melix/jobs/bench-cli-1/run-record.json",
              "log_path": "/tmp/melix/jobs/bench-cli-1/job.log",
              "follow_requested": false,
              "active_follow_supported": false,
              "content": "export started",
              "redacted_field_count": 0
            }
            """,
            for: .jobsLogs(.init(jobID: "bench-cli-1", json: true))
        )
        await runner.configureOutput(
            """
            {
              "schema_version": "melix.job_artifacts.v1",
              "job_id": "bench-cli-1",
              "artifact_count": 1,
              "artifacts": [
                {
                  "kind": "manifest",
                  "path": "/tmp/melix/jobs/bench-cli-1/manifest.json",
                  "relative_path": "manifest.json",
                  "exists": true
                }
              ]
            }
            """,
            for: .jobsArtifacts(.init(jobID: "bench-cli-1", json: true))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyRuntimeJobs(try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-1",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation"
          }
        ]
        """.utf8)))

        let view = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let buttons = renderedButtons(in: view)
        try #require(buttons.contains { $0.title == "Refresh Jobs" })
        try #require(buttons.contains { $0.title == "Refresh Detail" })
        try #require(buttons.contains { $0.title == "Fetch Logs" })
        try #require(buttons.contains { $0.title == "Refresh Artifacts" })

        buttons.first { $0.title == "Refresh Jobs" }?.performClick(nil)
        try await waitForDesktopFoundationCondition("expected jobs list refresh command") {
            viewModel.runtimeJobs.first?.updatedAtUnixMS == 1778912044000
        }

        buttons.first { $0.title == "Refresh Detail" }?.performClick(nil)
        try await waitForDesktopFoundationCondition("expected selected job detail") {
            viewModel.selectedRuntimeJobDetail?.summary.phase == "export"
        }

        buttons.first { $0.title == "Fetch Logs" }?.performClick(nil)
        try await waitForDesktopFoundationCondition("expected selected job logs") {
            viewModel.selectedRuntimeJobLogSnapshot?.content == "export started"
        }

        buttons.first { $0.title == "Refresh Artifacts" }?.performClick(nil)
        try await waitForDesktopFoundationCondition("expected selected job artifacts") {
            viewModel.selectedRuntimeJobArtifactSnapshot?.artifacts.first?.kind == "manifest"
        }

        let updatedView = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: updatedView)
        #expect(values.contains("export started"))
        #expect(values.contains("manifest"))
        #expect(values.contains("/tmp/melix/jobs/bench-cli-1/manifest.json"))
    }

    @Test("jobs tool section renders cancel request states for active and terminal jobs")
    @MainActor
    func jobsToolSectionRendersCancelRequestStatesForActiveAndTerminalJobs() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.jobs)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-active",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true,
            "cancellation_requested": false
          },
          {
            "job_id": "bench-terminal",
            "run_kind": "benchmark",
            "status": "completed",
            "phase": "completed",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": false,
            "cancellation_requested": false
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        let activeView = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let activeButtons = renderedButtons(in: activeView)
        let activeCancelButton = try #require(activeButtons.first { $0.title == "Request Cancel" })
        #expect(activeCancelButton.isEnabled)
        #expect(renderedTextValues(in: activeView).contains("Active job can receive a durable cancel request"))

        viewModel.selectRuntimeJob(id: "bench-terminal")
        let terminalView = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let terminalButtons = renderedButtons(in: terminalView)
        let terminalCancelButton = try #require(terminalButtons.first { $0.title == "Request Cancel" })
        #expect(terminalCancelButton.isEnabled == false)
        #expect(renderedTextValues(in: terminalView).contains("Terminal job cannot be canceled"))
    }

    @Test("jobs tool section cancel button dispatches and renders cancel result")
    @MainActor
    func jobsToolSectionCancelButtonDispatchesAndRendersCancelResult() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            """
            {
              "schema_version": "melix.job_cancel_result.v1",
              "job_id": "bench-active",
              "cancel_requested": true,
              "status": "running",
              "phase": "sampling",
              "request_path": "/tmp/melix/jobs/bench-active/cancel-request.json",
              "request": {
                "requested_at_unix_ms": 1778913000000,
                "process_signal": {
                  "pid": null,
                  "sent": false,
                  "reason": "direct_process_signal_disabled"
                }
              }
            }
            """,
            for: .jobsCancel(.init(jobID: "bench-active", json: true))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.selectToolSection(.jobs)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-active",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true,
            "cancellation_requested": false
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        let view = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let cancelButton = try #require(renderedButtons(in: view).first { $0.title == "Request Cancel" })
        cancelButton.performClick(nil)

        try await waitForDesktopFoundationCondition("expected selected job cancel result") {
            viewModel.selectedRuntimeJobCancelResult?.cancelRequested == true
        }

        let updatedView = hostView(DesktopJobsToolSectionView(viewModel: viewModel))
        let values = renderedTextValues(in: updatedView)
        #expect(values.contains("Cancellation requested"))
        #expect(values.contains("/tmp/melix/jobs/bench-active/cancel-request.json"))
        #expect(await runner.snapshotRecordedCommands() == [.jobsCancel(.init(jobID: "bench-active", json: true))])
    }

    @Test("training defaults to preset-first primary fields with advanced folded")
    @MainActor
    func trainingDefaultsToPresetFirstPrimaryFieldsWithAdvancedFolded() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopTrainingToolSectionView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)
        let summaryItems = DesktopTrainingToolSectionView.summaryItems(for: viewModel)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopTrainingWorkspaceDefaults.showsAdvancedParameters == false)
        #expect(DesktopTrainingWorkspaceDefaults.advancedParametersTitle == "Advanced Training Parameters")
        #expect(summaryItems.count == 4)
        #expect(summaryItems.first(where: { $0.title == "Dataset" })?.detail == "Local package dataset")
        #expect(summaryItems.first(where: { $0.title == "Preset" })?.detail == "Auto experiment grouping")
        #expect(renderedTexts.contains(viewModel.selectedLoraModelID))
        #expect(renderedTexts.contains(viewModel.loraAdapterName))
        #expect(renderedTexts.contains(viewModel.loraTargetRepo))
        #expect(renderedTexts.contains("Rank") == false)
        #expect(renderedTexts.contains("Alpha") == false)
        #expect(renderedTexts.contains("Dropout") == false)
        #expect(renderedTexts.contains(RuntimeLoraActivationMode.adapterBackedRuntime.title))
    }

    @Test("training exposes issue 365 alignment modes and mode-specific controls")
    @MainActor
    func trainingExposesIssue365AlignmentModesAndModeSpecificControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let modeTitles = RuntimeLoraTrainingMode.allCases.map(\.title)
        #expect(modeTitles.contains("CPO"))
        #expect(modeTitles.contains("GRPO"))
        #expect(modeTitles.contains("RLHF"))

        viewModel.loraTrainingMode = .grpo
        viewModel.loraGRPOCandidateCount = "4"
        viewModel.loraReferenceModelPath = "/tmp/melix/reference-model"
        viewModel.loraKLPenalty = "0.02"
        let grpoView = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let grpoTexts = renderedTextValues(in: grpoView)
        #expect(grpoTexts.contains("Alignment Controls"))
        #expect(grpoTexts.contains("GRPO"))
        #expect(grpoTexts.contains("/tmp/melix/reference-model"))
        #expect(grpoTexts.contains("4"))
        #expect(grpoTexts.contains("0.02"))

        viewModel.loraTrainingMode = .rlhf
        viewModel.loraRewardModelManifestPath = "/tmp/melix/reward-model/manifest.json"
        let rlhfView = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let rlhfTexts = renderedTextValues(in: rlhfView)
        #expect(rlhfTexts.contains("RLHF"))
        #expect(rlhfTexts.contains("/tmp/melix/reward-model/manifest.json"))
        #expect(rlhfTexts.contains("0.02"))

        viewModel.loraTrainingMode = .dpo
        let dpoView = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let dpoTexts = renderedTextValues(in: dpoView)
        #expect(dpoTexts.contains("DPO"))
        #expect(dpoTexts.contains("Alignment Controls"))
        #expect(dpoTexts.contains("0.02") == false)
    }

    @Test("training core setup uses editorial field groups instead of one large form slab")
    @MainActor
    func trainingCoreSetupUsesEditorialFieldGroups() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1200, height: 1600)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Run Identity"))
        #expect(renderedTexts.contains("Dataset & Mode"))
        #expect(renderedTexts.contains("Delivery"))
    }

    @Test("training surface adopts the system design guide overview hierarchy")
    @MainActor
    func trainingSurfaceAdoptsSystemDesignGuideOverviewHierarchy() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1900)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Primary Model"))
        #expect(renderedTexts.contains("Workflow Snapshot"))
        #expect(renderedTexts.contains("Saved Jobs"))
        #expect(renderedTexts.contains("Run Draft"))
        #expect(renderedTexts.contains("Adapter Registry"))
        #expect(renderedTexts.contains("Experiment Groups"))
        #expect(renderedTexts.contains("Training History"))
        #expect(renderedTexts.contains("Workflow Actions") == false)
        #expect(renderedTexts.contains("Selected Configuration") == false)
        #expect(renderedTexts.contains("Training Configuration") == false)
        #expect(renderedTexts.contains("Adapter Activation") == false)
        #expect(renderedTexts.contains("Saved Adapters") == false)
        #expect(renderedTexts.contains("Training Jobs") == false)
    }

    @Test("training surface renders saved lora job detail and follow-up actions")
    @MainActor
    func trainingSurfaceRendersSavedLoraJobDetailAndFollowUpActions() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "local_package",
            datasetURI: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
            adapterName: "saved-adapter",
            targetRepo: "melix/adapters/saved-adapter",
            experimentGroupID: "saved-group",
            trainingMode: "qlora",
            presetID: "balanced_adapter",
            activationMode: "adapter_backed_runtime",
            rank: "16",
            alpha: "32",
            batchSize: "2",
            epochs: "2",
            responseOnly: true,
            maskPrompt: true,
            gradientCheckpointing: true,
            derivedModelAlias: "melix-dev-text-lora"
        )
        let job = LoraTrainingJobRecord(
            id: "saved-job",
            title: "Saved Adapter",
            config: config,
            status: .succeeded,
            lastRunJobID: "model-ops-0001",
            outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            manifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            latestOutputText: #"{"operation":"train_lora"}"#,
            terminalMessage: "Training completed.",
            followUpArtifacts: .init(
                adapterManifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
                derivedModelID: "melix-dev-text-lora",
                quantizedArtifactPath: "/tmp/melix-quantize/saved-adapter/quantized.artifact",
                convertedArtifactPath: "/tmp/melix-convert/saved-adapter/converted.artifact",
                benchmarkJobID: "bench-saved-adapter",
                evaluationJobID: "eval-saved-adapter",
                memoryFitSummaryText: "Blocked - Training optimizer estimate exceeds unified memory. • threshold 85%"
            )
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 2200)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Saved Jobs"))
        #expect(renderedTexts.contains("Saved Adapter"))
        #expect(renderedTexts.contains { $0.contains("model-ops-0001") })
        #expect(renderedTexts.contains("Follow-up Actions"))
        #expect(renderedTexts.contains("Follow-up Artifacts"))
        #expect(renderedTexts.contains("Quantized Artifact"))
        #expect(renderedTexts.contains("Converted Artifact"))
        #expect(renderedTexts.contains("Benchmark Job"))
        #expect(renderedTexts.contains("Evaluation Job"))
        #expect(renderedTexts.contains("Memory Fit"))
        #expect(renderedTexts.contains("Blocked - Training optimizer estimate exceeds unified memory. • threshold 85%"))
        #expect(renderedTexts.contains("Activation"))
        #expect(renderedTexts.contains("Quantization"))
        #expect(renderedTexts.contains("Benchmark"))
        #expect(renderedTexts.contains("Evaluation"))
        #expect(renderedTexts.contains("Import Config Path"))
        #expect(renderedTexts.contains("Export Config Path"))
    }

    @Test("training surface renders saved lora adapter capability receipt")
    @MainActor
    func trainingSurfaceRendersSavedLoraAdapterCapabilityReceipt() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "local_package",
            datasetURI: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
            adapterName: "unsupported-adapter",
            trainingMode: "dora",
            activationMode: "adapter_backed_runtime"
        )
        let job = LoraTrainingJobRecord(
            id: "adapter-capability-job",
            title: "Adapter Capability Job",
            config: config,
            status: .failed,
            lastRunJobID: "model-ops-adapter-capability",
            outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            manifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            latestOutputText: #"""
            {
              "operation": "train_lora",
              "adapter_family": "unsupported_adapter",
              "adapter_algorithm": "dora",
              "backend_supported": false,
              "unsupported_reason": "unsupported_backend"
            }
            """#,
            terminalMessage: "Training failed."
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1600)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Adapter Capability"))
        #expect(renderedTexts.contains("Family"))
        #expect(renderedTexts.contains("unsupported_adapter"))
        #expect(renderedTexts.contains("Algorithm"))
        #expect(renderedTexts.contains("dora"))
        #expect(renderedTexts.contains("Backend Support"))
        #expect(renderedTexts.contains("Unsupported"))
        #expect(renderedTexts.contains("Unsupported Reason"))
        #expect(renderedTexts.contains("unsupported_backend"))
    }

    @Test("training surface renders response-only truncation safety receipt")
    @MainActor
    func trainingSurfaceRendersResponseOnlyTruncationSafetyReceipt() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "hf_dataset",
            hfDatasetPath: "HuggingFaceH4/ultrachat_200k",
            hfTrainSplit: "train_sft",
            chatFeature: "messages",
            adapterName: "truncated-response-adapter",
            trainingMode: "qlora",
            activationMode: "adapter_backed_runtime",
            maxSeqLength: "1024",
            responseOnly: true,
            maskPrompt: true
        )
        let job = LoraTrainingJobRecord(
            id: "response-only-truncated-job",
            title: "Response-only Truncated Job",
            config: config,
            status: .failed,
            lastRunJobID: "model-ops-response-only",
            outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            manifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            latestOutputText: #"""
            {
              "error_code": "response_only_labels_truncated",
              "details": {
                "max_seq_length": "1024",
                "response_only_boundary_sample_count": "2",
                "response_only_boundary_min": "1100",
                "response_only_boundary_max": "1200",
                "response_only_boundary_mean": "1150.000",
                "response_only_response_tokens_mean": "9.000",
                "response_only_trainable_response_token_count": "0",
                "response_only_fully_truncated_response_sample_count": "2"
              }
            }
            """#,
            terminalMessage: "Training failed."
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Response-only Safety"))
        #expect(renderedTexts.contains("Blocked"))
        #expect(renderedTexts.contains("Increase max_seq_length, shorten the system prompt, or disable response-only masking."))
        #expect(renderedTexts.contains("Max Seq Length"))
        #expect(renderedTexts.contains("1024"))
        #expect(renderedTexts.contains("Boundary Range"))
        #expect(renderedTexts.contains("1100-1200"))
        #expect(renderedTexts.contains("Trainable Response Tokens"))
        #expect(renderedTexts.contains("Fully Truncated Samples"))
    }

    @Test("training surface suppresses response-only recovery for observed jobs")
    @MainActor
    func trainingSurfaceSuppressesResponseOnlyRecoveryForObservedJobs() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "hf_dataset",
            hfDatasetPath: "HuggingFaceH4/ultrachat_200k",
            hfTrainSplit: "train_sft",
            chatFeature: "messages",
            adapterName: "observed-response-adapter",
            trainingMode: "qlora",
            activationMode: "adapter_backed_runtime",
            maxSeqLength: "2048",
            responseOnly: true,
            maskPrompt: true
        )
        let job = LoraTrainingJobRecord(
            id: "response-only-observed-job",
            title: "Response-only Observed Job",
            config: config,
            status: .succeeded,
            latestOutputText: #"""
            {
              "details": {
                "max_seq_length": "2048",
                "response_only_boundary_sample_count": "3",
                "response_only_boundary_min": "128",
                "response_only_boundary_max": "256",
                "response_only_response_tokens_mean": "9.500",
                "response_only_trainable_response_token_count": "24"
              }
            }
            """#,
            terminalMessage: "Training completed."
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Response-only Safety"))
        #expect(renderedTexts.contains("Observed"))
        #expect(renderedTexts.contains("Recovery") == false)
        #expect(renderedTexts.contains("Increase max_seq_length, shorten the system prompt, or disable response-only masking.") == false)
    }

    @Test("training surface renders response-only partially truncated sample counts")
    @MainActor
    func trainingSurfaceRendersResponseOnlyPartiallyTruncatedSampleCounts() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "hf_dataset",
            hfDatasetPath: "HuggingFaceH4/ultrachat_200k",
            hfTrainSplit: "train_sft",
            chatFeature: "messages",
            adapterName: "partially-truncated-response-adapter",
            trainingMode: "qlora",
            activationMode: "adapter_backed_runtime",
            maxSeqLength: "1024",
            responseOnly: true,
            maskPrompt: true
        )
        let job = LoraTrainingJobRecord(
            id: "response-only-partially-truncated-job",
            title: "Response-only Partially Truncated Job",
            config: config,
            status: .succeeded,
            latestOutputText: #"""
            {
              "details": {
                "max_seq_length": "1024",
                "response_only_boundary_sample_count": "3",
                "response_only_boundary_min": "900",
                "response_only_boundary_max": "1120",
                "response_only_response_tokens_mean": "7.000",
                "response_only_trainable_response_token_count": "12",
                "response_only_truncated_response_sample_count": "1"
              }
            }
            """#,
            terminalMessage: "Training completed."
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Response-only Safety"))
        #expect(renderedTexts.contains("Truncated"))
        #expect(renderedTexts.contains("Truncated Samples"))
        #expect(renderedTexts.contains("1"))
    }

    @Test("training surface renders saved lora adapter support matrix receipt")
    @MainActor
    func trainingSurfaceRendersSavedLoraAdapterSupportMatrixReceipt() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "local_package",
            datasetURI: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
            adapterName: "relora-adapter",
            trainingMode: "qlora",
            activationMode: "adapter_backed_runtime"
        )
        let job = LoraTrainingJobRecord(
            id: "adapter-support-matrix-job",
            title: "Adapter Support Matrix Job",
            config: config,
            status: .succeeded,
            lastRunJobID: "model-ops-adapter-support-matrix",
            outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            manifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            latestOutputText: #"""
            {
              "operation": "train_lora",
              "adapter_family": "fake_relora",
              "adapter_algorithm": "fake_relora",
              "backend_supported": true,
              "unsupported_reason": "",
              "adapter_capabilities": {
                "lora_like": true,
                "mergeable": false,
                "relora_compatible": true,
                "quantized_base_supported": false
              }
            }
            """#,
            terminalMessage: "Training completed."
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1600)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Adapter Capability"))
        #expect(renderedTexts.contains("LoRA-like"))
        #expect(renderedTexts.contains("Mergeable"))
        #expect(renderedTexts.contains("ReLoRA-compatible"))
        #expect(renderedTexts.contains("Quantized Base"))
        #expect(renderedTexts.contains("Supported"))
        #expect(renderedTexts.contains("Unsupported"))
    }

    @Test("training surface renders unknown family and unsupported quantized base states")
    @MainActor
    func trainingSurfaceRendersUnknownFamilyAndUnsupportedQuantizedBaseStates() async throws {
        let config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "local_package",
            datasetURI: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
            adapterName: "unknown-family-adapter",
            trainingMode: "custom",
            activationMode: "adapter_backed_runtime"
        )
        let job = LoraTrainingJobRecord(
            id: "adapter-unknown-family-job",
            title: "Adapter Unknown Family Job",
            config: config,
            status: .failed,
            lastRunJobID: "model-ops-adapter-unknown-family",
            outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            manifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            latestOutputText: #"""
            {
              "operation": "train_lora",
              "adapter_algorithm": "custom_adapter",
              "backend_supported": true,
              "unsupported_reason": "unsupported_quantized_base",
              "adapter_capabilities": {
                "lora_like": true,
                "mergeable": true,
                "relora_compatible": false,
                "quantized_base_supported": false
              }
            }
            """#,
            terminalMessage: "Training failed."
        )
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1600)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Adapter Capability"))
        #expect(renderedTexts.contains("Family"))
        #expect(renderedTexts.contains("Unknown Family"))
        #expect(renderedTexts.contains("Quantized Base"))
        #expect(renderedTexts.contains("Unsupported quantized base"))
        #expect(renderedTexts.contains("unsupported_quantized_base"))
    }

    @Test("training surface renders saved job follow-up activation gating from adapter receipts")
    @MainActor
    func trainingSurfaceRendersSavedJobFollowUpActivationGatingFromAdapterReceipts() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/non-mergeable-adapter"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        var config = LoraTrainingJobConfig(
            modelID: "melix-dev-text",
            datasetSourceKind: "local_package",
            datasetURI: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
            adapterName: "non-mergeable-adapter",
            targetRepo: "melix/adapters/non-mergeable-adapter",
            trainingMode: "qlora",
            activationMode: RuntimeLoraActivationMode.fusedDerivedModel.rawValue
        )
        config.derivedModelAlias = "melix-dev-text-fused"
        var job = LoraTrainingJobRecord(
            id: "adapter-gating-job",
            title: "Adapter Gating Job",
            config: config,
            status: .succeeded,
            lastRunJobID: "model-ops-adapter-gating",
            outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            manifestPath: "/tmp/melix-train-lora/train_lora.adapter.json",
            latestOutputText: #"""
            {
              "operation": "train_lora",
              "adapter_family": "fake_relora",
              "adapter_algorithm": "fake_relora",
              "backend_supported": true,
              "unsupported_reason": "non_mergeable_adapter",
              "adapter_capabilities": {
                "lora_like": true,
                "mergeable": false,
                "relora_compatible": true,
                "quantized_base_supported": true
              }
            }
            """#,
            terminalMessage: "Training completed."
        )
        job.followUpArtifacts.adapterManifestPath = "/tmp/melix-train-lora/train_lora.adapter.json"
        let viewModel = RuntimeViewModel(
            client: client,
            loraTrainingJobStore: FakeLoraTrainingJobStore(jobs: [job])
        )
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        viewModel.prepareSelectedLoraTrainingJobFollowUp(RuntimeLoraTrainingJobFollowUpAction.activation)
        let disabledReason = "Fused activation is disabled for fake_relora: non_mergeable_adapter. Use Adapter-backed Serving instead."
        #expect(viewModel.loraFusedActivationUnavailableText == disabledReason)

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1800)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Adapter Gating Job"))
        #expect(renderedTexts.contains("Follow-up Actions"))
        #expect(renderedTexts.contains("Activation"))
        #expect(renderedTexts.contains("Adapter Capability"))
        #expect(renderedTexts.contains("Mergeable"))
        #expect(renderedTexts.contains(disabledReason))
    }

    @Test("training keeps Hugging Face dataset mapping fields folded behind a secondary reveal by default")
    @MainActor
    func trainingKeepsHFDatasetMappingFoldedByDefault() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraHFDatasetPath = "HuggingFaceH4/ultrachat_200k"
        viewModel.loraHFDatasetName = "train_sft"
        viewModel.loraHFDatasetRevision = "test_sft"
        viewModel.loraHFTrainSplit = "train"
        viewModel.loraHFValidSplit = "test"

        let view = hostView(DesktopTrainingToolSectionView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("HuggingFaceH4/ultrachat_200k"))
        #expect(renderedTexts.contains("train_sft") == false)
        #expect(renderedTexts.contains("test_sft") == false)
        #expect(renderedTexts.contains("messages") == false)
    }

    @Test("training expanded reveals render dataset mapping and advanced tuning fields")
    @MainActor
    func trainingExpandedRevealsRenderDatasetMappingAndAdvancedTuningFields() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraHFDatasetPath = "HuggingFaceH4/ultrachat_200k"
        viewModel.loraHFDatasetName = "train_sft"
        viewModel.loraHFDatasetRevision = "test_sft"
        viewModel.loraHFTrainSplit = "train"
        viewModel.loraHFValidSplit = "test"
        viewModel.loraTextFeature = "messages"
        viewModel.loraPromptFeature = "prompt"
        viewModel.loraCompletionFeature = "completion"
        viewModel.loraChatFeature = "chat"
        viewModel.loraRank = "32"
        viewModel.loraAlpha = "64"
        viewModel.loraDropout = "0.10"
        viewModel.loraBatchSize = "4"
        viewModel.loraEpochs = "3"
        viewModel.loraLearningRate = "2e-4"
        viewModel.loraMaxSeqLength = "8192"
        viewModel.loraTargetModules = "q_proj,v_proj"
        viewModel.loraNumLayers = "24"
        viewModel.loraDerivedModelAlias = "melix-qwen35-acceptance"
        viewModel.loraResponseOnly = true
        viewModel.loraMaskPrompt = true
        viewModel.loraGradientCheckpointing = true

        let view = hostView(
            DesktopTrainingToolSectionView(
                viewModel: viewModel,
                showsAdvanced: true,
                showsDatasetMapping: true
            )
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("train_sft"))
        #expect(renderedTexts.contains("test_sft"))
        #expect(renderedTexts.contains("messages"))
        #expect(renderedTexts.contains("prompt"))
        #expect(renderedTexts.contains("completion"))
        #expect(renderedTexts.contains("chat"))
        #expect(renderedTexts.contains("32"))
        #expect(renderedTexts.contains("64"))
        #expect(renderedTexts.contains("0.10"))
        #expect(renderedTexts.contains("8192"))
        #expect(renderedTexts.contains("q_proj,v_proj"))
        #expect(renderedTexts.contains("24"))
        #expect(renderedTexts.contains("melix-qwen35-acceptance"))
    }

    @Test("training workspace renders grouped experiments adapters and job history with reuse actions")
    @MainActor
    func trainingWorkspaceRendersGroupedExperimentsAdaptersAndJobHistory() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeTrainingWorkspaceRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        viewModel.selectedAdapterPackageID = "adapter-1"

        #expect(viewModel.loraExperimentGroups.count == 2)
        #expect(viewModel.adapterPackages.count == 2)
        #expect(viewModel.trainingHistory.count == 2)

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1200, height: 2400)
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedAdapterPackage?.adapterName == "qwen35-acceptance")
        #expect(viewModel.loraExperimentGroups.first?.title == "Phase 8 Acceptance")
        #expect(viewModel.loraExperimentGroups.first?.resumeReadySummaryText == "1 of 2 runs resume-ready")
        #expect(viewModel.trainingHistory.first?.adapterName == "qwen35-acceptance")
    }

    @Test("training idle workflow promotes resume ready groups when no adapter is selected")
    @MainActor
    func trainingIdleWorkflowPromotesResumeReadyGroupsWhenNoAdapterIsSelected() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeResumeReadyExperimentGroupsRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        #expect(viewModel.adapterPackages.isEmpty)
        #expect(viewModel.loraExperimentGroups.count == 1)

        let view = hostView(
            DesktopTrainingToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1200, height: 2400)
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedAdapterPackage == nil)
        #expect(viewModel.loraExperimentGroups.first?.resumeReadySummaryText == "1 of 2 runs resume-ready")
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
        await section.removeDerivedModel()

        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.selectedAdapterPackage?.derivedModelID == "melix-dev-text-lora-adapter")
        #expect(await client.recordedActions.contains("operation:train_lora:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:activate_adapter:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:remove_derived_model:melix-dev-text"))
    }

    @Test("training tool section renders workflow status feedback for activation progress and success")
    @MainActor
    func trainingToolSectionRendersWorkflowStatusFeedback() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperationDelay(.milliseconds(120))
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
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "activate_adapter",
                outputPath: "/tmp/melix-activate/activate_adapter.derived_model.json",
                manifestJSON: #"{"operation":"activate_adapter","derived_model_path":"/tmp/melix-activate/activate_adapter.derived_model.json"}"#
            ),
            forNamedOperation: "activate_adapter"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let task = Task { await DesktopTrainingToolSectionView(viewModel: viewModel).activateAdapter() }
        try await Task.sleep(for: .milliseconds(20))

        let pendingView = hostView(DesktopTrainingToolSectionView(viewModel: viewModel))
        #expect(pendingView.subviews.isEmpty == false)
        #expect(viewModel.loraWorkflowStatus?.phase == .running)
        #expect(viewModel.loraWorkflowStatus?.title == "Activating Adapter")

        await task.value

        let completedView = hostView(DesktopTrainingToolSectionView(viewModel: viewModel))
        #expect(completedView.subviews.isEmpty == false)
        #expect(viewModel.loraWorkflowStatus?.phase == .succeeded)
        #expect(viewModel.loraWorkflowStatus?.title == "Adapter Activated")
        #expect(viewModel.loraWorkflowStatus?.detail.contains("activate_adapter.derived_model.json") == true)
    }

    @Test("diagnostics empty states explain how to unlock benchmark and evaluation evidence")
    @MainActor
    func diagnosticsEmptyStatesExplainHowToUnlockEvidence() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        let view = hostView(section)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.emptyBenchmarkTitle == "No Benchmark Results Yet")
        #expect(DesktopDiagnosticsToolSectionView.emptyBenchmarkDetail == "Run Benchmark to capture latency and throughput history.")
        #expect(DesktopDiagnosticsToolSectionView.emptyEvaluationTitle == "No Evaluation Results Yet")
        #expect(DesktopDiagnosticsToolSectionView.emptyEvaluationDetail == "Run Evaluation to inspect scores and sample previews.")
        #expect(viewModel.benchmarkMetricCards.isEmpty)
        #expect(viewModel.evaluationMetricCards.isEmpty)
    }

    @Test("training tool section remove-derived helper surfaces local guard rails without an activated adapter")
    @MainActor
    func trainingToolSectionRemoveDerivedRequiresActivatedAdapter() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let section = DesktopTrainingToolSectionView(viewModel: viewModel)
        await section.removeDerivedModel()

        #expect(viewModel.lastError == "Select an activated adapter before removing its derived model.")
        #expect(await client.recordedActions.contains("operation:remove_derived_model:melix-dev-text") == false)
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
                initialSection: .authentication,
                showsSidebar: .constant(true),
                showsInspector: .constant(false)
            )
        )
        let quickStarts = hostView(
            DesktopAPIWorkspaceView(
                viewModel: viewModel,
                foundation: foundation,
                initialSection: .quickStarts,
                showsSidebar: .constant(true),
                showsInspector: .constant(false)
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

    @Test("api authentication surface includes companion pairing token controls")
    func apiAuthenticationSurfaceIncludesCompanionPairingTokenControls() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let shellSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift"
        )
        let shellSource = try String(contentsOf: shellSourceURL, encoding: .utf8)

        #expect(shellSource.contains("DesktopAPICompanionPairingPanel"))
        #expect(shellSource.contains("Companion Pairing"))
        #expect(shellSource.contains("Issue Read-Only Token"))
        #expect(shellSource.contains("Copy Pairing Bundle"))
        #expect(shellSource.contains("Revoke Token"))
    }

    @Test("api authentication surface includes companion status log tail panel")
    func apiAuthenticationSurfaceIncludesCompanionStatusLogTailPanel() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let shellSourceURL = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift"
        )
        let shellSource = try String(contentsOf: shellSourceURL, encoding: .utf8)

        #expect(shellSource.contains("DesktopAPICompanionStatusPanel"))
        #expect(shellSource.contains("Companion Status"))
        #expect(shellSource.contains("Refresh Status"))
        #expect(shellSource.contains("Redacted Log Tail"))
    }

    @Test("companion pairing panel renders idle active and failure states")
    @MainActor
    func companionPairingPanelRendersIdleActiveAndFailureStates() async throws {
        let idleViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await idleViewModel.start()
        let idlePresentation = DesktopAPICompanionPairingPresentation(pairing: idleViewModel.companionPairing)
        _ = hostView(DesktopAPICompanionPairingPanel(viewModel: idleViewModel))

        #expect(idlePresentation.statusTitle == "No active companion token")
        #expect(idlePresentation.scopeText == "companion_read_only")
        #expect(idlePresentation.issueDisabled == false)
        #expect(idlePresentation.copyDisabled)
        #expect(idlePresentation.revokeDisabled)

        let activeClient = FakeCompanionPairingClient()
        await activeClient.configureIssueResult(
            CompanionPairingIssueResult(
                sessionID: "companion-ui-session",
                scope: "companion_read_only",
                rememberMe: true,
                expiresAtUnixMS: 1_718_000_000_000,
                resumeHeader: "x-melix-session",
                resumeToken: "melix_companion_ui_secret",
                pairing: CompanionPairingDescriptor(
                    schemaVersion: "melix.companion.pairing.v1",
                    statusURL: "http://127.0.0.1:12436/v1/melix/companion/status",
                    resumeHeader: "x-melix-session",
                    tokenTransport: "resume_header",
                    allowedRoutes: ["GET /v1/melix/companion/status"],
                    forbiddenCapabilities: ["mutate_runtime"],
                    expiresAtUnixMS: 1_718_000_000_000
                )
            )
        )
        let activeTemporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-companion-panel-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: activeTemporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: activeTemporaryRoot) }
        let activeMelixHome = MelixHome(environment: ["MELIX_HOME": activeTemporaryRoot.path])
        let activeAPIKeyStore = ServerSessionAPIKeyStore(melixHome: activeMelixHome)
        let activeViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            serverSessionAPIKeyStore: activeAPIKeyStore,
            companionPairingClient: activeClient
        )

        await activeViewModel.start()
        try activeAPIKeyStore.savePrimaryKey(
            serverSessionID: try #require(activeViewModel.selectedServerSession?.id),
            primaryKey: "melix_primary_desktop",
            keyID: "primary"
        )
        await activeViewModel.issueCompanionPairing()
        let activePresentation = DesktopAPICompanionPairingPresentation(pairing: activeViewModel.companionPairing)
        _ = hostView(DesktopAPICompanionPairingPanel(viewModel: activeViewModel))

        #expect(activePresentation.statusTitle == "Read-only companion token active")
        #expect(activePresentation.statusDetail.contains("1718000000000") == false)
        #expect(activePresentation.statusDetail.contains("expires at"))
        #expect(activePresentation.statusURL == "http://127.0.0.1:12436/v1/melix/companion/status")
        #expect(activePresentation.allowedRoutesText == "Allowed routes: GET /v1/melix/companion/status")
        #expect(activePresentation.copyDisabled == false)
        #expect(activePresentation.revokeDisabled == false)

        let failureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await failureViewModel.start()
        await failureViewModel.revokeCompanionPairing()
        let failurePresentation = DesktopAPICompanionPairingPresentation(pairing: failureViewModel.companionPairing)
        _ = hostView(DesktopAPICompanionPairingPanel(viewModel: failureViewModel))

        #expect(failurePresentation.statusTitle == "Companion pairing needs attention")
        #expect(failurePresentation.errorText == "No active companion pairing token to revoke.")
    }

    @Test("companion status panel renders idle loaded and failure states")
    @MainActor
    func companionStatusPanelRendersIdleLoadedAndFailureStates() async throws {
        let idleViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await idleViewModel.start()
        let idlePresentation = DesktopAPICompanionStatusPresentation(status: idleViewModel.companionStatus)
        _ = hostView(DesktopAPICompanionStatusPanel(viewModel: idleViewModel))

        #expect(idlePresentation.statusTitle == "Companion status not loaded")
        #expect(idlePresentation.statusDetail == "Refresh after issuing a read-only companion token.")
        #expect(idlePresentation.refreshDisabled == false)
        #expect(idlePresentation.logRows.isEmpty)

        let loadingPresentation = DesktopAPICompanionStatusPresentation(
            status: CompanionStatusState(phase: .loading)
        )
        #expect(loadingPresentation.statusTitle == "Refreshing companion status")
        #expect(loadingPresentation.statusDetail == "Reading the companion status endpoint with the transient read-only token.")
        #expect(loadingPresentation.refreshDisabled)

        let activePairingClient = FakeCompanionPairingClient()
        let statusClient = FakeCompanionStatusClient()
        let activeTemporaryRoot = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-menubar-companion-status-panel-\(UUID().uuidString)"
        )
        try FileManager.default.createDirectory(at: activeTemporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: activeTemporaryRoot) }
        let activeMelixHome = MelixHome(environment: ["MELIX_HOME": activeTemporaryRoot.path])
        let activeAPIKeyStore = ServerSessionAPIKeyStore(melixHome: activeMelixHome)
        await statusClient.configureRefreshResult(
            CompanionStatusSnapshot(
                status: "ok",
                readOnly: true,
                authorizationScope: "companion_read_only",
                logTail: CompanionStatusLogTailState(
                    source: "image_jobs",
                    visible: 1,
                    total: 2,
                    entries: [
                        CompanionStatusLogEntryState(
                            eventType: "state_update",
                            source: "image_jobs",
                            jobID: "image-job-ui",
                            requestID: "request-ui",
                            modelID: "melix-dev-image",
                            operation: "image_generate",
                            state: "failed",
                            lane: "interactive",
                            workerID: "image-worker-ui",
                            progressStage: "failed",
                            updatedAtUnixMS: 1_718_000_020_000,
                            failureCode: "image_worker_failed",
                            redactionSummary: "raw log line omitted; raw prompt omitted; request body omitted; artifact URIs omitted; local paths omitted; error message omitted"
                        ),
                    ]
                ),
                redactionLogs: "redacted_tail"
            )
        )
        let activeViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            serverSessionAPIKeyStore: activeAPIKeyStore,
            companionPairingClient: activePairingClient,
            companionStatusClient: statusClient
        )

        await activeViewModel.start()
        try activeAPIKeyStore.savePrimaryKey(
            serverSessionID: try #require(activeViewModel.selectedServerSession?.id),
            primaryKey: "melix_primary_desktop",
            keyID: "primary"
        )
        await activeViewModel.issueCompanionPairing()
        await activeViewModel.refreshCompanionStatus()
        let loadedPresentation = DesktopAPICompanionStatusPresentation(status: activeViewModel.companionStatus)
        _ = hostView(DesktopAPICompanionStatusPanel(viewModel: activeViewModel))

        #expect(loadedPresentation.statusTitle == "Companion status ok")
        #expect(loadedPresentation.statusDetail == "Read-only companion status, 1 of 2 redacted log entries visible.")
        #expect(loadedPresentation.logRows.map(\.title) == ["image-job-ui • failed"])
        #expect(loadedPresentation.logRows.first?.detail.contains("image_worker_failed") == true)
        #expect(loadedPresentation.logRows.first?.redactionText.contains("raw prompt omitted") == true)
        #expect(loadedPresentation.redactionText == "redacted_tail")

        let unknownTimePresentation = DesktopAPICompanionStatusPresentation(
            status: CompanionStatusState.loaded(
                from: CompanionStatusSnapshot(
                    status: "",
                    readOnly: true,
                    authorizationScope: "companion_read_only",
                    logTail: CompanionStatusLogTailState(
                        visible: 1,
                        total: 1,
                        entries: [
                            CompanionStatusLogEntryState(
                                eventType: "state_update",
                                source: "image_jobs",
                                jobID: "image-job-unknown-time",
                                requestID: "request-ui",
                                modelID: "melix-dev-image",
                                operation: "image_generate",
                                state: "queued",
                                lane: "background",
                                workerID: "",
                                progressStage: "queued",
                                updatedAtUnixMS: 0,
                                failureCode: "",
                                redactionSummary: "raw log line omitted"
                            )
                        ]
                    ),
                    redactionLogs: ""
                )
            )
        )
        #expect(unknownTimePresentation.statusTitle == "Companion status loaded")
        #expect(unknownTimePresentation.logRows.first?.timeText == "unknown")

        let failureStatus = CompanionStatusState.failed("Companion status refresh failed: gateway offline")
        let failurePresentation = DesktopAPICompanionStatusPresentation(status: failureStatus)
        #expect(failurePresentation.statusTitle == "Companion status needs attention")
        #expect(failurePresentation.errorText == "Companion status refresh failed: gateway offline")
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
            effectivePort: 12_436,
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
        #expect(openAIGroup.snippets.contains { $0.body.contains("http://127.0.0.1:12436/v1") })
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
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            healthState: .runtimeReady,
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

        _ = hostView(
            DesktopAPIQuickStartPanel(
                foundation: emptyFoundation,
                selectedSession: nil
            )
        )
        _ = hostView(
            DesktopAPIQuickStartPanel(
                foundation: emptyFoundation,
                selectedSession: session
            )
        )
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
                == "Select a provider to render auth guidance."
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

        _ = hostView(DesktopServerGatewayAccessSummaryView(session: session))
        #expect(session.sharedAccessSummaryText.contains("enabled"))
        #expect(session.persistentSessionSummaryText.contains("2 remembered sessions active"))
        #expect(session.lastAuthSessionSignOutLatencyMs == 14)
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

    @Test("dashboard residency rows render model metadata load trust receipts")
    @MainActor
    func dashboardResidencyRowsRenderModelMetadataLoadTrustReceipts() throws {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-remote-code"
        model.kind = "text"
        model.state = .modelWarm
        model.settings.alias = "Remote Code Model"
        model.settings.loadTrustMode = .modelLoadTrustTrustRemoteCode
        var loadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        loadTrust.requestedMode = .modelLoadTrustTrustRemoteCode
        loadTrust.effectiveMode = .modelLoadTrustDefaultSafe
        loadTrust.customLoaderRequired = true
        loadTrust.customLoaderDetectionSource = "model-config-auto-map"
        loadTrust.blockReason = "remote code trust is not enabled"
        loadTrust.requiresReloadForTrustChange = true
        model.loadTrust = loadTrust
        var capabilityReceipt = Melix_Controlplane_V1_ModelCapabilityReceipt()
        capabilityReceipt.schemaVersion = "melix.model_capabilities.v1"
        var completionReceipt = Melix_Controlplane_V1_TaskCapabilityReceipt()
        completionReceipt.capability = "completion"
        completionReceipt.state = .capabilitySupported
        completionReceipt.provenance = "model catalog"
        capabilityReceipt.tasks = [completionReceipt]
        model.capabilityReceipt = capabilityReceipt
        snapshot.models = [model]

        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Snapshot hydrated",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-load-trust",
            features: ["models"],
            productUpdateSummary: nil,
            productUpdateDetail: nil,
            lastError: nil,
            recentEvents: []
        )
        let view = hostView(DesktopDashboardTabView(foundation: foundation))
        let row = try #require(foundation.models.first)

        #expect(view.subviews.isEmpty == false)
        #expect(row.loadTrustReceiptRows.contains("requested Trust Remote Code • effective Default Safe"))
        #expect(row.loadTrustReceiptRows.contains("custom loader Required • model-config-auto-map"))
        #expect(row.loadTrustReceiptRows.contains("blocked remote code trust is not enabled"))
        #expect(row.loadTrustReceiptRows.contains("Reload Required"))
        #expect(
            row.loadTrustReceiptRows.contains(
                "guidance unload and reload this model to apply Trust Remote Code; active runtime is Default Safe"
            )
        )
        #expect(row.capabilityReceiptRows.contains("task completion: supported • model catalog"))
    }

    @Test("dashboard residency rows suppress load trust reload guidance when not needed")
    @MainActor
    func dashboardResidencyRowsSuppressLoadTrustReloadGuidanceWhenNotNeeded() throws {
        var absentModel = Melix_Controlplane_V1_ModelSummary()
        absentModel.modelID = "melix-no-trust"
        absentModel.kind = "text"
        absentModel.state = .modelWarm

        var noReloadModel = Melix_Controlplane_V1_ModelSummary()
        noReloadModel.modelID = "melix-no-reload"
        noReloadModel.kind = "text"
        noReloadModel.state = .modelWarm
        noReloadModel.settings.loadTrustMode = .modelLoadTrustTrustRemoteCode
        var noReloadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        noReloadTrust.requestedMode = .modelLoadTrustTrustRemoteCode
        noReloadTrust.effectiveMode = .modelLoadTrustDefaultSafe
        noReloadModel.loadTrust = noReloadTrust

        var alreadyEffectiveModel = Melix_Controlplane_V1_ModelSummary()
        alreadyEffectiveModel.modelID = "melix-trust-applied"
        alreadyEffectiveModel.kind = "text"
        alreadyEffectiveModel.state = .modelWarm
        alreadyEffectiveModel.settings.loadTrustMode = .modelLoadTrustTrustRemoteCode
        var alreadyEffectiveTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        alreadyEffectiveTrust.requestedMode = .modelLoadTrustTrustRemoteCode
        alreadyEffectiveTrust.effectiveMode = .modelLoadTrustTrustRemoteCode
        alreadyEffectiveTrust.requiresReloadForTrustChange = true
        alreadyEffectiveModel.loadTrust = alreadyEffectiveTrust

        #expect(makeRuntimeModelRow(absentModel).loadTrustReceiptRows.isEmpty)
        #expect(makeRuntimeModelRow(noReloadModel).loadTrustReceiptRows.contains { $0.hasPrefix("guidance ") } == false)
        #expect(makeRuntimeModelRow(alreadyEffectiveModel).loadTrustReceiptRows.contains { $0.hasPrefix("guidance ") } == false)
    }

    @Test("models workspace wires model load trust opt-in controls")
    @MainActor
    func modelsWorkspaceWiresModelLoadTrustOptInControls() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-remote-code"
        model.kind = "text"
        model.state = .modelWarm
        model.settings.alias = "Remote Code Model"
        var loadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        loadTrust.requestedMode = .modelLoadTrustTrustRemoteCode
        loadTrust.effectiveMode = .modelLoadTrustDefaultSafe
        model.loadTrust = loadTrust
        snapshot.models = [model]

        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        let view = hostView(
            tab
        )

        #expect(view.subviews.isEmpty == false)

        tab.trustRemoteCodeForPrimaryModelAction()()
        try await waitForDesktopFoundationCondition("trust opt-in dispatched") {
            viewModel.modelSettingsLoadTrustModeText == "Trust Remote Code"
        }
        var updates = await client.recordedModelSettingsUpdates
        #expect(updates.last?.values["load_trust_mode"] == "trust_remote_code")

        tab.clearPrimaryModelLoadTrustOverrideAction()()
        try await waitForDesktopFoundationCondition("trust clear dispatched") {
            viewModel.modelSettingsLoadTrustModeText == "Unspecified"
        }
        updates = await client.recordedModelSettingsUpdates
        #expect(updates.last?.values["load_trust_mode"] == "")
    }

    @Test("model detail renders requested and effective load trust modes")
    @MainActor
    func modelDetailRendersRequestedAndEffectiveLoadTrustModes() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-remote-code"
        model.kind = "text"
        model.state = .modelWarm
        model.settings.alias = "Remote Code Model"
        var loadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        loadTrust.requestedMode = .modelLoadTrustTrustRemoteCode
        loadTrust.effectiveMode = .modelLoadTrustDefaultSafe
        model.loadTrust = loadTrust
        snapshot.models = [model]

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 4096
        info.supportedParsers = ["text"]
        info.supportedModalities = ["text"]

        await client.configureSnapshot(snapshot)
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.inspectPrimaryModel()

        let selectedInfo = try #require(viewModel.selectedModelInfo)
        let content = desktopModelInfoSummaryContent(selectedInfo)

        #expect(selectedInfo.requestedLoadTrustModeText == "Trust Remote Code")
        #expect(selectedInfo.effectiveLoadTrustModeText == "Default Safe")
        #expect(content.detailLines.contains("requested trust mode: Trust Remote Code"))
        #expect(content.detailLines.contains("effective trust mode: Default Safe"))
    }

    @Test("model detail maps all load trust mode labels")
    @MainActor
    func modelDetailMapsAllLoadTrustModeLabels() async throws {
        let unrecognized = try #require(Melix_Controlplane_V1_ModelLoadTrustMode(rawValue: 99))
        let cases: [(String, Melix_Controlplane_V1_ModelLoadTrustMode?, String)] = [
            ("absent", nil, ""),
            ("default-safe", .modelLoadTrustDefaultSafe, "Default Safe"),
            ("trust-remote-code", .modelLoadTrustTrustRemoteCode, "Trust Remote Code"),
            ("not-applicable", .modelLoadTrustNotApplicable, "Not Applicable"),
            ("unspecified", .unspecified, "Unspecified"),
            ("unrecognized", unrecognized, "Unrecognized 99"),
        ]

        for (suffix, mode, expectedText) in cases {
            let client = FakeControlPlaneXPCClient()
            var snapshot = Melix_Controlplane_V1_ServerSnapshot()
            snapshot.serverState = .serverReady

            let modelID = "melix-load-trust-\(suffix)"
            var model = Melix_Controlplane_V1_ModelSummary()
            model.modelID = modelID
            model.kind = "text"
            model.state = .modelWarm
            if let mode {
                var loadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
                loadTrust.requestedMode = mode
                loadTrust.effectiveMode = mode
                model.loadTrust = loadTrust
            }
            snapshot.models = [model]

            var info = Melix_Controlplane_V1_ModelInfo()
            info.ok = true
            info.modelKind = "text"
            info.maxContext = 4096
            info.supportedParsers = ["text"]
            info.supportedModalities = ["text"]

            await client.configureSnapshot(snapshot)
            await client.configureModelInfo(info)

            let viewModel = RuntimeViewModel(client: client)
            await viewModel.start()
            await viewModel.fetchModelInfo(modelID: modelID)

            #expect(viewModel.selectedModelInfo?.requestedLoadTrustModeText == expectedText)
            #expect(viewModel.selectedModelInfo?.effectiveLoadTrustModeText == expectedText)
        }
    }

    @Test("model detail renders load trust custom loader block and reload markers")
    @MainActor
    func modelDetailRendersLoadTrustCustomLoaderBlockAndReloadMarkers() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-custom-loader"
        model.kind = "text"
        model.state = .modelWarm
        model.settings.loadTrustMode = .modelLoadTrustTrustRemoteCode
        var loadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        loadTrust.requestedMode = .modelLoadTrustTrustRemoteCode
        loadTrust.effectiveMode = .modelLoadTrustDefaultSafe
        loadTrust.customLoaderRequired = true
        loadTrust.customLoaderDetectionSource = "model-config-auto-map"
        loadTrust.blockReason = "remote code trust is not enabled"
        loadTrust.requiresReloadForTrustChange = true
        model.loadTrust = loadTrust
        snapshot.models = [model]

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 4096
        info.supportedParsers = ["text"]
        info.supportedModalities = ["text"]

        await client.configureSnapshot(snapshot)
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.fetchModelInfo(modelID: "melix-custom-loader")

        let selectedInfo = try #require(viewModel.selectedModelInfo)
        let content = desktopModelInfoSummaryContent(selectedInfo)

        #expect(selectedInfo.loadTrustCustomLoaderText == "Required • model-config-auto-map")
        #expect(selectedInfo.loadTrustBlockReasonText == "remote code trust is not enabled")
        #expect(selectedInfo.loadTrustReloadRequiredText == "Reload Required")
        #expect(
            selectedInfo.loadTrustRuntimeGuidanceText
                == "Unload and reload this model to apply Trust Remote Code; active runtime is Default Safe."
        )
        #expect(content.detailLines.contains("custom loader: Required • model-config-auto-map"))
        #expect(content.detailLines.contains("trust block reason: remote code trust is not enabled"))
        #expect(content.detailLines.contains("trust reload: Reload Required"))
        #expect(
            content.detailLines.contains(
                "trust guidance: Unload and reload this model to apply Trust Remote Code; active runtime is Default Safe."
            )
        )
    }

    @Test("model detail maps custom loader detection edge labels")
    @MainActor
    func modelDetailMapsCustomLoaderDetectionEdgeLabels() async throws {
        let cases: [(String, Bool, String, String)] = [
            ("required-no-source", true, "   ", "Required"),
            ("not-required-source", false, "metadata-scan", "Not Required • metadata-scan"),
        ]

        for (suffix, customLoaderRequired, detectionSource, expectedText) in cases {
            let client = FakeControlPlaneXPCClient()
            var snapshot = Melix_Controlplane_V1_ServerSnapshot()
            snapshot.serverState = .serverReady

            let modelID = "melix-custom-loader-\(suffix)"
            var model = Melix_Controlplane_V1_ModelSummary()
            model.modelID = modelID
            model.kind = "text"
            model.state = .modelWarm
            var loadTrust = Melix_Controlplane_V1_ModelLoadTrustPolicy()
            loadTrust.requestedMode = .modelLoadTrustDefaultSafe
            loadTrust.effectiveMode = .modelLoadTrustDefaultSafe
            loadTrust.customLoaderRequired = customLoaderRequired
            loadTrust.customLoaderDetectionSource = detectionSource
            model.loadTrust = loadTrust
            snapshot.models = [model]

            var info = Melix_Controlplane_V1_ModelInfo()
            info.ok = true
            info.modelKind = "text"
            info.maxContext = 4096
            info.supportedParsers = ["text"]
            info.supportedModalities = ["text"]

            await client.configureSnapshot(snapshot)
            await client.configureModelInfo(info)

            let viewModel = RuntimeViewModel(client: client)
            await viewModel.start()
            await viewModel.fetchModelInfo(modelID: modelID)

            #expect(viewModel.selectedModelInfo?.loadTrustCustomLoaderText == expectedText)
        }
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
            capabilityReceiptRows: [
                "task completion: supported • model catalog",
                "task embedding: supported • model catalog",
                "task vision: supported • vision metadata",
                "task tools: supported • tool parser metadata",
                "task reasoning: supported • reasoning policy",
                "task insert: supported • tokenizer metadata",
            ],
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
        #expect(content.detailLines.contains("capability task completion: supported • model catalog"))
        #expect(content.detailLines.contains("capability task embedding: supported • model catalog"))
        #expect(content.detailLines.contains("capability task vision: supported • vision metadata"))
        #expect(content.detailLines.contains("capability task tools: supported • tool parser metadata"))
        #expect(content.detailLines.contains("capability task reasoning: supported • reasoning policy"))
        #expect(content.detailLines.contains("capability task insert: supported • tokenizer metadata"))
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
        var snapshot = makeAudioSetupSnapshot(
            models: [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
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
        #expect(actions.contains("info:\(desktopTestReadyModelID)"))
        #expect(actions.contains("operation:registry_snapshot:\(desktopTestReadyModelID)"))
        #expect(actions.contains("doctor"))
        #expect(actions.contains("bench"))
        #expect(actions.contains("operation:convert:\(desktopTestReadyModelID)"))
        #expect(actions.contains("operation:quantize:\(desktopTestReadyModelID)"))
        #expect(actions.contains("operation:train_lora:\(desktopTestReadyModelID)"))
        #expect(actions.contains("operation:activate_adapter:\(desktopTestReadyModelID)"))
        #expect(actions.contains("operation:download:\(desktopTestReadyModelID)"))
        #expect(actions.contains("operation:upload:\(desktopTestReadyModelID)"))
        #expect(viewModel.selectedModelInfo?.modelID == desktopTestReadyModelID)
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
        derivedModel.settings.ext["melix.memory_fit.benchmark.status"] = "heavy"
        derivedModel.settings.ext["melix.memory_fit.benchmark.reason"] = "Benchmark KV cache may exceed comfort budget."
        derivedModel.settings.ext["melix.memory_fit.benchmark.estimated_active_memory_bytes"] = "34359738368"
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
        let renderedTexts = renderedTextValues(in: view)
        let selectedRunIndex = try #require(renderedTexts.firstIndex(where: { $0.contains("Selected run ") }))
        let configIndex = try #require(renderedTexts.firstIndex(of: "Start New Provider..."))

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .benchmark)
        #expect(selectedRunIndex < configIndex)
        #expect(viewModel.benchmarkHistory.count == 3)
        #expect(viewModel.selectedBenchmarkHistoryEntry?.profileSummaryText == "Profile: Throughput")
        #expect(renderedTexts.contains("Profile: Throughput"))
        #expect(renderedTexts.contains { $0.contains("Memory fit: Heavy - Benchmark KV cache may exceed comfort budget.") })
        #expect(viewModel.benchmarkMetricCards.isEmpty == false)
        #expect(viewModel.benchmarkChartPoints.count == 2)
    }

    @Test("diagnostics uses report-first section titles across stages")
    @MainActor
    func diagnosticsUsesReportFirstSectionTitlesAcrossStages() async throws {
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
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        await viewModel.refreshBenchmarkHistory()

        let benchmarkView = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1800)
        )
        let benchmarkTexts = renderedTextValues(in: benchmarkView)
        #expect(benchmarkTexts.contains("Bench Report"))
        #expect(benchmarkTexts.contains("Benchmark Snapshot") == false)
        #expect(benchmarkTexts.contains("Benchmark Results") == false)

        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.preferredDiagnosticsStage = .matrix
        let matrixView = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1800)
        )
        let matrixTexts = renderedTextValues(in: matrixView)
        #expect(matrixTexts.contains("Matrix Report"))
        #expect(matrixTexts.contains("Matrix Snapshot") == false)
        #expect(matrixTexts.contains("Matrix Results") == false)

        viewModel.preferredDiagnosticsStage = .evaluation
        let evaluationView = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1800)
        )
        let evaluationTexts = renderedTextValues(in: evaluationView)
        #expect(evaluationTexts.contains("Evaluation Report"))
        #expect(evaluationTexts.contains("Evaluation Snapshot") == false)
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
        let selectedRunIndex = try #require(renderedTexts.firstIndex(where: { $0.contains("Selected matrix run ") }))
        let configIndex = try #require(renderedTexts.firstIndex(of: "Start New Provider..."))

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .matrix)
        #expect(selectedRunIndex < configIndex)
        #expect(renderedTexts.contains("Benchmark"))
        #expect(renderedTexts.contains("Matrix"))
        #expect(renderedTexts.contains("Evaluation"))
        #expect(renderedTexts.contains("Requests"))
        #expect(renderedTexts.contains("Duration"))
        #expect(viewModel.benchmarkMatrixHistory.count == 2)
        #expect(viewModel.selectedBenchmarkMatrixHistoryEntry?.profileSummaryText == "Profile: Low Memory")
        #expect(renderedTexts.contains("Profile: Low Memory"))
        #expect(viewModel.benchmarkMatrixSummaryRows.count == 2)
        #expect(viewModel.benchmarkMatrixSummaryRows.contains { $0.configurationSummary.contains("Low Memory") })
        #expect(viewModel.benchmarkMatrixContextChartPoints.count == 2)
        #expect(viewModel.benchmarkMatrixThroughputChartPoints.count == 2)
    }

    @Test("diagnostics tool section action helpers dispatch benchmark operations and render exported state")
    @MainActor
    func diagnosticsToolSectionActionHelpersDispatchBenchmarkOperations() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
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
        #expect(actions.contains("info:\(desktopTestReadyModelID)"))
        #expect(actions.contains("doctor"))
        #expect(actions.contains("bench"))
        #expect(actions.contains("eval"))
        #expect(actions.contains("bench.export"))
        #expect(actions.contains("operation:registry_snapshot:\(desktopTestReadyModelID)"))
        #expect(viewModel.lastBenchmarkCSVExport?.rowCount == 3)
        #expect(viewModel.lastEvaluationExport?.rowCount == 2)
        #expect(viewModel.selectedBenchmarkHistoryJobID == "bench-older")
        #expect(viewModel.selectedEvaluationHistoryJobID == "eval-newer")
        #expect(viewModel.selectedBenchmarkSuiteIDs.contains("latency"))
    }

    @Test("diagnostics evaluation renders CLI workflow failures inline")
    @MainActor
    func diagnosticsEvaluationRendersCLIWorkflowFailuresInline() async throws {
        let client = FakeControlPlaneXPCClient()
        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        await workflowRunner.configureHandler { command in
            switch command {
            case .evalRun:
                return .failure(
                    .processFailed(
                        commandID: "eval.run",
                        surface: .subprocess,
                        exitCode: 2,
                        stderr: "dataset top200.event-extraction.top20.v1 was not found"
                    )
                )
            default:
                return .success("{}\n")
            }
        }
        let viewModel = RuntimeViewModel(
            client: client,
            cliWorkflowRunner: workflowRunner
        )
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.preferredDiagnosticsStage = .evaluation

        await viewModel.runEvaluation()

        let view = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1800)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(renderedTexts.contains("Evaluation Command Failed"))
        #expect(renderedTexts.contains { $0.contains("eval.run") })
        #expect(renderedTexts.contains { $0.contains("dataset top200.event-extraction.top20.v1 was not found") })
    }

    @Test("workspace diagnostics renders evaluation compare controls")
    @MainActor
    func workspaceDiagnosticsRendersEvaluationCompareControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let derivedModel = makeMenuBarModelSummary(modelID: desktopTestReadyLoRAModelID, state: .modelWarm)
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
                derivedModel,
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedEvaluationMode = .compare

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .evaluation)
        #expect(renderedTexts.contains("Compare"))
        #expect(renderedTexts.contains("multiple_choice_accuracy"))
        #expect(renderedTexts.contains("sandboxed"))
        #expect(viewModel.evaluationCompareTargetModels.map(\.modelID) == [desktopTestReadyLoRAModelID])
    }

    @Test("diagnostics tool section runComparison helper dispatches compare parameters through shared state")
    @MainActor
    func diagnosticsToolSectionRunComparisonDispatchesCompareParameters() async throws {
        let client = FakeControlPlaneXPCClient()
        let derivedModel = makeMenuBarModelSummary(modelID: desktopTestReadyLoRAModelID, state: .modelWarm)
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
                derivedModel,
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectedEvaluationModelID = desktopTestReadyModelID
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        viewModel.selectedEvaluationCompareTargetModelIDs = [desktopTestReadyLoRAModelID]
        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )

        await section.runEvaluationCompare()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(viewModel.selectedEvaluationMode == .compare)
        #expect(request.modelID == desktopTestReadyModelID)
        #expect(request.parameters["compare_mode"] == "base_vs_targets")
        #expect(request.parameters["compare_target_model_ids"] == desktopTestReadyLoRAModelID)
    }

    @Test("diagnostics tool section runComparison helper requires an explicit compare target")
    @MainActor
    func diagnosticsToolSectionRunComparisonRequiresExplicitTarget() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )

        await section.runEvaluationCompare()

        #expect(viewModel.selectedEvaluationMode == .compare)
        #expect(viewModel.lastError == "Select at least one compare target model before running Evaluation Compare.")
        #expect(await client.recordedEvaluationRequests.isEmpty)
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
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
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

    @Test("diagnostics tool section does not render hub repository benchmark targets")
    @MainActor
    func diagnosticsToolSectionDoesNotRenderHubRepositoryBenchmarkTargets() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)

        let section = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        let view = hostView(section)
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Hugging Face Repo") == false)
        #expect(viewModel.benchmarkTargetSummaryText.contains("unsloth/gemma-4-E4B-it-MLX-8bit") == false)
    }

    @Test("workspace diagnostics renders canonical benchmark and evaluation controls")
    @MainActor
    func workspaceDiagnosticsRendersCanonicalBenchmarkAndEvaluationControls() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .benchmark)
        #expect(renderedTexts.contains("Benchmark"))
        #expect(renderedTexts.contains("Matrix"))
        #expect(renderedTexts.contains("Evaluation"))
        #expect(renderedTexts.contains("Primary Provider"))
        #expect(renderedTexts.contains("Catalog Model") == false)
        #expect(renderedTexts.contains("Hugging Face Repo") == false)
        #expect(renderedTexts.contains("3"))
        #expect(renderedTexts.contains("Partial Prefix"))
        #expect(renderedTexts.contains("Enabled"))
        #expect(renderedTexts.contains("Json Schema"))
        #expect(renderedTexts.contains("multiple_choice_accuracy") == false)
        #expect(renderedTexts.contains("sandboxed") == false)

    }

    @Test("workspace diagnostics renders matrix duration budget input")
    @MainActor
    func workspaceDiagnosticsRendersMatrixDurationBudgetInput() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.preferredDiagnosticsStage = .matrix
        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkMatrixLoadBudgetMode = .durationSeconds
        viewModel.benchMatrixDurationSeconds = "45"

        let view = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1800)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .matrix)
        #expect(renderedTexts.contains("Matrix Configuration"))
        #expect(renderedTexts.contains("Duration"))
        #expect(renderedTexts.contains("45"))
        #expect(viewModel.selectedBenchmarkMatrixLoadBudgetMode == .durationSeconds)
        #expect(viewModel.benchMatrixDurationSeconds == "45")
    }

    @Test("workspace diagnostics renders Hugging Face evaluation dataset fields")
    @MainActor
    func workspaceDiagnosticsRendersHuggingFaceEvaluationDatasetFields() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeAudioSetupSnapshot(
            models: [
                ModelCatalog.devTextModel(),
                makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm),
            ]
        )
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.preferredDiagnosticsStage = .evaluation
        viewModel.evaluationDatasetSourceKind = .huggingFaceDataset
        viewModel.evaluationHFDatasetPath = "HuggingFaceH4/ultrachat_200k"
        viewModel.evaluationHFDatasetName = "train_sft"
        viewModel.evaluationHFDatasetRevision = "main"
        viewModel.evaluationHFDatasetSplit = "train"
        viewModel.evaluationFieldSystemPath = "messages[0].content"
        viewModel.evaluationFieldInputTextPath = "messages[-1].content"
        viewModel.evaluationFieldTargetPath = "answer"
        viewModel.evaluationFieldSampleIDPath = "id"
        viewModel.evaluationResultKind = "json"
        viewModel.evaluationExtractionMode = "json_path"
        viewModel.evaluationThreshold = "0.75"
        viewModel.evaluationOutputSchemaJSON = "{\"type\":\"object\"}"
        viewModel.evaluationIgnoredPaths = "metadata.debug"

        let view = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 2200)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .evaluation)
        #expect(viewModel.evaluationDatasetSourceKind == .huggingFaceDataset)
        #expect(renderedTexts.contains("HuggingFaceH4/ultrachat_200k"))
        #expect(renderedTexts.contains("train_sft"))
        #expect(renderedTexts.contains("messages[-1].content"))
        #expect(renderedTexts.contains("json_path"))
        #expect(renderedTexts.contains("0.75"))
    }

    @Test("diagnostics capability refusals are visible before worker dispatch")
    @MainActor
    func diagnosticsCapabilityRefusalsAreVisibleBeforeWorkerDispatch() async throws {
        var model = makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)
        var capabilityReceipt = Melix_Controlplane_V1_ModelCapabilityReceipt()
        var completion = Melix_Controlplane_V1_TaskCapabilityReceipt()
        completion.capability = "completion"
        completion.state = .capabilityUnsupported
        completion.unsupportedReason = .unsupportedReasonUnsupportedTask
        completion.recoveryHint = "Select a completion-capable model."
        completion.provenance = "model catalog"
        capabilityReceipt.tasks = [completion]
        model.capabilityReceipt = capabilityReceipt

        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [model]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        let benchmarkReason = "Benchmark is unavailable for \(desktopTestReadyModelID): completion capability is unsupported • reason unsupported task • recovery Select a completion-capable model."
        let benchmarkView = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1_280, height: 1_800)
        )
        let benchmarkTexts = renderedTextValues(in: benchmarkView)

        #expect(viewModel.diagnosticsBenchmarkUnavailableText == benchmarkReason)
        #expect(benchmarkTexts.contains(benchmarkReason))
        await viewModel.runBench()
        #expect(await client.recordedBenchRequests.isEmpty)
        #expect(viewModel.lastError == benchmarkReason)

        viewModel.preferredDiagnosticsStage = .evaluation
        let evaluationReason = "Evaluation is unavailable for \(desktopTestReadyModelID): completion capability is unsupported • reason unsupported task • recovery Select a completion-capable model."
        let evaluationView = hostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1_280, height: 1_800)
        )
        let evaluationTexts = renderedTextValues(in: evaluationView)

        #expect(viewModel.diagnosticsEvaluationUnavailableText == evaluationReason)
        #expect(evaluationTexts.contains(evaluationReason))
        await viewModel.runEvaluation()
        #expect(await client.recordedEvaluationRequests.isEmpty)
        #expect(viewModel.lastError == evaluationReason)
    }

    @Test("workspace diagnostics renders evaluation configuration history and sample previews")
    @MainActor
    func workspaceDiagnosticsRendersEvaluationConfigurationHistoryAndSamples() async throws {
        let client = FakeControlPlaneXPCClient()
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = "melix-dev-text-lora"
        derivedModel.settings.ext["melix.memory_fit.eval.status"] = "good"
        derivedModel.settings.ext["melix.memory_fit.eval.reason"] = "Eval sample size fits available memory."
        derivedModel.settings.ext["melix.memory_fit.eval.total_unified_memory_bytes"] = "68719476736"
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
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        await viewModel.refreshEvaluationHistory()

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)
        let selectedEvalIndex = try #require(renderedTexts.firstIndex(where: { $0.contains("Selected eval ") }))
        let configIndex = try #require(renderedTexts.firstIndex(of: "Start New Provider..."))

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .evaluation)
        #expect(selectedEvalIndex < configIndex)
        #expect(renderedTexts.contains("Compare"))
        #expect(renderedTexts.contains("multiple_choice_accuracy"))
        #expect(renderedTexts.contains("sandboxed"))
        #expect(renderedTexts.contains { $0.contains("Memory fit: Good - Eval sample size fits available memory.") })
        #expect(viewModel.evaluationHistory.count == 1)
        #expect(viewModel.evaluationMetricCards.count == 1)
        #expect(viewModel.evaluationSamplePreview.count == 2)
    }

    @Test("workspace diagnostics renders semantic judge controls")
    @MainActor
    func workspaceDiagnosticsRendersSemanticJudgeControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let remoteStore = FakeRemoteServerStore(
            servers: [
                RemoteServer(
                    id: "judge",
                    title: "Judge",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: "https://judge.example/v1",
                    defaultModelID: "judge-default",
                    timeoutSeconds: 41,
                    rateLimitPerMinute: 12,
                    credentialRef: RemoteServerStore.credentialRef(for: "judge"),
                    apiKeyHint: "sk-j...udge"
                ),
            ]
        )
        let viewModel = RuntimeViewModel(
            client: client,
            remoteServerStore: remoteStore
        )
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedEvaluationSuiteIDs = ["event_extraction"]
        viewModel.evaluationScoringMode = "event_extraction_weighted_f1"
        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "judge"
        viewModel.evaluationSemanticJudgeModelID = "judge-model"
        viewModel.preferredDiagnosticsStage = .evaluation

        let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopDiagnosticsToolSectionView.initialStage(for: viewModel) == .evaluation)
        #expect(renderedTexts.contains("Judge • judge"))
        #expect(renderedTexts.contains("judge-model"))
    }

    @Test("evaluation metric card view renders statistical evidence lines")
    @MainActor
    func evaluationMetricCardViewRendersStatisticalEvidenceLines() async throws {
        let metric = RuntimeEvaluationMetricCardState(
            id: "metric-1",
            suiteTitle: "MMLU",
            metricName: "eval.compare.delta_accuracy",
            metricLabel: "Delta Accuracy",
            value: 0.25,
            valueText: "0.25",
            unit: "score",
            verdictText: "improvement",
            thresholdText: "0.1000",
            bootstrapCIText: "[+0.1200, +0.4100]",
            analyticalCIText: "[+0.1000, +0.3800]"
        )

        let view = DesktopEvaluationMetricCardView(metric: metric)
        _ = view.body

        #expect(
            view.evidenceLines == [
                "Verdict: improvement",
                "Threshold: 0.1000",
                "Bootstrap CI: [+0.1200, +0.4100]",
                "Analytical CI: [+0.1000, +0.3800]",
            ]
        )
    }

    @Test("evaluation sample preview card view renders category and subject labels")
    @MainActor
    func evaluationSamplePreviewCardViewRendersCategoryAndSubjectLabels() async throws {
        let sample = RuntimeEvaluationSamplePreviewState(
            id: "sample-1",
            sampleID: "mmlu-0001",
            inputText: "What is 2 + 2?",
            target: "4",
            extractedResult: "4",
            rawResponse: "4",
            typedScoreText: "1.0000",
            statusText: "validated • extracted",
            timeText: "0.42s",
            categoryLabel: "math",
            subjectLabel: "arithmetic"
        )

        let view = DesktopEvaluationSamplePreviewCardView(sample: sample)
        _ = view.body

        #expect(view.categoryAndSubjectText == "math • arithmetic")
    }

    @Test("workspace diagnostics covers evaluation helper actions and running server configuration")
    @MainActor
    func workspaceDiagnosticsCoversEvaluationHelperActionsAndRunningServerConfiguration() async throws {
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

        let hosted = hostView(DesktopWorkspaceShellView(viewModel: viewModel))

        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.evaluationTargetSummaryText.contains("unsloth/gemma-4-E4B-it-MLX-8bit") == false)
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

    @Test("tools workspace renders grouped lora experiment recommendations")
    @MainActor
    func toolsWorkspaceRendersGroupedLoraExperimentRecommendations() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeExperimentGroupRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        let group = try #require(viewModel.loraExperimentGroups.first)
        let view = hostView(DesktopTrainingToolSectionView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(group.title == "nightly-qwen35")
        #expect(group.runCount == 2)
        #expect(group.latestPresetTitle == "Balanced Adapter")
        #expect(group.experimentSummaryText == "2 checkpoints • resume ready")
        #expect(group.performanceSummaryText == "128.5 tok/s • 5.25 GB peak")
        #expect(group.recommendedManifestPath == "/tmp/melix-train-lora/train_lora.adapter.json")
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

    @Test("workflow recipes surface renders compact inputs and variable rows")
    @MainActor
    func workflowRecipesSurfaceRendersCompactInputsAndVariableRows() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()
        viewModel.updateWorkflowRecipeTaskFilter("training")
        viewModel.updateWorkflowRecipeURIInspectDraft("hf://datasets/melix/train")
        viewModel.updateWorkflowRecipeInitTaskDraft("train-lora")
        viewModel.updateWorkflowRecipeSetKeyDraft("dataset_uri")
        viewModel.updateWorkflowRecipeSetValueDraft("hf://datasets/melix/train")
        viewModel.addWorkflowRecipeSetDraft()
        viewModel.updateWorkflowRecipePlanOutputPathDraft("/tmp/melix-plan/pipeline.json")
        viewModel.updateWorkflowRecipeApplyFromStepDraft("train")
        viewModel.applyWorkflowRecipeCatalog(
            RuntimeWorkflowRecipeCatalogState(
                schemaVersion: "workflow.recipes.v1",
                recipes: [
                    RuntimeWorkflowRecipeSummaryState(
                        id: "train-lora",
                        version: "1.0",
                        title: "Train LoRA",
                        tasks: ["training"],
                        digest: "sha256:recipe"
                    ),
                ],
                metrics: []
            )
        )
        let candidate = RuntimeWorkflowURICandidateState(
            id: "candidate-1",
            kind: "dataset",
            sourceKind: "hugging_face",
            taskKind: "training",
            confidence: 0.95,
            normalizedLocator: "hf://datasets/melix/train",
            repoID: "melix/train",
            revision: "main",
            reasons: ["dataset card matched"],
            warnings: ["requires network"],
            recommendedNextAction: "Preview Recipe Init",
            generatedCommandArguments: ["melix", "workflow", "init", "--task", "training"]
        )
        let inspection = RuntimeWorkflowURIInspectionState(
            schemaVersion: "workflow.uri.inspect.v1",
            originalURI: "hf://datasets/melix/train",
            normalizedLocator: "hf://datasets/melix/train",
            candidateCount: 1,
            ambiguityCount: 0,
            candidates: [candidate],
            metrics: []
        )
        let detail = RuntimeWorkflowRecipeDetailState(
            id: "train-lora",
            schemaVersion: "workflow.recipe.v1",
            version: "1.0",
            title: "Train LoRA",
            description: "Train an adapter from a dataset URI.",
            tasks: ["training"],
            digest: "sha256:recipe",
            inputRows: [
                RuntimeWorkflowRecipeInputRowState(
                    name: "dataset_uri",
                    valueType: "uri",
                    required: true,
                    defaultValueText: "",
                    uriKind: "dataset"
                ),
            ],
            preflightRows: [RuntimeWorkflowRecipeKeyValueRowState(name: "model", valueText: "available")],
            pipelineSteps: [
                RuntimeWorkflowRecipePipelineStepState(
                    id: "train",
                    command: "melix lora train",
                    argumentSummaryText: "--dataset hf://datasets/melix/train"
                ),
            ],
            outputRows: [RuntimeWorkflowRecipeKeyValueRowState(name: "adapter", valueText: "manifest")]
        )
        viewModel.applyWorkflowRecipeURIInspection(inspection)
        viewModel.applyWorkflowRecipeInitPreview(
            RuntimeWorkflowRecipeInitPreviewState(
                recipe: detail,
                source: "uri",
                sourceURIDigest: "sha256:uri",
                inspection: inspection,
                provenanceRows: [RuntimeWorkflowRecipeKeyValueRowState(name: "source", valueText: "uri")]
            )
        )
        viewModel.applyWorkflowRecipePlan(
            RuntimeWorkflowRecipePlanState(
                schemaVersion: "workflow.plan.v1",
                recipeID: "train-lora",
                recipeVersion: "1.0",
                recipeDigest: "sha256:recipe",
                pipelineSchemaVersion: "pipeline.v1",
                pipelineJSONText: "{\"steps\":[\"train\"]}",
                pipelineSteps: detail.pipelineSteps,
                artifactRows: [RuntimeWorkflowRecipeArtifactRowState(kind: "plan", path: "/tmp/melix-plan/pipeline.json")],
                metrics: [RuntimeWorkflowRecipeMetricState(name: "steps", valueText: "1")]
            )
        )
        viewModel.applyWorkflowRecipeResult(
            RuntimeWorkflowRecipeApplyResultState(
                schemaVersion: "workflow.apply.v1",
                name: "Train LoRA",
                traceID: "trace-1",
                status: "dry_run",
                receiptDir: "/tmp/melix-recipe",
                summaryPath: "/tmp/melix-recipe/summary.json",
                pipelineHash: "sha256:pipeline",
                inputsHash: "sha256:inputs",
                recipeRows: [RuntimeWorkflowRecipeKeyValueRowState(name: "recipe", valueText: "train-lora")],
                stepRows: [
                    RuntimeWorkflowRecipeApplyStepRowState(
                        id: "train",
                        command: "melix lora train",
                        status: "planned",
                        receiptPath: "/tmp/melix-recipe/train.json",
                        artifactPaths: ["/tmp/melix-recipe/adapter.json"],
                        commandID: "lora.train",
                        argsHash: "sha256:args"
                    ),
                ],
                metrics: [RuntimeWorkflowRecipeMetricState(name: "duration_ms", valueText: "42")]
            )
        )

        let view = hostView(
            DesktopWorkflowRecipesToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1500, height: 2400)
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(renderedTexts.contains("training"))
        #expect(renderedTexts.contains("hf://datasets/melix/train"))
        #expect(renderedTexts.contains("train-lora"))
        #expect(renderedTexts.contains("--set dataset_uri=hf://datasets/melix/train"))
        #expect(renderedTexts.contains("/tmp/melix-plan/pipeline.json"))
        #expect(renderedTexts.contains("{\"steps\":[\"train\"]}"))
        #expect(renderedTexts.contains("trace-1"))
        #expect(renderedTexts.contains("/tmp/melix-recipe"))
    }

    @Test("synthetic dataset column editor renders compact row and add action")
    @MainActor
    func syntheticDatasetColumnEditorRendersCompactRowAndAddAction() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()
        viewModel.updateSyntheticDatasetIDDraft("melix-synthetic")
        viewModel.updateSyntheticDatasetNameDraft("Melix Synthetic")
        viewModel.updateSyntheticDatasetOutputDirDraft("/tmp/melix-synthetic")
        viewModel.updateSyntheticDatasetProviderEndpointDraft("http://127.0.0.1:12436/v1")
        viewModel.updateSyntheticDatasetModelDraft("melix-dev-text")
        viewModel.updateSyntheticDatasetColumnNameDraft("prompt")
        viewModel.updateSyntheticDatasetColumnTypeDraft("llm_text")
        viewModel.updateSyntheticDatasetColumnPayloadDraft("{\"topic\":\"ui\"}")

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        let view = hostView(section, size: CGSize(width: 1500, height: 2200))
        section.addColumnAction()

        let updatedView = hostView(
            DesktopSyntheticDatasetToolSectionView(viewModel: viewModel),
            size: CGSize(width: 1500, height: 2200)
        )
        let renderedTexts = renderedTextValues(in: updatedView)

        #expect(view.subviews.isEmpty == false)
        #expect(updatedView.subviews.isEmpty == false)
        #expect(viewModel.syntheticDatasetColumns.count == 1)
        #expect(renderedTexts.contains(where: { $0.contains("prompt:llm_text:{\"topic\":\"ui\"}") }))
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
        managedLocal.settings.ext["melix.model_path"] = "/Users/test/.melix/models/default-managed/hf/mlx-community/whisper-large-v3-turbo-asr-fp16/mlx-audio"

        await client.configureSnapshot(
            makeAudioSetupSnapshot(models: [ModelCatalog.devTextModel(), missingRuntime])
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "install_audio_runtime",
                outputPath: "/Users/test/.melix/runtime-packs/audio/melix-audio-runtime-pack/0.3.0",
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

    @Test("downloads section exposes saved lora packaging target")
    @MainActor
    func downloadsSectionExposesSavedLoRAPackagingTarget() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)
        viewModel.selectedModelOperationTargetModelID = "melix-dev-text-lora"

        let view = hostView(
            DesktopWorkspaceShellView(viewModel: viewModel),
            size: CGSize(width: 1280, height: 1000)
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.hasExplicitModelOperationTarget)
        #expect(viewModel.modelOperationTargetModelID == "melix-dev-text-lora")
        #expect(viewModel.modelOperationTargetDetailText.contains("Saved LoRA job"))
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

    @Test("downloads ingest action strip dispatches model operations")
    @MainActor
    func downloadsIngestActionStripDispatchesModelOperations() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)

        let section = DesktopDownloadsToolSectionView(viewModel: viewModel)
        let view = hostView(section, size: CGSize(width: 1280, height: 1200))

        section.quantizeModelAction()
        section.convertModelAction()
        section.downloadModelAction()
        section.uploadArtifactAction()

        let deadline = ContinuousClock.now + .seconds(2)
        while await client.recordedModelOperationRequests.count < 4, ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(10))
        }

        let operations = await client.recordedModelOperationRequests.map(\.operation)
        #expect(view.subviews.isEmpty == false)
        #expect(operations.count >= 4)
        #expect(operations.contains("quantize"))
        #expect(operations.contains("convert"))
        #expect(operations.contains("download"))
        #expect(operations.contains("upload"))
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
        let settingsSummary = DesktopSettingsTabView(foundation: foundation).accessibilitySummary
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
        #expect(settingsSummary.contains("Connection"))
        #expect(settingsSummary.contains("Connected"))
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
        try bindSelectedChatSessionToPrimaryServer(viewModel)
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
        try bindSelectedChatSessionToPrimaryServer(viewModel)
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

    @Test("chat artifact preview trigger swaps the right rail from inspector to preview")
    @MainActor
    func chatArtifactPreviewTriggerSwapsTheRightRailFromInspectorToPreview() async throws {
        #expect(
            DesktopChatArtifactPathDetector.firstPath(
                in: #"{"path":"/tmp/melix-chat/report.md"}"#
            ) == "/tmp/melix-chat/report.md"
        )
        #expect(
            DesktopChatArtifactPathDetector.firstPath(
                in: "artifact=s3://melix-runs/report.jsonl"
            ) == "s3://melix-runs/report.jsonl"
        )
        #expect(
            DesktopChatArtifactPathDetector.firstPath(
                in: #"{"path":"/tmp/melix-chat/already-sanitized.json"}"#,
                isSanitized: true
            ) == "/tmp/melix-chat/already-sanitized.json"
        )
        #expect(
            DesktopChatArtifactPathDetector.firstPath(
                in: "artifact=s3://melix-runs/report.jsonl trailing /tmp/later.md",
                isSanitized: true
            ) == "s3://melix-runs/report.jsonl"
        )
        #expect(
            DesktopChatArtifactPathDetector.firstPath(
                in: "plain status text without an artifact path"
            ) == nil
        )

        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .toolCallDelta(
                callID: "artifact-1",
                toolName: "filesystem",
                argumentsFragment: #"{"path":"/tmp/melix-chat/report.md"}"#
            ),
            .completed(finishReason: "stop", assistantText: "Report is ready.", reasoningText: ""),
        ])
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Create an artifact preview"

        await viewModel.submitChatPrompt()

        #expect(viewModel.chatTranscript.contains {
            $0.kind == .tool && $0.body.contains("/tmp/melix-chat/report.md")
        })
        let toolEntry = try #require(viewModel.chatTranscript.first { $0.kind == .tool })
        var selectedPreview: DesktopChatArtifactPreviewState?
        let rowView = hostView(DesktopChatTranscriptRowView(entry: toolEntry) { preview in
            selectedPreview = preview
        })

        #expect(renderedTextValues(in: rowView).contains("/tmp/melix-chat/report.md"))
        #expect(accessibilityPressElement(labeled: "Preview Artifact", in: rowView))
        #expect(selectedPreview?.path == "/tmp/melix-chat/report.md")

        let preview = try #require(selectedPreview)
        let previewView = hostView(DesktopChatArtifactPreviewRail(preview: preview) {
            selectedPreview = nil
        })
        let renderedTexts = renderedTextValues(in: previewView)
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(renderedTexts.contains("Artifact Preview"))
        #expect(renderedTexts.contains("/tmp/melix-chat/report.md"))
        #expect(source.contains("DesktopChatTabContentView"))
        #expect(source.contains("if let artifactPreview"))
        #expect(source.contains("DesktopChatArtifactPreviewRail(preview: artifactPreview)"))
        #expect(source.contains("isSanitized: Bool = false"))
        #expect(source.contains("unicodeScalars.lazy.split"))
        #expect(source.contains("isSanitized: true"))
        selectedPreview = nil
        #expect(selectedPreview == nil)
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
        try bindSelectedChatSessionToPrimaryServer(viewModel)
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

    @Test("chat transcript row renders pending assistant state")
    @MainActor
    func chatTranscriptRowRendersPendingAssistantState() {
        let view = hostView(DesktopChatTranscriptRowView(
            entry: DesktopChatTranscriptEntry(
                id: "assistant-pending",
                kind: .assistant,
                title: "Assistant",
                body: "",
                detail: ""
            ),
            isPending: true,
            pendingStatusText: "Preparing"
        ))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat transcript rows expose light workspace role treatments")
    @MainActor
    func chatTranscriptRowsExposeLightWorkspaceRoleTreatments() throws {
        let reasoningView = hostView(DesktopChatTranscriptRowView(
            entry: DesktopChatTranscriptEntry(
                id: "reasoning-complete",
                kind: .reasoning,
                title: "Reasoning",
                body: "Checked local runtime state.",
                detail: "trace"
            ),
            isStreaming: false
        ))
        let streamingToolView = hostView(DesktopChatTranscriptRowView(
            entry: DesktopChatTranscriptEntry(
                id: "tool-streaming",
                kind: .tool,
                title: "Tool",
                body: "{\"path\":\"/tmp/report.md\"}",
                detail: "filesystem"
            ),
            isStreaming: true
        ))
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(renderedTextValues(in: reasoningView).contains("Thought recorded"))
        #expect(renderedTextValues(in: streamingToolView).contains("Calling tool"))
        #expect(source.contains("DesktopChatUserBubbleView"))
        #expect(source.contains("DesktopChatAssistantDocumentView"))
        #expect(source.contains("DesktopChatActivityBlockView"))
        #expect(source.contains(".accessibilityElement(children: .combine)"))
        #expect(source.contains("User message: \\(accessibilityMessageBody)"))
    }

    @Test("chat activity blocks expose thinking and tool summary decisions")
    @MainActor
    func chatActivityBlocksExposeThinkingAndToolSummaryDecisions() throws {
        let reasoningBlock = DesktopChatActivityBlockView(
            kind: .reasoning,
            title: "Reasoning",
            messageBody: "## Plan\n- Inspect runtime",
            detail: "",
            isStreaming: false
        )
        let toolBlock = DesktopChatActivityBlockView(
            kind: .tool,
            title: "",
            messageBody: "",
            detail: "",
            isStreaming: true
        )
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(reasoningBlock.summaryText == "Thought recorded")
        #expect(reasoningBlock.systemImageName == "brain.head.profile")
        #expect(toolBlock.summaryText == "Calling tool")
        #expect(toolBlock.systemImageName == "hammer")
        #expect(hostView(reasoningBlock.activityBody).fittingSize.width >= 0)
        #expect(hostView(toolBlock.activityBody).fittingSize.width >= 0)
        #expect(source.contains(".onChange(of: isStreaming)"))
        #expect(source.contains("isExpanded = newValue"))
    }

    @Test("chat composer runtime controls select server recovery actions")
    @MainActor
    func chatComposerRuntimeControlsSelectServerRecoveryActions() {
        var openedServerCount = 0
        var startCount = 0
        var resumeCount = 0
        var wakeCount = 0

        let baseSession = DesktopServerSessionState(
            id: "server-session-chat-controls",
            title: "Chat Runtime",
            modelID: "melix-dev-text",
            lifecycle: .running,
            powerState: .active
        )
        let capability = DesktopChatCapabilityRow(
            id: "text",
            title: "Interactive Text",
            modelID: "melix-dev-text",
            detail: "melix-dev-text • Ready",
            isReady: true
        )

        let chooseStrip = DesktopChatRuntimeControlStrip(
            serverSession: nil,
            capabilities: [],
            onOpenServer: { openedServerCount += 1 },
            onStartServer: { startCount += 1 },
            onResumeServer: { resumeCount += 1 },
            onWakeServer: { wakeCount += 1 }
        )
        #expect(chooseStrip.recoveryAction?.title == "Choose Provider")
        if let action = chooseStrip.recoveryAction {
            chooseStrip.perform(action)
        }
        chooseStrip.onOpenServer()

        var stoppedSession = baseSession
        stoppedSession.lifecycle = .stopped
        stoppedSession.powerState = .stopped
        let stoppedStrip = DesktopChatRuntimeControlStrip(
            serverSession: stoppedSession,
            capabilities: [capability],
            onOpenServer: { openedServerCount += 1 },
            onStartServer: { startCount += 1 },
            onResumeServer: { resumeCount += 1 },
            onWakeServer: { wakeCount += 1 }
        )
        #expect(stoppedStrip.recoveryAction?.title == "Start Provider")
        #expect(stoppedStrip.recoveryAction?.isProminent == true)
        if let action = stoppedStrip.recoveryAction {
            stoppedStrip.perform(action)
        }

        var pausedSession = baseSession
        pausedSession.lifecycle = .paused
        let pausedStrip = DesktopChatRuntimeControlStrip(
            serverSession: pausedSession,
            capabilities: [capability],
            onOpenServer: { openedServerCount += 1 },
            onStartServer: { startCount += 1 },
            onResumeServer: { resumeCount += 1 },
            onWakeServer: { wakeCount += 1 }
        )
        #expect(pausedStrip.recoveryAction?.title == "Resume Provider")
        if let action = pausedStrip.recoveryAction {
            pausedStrip.perform(action)
        }

        var sleepingSession = baseSession
        sleepingSession.lifecycle = .sleeping
        sleepingSession.powerState = .deepSleep
        let sleepingStrip = DesktopChatRuntimeControlStrip(
            serverSession: sleepingSession,
            capabilities: [capability],
            onOpenServer: { openedServerCount += 1 },
            onStartServer: { startCount += 1 },
            onResumeServer: { resumeCount += 1 },
            onWakeServer: { wakeCount += 1 }
        )
        #expect(sleepingStrip.recoveryAction?.title == "Wake")
        #expect(sleepingStrip.recoveryAction?.isProminent == false)
        if let action = sleepingStrip.recoveryAction {
            sleepingStrip.perform(action)
        }

        var errorSession = baseSession
        errorSession.lifecycle = .error
        errorSession.lastError = "worker failed"
        let errorStrip = DesktopChatRuntimeControlStrip(
            serverSession: errorSession,
            capabilities: [capability],
            onOpenServer: { openedServerCount += 1 },
            onStartServer: { startCount += 1 },
            onResumeServer: { resumeCount += 1 },
            onWakeServer: { wakeCount += 1 }
        )
        #expect(errorStrip.recoveryAction?.title == "Open Providers")
        #expect(errorStrip.recoveryAction?.isProminent == true)
        if let action = errorStrip.recoveryAction {
            errorStrip.perform(action)
        }

        let runningStrip = DesktopChatRuntimeControlStrip(
            serverSession: baseSession,
            capabilities: [capability],
            onOpenServer: { openedServerCount += 1 },
            onStartServer: { startCount += 1 },
            onResumeServer: { resumeCount += 1 },
            onWakeServer: { wakeCount += 1 }
        )
        #expect(runningStrip.recoveryAction == nil)
        #expect(hostView(runningStrip).subviews.isEmpty == false)

        #expect(openedServerCount == 3)
        #expect(startCount == 1)
        #expect(resumeCount == 1)
        #expect(wakeCount == 1)
    }

    @Test("chat composer surface routes primary clear and command submit actions")
    @MainActor
    func chatComposerSurfaceRoutesPrimaryClearAndCommandSubmitActions() {
        var submitCount = 0
        var clearCount = 0
        var commandDraft = ""
        var text = "Send this"
        let composer = DesktopChatComposerSurface(
            text: Binding(get: { text }, set: { text = $0 }),
            isSubmitAvailable: true,
            isSendDisabled: false,
            isStreaming: false,
            statusText: "Ready",
            usageText: "12 prompt • 24 completion",
            serverSession: DesktopServerSessionState(
                id: "server-session-compose",
                title: "Compose Runtime",
                modelID: "melix-dev-text",
                lifecycle: .running,
                powerState: .active
            ),
            capabilities: [],
            onCommandSubmit: { draft in
                commandDraft = draft
            },
            onSubmit: {
                submitCount += 1
            },
            onClear: {
                clearCount += 1
            },
            onOpenServer: {},
            onStartServer: {},
            onResumeServer: {},
            onWakeServer: {}
        )

        #expect(hostView(composer.primaryActionLabel).fittingSize.width >= 0)
        composer.primaryAction()
        composer.onClear()
        #expect(submitCount == 1)
        #expect(clearCount == 1)
        #expect(commandDraft.isEmpty)
    }

    @Test("chat workspace preview and recovery helpers update shell state")
    @MainActor
    func chatWorkspacePreviewAndRecoveryHelpersUpdateShellState() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
        snapshot.runtimeSessions = [
            makeDesktopRuntimeSession(lifecycleState: .stopped, powerState: .stopped),
        ]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)

        var showsSidebar = true
        var showsInspector = false
        var previewState: DesktopChatArtifactPreviewState?
        let toolEntry = DesktopChatTranscriptEntry(
            id: "tool-preview",
            kind: .tool,
            title: "Tool",
            body: "/tmp/melix-chat/preview.json",
            detail: ""
        )
        let preview = DesktopChatArtifactPreviewState(entry: toolEntry, path: "/tmp/melix-chat/preview.json")
        let tabContent = DesktopChatTabContentView(
            viewModel: viewModel,
            showsSidebar: Binding(get: { showsSidebar }, set: { showsSidebar = $0 }),
            showsInspector: Binding(get: { showsInspector }, set: { showsInspector = $0 }),
            artifactPreview: Binding(get: { previewState }, set: { previewState = $0 })
        )

        tabContent.selectArtifactPreview(preview)
        #expect(previewState == preview)
        #expect(showsInspector)
        tabContent.clearArtifactPreview()
        #expect(previewState == nil)

        var workspace = DesktopChatSessionWorkspace(
            viewModel: viewModel,
            showsSidebar: Binding(get: { showsSidebar }, set: { showsSidebar = $0 }),
            showsInspector: Binding(get: { showsInspector }, set: { showsInspector = $0 })
        )
        workspace.openServerSurface()
        #expect(viewModel.selectedSurface == .server)

        workspace.startSelectedChatServerSession()
        try await waitForRecordedClientAction("server.start:server-session-1", client: client)

        workspace.resumeSelectedChatServerSession()
        try await waitForRecordedClientAction("server.resume:server-session-1", client: client)

        workspace.wakeSelectedChatServerSession()
        try await waitForRecordedClientAction("server.wake:server-session-1", client: client)

        let emptyClient = FakeControlPlaneXPCClient()
        var emptySnapshot = Melix_Controlplane_V1_ServerSnapshot()
        emptySnapshot.serverState = .serverReady
        await emptyClient.configureSnapshot(emptySnapshot)
        let emptyViewModel = RuntimeViewModel(client: emptyClient)
        await emptyViewModel.start()
        workspace = DesktopChatSessionWorkspace(
            viewModel: emptyViewModel,
            showsSidebar: Binding(get: { showsSidebar }, set: { showsSidebar = $0 }),
            showsInspector: Binding(get: { showsInspector }, set: { showsInspector = $0 })
        )
        workspace.startSelectedChatServerSession()
        try await waitForDesktopFoundationCondition("expected missing bound server to open server surface") {
            emptyViewModel.selectedSurface == .server
        }
    }

    @Test("chat composer streaming guard and provider signals cover alternate states")
    @MainActor
    func chatComposerStreamingGuardAndProviderSignalsCoverAlternateStates() {
        var submitCount = 0
        var text = "Streaming draft"
        let streamingComposer = DesktopChatComposerSurface(
            text: Binding(get: { text }, set: { text = $0 }),
            isSubmitAvailable: false,
            isSendDisabled: true,
            isStreaming: true,
            statusText: "Streaming",
            usageText: "",
            serverSession: nil,
            capabilities: [],
            onCommandSubmit: { _ in },
            onSubmit: {
                submitCount += 1
            },
            onClear: {},
            onOpenServer: {},
            onStartServer: {},
            onResumeServer: {},
            onWakeServer: {}
        )
        streamingComposer.primaryAction()
        #expect(submitCount == 0)
        #expect(hostView(streamingComposer.primaryActionLabel).fittingSize.width >= 0)

        let emptySignal = DesktopChatProviderStatusSignal(serverSession: nil)
        var errorSession = DesktopServerSessionState(
            id: "server-session-error",
            title: "Broken Runtime",
            modelID: "melix-dev-text",
            lifecycle: .error,
            powerState: .active,
            lastError: "worker failed"
        )
        let errorSignal = DesktopChatProviderStatusSignal(serverSession: errorSession)
        errorSession.lifecycle = .starting
        let startingSignal = DesktopChatProviderStatusSignal(serverSession: errorSession)

        let capabilitySignal = DesktopChatCapabilityStatusSignal(
            capabilities: [
                DesktopChatCapabilityRow(
                    id: "text",
                    title: "Interactive Text",
                    modelID: "melix-dev-text",
                    detail: "melix-dev-text • Ready",
                    isReady: true
                ),
                DesktopChatCapabilityRow(
                    id: "vision",
                    title: "Vision",
                    modelID: "melix-dev-vision",
                    detail: "melix-dev-vision • Missing",
                    isReady: false
                )
            ]
        )

        #expect(emptySignal.serverTitle == "No Provider")
        #expect(emptySignal.serverDetail == "Choose Provider")
        #expect(emptySignal.statusShortText == "SET")
        #expect(errorSignal.serverDetail == "Error • melix-dev-text")
        #expect(errorSignal.statusShortText == "ERR")
        #expect(errorSignal.statusColor == MelixDesignTokens.StatusColor.error)
        #expect(startingSignal.statusColor == MelixDesignTokens.StatusColor.warning)
        #expect(capabilitySignal.readyCount == 1)
        #expect(capabilitySignal.statusColor == MelixDesignTokens.StatusColor.warning)
        #expect(DesktopChatRuntimeSignalMetrics.providerSignalWidth <= 72)
        #expect(DesktopChatRuntimeSignalMetrics.capabilitySignalWidth <= 68)
    }

    @Test("chat transcript auto-scroll snapshot tracks trailing content growth")
    func chatTranscriptAutoScrollSnapshotTracksTrailingContentGrowth() {
        let initial = DesktopChatTranscriptAutoScroll.snapshot(
            transcript: [
                DesktopChatTranscriptEntry(
                    id: "assistant-1",
                    kind: .assistant,
                    title: "Assistant",
                    body: "",
                    detail: ""
                )
            ],
            isStreaming: true,
            statusText: "Preparing"
        )
        let advanced = DesktopChatTranscriptAutoScroll.snapshot(
            transcript: [
                DesktopChatTranscriptEntry(
                    id: "assistant-1",
                    kind: .assistant,
                    title: "Assistant",
                    body: "Token delta",
                    detail: ""
                )
            ],
            isStreaming: true,
            statusText: "Decoding"
        )
        let completed = DesktopChatTranscriptAutoScroll.snapshot(
            transcript: [
                DesktopChatTranscriptEntry(
                    id: "assistant-1",
                    kind: .assistant,
                    title: "Assistant",
                    body: "Token delta",
                    detail: ""
                ),
                DesktopChatTranscriptEntry(
                    id: "assistant-2",
                    kind: .assistant,
                    title: "Assistant",
                    body: "Final answer",
                    detail: ""
                )
            ],
            isStreaming: false,
            statusText: "Completed"
        )

        #expect(initial != advanced)
        #expect(advanced != completed)
        #expect(completed.lastEntryID == "assistant-2")
    }

    @Test("chat transcript source wires bottom-anchor auto-scroll")
    @MainActor
    func chatTranscriptSourceWiresBottomAnchorAutoScroll() throws {
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(source.contains("ScrollViewReader"))
        #expect(source.contains("DesktopChatTranscriptAutoScroll.Anchor.bottom"))
        #expect(source.contains("scrollChatTranscriptToBottom"))
    }

    @Test("chat markdown parser builds assistant display blocks")
    func chatMarkdownParserBuildsAssistantDisplayBlocks() {
        let blocks = DesktopChatMarkdownRenderer.blocks(from: """
        Intro **bold** and _italic_ with `code`.

        - one
        - two

        1. first
        2. second

        ```swift
        let value = 1
        ```

        | Metric | Value |
        | --- | ---: |
        | TTFT | 12 ms |
        """)

        #expect(blocks == [
            .paragraph("Intro **bold** and _italic_ with `code`\\."),
            .unorderedList([
                DesktopChatMarkdownListItem(text: "one"),
                DesktopChatMarkdownListItem(text: "two"),
            ]),
            .orderedList(start: 1, items: [
                DesktopChatMarkdownListItem(text: "first"),
                DesktopChatMarkdownListItem(text: "second"),
            ]),
            .codeBlock(language: "swift", code: "let value = 1"),
            .table(
                header: ["Metric", "Value"],
                alignments: [.none, .trailing],
                rows: [["TTFT", "12 ms"]]
            ),
        ])
    }

    @Test("chat markdown parser builds AST backed blocks")
    func chatMarkdownParserBuildsASTBackedBlocks() {
        let blocks = DesktopChatMarkdownRenderer.blocks(from: """
        # Result

        > quoted **answer**

        - parent
          - child

        3. first
           1. child

        ---

        ![diagram alt](https://example.com/diagram.png)

        | Name | Alignment | Note |
        | :--- | ---: | :---: |
        | Alpha \\| Beta | Right | Center |
        """)

        #expect(blocks == [
            .heading(level: 1, text: "Result"),
            .blockQuote([
                .paragraph("quoted **answer**"),
            ]),
            .unorderedList([
                DesktopChatMarkdownListItem(
                    text: "parent",
                    children: [
                        .unorderedList([
                            DesktopChatMarkdownListItem(text: "child"),
                        ]),
                    ]
                ),
            ]),
            .orderedList(
                start: 3,
                items: [
                    DesktopChatMarkdownListItem(
                        text: "first",
                        children: [
                            .orderedList(
                                start: 1,
                                items: [
                                    DesktopChatMarkdownListItem(text: "child"),
                                ]
                            ),
                        ]
                    ),
                ]
            ),
            .thematicBreak,
            .paragraph("diagram alt"),
            .table(
                header: ["Name", "Alignment", "Note"],
                alignments: [.leading, .trailing, .center],
                rows: [["Alpha \\| Beta", "Right", "Center"]]
            ),
        ])
    }

    @Test("chat markdown list items preserve loose child order")
    func chatMarkdownListItemsPreserveLooseChildOrder() {
        let blocks = DesktopChatMarkdownRenderer.blocks(from: """
        - intro

          - nested

          conclusion
        """)

        #expect(blocks == [
            .unorderedList([
                DesktopChatMarkdownListItem(
                    text: "intro",
                    children: [
                        .unorderedList([
                            DesktopChatMarkdownListItem(text: "nested"),
                        ]),
                        .paragraph("conclusion"),
                    ]
                ),
            ]),
        ])

        let codeOnlyItem = DesktopChatMarkdownRenderer.blocks(from: """
        -
          ```swift
          let value = 1
          ```
        """)

        #expect(codeOnlyItem == [
            .unorderedList([
                DesktopChatMarkdownListItem(
                    text: "",
                    children: [
                        .codeBlock(language: "swift", code: "let value = 1"),
                    ]
                ),
            ]),
        ])
    }

    @Test("chat markdown literal punctuation stays literal after inline parse")
    func chatMarkdownLiteralPunctuationStaysLiteralAfterInlineParse() {
        let blocks = DesktopChatMarkdownRenderer.blocks(from: "multiply: 2 * 3 or 4 * 5")

        #expect(blocks == [.paragraph("multiply: 2 \\* 3 or 4 \\* 5")])

        let text: String
        if case .paragraph(let paragraphText) = blocks.first {
            text = paragraphText
        } else {
            text = ""
        }
        let attributed = DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: text)
        let inlineCodeWithBacktick = DesktopChatMarkdownRenderer.blocks(from: "``a ` b``")

        #expect(String(attributed.characters) == "multiply: 2 * 3 or 4 * 5")
        #expect(attributed.runs.allSatisfy { $0.inlinePresentationIntent == nil })
        #expect(inlineCodeWithBacktick == [.paragraph("``a ` b``")])
    }

    @Test("chat markdown inline formatter removes markdown markers while preserving readable text")
    func chatMarkdownInlineFormatterRemovesMarkers() {
        let attributed = DesktopChatMarkdownInlineFormatter.attributedString(
            from: "**bold** and _italic_ and `code` and ~~strike~~"
        )
        let linked = DesktopChatMarkdownInlineFormatter.attributedString(
            from: "[Melix](https://example.com)"
        )
        let image = DesktopChatMarkdownInlineFormatter.attributedString(
            from: "![Diagram](https://example.com/diagram.png)"
        )
        let imageTitle = DesktopChatMarkdownInlineFormatter.attributedString(
            from: "![](https://example.com/diagram.png \"Diagram title\")"
        )
        let lineBreaks = DesktopChatMarkdownInlineFormatter.attributedString(
            fromSanitized: "soft\nbreak and hard  \nbreak"
        )
        let inlineHTML = DesktopChatMarkdownInlineFormatter.attributedString(
            fromSanitized: "Hello <span>ignored</span>"
        )

        #expect(String(attributed.characters) == "bold and italic and code and strike")
        #expect(String(linked.characters) == "Melix")
        #expect(String(image.characters) == "Diagram")
        #expect(String(imageTitle.characters) == "Diagram title")
        #expect(String(lineBreaks.characters) == "soft break and hard\nbreak")
        #expect(String(inlineHTML.characters) == "Hello ignored")
        #expect(linked.runs.allSatisfy { $0.link == nil })
    }

    @Test("chat markdown body view hosts paragraph list code and table blocks")
    @MainActor
    func chatMarkdownBodyViewHostsParagraphListCodeAndTableBlocks() {
        let view = hostView(DesktopChatMarkdownBodyView(rawText: """
        Intro **bold** and _italic_ with `code`.

        - one
        - two

        1. first
        2. second

        ```swift
        let value = 1
        ```

        | Metric | Value |
        | --- | --- |
        | TTFT |
        | TPS | 20 |
        """))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat markdown body view hosts rich AST backed block branches")
    @MainActor
    func chatMarkdownBodyViewHostsRichASTBackedBlockBranches() {
        let view = hostView(DesktopChatMarkdownBodyView(rawText: """
        # Heading
        ## Subheading
        ### Minor
        #### Body-sized

        > quoted

        ---

        - parent
          - child

        3. first
           1. child

        ```
        blank language
        ```

        | Left | Center | Right |
        | :--- | :---: | ---: |
        | A | B | C |
        | Long | Row | Extra | Trimmed |
        """))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat markdown code blocks expose badge highlight and copy behavior")
    func chatMarkdownCodeBlocksExposeBadgeHighlightAndCopyBehavior() throws {
        let code = """
        let enabled = true
        // keep comments readable
        """
        let presentation = DesktopChatMarkdownCodeBlockPresentation(language: " swift ", code: code)
        let pasteboard = RecordingPasteboard()

        DesktopChatMarkdownCodeBlockClipboard.copy(code, to: pasteboard)

        #expect(presentation.languageBadge == "Swift")
        #expect(presentation.copyAccessibilityLabel == "Copy code")
        #expect(String(presentation.highlightedCode.characters) == code)
        #expect(presentation.highlightedCode.runs.contains { $0.foregroundColor != nil })
        #expect(pasteboard.string == code)
    }

    @Test("chat markdown code language badges and highlighter branches")
    func chatMarkdownCodeLanguageBadgesAndHighlighterBranches() {
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "javascript") == "JavaScript")
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "ts") == "TypeScript")
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "bash") == "Shell")
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "python") == "Python")
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "patch") == "Diff")
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "toml") == "TOML")
        #expect(DesktopChatMarkdownCodeLanguage.badge(for: "") == "Plain Text")

        let json = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: #"{"enabled": true, "count": 12, "label": "ok"}"#,
            language: "json"
        )
        let shell = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: "git status\n# comment line here\nvalue",
            language: "bash"
        )
        let diff = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: """
            @@ -1 +1 @@
            -old
            +new
             context
            """,
            language: "diff"
        )
        let plain = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: "",
            language: "text"
        )

        #expect(String(json.characters).contains(#""enabled""#))
        #expect(json.runs.contains { $0.foregroundColor != nil })
        #expect(
            attributedString(shell, hasColoredRunCovering: "# comment line here"),
            "Full comment line should be colored, not just the delimiter"
        )
        #expect(diff.runs.contains { $0.foregroundColor != nil })
        #expect(String(plain.characters).isEmpty)
    }

    @Test("chat markdown JS and Python keywords are colored with language-specific sets")
    func chatMarkdownJSAndPythonKeywordsAreColoredWithLanguageSpecificSets() {
        let js = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: "function foo() { return null; }",
            language: "javascript"
        )
        let py = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: "def foo():\n    pass\n    return None",
            language: "python"
        )
        let swift = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: "func foo() -> Void { return }",
            language: "swift"
        )

        // JS-specific keywords like `function` and `null` must be colored.
        let jsText = String(js.characters)
        let functionRange = jsText.range(of: "function")
        #expect(functionRange != nil)
        if let range = functionRange {
            let charIndex = jsText.distance(from: jsText.startIndex, to: range.lowerBound)
            let colored = js.runs.contains { run in
                let start = js.characters.distance(from: js.characters.startIndex, to: run.range.lowerBound)
                return start == charIndex && run.foregroundColor != nil
            }
            #expect(colored, "`function` should be highlighted in JavaScript")
        }

        // Python-specific keywords like `def` and `None` must be colored.
        let pyText = String(py.characters)
        let defRange = pyText.range(of: "def")
        #expect(defRange != nil)
        if let range = defRange {
            let charIndex = pyText.distance(from: pyText.startIndex, to: range.lowerBound)
            let colored = py.runs.contains { run in
                let start = py.characters.distance(from: py.characters.startIndex, to: run.range.lowerBound)
                return start == charIndex && run.foregroundColor != nil
            }
            #expect(colored, "`def` should be highlighted in Python")
        }

        // `func` is a Swift keyword and should be colored in Swift but not be
        // incorrectly used to color JS/Python (they have `function`/`def`).
        #expect(swift.runs.contains { $0.foregroundColor != nil })
    }

    @Test("chat markdown stable identities avoid positional render ids")
    func chatMarkdownStableIdentitiesAvoidPositionalRenderIDs() {
        let chunks = [
            DesktopChatMarkdownRenderChunk(
                source: "duplicate",
                blocks: [.paragraph("repeat")],
                isStable: true
            ),
            DesktopChatMarkdownRenderChunk(
                source: "duplicate",
                blocks: [.paragraph("repeat")],
                isStable: true
            ),
        ]
        let blocks: [DesktopChatMarkdownBlock] = [
            .paragraph("repeat"),
            .paragraph("repeat"),
            .heading(level: 2, text: "Title"),
            .unorderedList([
                DesktopChatMarkdownListItem(text: "child"),
            ]),
        ]
        let firstBlockIDs = DesktopChatMarkdownStableIdentity.identifiedBlocks(blocks).map(\.id)
        let secondBlockIDs = DesktopChatMarkdownStableIdentity.identifiedBlocks(blocks).map(\.id)
        let items = [
            DesktopChatMarkdownListItem(text: "same"),
            DesktopChatMarkdownListItem(text: "same"),
            DesktopChatMarkdownListItem(text: "different"),
        ]
        let identifiedItems = DesktopChatMarkdownStableIdentity.identifiedListItems(items)
        let chunkIDs = DesktopChatMarkdownStableIdentity.identifiedChunks(chunks).map(\.id)
        let itemIDs = identifiedItems.map(\.id)

        #expect(Set(chunkIDs).count == chunkIDs.count)
        #expect(firstBlockIDs == secondBlockIDs)
        #expect(Set(firstBlockIDs).count == firstBlockIDs.count)
        #expect(Set(itemIDs).count == itemIDs.count)
        #expect(identifiedItems.map(\.offset) == [0, 1, 2])
    }

    @Test("chat markdown table layout bounds wide content")
    func chatMarkdownTableLayoutBoundsWideContent() {
        let layout = DesktopChatMarkdownTableLayout(
            header: ["Name", "Very Long Column", "Status"],
            rows: [[
                "alpha",
                String(repeating: "wide-content-", count: 24),
                "ready",
            ]]
        )

        #expect(layout.columnWidths.count == 3)
        #expect(layout.columnWidths.allSatisfy { $0 >= DesktopChatMarkdownLayoutMetrics.tableColumnMinWidth })
        #expect(layout.columnWidths.contains(DesktopChatMarkdownLayoutMetrics.tableColumnMaxWidth))
        #expect(
            layout.lineLimit(for: String(repeating: "wide-content-", count: 24)) ==
                DesktopChatMarkdownLayoutMetrics.tableCellMaximumLineCount
        )
    }

    @Test("chat markdown body view hosts code and table polish controls")
    @MainActor
    func chatMarkdownBodyViewHostsCodeAndTablePolishControls() {
        let view = hostView(DesktopChatMarkdownBodyView(rawText: """
        ```json
        {"enabled": true, "mode": "local"}
        ```

        | Column | Long |
        | --- | --- |
        | A | \(String(repeating: "wide ", count: 80)) |
        """))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat markdown body view hosts lazy long response plans")
    @MainActor
    func chatMarkdownBodyViewHostsLazyLongResponsePlans() {
        let view = hostView(DesktopChatMarkdownBodyView(rawText: chatMarkdownLongStreamingSample(sectionCount: 56)))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat markdown renderer builds lazy streaming render plans")
    func chatMarkdownRendererBuildsLazyStreamingRenderPlans() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 64)
        let stableBlocks = chatMarkdownLongStreamingSample(sectionCount: 48)
        let firstStream = stableBlocks + "\n\nPartial tail"
        let secondStream = firstStream + " still streaming"

        let firstPlan = DesktopChatMarkdownRenderer.renderPlan(from: firstStream, mode: .streaming)
        let firstStats = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        let secondPlan = DesktopChatMarkdownRenderer.renderPlan(from: secondStream, mode: .streaming)
        let secondStats = DesktopChatMarkdownRenderer.cacheStatsForTesting()

        #expect(firstPlan.usesLazyRendering)
        #expect(firstPlan.chunks.count > 1)
        #expect(firstPlan.blocks == DesktopChatMarkdownRenderer.blocks(from: firstStream))
        #expect(secondPlan.chunks.count == firstPlan.chunks.count)
        #expect(secondStats.chunkHitCount > firstStats.chunkHitCount)
        #expect(secondStats.chunkMissCount - firstStats.chunkMissCount <= 1)

        DesktopChatMarkdownRenderer.resetCacheForTesting()
    }

    @Test("chat markdown complete render plans cache the tail chunk")
    func chatMarkdownCompleteRenderPlansCacheTheTailChunk() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 64)
        let source = chatMarkdownLongStreamingSample(sectionCount: 48) + "\n\nComplete tail"

        _ = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .complete)
        let firstCompleteStats = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .complete)
        let secondCompleteStats = DesktopChatMarkdownRenderer.cacheStatsForTesting()

        #expect(secondCompleteStats.chunkHitCount > firstCompleteStats.chunkHitCount)
        #expect(secondCompleteStats.chunkMissCount == firstCompleteStats.chunkMissCount)

        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 64)
        _ = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .streaming)
        let firstStreamingStats = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .streaming)
        let secondStreamingStats = DesktopChatMarkdownRenderer.cacheStatsForTesting()

        #expect(secondStreamingStats.chunkHitCount > firstStreamingStats.chunkHitCount)
        #expect(secondStreamingStats.chunkMissCount > firstStreamingStats.chunkMissCount)

        DesktopChatMarkdownRenderer.resetCacheForTesting()
    }

    @Test("chat markdown chunker keeps mismatched fence markers inside code")
    func chatMarkdownChunkerKeepsMismatchedFenceMarkersInsideCode() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 64)
        let longCode = Array(repeating: "let value = 42", count: 180).joined(separator: "\n")
        let source = """
        ```swift
        \(longCode)
        ~~~not a closing fence~~~

        \(longCode)
        ```
        """

        let plan = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .complete)

        #expect(plan.chunks.count == 1)
        #expect(plan.blocks == [
            .codeBlock(
                language: "swift",
                code: "\(longCode)\n~~~not a closing fence~~~\n\n\(longCode)"
            ),
        ])

        let longerFenceSource = """
        ````swift
        \(longCode)
        ```

        \(longCode)
        ````
        """
        let longerFencePlan = DesktopChatMarkdownRenderer.renderPlan(from: longerFenceSource, mode: .complete)

        #expect(longerFencePlan.chunks.count == 1)
        #expect(longerFencePlan.blocks == [
            .codeBlock(language: "swift", code: "\(longCode)\n```\n\n\(longCode)"),
        ])

        let shortFenceMarkerSource = String(repeating: "plain text\n", count: 220) + "\n``\n\ntrailing"
        let shortFenceMarkerPlan = DesktopChatMarkdownRenderer.renderPlan(
            from: shortFenceMarkerSource,
            mode: .complete
        )

        #expect(shortFenceMarkerPlan.blocks.isEmpty == false)

        DesktopChatMarkdownRenderer.resetCacheForTesting()
    }

    @Test("chat markdown renderer evicts old chunk cache entries")
    func chatMarkdownRendererEvictsOldChunkCacheEntries() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 1)

        _ = DesktopChatMarkdownRenderer.renderPlan(
            from: chatMarkdownLongStreamingSample(sectionCount: 36),
            mode: .complete
        )
        let stats = DesktopChatMarkdownRenderer.cacheStatsForTesting()

        #expect(stats.chunkMissCount > 1)
        #expect(stats.evictionCount > 0)

        DesktopChatMarkdownRenderer.resetCacheForTesting()
    }

    @Test("chat markdown fixture snapshot stays stable")
    func chatMarkdownFixtureSnapshotStaysStable() throws {
        let source = try chatMarkdownFixture(named: "chat-markdown-rich.md")
        let expected = try chatMarkdownFixture(named: "chat-markdown-rich.snapshot.txt")

        let snapshot = chatMarkdownBlockSnapshot(DesktopChatMarkdownRenderer.blocks(from: source))

        #expect(snapshot == expected.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    #if DEBUG
    @Test("chat markdown performance probe reports large sample cache benefit")
    func chatMarkdownPerformanceProbeReportsLargeSampleCacheBenefit() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 256)

        let report = DesktopChatMarkdownPerformanceProbe.measure(sampleSizes: [5_000, 50_000, 200_000])

        #expect(report.samples.map(\.targetByteCount) == [5_000, 50_000, 200_000])
        #expect(report.samples.allSatisfy { $0.blockCount > 0 })
        #expect(report.samples.allSatisfy { $0.chunkCount > 0 })
        #expect(report.samples.allSatisfy { $0.firstParseDurationMS >= 0 })
        #expect(report.samples.allSatisfy { $0.cachedParseDurationMS >= 0 })
        #expect(report.samples.allSatisfy { $0.cacheHitDelta > 0 })

        let stats = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        let sampleMetrics = report.samples
            .map {
                "\($0.targetByteCount):first_ms=\(String(format: "%.3f", $0.firstParseDurationMS)),cached_ms=\(String(format: "%.3f", $0.cachedParseDurationMS)),hits=\($0.cacheHitDelta),misses=\($0.cacheMissDelta),evictions=\($0.evictionDelta),chunks=\($0.chunkCount)"
            }
            .joined(separator: ";")
        print(
            "M16_CHAT_MARKDOWN_PERF=samples=[\(sampleMetrics)] eviction_count=\(stats.evictionCount) latest_build_ms=\(String(format: "%.3f", stats.latestBuildDurationMS))"
        )

        DesktopChatMarkdownRenderer.resetCacheForTesting()
    }
    #endif

    @Test("chat markdown surfaces keep restrained low-border styling")
    func chatMarkdownSurfacesKeepRestrainedLowBorderStyling() {
        #expect(
            DesktopChatMarkdownLayoutMetrics.codeBlockBorderOpacity < MelixDesignTokens.StrokeOpacity.interactive
        )
        #expect(
            DesktopChatMarkdownLayoutMetrics.tableHeaderBackgroundOpacity < MelixDesignTokens.SurfaceOpacity.elevated
        )
        #expect(
            DesktopChatMarkdownLayoutMetrics.tableSurfaceBackgroundOpacity < MelixDesignTokens.SurfaceOpacity.card
        )
    }

    @Test("chat markdown rendering is limited to assistant and reasoning rows")
    func chatMarkdownRenderingIsLimitedToAssistantAndReasoningRows() {
        #expect(DesktopChatMarkdownRenderer.usesMarkdown(for: .assistant))
        #expect(DesktopChatMarkdownRenderer.usesMarkdown(for: .reasoning))
        #expect(DesktopChatMarkdownRenderer.usesMarkdown(for: .user) == false)
        #expect(DesktopChatMarkdownRenderer.usesMarkdown(for: .tool) == false)
        #expect(DesktopChatMarkdownRenderer.usesMarkdown(for: .error) == false)
    }

    @Test("chat markdown renderer sanitizes html and unsafe links before parsing")
    func chatMarkdownRendererSanitizesHTMLAndUnsafeLinksBeforeParsing() {
        let blocks = DesktopChatMarkdownRenderer.blocks(from: """
        <b>Hello</b> [click](javascript:alert(1))

        ```html
        <b>keep as code</b>
        [keep](javascript:alert(1))
        ```
        """)

        #expect(blocks == [
            .paragraph("Hello click"),
            .codeBlock(
                language: "html",
                code: "<b>keep as code</b>\n[keep](javascript:alert(1))"
            ),
        ])
    }

    @Test("chat markdown renderer preserves inline source edge cases")
    func chatMarkdownRendererPreservesInlineSourceEdgeCases() {
        let softBreak = DesktopChatMarkdownRenderer.blocks(from: "soft\nbreak")
        let hardBreak = DesktopChatMarkdownRenderer.blocks(from: "hard  \nbreak")
        let strikeLinkAndTitleImage = DesktopChatMarkdownRenderer.blocks(from: """
        ~~gone~~ [label](https://example.com) ![](https://example.com/image.png "fallback")
        """)
        let unclosedFence = DesktopChatMarkdownRenderer.blocks(from: """
        ```swift
        let value = 2
        """)
        let pureHTML = DesktopChatMarkdownRenderer.blocks(from: "<br />")

        #expect(softBreak == [.paragraph("soft break")])
        #expect(hardBreak == [.paragraph("hard\nbreak")])
        #expect(strikeLinkAndTitleImage == [.paragraph("~~gone~~ label fallback")])
        #expect(unclosedFence == [.codeBlock(language: "swift", code: "let value = 2")])
        #expect(pureHTML == [])
    }

    @Test("chat markdown renderer caches parsed blocks and evicts old entries")
    func chatMarkdownRendererCachesParsedBlocksAndEvictsOldEntries() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 2)

        _ = DesktopChatMarkdownRenderer.blocks(from: "A")
        let first = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownRenderer.blocks(from: "A")
        let second = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownRenderer.blocks(from: "B")
        _ = DesktopChatMarkdownRenderer.blocks(from: "C")
        let third = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownRenderer.blocks(from: "A")
        let fourth = DesktopChatMarkdownRenderer.cacheStatsForTesting()

        #expect(first.parseMissCount == 1)
        #expect(second.parseHitCount == 1)
        #expect(third.evictionCount == 1)
        // Misses are cumulative since reset: A, B, C, then A again after eviction.
        #expect(fourth.parseMissCount == 4)
        #expect(fourth.latestBuildDurationMS >= 0)
    }

    @Test("chat markdown renderer caches inline attributed strings and evicts old entries")
    func chatMarkdownRendererCachesInlineAttributedStringsAndEvictsOldEntries() {
        DesktopChatMarkdownRenderer.resetCacheForTesting(capacity: 1)
        let firstSource = String(repeating: "**A** ", count: 512)

        _ = DesktopChatMarkdownInlineFormatter.attributedString(from: firstSource)
        let first = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownInlineFormatter.attributedString(from: firstSource)
        let second = DesktopChatMarkdownRenderer.cacheStatsForTesting()
        _ = DesktopChatMarkdownInlineFormatter.attributedString(from: "**B**")
        let third = DesktopChatMarkdownRenderer.cacheStatsForTesting()

        #expect(first.inlineMissCount == 1)
        #expect(first.latestBuildDurationMS > 0)
        #expect(second.inlineHitCount == 1)
        #expect(third.evictionCount == 1)

        DesktopChatMarkdownRenderer.resetCacheForTesting()
    }

    @Test("chat session sidebar renders the empty state when no chat sessions exist")
    @MainActor
    func chatSessionSidebarRendersTheEmptyStateWhenNoChatSessionsExist() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        for session in viewModel.chatSessions {
            viewModel.deleteChatSession(id: session.id)
        }

        let view = hostView(DesktopChatSessionSidebar(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.chatSessions.isEmpty)
    }

    @Test("chat empty state buttons dispatch new chat and server navigation")
    @MainActor
    func chatEmptyStateButtonsDispatchNewChatAndServerNavigation() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        for session in viewModel.chatSessions {
            viewModel.deleteChatSession(id: session.id)
        }

        let sidebar = DesktopChatSessionSidebar(viewModel: viewModel)
        let initialView = hostView(sidebar)
        sidebar.createChatSessionAction()

        #expect(initialView.subviews.isEmpty == false)
        #expect(viewModel.chatSessions.count == 1)
        #expect(viewModel.selectedSurface == .chat)
        #expect(viewModel.selectedChatSession?.statusText == "Choose Provider")

        let serverView = hostView(sidebar)
        sidebar.openServerAction()

        #expect(serverView.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .server)
    }

    @Test("chat workspace uses compact layout metrics")
    @MainActor
    func chatWorkspaceUsesCompactLayoutMetrics() {
        #expect(DesktopChatLayoutMetrics.sidebarIdealWidth <= 230)
        #expect(DesktopChatLayoutMetrics.sidebarMaxWidth <= 260)
        #expect(DesktopChatLayoutMetrics.inspectorIdealWidth <= 240)
        #expect(DesktopChatLayoutMetrics.composerMinHeight <= 84)
        #expect(DesktopChatLayoutMetrics.collapsedRailWidth == 0)
    }

    @Test("chat tab omits collapsed rails when both side panes start hidden")
    @MainActor
    func chatTabOmitsCollapsedRailsWhenBothSidePanesStartHidden() async throws {
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

    @Test("chat session workspace leaves empty transcript visually quiet")
    @MainActor
    func chatSessionWorkspaceLeavesEmptyTranscriptVisuallyQuiet() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let hosted = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(false)
            )
        )
        let renderedTexts = renderedTextValues(in: hosted)

        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.chatTranscript.isEmpty)
        #expect(renderedTexts.contains("Start a conversation") == false)
        #expect(renderedTexts.contains { $0.contains("Messages will appear here after you send.") } == false)

        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )
        #expect(source.contains("Start a conversation") == false)
        #expect(source.contains("Messages will appear here after you send.") == false)
    }

    @Test("new chat session button opts out of launch focus highlight")
    @MainActor
    func newChatSessionButtonOptsOutOfLaunchFocusHighlight() throws {
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(source.contains(".accessibilityLabel(\"New Chat Session\")"))
        #expect(source.contains(".focusable(false)"))
    }

    @Test("desktop shell chrome opts titlebar buttons out of focus ring and root sets app tint")
    func desktopShellChromeOptsTitlebarButtonsOutOfFocusRingAndRootSetsAppTint() throws {
        let root = try repositoryRootForDesktopFoundationTests()
        let shellChrome = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift"
        )
        let rootView = root.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift"
        )
        let chromeSource = try String(contentsOf: shellChrome, encoding: .utf8)
        let rootSource = try String(contentsOf: rootView, encoding: .utf8)

        #expect(chromeSource.contains(".focusable(false)"))
        #expect(rootSource.contains(".tint(MelixDesignTokens.accent)"))
    }

    @Test("chat session branch display hides main but keeps fork labels")
    @MainActor
    func chatSessionBranchDisplayHidesMainButKeepsForkLabels() throws {
        let mainSession = DesktopChatSessionState(
            id: "chat-main",
            title: "Chat 1",
            serverSessionID: "server-main",
            branchID: "main",
            branchTitle: "Main"
        )
        let forkSession = DesktopChatSessionState(
            id: "chat-fork",
            title: "Chat 2",
            serverSessionID: "server-main",
            branchID: "branch-2",
            branchTitle: "Branch 2"
        )
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(mainSession.displayBranchTitle == nil)
        #expect(forkSession.displayBranchTitle == "Branch 2")
        #expect(source.contains("selectedChatSession?.displayBranchTitle"))
    }

    @Test("chat workspace renders selected branch badge")
    @MainActor
    func chatWorkspaceRendersSelectedBranchBadge() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarModelSummary(modelID: desktopTestReadyModelID, state: .modelWarm)]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.createChatSession()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.forkSelectedChatSession()

        let branchTitle = try #require(viewModel.selectedChatSession?.displayBranchTitle)
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(branchTitle.hasPrefix("Branch "))
        #expect(source.contains("DesktopChatSessionBranchBadgeView(branch: branch)"))
        #expect(source.contains(".accessibilityLabel(branch)"))
    }

    @Test("chat session inspector labels snapshot capabilities without claiming route traces")
    @MainActor
    func chatSessionInspectorLabelsSnapshotCapabilitiesWithoutClaimingRouteTraces() throws {
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(source.contains("DesktopChatServerPicker"))
        #expect(source.contains("bindSelectedChatSessionToServer"))
        #expect(source.contains("DesktopInspectorContractView"))
        #expect(source.contains("GroupBox(\"Model Capabilities\")"))
        #expect(source.contains("DesktopChatCapabilityIconGrid"))
        #expect(source.contains("MelixSectionCard(\"Runtime\")") == false)
        #expect(source.contains("Text(\"request \\(") == false)
        #expect(source.contains("MelixSectionCard(\"Analysis Routes\")") == false)
    }

    @Test("chat composer owns runtime control strip inside the input surface")
    @MainActor
    func chatComposerOwnsRuntimeControlStripInsideTheInputSurface() throws {
        let source = try String(
            contentsOf: repositoryRootForDesktopFoundationTests()
                .appendingPathComponent("apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift"),
            encoding: .utf8
        )

        #expect(source.contains("DesktopChatComposerSurface"))
        #expect(source.contains("DesktopChatRuntimeControlStrip"))
        #expect(source.contains("DesktopChatProviderStatusSignal"))
        #expect(source.contains("DesktopChatCapabilityStatusSignal"))
        #expect(source.contains("DesktopChatRuntimeSignalMetrics.providerSignalWidth"))
        #expect(source.contains("DesktopChatRuntimeSignalMetrics.capabilitySignalWidth"))
        #expect(source.contains("DesktopChatRuntimeServerCapsule") == false)
        #expect(source.contains("DesktopChatInlineCapabilityCluster") == false)
        #expect(source.contains("Label(\"Send\", systemImage: \"paperplane.fill\")"))
        #expect(source.contains("Label(\"Stop\", systemImage: \"stop.fill\")"))
        #expect(source.contains("DesktopChatComposerTextView("))
        #expect(source.contains("DesktopChatArtifactPreviewRail"))
        #expect(source.contains("DesktopChatArtifactPreviewTrigger"))
    }

    @Test("chat composer keyboard policy submits only command return")
    @MainActor
    func chatComposerKeyboardPolicySubmitsOnlyCommandReturn() {
        #expect(
            DesktopChatComposerKeyPolicy.action(
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode,
                modifiers: [.command]
            ) == .submit
        )
        #expect(
            DesktopChatComposerKeyPolicy.action(
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode,
                modifiers: [.control]
            ) == .insertNewline
        )
    }

    @Test("chat composer AppKit return commands follow the same submit policy")
    @MainActor
    func chatComposerAppKitReturnCommandsFollowTheSameSubmitPolicy() {
        #expect(
            DesktopChatComposerReturnCommandPolicy.action(
                selector: #selector(NSTextView.insertNewline(_:)),
                modifiers: [.command]
            ) == .submit
        )
        #expect(
            DesktopChatComposerReturnCommandPolicy.action(
                selector: #selector(NSTextView.insertLineBreak(_:)),
                modifiers: [.command]
            ) == .submit
        )
        #expect(
            DesktopChatComposerReturnCommandPolicy.action(
                selector: #selector(NSTextView.insertNewlineIgnoringFieldEditor(_:)),
                modifiers: [.control]
            ) == .insertNewline
        )
        #expect(
            DesktopChatComposerReturnCommandPolicy.action(
                selector: #selector(NSTextView.deleteBackward(_:)),
                modifiers: [.command]
            ) == .passThrough
        )
    }

    @Test("chat composer handles command return as a key equivalent")
    @MainActor
    func chatComposerHandlesCommandReturnAsAKeyEquivalent() throws {
        let textView = DesktopChatComposerCommandSubmitTextView()
        textView.string = "Send this prompt"
        var submittedText: String?
        textView.onCommandSubmit = { currentText in
            submittedText = currentText
            return true
        }
        let event = try #require(
            NSEvent.keyEvent(
                with: .keyDown,
                location: .zero,
                modifierFlags: [.command],
                timestamp: 0,
                windowNumber: 0,
                context: nil,
                characters: "\r",
                charactersIgnoringModifiers: "\r",
                isARepeat: false,
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode
            )
        )

        #expect(textView.performKeyEquivalent(with: event))
        #expect(submittedText == "Send this prompt")
    }

    @Test("chat composer local key monitor consumes command return")
    @MainActor
    func chatComposerLocalKeyMonitorConsumesCommandReturn() throws {
        let textView = DesktopChatComposerCommandSubmitTextView()
        textView.string = "Send from local monitor"
        var submittedText: String?
        textView.onCommandSubmit = { currentText in
            submittedText = currentText
            return true
        }
        let event = try #require(
            NSEvent.keyEvent(
                with: .keyDown,
                location: .zero,
                modifierFlags: [.command],
                timestamp: 0,
                windowNumber: 0,
                context: nil,
                characters: "\r",
                charactersIgnoringModifiers: "\r",
                isARepeat: false,
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode
            )
        )

        #expect(textView.handleLocalKeyDown(event))
        #expect(submittedText == "Send from local monitor")
    }

    @Test("chat composer scroll view handles command return key equivalents")
    @MainActor
    func chatComposerScrollViewHandlesCommandReturnKeyEquivalents() throws {
        let scrollView = DesktopChatComposerCommandSubmitScrollView()
        let textView = DesktopChatComposerCommandSubmitTextView()
        textView.string = "Send from scroll key equivalent"
        scrollView.commandSubmitTextView = textView
        scrollView.documentView = textView
        var submittedText: String?
        textView.onCommandSubmit = { currentText in
            submittedText = currentText
            return true
        }
        let event = try #require(
            NSEvent.keyEvent(
                with: .keyDown,
                location: .zero,
                modifierFlags: [.command],
                timestamp: 0,
                windowNumber: 0,
                context: nil,
                characters: "\r",
                charactersIgnoringModifiers: "\r",
                isARepeat: false,
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode
            )
        )

        #expect(scrollView.performKeyEquivalent(with: event))
        #expect(submittedText == "Send from scroll key equivalent")
    }

    @Test("chat session workspace renders the server required state when no server is running")
    @MainActor
    func chatSessionWorkspaceRendersTheServerRequiredStateWhenNoServerIsRunning() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
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
        try bindSelectedChatSessionToPrimaryServer(viewModel)

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
        try bindSelectedChatSessionToPrimaryServer(viewModel)
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

    @Test("image workspace folds advanced defaults by default")
    @MainActor
    func imageWorkspaceFoldsAdvancedDefaultsByDefault() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeMenuBarImageModelSummary()]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: .constant(.generate),
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )
        let renderedTexts = renderedTextValues(in: view)

        #expect(view.subviews.isEmpty == false)
        #expect(DesktopImageWorkspaceDefaults.showsAdvancedDefaults == false)
        #expect(DesktopImageWorkspaceDefaults.advancedDefaultsTitle == "Advanced Image Defaults")
        #expect(renderedTexts.contains(viewModel.imageSize))
        #expect(renderedTexts.contains("Steps") == false)
        #expect(renderedTexts.contains("Guidance") == false)
        #expect(renderedTexts.contains("Negative prompt") == false)
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

    @Test("image empty state buttons dispatch workspace and model navigation")
    @MainActor
    func imageEmptyStateButtonsDispatchWorkspaceAndModelNavigation() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let sidebar = DesktopImageJobsSidebar(viewModel: viewModel)
        let view = hostView(sidebar)

        sidebar.openImageWorkspaceAction()
        #expect(viewModel.selectedSurface == .image)

        sidebar.chooseModelAction()
        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .models)
        #expect(viewModel.selectedToolSection == .modelsLibrary)
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

private enum DesktopFoundationTestError: Error {
    case repositoryRootNotFound
}

private func repositoryRootForDesktopFoundationTests(
    startingAt start: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
) throws -> URL {
    var current = start
    for _ in 0..<8 {
        let designSystemLogo = current.appendingPathComponent("docs/design-system/assets/melix_logo.svg")
        let appLogo = current.appendingPathComponent(
            "apps/macos-menubar/Sources/AppMain/Resources/Branding/melix_logo.svg"
        )
        if FileManager.default.fileExists(atPath: current.appendingPathComponent("AGENTS.md").path),
           FileManager.default.fileExists(atPath: designSystemLogo.path),
           FileManager.default.fileExists(atPath: appLogo.path)
        {
            return current
        }
        let parent = current.deletingLastPathComponent()
        guard parent.path != current.path else {
            break
        }
        current = parent
    }
    throw DesktopFoundationTestError.repositoryRootNotFound
}

private extension String {
    func slice(from startMarker: String, to endMarker: String) -> String? {
        guard let startRange = range(of: startMarker),
              let endRange = range(of: endMarker, range: startRange.upperBound..<endIndex)
        else {
            return nil
        }
        return String(self[startRange.lowerBound..<endRange.lowerBound])
    }
}

@Suite("Phase 8 Window UI Acceptance Runner", .serialized)
struct Phase8WindowUIAcceptanceRunnerTests {
    @Test("phase 8 window ui acceptance config normalizes blank environment values")
    func phase8WindowUIAcceptanceConfigNormalizesBlankEnvironmentValues() throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-window-ui-config-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let melixHome = tempRoot.appendingPathComponent("melix-home", isDirectory: true)
        let cliBundlePath = melixHome
            .appendingPathComponent("acceptance/phase8/cli/2026-04-09T162920Z/bundle.json")
        try fileManager.createDirectory(
            at: cliBundlePath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("{\"surface\":\"cli\"}\n".utf8).write(to: cliBundlePath)

        let config = Phase8WindowUIAcceptanceConfig(
            environment: [
                "MELIX_HOME": melixHome.path,
                "MELIX_REPO_ROOT": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TRAINING_FIXTURE": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES": " smoke , latency ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES": " mmlu , gsm8k ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_DATASET": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_SERVER_SESSION_ID": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH": "   ",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP": "   ",
            ]
        )

        #expect(config.repoRoot == FileManager.default.currentDirectoryPath)
        #expect(config.melixHome == melixHome.path)
        #expect(config.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(config.localModelPath.isEmpty)
        #expect(config.trainingFixture == "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1")
        #expect(config.benchSuites == ["smoke", "latency"])
        #expect(config.matrixSuites == ["smoke"])
        #expect(config.evaluationSuites == ["mmlu", "gsm8k"])
        #expect(config.evaluationDataset == "mmlu.dev.v1")
        #expect(config.serverSessionID == "server-session-1")
        #expect(
            URL(fileURLWithPath: config.cliEvidenceBundlePath).resolvingSymlinksInPath().path
                == cliBundlePath.resolvingSymlinksInPath().path
        )
        #expect(config.timestamp.isEmpty == false)
    }

    @Test("phase 8 window ui downloads surface exposes quantization modes")
    @MainActor
    func phase8WindowUIDownloadsSurfaceExposesQuantizationModes() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)
        viewModel.selectedQuantizationMode = .qat

        let view = hostView(DesktopDownloadsToolSectionView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(RuntimeQuantizationMode.ptq.id == "ptq")
        #expect(RuntimeQuantizationMode.ptq.title == "PTQ")
        #expect(RuntimeQuantizationMode.qat.id == "qat")
        #expect(RuntimeQuantizationMode.qat.title == "QAT")
        #expect(viewModel.selectedQuantizationMode == .qat)
    }

    @Test("phase 8 window ui release gate requires top-level and case-level real CLI evidence")
    func phase8WindowUIReleaseGateRequiresRealCLIEvidence() throws {
        let dryRunBundle = try decodePhase8Issue365CLIBundle(
            #"""
            {
              "execution_mode": "dry-run",
              "release_ready": false,
              "cases": [
                {
                  "case_id": "lora_export_inference",
                  "status": "planned",
                  "evidence_tier": "deterministic_dry_run",
                  "release_ready": false
                }
              ]
            }
            """#
        )
        let dryRunGate = Phase8WindowUIReleaseGateResolver.releaseGate(
            cliCaseID: "lora_export_inference",
            cliEvidenceBundle: dryRunBundle
        )
        #expect(dryRunGate.releaseReady == false)
        #expect(dryRunGate.releaseReadyBlocker == "real_local_runtime_matrix_not_run")
        #expect(dryRunGate.cliExecutionMode == "dry-run")
        #expect(dryRunGate.cliCaseStatus == "planned")
        #expect(dryRunGate.cliCaseEvidenceTier == "deterministic_dry_run")

        let unreadyBundle = try decodePhase8Issue365CLIBundle(
            #"""
            {
              "execution_mode": "real",
              "release_ready": false,
              "cases": [
                {
                  "case_id": "lora_export_inference",
                  "status": "succeeded",
                  "evidence_tier": "real_local_runtime",
                  "release_ready": true
                }
              ]
            }
            """#
        )
        let unreadyGate = Phase8WindowUIReleaseGateResolver.releaseGate(
            cliCaseID: "lora_export_inference",
            cliEvidenceBundle: unreadyBundle
        )
        #expect(unreadyGate.releaseReady == false)
        #expect(unreadyGate.releaseReadyBlocker == "real_local_runtime_bundle_not_release_ready")
        #expect(unreadyGate.cliCaseReleaseReady == true)

        let missingCaseBundle = try decodePhase8Issue365CLIBundle(
            #"""
            {
              "execution_mode": "real",
              "release_ready": true,
              "cases": []
            }
            """#
        )
        let missingCaseGate = Phase8WindowUIReleaseGateResolver.releaseGate(
            cliCaseID: "lora_export_inference",
            cliEvidenceBundle: missingCaseBundle
        )
        #expect(missingCaseGate.releaseReady == false)
        #expect(missingCaseGate.releaseReadyBlocker == "real_local_runtime_case_missing:lora_export_inference")
        #expect(missingCaseGate.cliCaseStatus == "")

        let failedCaseBundle = try decodePhase8Issue365CLIBundle(
            #"""
            {
              "execution_mode": "real",
              "release_ready": true,
              "cases": [
                {
                  "case_id": "lora_export_inference",
                  "status": "failed",
                  "evidence_tier": "real_local_runtime",
                  "release_ready": false
                }
              ]
            }
            """#
        )
        let failedCaseGate = Phase8WindowUIReleaseGateResolver.releaseGate(
            cliCaseID: "lora_export_inference",
            cliEvidenceBundle: failedCaseBundle
        )
        #expect(failedCaseGate.releaseReady == false)
        #expect(failedCaseGate.releaseReadyBlocker == "real_local_runtime_case_not_release_ready:lora_export_inference")
        #expect(failedCaseGate.cliCaseStatus == "failed")
    }

    @Test("phase 8 fixture export response surfaces write failures")
    func phase8FixtureExportResponseSurfacesWriteFailures() {
        let command = MelixCLICommand.benchExportCSV(
            .init(jobID: "bench-newer", outputPath: "/dev/null/bench.csv", json: true)
        )

        let result = makePhase8FixtureExportResponse(
            command: command,
            jobID: "bench-newer",
            outputPath: "/dev/null/bench.csv",
            rowCount: 1,
            contents: "metric,value\nbench,1\n"
        )

        switch result {
        case .success(let output):
            Issue.record("expected fixture export write failure, got \(output)")
        case .failure(let error):
            #expect(error.failureKind == .processFailed)
            #expect(error.errorDescription?.contains("Failed to write fixture export") == true)
        }
    }

    @Test("phase 8 window ui acceptance runner writes a screenshot and evidence bundle")
    @MainActor
    func phase8WindowUIAcceptanceRunnerWritesEvidenceBundle() async throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-window-ui-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let cliBundlePath = tempRoot
            .appendingPathComponent("melix-home", isDirectory: true)
            .appendingPathComponent("acceptance/phase8/cli/2026-04-09T162920Z/bundle.json")
        try fileManager.createDirectory(
            at: cliBundlePath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data(makeIssue365ReleaseReadyCLIBundleJSON().utf8).write(to: cliBundlePath)
        let materializedModelID = "melix-dev-qwen-local"
        let derivedModelID = "\(materializedModelID)-lora-adapter"

        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var baseModel = ModelCatalog.devTextModel()
        baseModel.modelID = "melix-dev-text"
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = derivedModelID
        snapshot.models = [baseModel, derivedModel]
        var runtimeSession = makeDesktopRuntimeSession()
        runtimeSession.serverSessionID = "server-session-1"
        runtimeSession.lifecycleState = .ready
        runtimeSession.powerState = .active
        snapshot.runtimeSessions = [runtimeSession]
        await client.configureSnapshot(snapshot)
        await configurePhase8ReadyRegistrySnapshot(client, modelID: materializedModelID)

        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await workflowRunner.configureHandler { command in
            switch command {
            case .modelImport(let options):
                return .success(
                    makeManagedModelReceiptJSON(
                        modelID: options.modelID,
                        managedModelPath: "/tmp/melix-managed/\(options.modelID)",
                        sourceKind: "local_path",
                        sourceLocator: options.path
                    )
                )
            case .modelRootsRescan:
                return .success("{\"registry_roots\":[\"/tmp/melix-managed\"]}\n")
            case .serverSessionCreate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionUpdate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionSelect:
                return .success("{\"selected_server_session_id\":\"server-session-1\"}\n")
            case .serverStart(let options):
                return .success(makeCLIServerSnapshotJSON(serverSessionID: options.serverSessionID))
            case .chatRun(let options):
                let assistantText = options.modelID == derivedModelID ? "DERIVED_OK" : "BASE_OK"
                return .success(
                    """
                    {
                      "model_id": "\(options.modelID)",
                      "server_session_id": "server-session-1",
                      "assistant_text": "\(assistantText)",
                      "finish_reason": "stop",
                      "request_id": "chat-\(assistantText.lowercased())"
                    }
                    """
                )
            case .loraTrain(let options):
                return .success(
                    """
                    {
                      "operation": "train_lora",
                      "job_id": "model-ops-0001",
                      "source_model": "\(options.modelID)",
                      "output_path": "/tmp/melix-train-lora/model-ops-0001/adapters.safetensors",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
                    }
                    """
                )
            case .loraActivate(let options):
                return .success(
                    """
                    {
                      "operation": "activate_adapter",
                      "job_id": "model-ops-0002",
                      "source_model": "\(options.modelID)",
                      "output_path": "/tmp/melix-activate/model-ops-0002/manifest.json",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                      "derived_model_id": "\(derivedModelID)",
                      "derived_model_path": "/tmp/melix-activate/model-ops-0002/derived"
                    }
                    """
                )
            case .benchRun:
                return .success(makeCLIBenchRunJSON())
            case .benchMatrixRun:
                return .success(makeCLIBenchmarkMatrixRunJSON(jobID: "matrix-newer"))
            case .evalRun:
                return .success(makeCLIEvaluationRunJSON(jobID: "eval-newer"))
            case .benchExportCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "metric,value\nbench,1\n"
                )
            case .benchMatrixExportSummaryCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "suite,ttft_ms\nsmoke,21.1\n"
                )
            case .benchMatrixExportRequestsCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "request,latency_ms\n0,28.7\n"
                )
            case .evalExportSummaryCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "{\"ok\":true}\n"
                )
            case .evalExportSamplesCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "{\"ok\":true}\n"
                )
            case .evalExportSamplesJSONL(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "{\"ok\":true}\n"
                )
            default:
                return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
            }
        }

        let viewModel = RuntimeViewModel(client: client, cliWorkflowRunner: workflowRunner)
        let renderer = RecordingPhase8WindowUIRenderer()
        let runner = try Phase8WindowUIAcceptanceRunner(
            viewModel: viewModel,
            cliWorkflowRunner: workflowRunner,
            config: .init(
                repoRoot: tempRoot.path,
                melixHome: tempRoot.appendingPathComponent("melix-home", isDirectory: true).path,
                modelID: materializedModelID,
                localModelPath: tempRoot.appendingPathComponent("fixture-model", isDirectory: true).path,
                trainingFixture: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                benchSuites: ["smoke"],
                matrixSuites: ["smoke"],
                evaluationSuites: ["mmlu"],
                evaluationDataset: "mmlu.dev.v1",
                serverSessionID: "server-session-1",
                cliEvidenceBundlePath: cliBundlePath.path,
                timestamp: "2026-04-09T120000Z"
            ),
            renderer: renderer
        )

        let result = try await runner.run()

        #expect(FileManager.default.fileExists(atPath: result.bundlePath))
        #expect(FileManager.default.fileExists(atPath: result.screenshotPath))
        #expect((try Data(contentsOf: URL(fileURLWithPath: result.screenshotPath))).isEmpty == false)

        let bundleData = try Data(contentsOf: URL(fileURLWithPath: result.bundlePath))
        let bundleJSON = try #require(
            JSONSerialization.jsonObject(with: bundleData) as? [String: Any]
        )
        #expect(bundleJSON["cli_evidence_bundle_path"] as? String == cliBundlePath.path)
        #expect(bundleJSON["screenshot_path"] as? String == result.screenshotPath)
        let businessLines = try #require(bundleJSON["business_lines"] as? [[String: Any]])
        #expect(businessLines.count == 10)
        let caseIDs = Set(businessLines.compactMap { $0["case_id"] as? String })
        #expect(caseIDs == Set([
            "base_lora_export_local_inference",
            "base_qlora_export_local_inference",
            "base_dora_export_local_inference",
            "lora_dpo_export_local_inference",
            "lora_orpo_export_local_inference",
            "lora_cpo_export_local_inference",
            "lora_grpo_export_local_inference",
            "lora_rlhf_export_local_inference",
            "lora_preference_ptq_local_inference",
            "qat_quantized_local_inference",
        ]))
        #expect(businessLines.allSatisfy { $0["visible"] as? Bool == true })
        #expect(businessLines.allSatisfy { $0["selectable"] as? Bool == true })
        #expect(businessLines.allSatisfy { $0["runnable"] as? Bool == true })
        #expect(businessLines.allSatisfy { $0["inspectable"] as? Bool == true })
        #expect(businessLines.allSatisfy { $0["release_ready"] as? Bool == true })
        #expect(businessLines.allSatisfy { $0["release_ready_blocker"] as? String == "" })
        #expect(businessLines.allSatisfy { $0["evidence_level"] as? String == "window_route_matrix_with_real_cli_runtime" })
        #expect(businessLines.allSatisfy { $0["cli_execution_mode"] as? String == "real" })
        #expect(businessLines.allSatisfy { $0["cli_case_status"] as? String == "succeeded" })
        #expect(businessLines.allSatisfy { $0["cli_case_evidence_tier"] as? String == "real_local_runtime" })
        #expect(businessLines.allSatisfy { $0["cli_case_release_ready"] as? Bool == true })
        let loraLine = try #require(
            businessLines.first { $0["case_id"] as? String == "base_lora_export_local_inference" }
        )
        #expect(loraLine["cli_case_id"] as? String == "lora_export_inference")
        let dpoLine = try #require(businessLines.first { $0["case_id"] as? String == "lora_dpo_export_local_inference" })
        #expect(dpoLine["cli_case_id"] as? String == "lora_dpo_export_inference")
        #expect(dpoLine["routed_command"] as? String == "alignment.train")
        let qatLine = try #require(businessLines.first { $0["case_id"] as? String == "qat_quantized_local_inference" })
        #expect(qatLine["cli_case_id"] as? String == "qat_quantized_inference")
        #expect(qatLine["selected_quantization_mode"] as? String == "qat")
        #expect(qatLine["routed_command"] as? String == "model.quantize")

        let recordedCommands = await workflowRunner.snapshotRecordedCommands()
        #expect(recordedCommands.contains(where: {
            if case .modelImport = $0 { return true }
            return false
        }))
        #expect(recordedCommands.contains(where: {
            if case .serverStart = $0 { return true }
            return false
        }))
        #expect(recordedCommands.contains(where: {
            if case .loraTrain = $0 { return true }
            return false
        }))
        #expect(recordedCommands.contains(where: {
            if case .benchRun = $0 { return true }
            return false
        }))
        #expect(recordedCommands.contains(where: {
            if case .evalRun = $0 { return true }
            return false
        }))
        let evaluationCommand = try #require(recordedCommands.first(where: {
            if case .evalRun = $0 { return true }
            return false
        }))
        guard case .evalRun(let evaluationOptions) = evaluationCommand else {
            Issue.record("Expected the phase 8 acceptance runner to record an evalRun command.")
            return
        }
        #expect(evaluationOptions.parameters["scoring_mode"] == "multiple_choice_accuracy")
    }

    @Test("phase 8 window ui acceptance runner routes lora workflows through the materialized model id")
    @MainActor
    func phase8WindowUIAcceptanceRunnerRoutesLoraWorkflowsThroughMaterializedModel() async throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-window-ui-materialized-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let cliBundlePath = tempRoot
            .appendingPathComponent("melix-home", isDirectory: true)
            .appendingPathComponent("acceptance/phase8/cli/2026-04-09T162920Z/bundle.json")
        try fileManager.createDirectory(
            at: cliBundlePath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("{\"ok\":true}\n".utf8).write(to: cliBundlePath)

        let materializedModelID = "melix-dev-qwen-local"
        let derivedModelID = "\(materializedModelID)-lora-adapter"
        let adapterManifestPath = "/tmp/melix-train-lora/model-ops-0001/train_lora.adapter.json"
        let adapterWeightsPath = "/tmp/melix-train-lora/model-ops-0001/adapter/adapters.safetensors"

        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var fallbackTextModel = ModelCatalog.devTextModel()
        fallbackTextModel.modelID = "melix-dev-text"
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = derivedModelID
        snapshot.models = [fallbackTextModel, derivedModel]
        var runtimeSession = makeDesktopRuntimeSession()
        runtimeSession.serverSessionID = "server-session-1"
        runtimeSession.lifecycleState = .ready
        runtimeSession.powerState = .active
        snapshot.runtimeSessions = [runtimeSession]
        await client.configureSnapshot(snapshot)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: #"""
                {
                  "operation": "registry_snapshot",
                  "jobs": [],
                  "adapters": [],
                  "derived_models": [],
                  "model_registry": {
                    "scanned_at_unix_ms": 1712300000000,
                    "roots": [
                      {
                        "root_id": "root-managed",
                        "root_path": "/tmp/melix-managed",
                        "root_order": 0,
                        "accessible": true,
                        "error_code": "",
                        "error_message": "",
                        "discovered_model_ids": ["\#(materializedModelID)"]
                      }
                    ],
                    "models": [
                      {
                        "model_id": "\#(materializedModelID)",
                        "model_path": "/tmp/melix-managed/\#(materializedModelID)",
                        "model_kind": "text",
                        "revision": "main",
                        "max_context": 4096,
                        "ext": {
                          "melix.registry_model_name": "Qwen Local",
                          "melix.capability.supported_modalities": "text",
                          "melix.capability.supported_tasks": "generate",
                          "melix.capability.class": "text",
                          "melix.source_kind": "managed_import"
                        }
                      }
                    ]
                  }
                }
                """#
            ),
            forNamedOperation: "registry_snapshot"
        )

        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await workflowRunner.configureHandler { command in
            switch command {
            case .modelImport(let options):
                return .success(
                    makeManagedModelReceiptJSON(
                        modelID: options.modelID,
                        managedModelPath: "/tmp/melix-managed/\(options.modelID)",
                        sourceKind: "local_path",
                        sourceLocator: options.path
                    )
                )
            case .modelRootsRescan:
                return .success("{\"registry_roots\":[\"/tmp/melix-managed\"]}\n")
            case .serverSessionCreate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionUpdate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionSelect:
                return .success("{\"selected_server_session_id\":\"server-session-1\"}\n")
            case .serverStart(let options):
                return .success(makeCLIServerSnapshotJSON(serverSessionID: options.serverSessionID))
            case .chatRun(let options):
                let assistantText = options.modelID == derivedModelID ? "DERIVED_OK" : "BASE_OK"
                return .success(
                    """
                    {
                      "model_id": "\(options.modelID)",
                      "server_session_id": "server-session-1",
                      "assistant_text": "\(assistantText)",
                      "finish_reason": "stop",
                      "request_id": "chat-\(assistantText.lowercased())"
                    }
                    """
                )
            case .loraTrain(let options):
                guard options.modelID == materializedModelID else {
                    return .failure(
                        .processFailed(
                            commandID: command.workflowCommandID,
                            surface: .subprocess,
                            exitCode: 1,
                            stderr: "expected lora train to use \(materializedModelID), got \(options.modelID)"
                        )
                    )
                }
                return .success(
                    """
                    {
                      "operation": "train_lora",
                      "job_id": "model-ops-0001",
                      "source_model": "\(materializedModelID)",
                      "output_path": "\(adapterWeightsPath)",
                      "artifact_path": "\(adapterManifestPath)",
                      "weights_path": "\(adapterWeightsPath)",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
                    }
                    """
                )
            case .loraActivate(let options):
                guard options.modelID == materializedModelID else {
                    return .failure(
                        .processFailed(
                            commandID: command.workflowCommandID,
                            surface: .subprocess,
                            exitCode: 1,
                            stderr: "expected lora activate to use \(materializedModelID), got \(options.modelID)"
                        )
                    )
                }
                guard options.adapterPath == adapterManifestPath else {
                    return .failure(
                        .processFailed(
                            commandID: command.workflowCommandID,
                            surface: .subprocess,
                            exitCode: 1,
                            stderr: "expected lora activate to use \(adapterManifestPath), got \(options.adapterPath)"
                        )
                    )
                }
                return .success(
                    """
                    {
                      "operation": "activate_adapter",
                      "job_id": "model-ops-0002",
                      "source_model": "\(materializedModelID)",
                      "output_path": "/tmp/melix-activate/model-ops-0002/manifest.json",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                      "derived_model_id": "\(derivedModelID)",
                      "derived_model_path": "/tmp/melix-activate/model-ops-0002/derived"
                    }
                    """
                )
            case .benchRun:
                return .success(makeCLIBenchRunJSON())
            case .benchMatrixRun:
                return .success(makeCLIBenchmarkMatrixRunJSON(jobID: "matrix-newer"))
            case .evalRun:
                return .success(makeCLIEvaluationRunJSON(jobID: "eval-newer"))
            case .benchExportCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "metric,value\nbench,1\n"
                )
            case .benchMatrixExportSummaryCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "suite,ttft_ms\nsmoke,21.1\n"
                )
            case .benchMatrixExportRequestsCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "request,latency_ms\n0,28.7\n"
                )
            case .evalExportSummaryCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "{\"ok\":true}\n"
                )
            case .evalExportSamplesCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "{\"ok\":true}\n"
                )
            case .evalExportSamplesJSONL(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "{\"ok\":true}\n"
                )
            default:
                return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
            }
        }

        let runner = try Phase8WindowUIAcceptanceRunner(
            viewModel: RuntimeViewModel(client: client, cliWorkflowRunner: workflowRunner),
            cliWorkflowRunner: workflowRunner,
            config: .init(
                repoRoot: tempRoot.path,
                melixHome: tempRoot.appendingPathComponent("melix-home", isDirectory: true).path,
                modelID: materializedModelID,
                localModelPath: tempRoot.appendingPathComponent("fixture-model", isDirectory: true).path,
                trainingFixture: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                benchSuites: ["smoke"],
                matrixSuites: ["smoke"],
                evaluationSuites: ["mmlu"],
                evaluationDataset: "mmlu.dev.v1",
                serverSessionID: "server-session-1",
                cliEvidenceBundlePath: cliBundlePath.path,
                timestamp: "2026-04-09T120000Z"
            ),
            renderer: RecordingPhase8WindowUIRenderer()
        )

        let result = try await runner.run()
        #expect(FileManager.default.fileExists(atPath: result.bundlePath))

        let recordedCommands = await workflowRunner.snapshotRecordedCommands()
        let trainCommand = try #require(recordedCommands.first(where: {
            if case .loraTrain = $0 { return true }
            return false
        }))
        if case .loraTrain(let options) = trainCommand {
            #expect(options.modelID == materializedModelID)
        } else {
            Issue.record("expected a lora train command")
        }

        let activateCommand = try #require(recordedCommands.first(where: {
            if case .loraActivate = $0 { return true }
            return false
        }))
        if case .loraActivate(let options) = activateCommand {
            #expect(options.modelID == materializedModelID)
            #expect(options.adapterPath == adapterManifestPath)
        } else {
            Issue.record("expected a lora activate command")
        }
    }

    @Test("phase 8 window ui acceptance runner rejects lora train receipts without an adapter manifest path")
    @MainActor
    func phase8WindowUIAcceptanceRunnerRejectsMissingAdapterManifestPath() async throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-window-ui-missing-adapter-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let cliBundlePath = tempRoot
            .appendingPathComponent("melix-home", isDirectory: true)
            .appendingPathComponent("acceptance/phase8/cli/2026-04-09T162920Z/bundle.json")
        try fileManager.createDirectory(
            at: cliBundlePath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("{\"ok\":true}\n".utf8).write(to: cliBundlePath)

        let materializedModelID = "melix-dev-qwen-local"

        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var fallbackTextModel = ModelCatalog.devTextModel()
        fallbackTextModel.modelID = "melix-dev-text"
        var importedModel = ModelCatalog.devTextModel()
        importedModel.modelID = materializedModelID
        importedModel.kind = "text"
        importedModel.features = ["chat"]
        importedModel.settings.alias = "Qwen Local"
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = "\(materializedModelID)-lora-adapter"
        snapshot.models = [fallbackTextModel, importedModel, derivedModel]
        var runtimeSession = makeDesktopRuntimeSession()
        runtimeSession.serverSessionID = "server-session-1"
        runtimeSession.lifecycleState = .ready
        runtimeSession.powerState = .active
        snapshot.runtimeSessions = [runtimeSession]
        await client.configureSnapshot(snapshot)
        await configurePhase8ReadyRegistrySnapshot(client, modelID: materializedModelID)

        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await workflowRunner.configureHandler { command in
            switch command {
            case .modelImport(let options):
                return .success(
                    makeManagedModelReceiptJSON(
                        modelID: options.modelID,
                        managedModelPath: "/tmp/melix-managed/\(options.modelID)",
                        sourceKind: "local_path",
                        sourceLocator: options.path
                    )
                )
            case .modelRootsRescan:
                return .success("{\"registry_roots\":[\"/tmp/melix-managed\"]}\n")
            case .serverSessionCreate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionUpdate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionSelect:
                return .success("{\"selected_server_session_id\":\"server-session-1\"}\n")
            case .serverStart(let options):
                return .success(makeCLIServerSnapshotJSON(serverSessionID: options.serverSessionID))
            case .chatRun:
                return .success(
                    """
                    {
                      "model_id": "\(materializedModelID)",
                      "server_session_id": "server-session-1",
                      "assistant_text": "BASE_OK",
                      "finish_reason": "stop",
                      "request_id": "chat-base"
                    }
                    """
                )
            case .loraTrain(let options):
                return .success(
                    """
                    {
                      "operation": "train_lora",
                      "job_id": "model-ops-0001",
                      "source_model": "\(options.modelID)",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
                    }
                    """
                )
            default:
                return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
            }
        }

        let runner = try Phase8WindowUIAcceptanceRunner(
            viewModel: RuntimeViewModel(client: client, cliWorkflowRunner: workflowRunner),
            cliWorkflowRunner: workflowRunner,
            config: .init(
                repoRoot: tempRoot.path,
                melixHome: tempRoot.appendingPathComponent("melix-home", isDirectory: true).path,
                modelID: materializedModelID,
                localModelPath: tempRoot.appendingPathComponent("fixture-model", isDirectory: true).path,
                trainingFixture: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                benchSuites: ["smoke"],
                matrixSuites: ["smoke"],
                evaluationSuites: ["mmlu"],
                evaluationDataset: "mmlu.dev.v1",
                serverSessionID: "server-session-1",
                cliEvidenceBundlePath: cliBundlePath.path,
                timestamp: "2026-04-09T120000Z"
            ),
            renderer: RecordingPhase8WindowUIRenderer()
        )

        do {
            _ = try await runner.run()
            Issue.record("expected the acceptance runner to reject the missing adapter manifest path")
        } catch let error as Phase8WindowUIAcceptanceError {
            switch error {
            case .missingAdapterManifestPath:
                break
            default:
                Issue.record("expected missingAdapterManifestPath, got \(error)")
            }
        } catch {
            Issue.record("expected Phase8WindowUIAcceptanceError, got \(error)")
        }
    }

    @Test("phase 8 window ui acceptance runner surfaces renderer failures")
    @MainActor
    func phase8WindowUIAcceptanceRunnerSurfacesRendererFailures() async throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-window-ui-failure-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let cliBundlePath = tempRoot
            .appendingPathComponent("melix-home", isDirectory: true)
            .appendingPathComponent("acceptance/phase8/cli/2026-04-09T162920Z/bundle.json")
        try fileManager.createDirectory(
            at: cliBundlePath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("{\"ok\":true}\n".utf8).write(to: cliBundlePath)
        let materializedModelID = "melix-dev-qwen-local"
        let derivedModelID = "\(materializedModelID)-lora-adapter"

        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        snapshot.runtimeSessions = [makeDesktopRuntimeSession()]
        await client.configureSnapshot(snapshot)
        await configurePhase8ReadyRegistrySnapshot(client, modelID: materializedModelID)

        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await workflowRunner.configureHandler { command in
            switch command {
            case .modelImport(let options):
                return .success(
                    makeManagedModelReceiptJSON(
                        modelID: options.modelID,
                        managedModelPath: "/tmp/melix-managed/\(options.modelID)",
                        sourceKind: "local_path",
                        sourceLocator: options.path
                    )
                )
            case .modelRootsRescan:
                return .success("{\"registry_roots\":[\"/tmp/melix-managed\"]}\n")
            case .serverSessionUpdate:
                return .success("{\"server_session_id\":\"server-session-1\"}\n")
            case .serverSessionSelect:
                return .success("{\"selected_server_session_id\":\"server-session-1\"}\n")
            case .serverStart(let options):
                return .success(makeCLIServerSnapshotJSON(serverSessionID: options.serverSessionID))
            case .chatRun:
                return .success(
                    """
                    {
                      "model_id": "melix-dev-text",
                      "server_session_id": "server-session-1",
                      "assistant_text": "BASE_OK",
                      "finish_reason": "stop",
                      "request_id": "chat-base"
                    }
                    """
                )
            case .loraTrain(let options):
                return .success(
                    """
                    {
                      "operation": "train_lora",
                      "job_id": "model-ops-0001",
                      "source_model": "\(options.modelID)",
                      "output_path": "/tmp/melix-train-lora/model-ops-0001/adapters.safetensors",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
                    }
                    """
                )
            case .loraActivate(let options):
                return .success(
                    """
                    {
                      "operation": "activate_adapter",
                      "job_id": "model-ops-0002",
                      "source_model": "\(options.modelID)",
                      "output_path": "/tmp/melix-activate/model-ops-0002/manifest.json",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                      "derived_model_id": "\(derivedModelID)",
                      "derived_model_path": "/tmp/melix-activate/model-ops-0002/derived"
                    }
                    """
                )
            case .benchRun:
                return .success(makeCLIBenchRunJSON())
            case .benchMatrixRun:
                return .success(makeCLIBenchmarkMatrixRunJSON(jobID: "matrix-newer"))
            case .evalRun:
                return .success(makeCLIEvaluationRunJSON(jobID: "eval-newer"))
            case .benchExportCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "ok\n"
                )
            case .benchMatrixExportSummaryCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "ok\n"
                )
            case .benchMatrixExportRequestsCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "ok\n"
                )
            case .evalExportSummaryCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "ok\n"
                )
            case .evalExportSamplesCSV(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "ok\n"
                )
            case .evalExportSamplesJSONL(let options):
                return makePhase8FixtureExportResponse(
                    command: command,
                    jobID: options.jobID,
                    outputPath: options.outputPath,
                    rowCount: 1,
                    contents: "ok\n"
                )
            default:
                return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
            }
        }

        let runner = try Phase8WindowUIAcceptanceRunner(
            viewModel: RuntimeViewModel(client: client, cliWorkflowRunner: workflowRunner),
            cliWorkflowRunner: workflowRunner,
            config: .init(
                repoRoot: tempRoot.path,
                melixHome: tempRoot.appendingPathComponent("melix-home", isDirectory: true).path,
                modelID: materializedModelID,
                localModelPath: tempRoot.appendingPathComponent("fixture-model", isDirectory: true).path,
                trainingFixture: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                benchSuites: ["smoke"],
                matrixSuites: ["smoke"],
                evaluationSuites: ["mmlu"],
                evaluationDataset: "mmlu.dev.v1",
                serverSessionID: "server-session-1",
                cliEvidenceBundlePath: cliBundlePath.path,
                timestamp: "2026-04-09T120000Z"
            ),
            renderer: FailingPhase8WindowUIRenderer()
        )

        do {
            _ = try await runner.run()
            Issue.record("expected the acceptance runner to surface the renderer failure")
        } catch let error as Phase8WindowUIAcceptanceError {
            switch error {
            case .screenshotRenderFailed:
                break
            default:
                Issue.record("expected screenshotRenderFailed, got \(error)")
            }
        } catch {
            Issue.record("expected Phase8WindowUIAcceptanceError, got \(error)")
        }
    }
}

@MainActor
private final class RecordingPhase8WindowUIRenderer: Phase8WindowUIRendering {
    func render(viewModel: RuntimeViewModel, to outputURL: URL, size: CGSize) throws {
        _ = viewModel
        _ = size
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("png".utf8).write(to: outputURL)
    }
}

private func makePhase8FixtureExportResponse(
    command: MelixCLICommand,
    jobID: String,
    outputPath: String,
    rowCount: Int,
    contents: String
) -> Result<String, MelixCLIWorkflowError> {
    let outputURL = URL(fileURLWithPath: outputPath)
    do {
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data(contents.utf8).write(to: outputURL)
        return .success(
            makeCLIExportResponseJSON(
                jobID: jobID,
                outputPath: outputPath,
                rowCount: rowCount
            )
        )
    } catch {
        return .failure(
            .processFailed(
                commandID: command.workflowCommandID,
                surface: .subprocess,
                exitCode: 1,
                stderr: "Failed to write fixture export at \(outputPath): \(error)"
            )
        )
    }
}

private func makeIssue365ReleaseReadyCLIBundleJSON() -> String {
    #"""
    {
      "schema_version": "melix.issue365.acceptance_bundle.v1",
      "execution_mode": "real",
      "release_ready": true,
      "known_gaps": [],
      "summary": {
        "case_count": 10,
        "succeeded_count": 10,
        "failed_count": 0,
        "blocked_count": 0,
        "release_ready_case_count": 10,
        "release_ready": true
      },
      "cases": [
        {
          "case_id": "lora_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "qlora_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "dora_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "lora_dpo_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "lora_orpo_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "lora_cpo_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "lora_grpo_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "lora_rlhf_export_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "lora_preference_ptq_quantized_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        },
        {
          "case_id": "qat_quantized_inference",
          "status": "succeeded",
          "evidence_tier": "real_local_runtime",
          "release_ready": true
        }
      ]
    }
    """#
}

private func decodePhase8Issue365CLIBundle(_ json: String) throws -> Phase8Issue365CLIEvidenceBundle {
    try JSONDecoder().decode(Phase8Issue365CLIEvidenceBundle.self, from: Data(json.utf8))
}

@MainActor
private struct FailingPhase8WindowUIRenderer: Phase8WindowUIRendering {
    func render(viewModel: RuntimeViewModel, to outputURL: URL, size: CGSize) throws {
        _ = viewModel
        _ = outputURL
        _ = size
        throw CocoaError(.fileWriteUnknown)
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
private func hostView<Content: View>(_ rootView: Content, size: CGSize) -> NSView {
    let controller = NSHostingController(rootView: rootView)
    let view = controller.view
    view.frame = NSRect(origin: .zero, size: size)
    view.layoutSubtreeIfNeeded()
    return view
}

@MainActor
private func renderedTextValues(in rootView: NSView) -> [String] {
    var values: [String] = []
    var visitedObjects = Set<ObjectIdentifier>()

    func appendValue(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty == false {
            values.append(trimmed)
        }
    }

    func accessibilityString(_ object: NSObject, selectorName: String) -> String? {
        let selector = NSSelectorFromString(selectorName)
        guard object.responds(to: selector),
              let value = object.perform(selector)?.takeUnretainedValue() as? String
        else {
            return nil
        }
        return value
    }

    func accessibilityChildren(_ object: NSObject) -> [Any] {
        let selector = NSSelectorFromString("accessibilityChildren")
        guard object.responds(to: selector),
              let children = object.perform(selector)?.takeUnretainedValue() as? [Any]
        else {
            return []
        }
        return children
    }

    func visitAccessibilityElement(_ element: Any) {
        if let view = element as? NSView {
            visit(view)
            return
        }
        guard let object = element as? NSObject else {
            return
        }
        let identifier = ObjectIdentifier(object)
        guard visitedObjects.insert(identifier).inserted else {
            return
        }
        appendValue(accessibilityString(object, selectorName: "accessibilityLabel") ?? "")
        appendValue(accessibilityString(object, selectorName: "accessibilityValue") ?? "")
        appendValue(accessibilityString(object, selectorName: "accessibilityHelp") ?? "")
        for child in accessibilityChildren(object) {
            visitAccessibilityElement(child)
        }
    }

    func visit(_ view: NSView) {
        let identifier = ObjectIdentifier(view)
        guard visitedObjects.insert(identifier).inserted else {
            return
        }
        appendValue(view.accessibilityLabel() ?? "")
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
        for child in view.accessibilityChildren() ?? [] {
            visitAccessibilityElement(child)
        }
    }

    visit(rootView)
    return values
}

@MainActor
private func renderedButtons(in rootView: NSView) -> [NSButton] {
    var buttons: [NSButton] = []

    func visit(_ view: NSView) {
        if let button = view as? NSButton {
            buttons.append(button)
        }
        for subview in view.subviews {
            visit(subview)
        }
    }

    visit(rootView)
    return buttons
}

@MainActor
private func accessibilityPressElement(labeled targetLabel: String, in rootView: NSView) -> Bool {
    var visitedObjects = Set<ObjectIdentifier>()

    func accessibilityString(_ object: NSObject, selectorName: String) -> String? {
        let selector = NSSelectorFromString(selectorName)
        guard object.responds(to: selector),
              let value = object.perform(selector)?.takeUnretainedValue() as? String
        else {
            return nil
        }
        return value
    }

    func accessibilityChildren(_ object: NSObject) -> [Any] {
        let selector = NSSelectorFromString("accessibilityChildren")
        guard object.responds(to: selector),
              let children = object.perform(selector)?.takeUnretainedValue() as? [Any]
        else {
            return []
        }
        return children
    }

    func press(_ object: NSObject) -> Bool {
        if let button = object as? NSButton,
           button.title == targetLabel || button.accessibilityLabel() == targetLabel {
            button.performClick(nil)
            return true
        }
        guard accessibilityString(object, selectorName: "accessibilityLabel") == targetLabel else {
            return false
        }
        let selector = NSSelectorFromString("accessibilityPerformPress")
        guard object.responds(to: selector) else {
            return false
        }
        _ = object.perform(selector)
        return true
    }

    func visitAccessibilityElement(_ element: Any) -> Bool {
        if let view = element as? NSView {
            return visit(view)
        }
        guard let object = element as? NSObject else {
            return false
        }
        let identifier = ObjectIdentifier(object)
        guard visitedObjects.insert(identifier).inserted else {
            return false
        }
        if press(object) {
            return true
        }
        for child in accessibilityChildren(object) where visitAccessibilityElement(child) {
            return true
        }
        return false
    }

    func visit(_ view: NSView) -> Bool {
        let identifier = ObjectIdentifier(view)
        guard visitedObjects.insert(identifier).inserted else {
            return false
        }
        if press(view) {
            return true
        }
        for subview in view.subviews where visit(subview) {
            return true
        }
        for child in view.accessibilityChildren() ?? [] where visitAccessibilityElement(child) {
            return true
        }
        return false
    }

    return visit(rootView)
}

private func expectedDesktopJobTimestampText(_ unixMS: Int64) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = .current
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss zzz"
    return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(unixMS) / 1_000))
}

@MainActor
private func bindSelectedChatSessionToPrimaryServer(_ viewModel: RuntimeViewModel) throws {
    let serverSessionID = try #require(viewModel.selectedServerSession?.id)
    viewModel.bindSelectedChatSessionToServer(serverSessionID: serverSessionID)
}

@MainActor
private final class CommandCenterOpenRecorder {
    private(set) var wasOpened = false

    func open() {
        wasOpened = true
    }
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

private func waitForRecordedClientAction(
    _ expectedAction: String,
    client: FakeControlPlaneXPCClient,
    timeout: Duration = .seconds(2),
    pollInterval: Duration = .milliseconds(10)
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await client.recordedActions.contains(expectedAction) {
            return
        }
        try await Task.sleep(for: pollInterval)
    }

    throw MenuBarTestError(description: "expected recorded client action \(expectedAction)")
}

private func waitForRecordedCLICommandCount(
    _ expectedCount: Int,
    runner: RecordingCLIWorkflowRunner,
    description: String,
    timeout: Duration = .seconds(2),
    pollInterval: Duration = .milliseconds(10)
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await runner.snapshotRecordedCommands().count == expectedCount {
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

private func configurePhase8ReadyRegistrySnapshot(
    _ client: FakeControlPlaneXPCClient,
    modelID: String,
    modelName: String = "Qwen Local",
    rootPath: String = "/tmp/melix-managed"
) async {
    await client.configureModelOperation(
        makeNamedModelOperationResult(
            operation: "registry_snapshot",
            outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
            manifestJSON: makePhase8ReadyRegistrySnapshotManifest(
                modelID: modelID,
                modelName: modelName,
                rootPath: rootPath
            )
        ),
        forNamedOperation: "registry_snapshot"
    )
}

private func makePhase8ReadyRegistrySnapshotManifest(
    modelID: String,
    modelName: String,
    rootPath: String
) -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [],
      "adapters": [],
      "derived_models": [],
      "model_registry": {
        "scanned_at_unix_ms": 1712300000000,
        "roots": [
          {
            "root_id": "root-managed",
            "root_path": "\#(rootPath)",
            "root_order": 0,
            "accessible": true,
            "error_code": "",
            "error_message": "",
            "discovered_model_ids": ["\#(modelID)"]
          }
        ],
        "models": [
          {
            "model_id": "\#(modelID)",
            "model_path": "\#(rootPath)/\#(modelID)",
            "model_kind": "text",
            "revision": "main",
            "max_context": 4096,
            "ext": {
              "melix.registry_model_name": "\#(modelName)",
              "melix.capability.supported_modalities": "text",
              "melix.capability.supported_tasks": "generate",
              "melix.capability.class": "text",
              "melix.source_kind": "managed_import"
            }
          }
        ]
      }
    }
    """#
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

private func makeTrainingWorkspaceRegistrySnapshotManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [
        {
          "job_id": "job-1",
          "operation": "train_lora",
          "source_model": "melix-dev-text",
          "status": "completed",
          "stage": "packaged",
          "pct": 1.0,
          "output_path": "/tmp/phase8/job-1/manifest.json",
          "manifest": {
            "adapter_name": "qwen35-acceptance",
            "dataset_uri": "HuggingFaceH4/ultrachat_200k",
            "target_repo": "melix/qwen35-acceptance",
            "preset_id": "quality_adapter",
            "preset_title": "Quality Adapter",
            "checkpoint_count": 3,
            "resume_ready": true,
            "tokens_per_second": 58.4,
            "peak_memory_gb": 6.8
          }
        },
        {
          "job_id": "job-2",
          "operation": "train_lora",
          "source_model": "melix-dev-text",
          "status": "completed",
          "stage": "packaged",
          "pct": 1.0,
          "output_path": "/tmp/phase8/job-2/manifest.json",
          "manifest": {
            "adapter_name": "qwen35-fallback",
            "dataset_uri": "datasets/melix-dev",
            "target_repo": "melix/qwen35-fallback",
            "preset_id": "balanced_adapter",
            "preset_title": "Balanced Adapter",
            "checkpoint_count": 1,
            "resume_ready": false,
            "tokens_per_second": 42.1,
            "peak_memory_gb": 5.4
          }
        }
      ],
      "adapters": [
        {
          "adapter_id": "adapter-1",
          "job_id": "job-1",
          "adapter_name": "qwen35-acceptance",
          "source_model": "melix-dev-text",
          "dataset_uri": "HuggingFaceH4/ultrachat_200k",
          "output_path": "/tmp/phase8/adapter-1/manifest.json",
          "activation_status": "activated",
          "derived_model_id": "melix-qwen35-acceptance",
          "derived_model_path": "/tmp/phase8/derived/model",
          "exportable_state": "ready",
          "published_state": "not_published",
          "target_repo": "melix/qwen35-acceptance",
          "published_repo": "",
          "status": "ready",
          "response_only": true,
          "gradient_checkpointing": true,
          "preset_id": "quality_adapter",
          "preset_title": "Quality Adapter",
          "checkpoint_count": 3,
          "resume_ready": true,
          "tokens_per_second": 58.4,
          "peak_memory_gb": 6.8,
          "training_duration_ms": 480000,
          "activation_duration_ms": 14000,
          "adapter_publish_ms": 0
        },
        {
          "adapter_id": "adapter-2",
          "job_id": "job-2",
          "adapter_name": "qwen35-fallback",
          "source_model": "melix-dev-text",
          "dataset_uri": "datasets/melix-dev",
          "output_path": "/tmp/phase8/adapter-2/manifest.json",
          "activation_status": "pending_activation",
          "derived_model_id": "",
          "derived_model_path": "",
          "exportable_state": "local_only",
          "published_state": "not_published",
          "target_repo": "",
          "published_repo": "",
          "status": "ready",
          "response_only": false,
          "gradient_checkpointing": false,
          "preset_id": "balanced_adapter",
          "preset_title": "Balanced Adapter",
          "checkpoint_count": 1,
          "resume_ready": false,
          "tokens_per_second": 42.1,
          "peak_memory_gb": 5.4,
          "training_duration_ms": 240000,
          "activation_duration_ms": 0,
          "adapter_publish_ms": 0
        }
      ],
      "experiment_groups": [
        {
          "group_id": "phase8-acceptance",
          "title": "Phase 8 Acceptance",
          "adapter_name": "qwen35-acceptance",
          "source_model": "melix-dev-text",
          "run_count": 2,
          "latest_preset_title": "Quality Adapter",
          "latest_tokens_per_second": 58.4,
          "latest_peak_memory_gb": 6.8,
          "latest_checkpoint_count": 3,
          "latest_resume_ready": true,
          "best_run_id": "run-best",
          "best_loss": 0.143,
          "recommended_manifest_path": "/tmp/phase8/best/manifest.json",
          "resume_ready_run_ids": ["run-best"],
          "checkpoint_lineage": [
            { "run_id": "run-best", "checkpoint_count": 3, "resume_ready": true },
            { "run_id": "run-prev", "checkpoint_count": 2, "resume_ready": false }
          ]
        },
        {
          "group_id": "phase8-fallback",
          "title": "Fallback Group",
          "adapter_name": "qwen35-fallback",
          "source_model": "melix-dev-text",
          "run_count": 1,
          "latest_preset_title": "Balanced Adapter",
          "latest_tokens_per_second": 42.1,
          "latest_peak_memory_gb": 5.4,
          "latest_checkpoint_count": 1,
          "latest_resume_ready": false,
          "best_run_id": "run-fallback",
          "best_loss": 0.271,
          "recommended_manifest_path": "",
          "resume_ready_run_ids": [],
          "checkpoint_lineage": []
        }
      ],
      "derived_models": [
        {
          "model_id": "melix-qwen35-acceptance",
          "model_path": "/tmp/phase8/derived/model",
          "adapter_set_hash": "adapter-alpha",
          "source_model": "melix-dev-text",
          "activation_mode": "fused_derived_model",
          "status": "activated"
        }
      ]
    }
    """#
}

private func makeResumeReadyExperimentGroupsRegistrySnapshotManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [],
      "adapters": [],
      "experiment_groups": [
        {
          "group_id": "phase8-acceptance",
          "title": "Phase 8 Acceptance",
          "adapter_name": "qwen35-acceptance",
          "source_model": "melix-dev-text",
          "run_count": 2,
          "latest_preset_title": "Quality Adapter",
          "latest_tokens_per_second": 58.4,
          "latest_peak_memory_gb": 6.8,
          "latest_checkpoint_count": 3,
          "latest_resume_ready": true,
          "best_run_id": "run-best",
          "best_loss": 0.143,
          "recommended_manifest_path": "/tmp/phase8/best/manifest.json",
          "resume_ready_run_ids": ["run-best"],
          "checkpoint_lineage": []
        }
      ],
      "derived_models": []
    }
    """#
}

private func makeExperimentGroupRegistrySnapshotManifest() -> String {
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
            "target_repo": "melix/adapters/melix-dev-adapter",
            "preset_id": "balanced_adapter",
            "preset_title": "Balanced Adapter",
            "checkpoint_count": 2,
            "resume_ready": true,
            "tokens_per_second": 128.5,
            "peak_memory_gb": 5.25
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
          "activation_status": "activated",
          "derived_model_id": "melix-dev-text-lora-adapter",
          "derived_model_path": "/tmp/melix-derived/model",
          "exportable_state": "ready",
          "published_state": "published",
          "target_repo": "melix/adapters/melix-dev-adapter",
          "published_repo": "melix/adapters/melix-dev-adapter",
          "status": "published",
          "response_only": true,
          "gradient_checkpointing": false,
          "preset_id": "balanced_adapter",
          "preset_title": "Balanced Adapter",
          "checkpoint_count": 2,
          "resume_ready": true,
          "tokens_per_second": 128.5,
          "peak_memory_gb": 5.25,
          "training_duration_ms": 1420.0,
          "activation_duration_ms": 321.0,
          "adapter_publish_ms": 118.0
        }
      ],
      "experiment_groups": [
        {
          "group_id": "nightly-qwen35",
          "title": "nightly-qwen35",
          "adapter_name": "melix-dev-adapter",
          "source_model": "melix-dev-text",
          "run_count": 2,
          "latest_preset_title": "Balanced Adapter",
          "latest_tokens_per_second": 128.5,
          "latest_peak_memory_gb": 5.25,
          "latest_checkpoint_count": 2,
          "latest_resume_ready": true,
          "best_loss": 0.33,
          "recommended_manifest_path": "/tmp/melix-train-lora/train_lora.adapter.json"
        }
      ],
      "derived_models": [
        {
          "model_id": "melix-dev-text-lora-adapter",
          "model_path": "/tmp/melix-derived/model",
          "adapter_set_hash": "adapter-alpha",
          "source_model": "melix-dev-text",
          "activation_mode": "adapter_backed_runtime",
          "status": "activated"
        }
      ]
    }
    """#
}

private func chatMarkdownFixture(named name: String) throws -> String {
    let fixtureURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
        .appendingPathComponent(name)
    return try String(contentsOf: fixtureURL, encoding: .utf8)
}

private func chatMarkdownBlockSnapshot(_ blocks: [DesktopChatMarkdownBlock]) -> String {
    blocks.flatMap { chatMarkdownBlockSnapshotLines($0, indent: 0) }
        .joined(separator: "\n")
}

private func attributedString(
    _ attributed: AttributedString,
    hasColoredRunCovering substring: String
) -> Bool {
    let plainText = String(attributed.characters)
    guard let range = plainText.range(of: substring) else {
        return false
    }
    let substringStart = plainText.distance(from: plainText.startIndex, to: range.lowerBound)
    let substringEnd = plainText.distance(from: plainText.startIndex, to: range.upperBound)

    return attributed.runs.contains { run in
        guard run.foregroundColor != nil else {
            return false
        }
        let runStart = attributed.characters.distance(
            from: attributed.characters.startIndex,
            to: run.range.lowerBound
        )
        let runEnd = attributed.characters.distance(
            from: attributed.characters.startIndex,
            to: run.range.upperBound
        )
        return runStart <= substringStart && runEnd >= substringEnd
    }
}

private func chatMarkdownLongStreamingSample(sectionCount: Int) -> String {
    (1...sectionCount)
        .map { index in
            """
            ## Section \(index)

            - item \(index)
            - cached \(index)

            ```swift
            let value\(index) = \(index)
            ```
            """
        }
        .joined(separator: "\n\n")
}

private func chatMarkdownBlockSnapshotLines(
    _ block: DesktopChatMarkdownBlock,
    indent: Int
) -> [String] {
    let prefix = String(repeating: "  ", count: indent)
    switch block {
    case .paragraph(let text):
        return ["\(prefix)paragraph: \(text)"]
    case .heading(let level, let text):
        return ["\(prefix)heading\(level): \(text)"]
    case .blockQuote(let children):
        return ["\(prefix)quote:"] + children.flatMap {
            chatMarkdownBlockSnapshotLines($0, indent: indent + 1)
        }
    case .unorderedList(let items):
        return ["\(prefix)unordered:"] + chatMarkdownListItemSnapshotLines(items, indent: indent + 1)
    case .orderedList(let start, let items):
        return ["\(prefix)ordered(\(start)):"]
            + chatMarkdownListItemSnapshotLines(items, indent: indent + 1)
    case .codeBlock(let language, let code):
        return [
            "\(prefix)code[\(language.isEmpty ? "plain" : language)]:",
            "\(prefix)  \(code.replacingOccurrences(of: "\n", with: "\\n"))",
        ]
    case .table(let header, let alignments, let rows):
        let alignmentText = alignments.map(String.init(describing:)).joined(separator: ",")
        let rowLines = rows.map { "\(prefix)  row: \($0.joined(separator: " | "))" }
        return [
            "\(prefix)table[\(alignmentText)]: \(header.joined(separator: " | "))",
        ] + rowLines
    case .thematicBreak:
        return ["\(prefix)thematic-break"]
    }
}

private func chatMarkdownListItemSnapshotLines(
    _ items: [DesktopChatMarkdownListItem],
    indent: Int
) -> [String] {
    items.flatMap { item -> [String] in
        let prefix = String(repeating: "  ", count: indent)
        return ["\(prefix)- \(item.text)"] + item.children.flatMap {
            chatMarkdownBlockSnapshotLines($0, indent: indent + 1)
        }
    }
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
