import AppKit
import Testing

@testable import AppMain

@Suite("Desktop Foundation Presenter", .serialized)
struct DesktopFoundationPresenterTests {
    @Test("presenter reuses one window instance and records open metrics")
    @MainActor
    func presenterReusesWindowAndRecordsMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await viewModel.start()

        let window = RecordingDesktopFoundationWindow()
        let builder = RecordingDesktopFoundationWindowBuilder(window: window)
        var activationCount = 0
        let presenter = DesktopFoundationPresenter(
            viewModel: viewModel,
            metrics: metrics,
            windowBuilder: builder,
            activateApp: { activationCount += 1 }
        )

        presenter.show()
        presenter.show()
        try await Task.sleep(for: .milliseconds(20))

        #expect(builder.buildCount == 1)
        #expect(window.showCount == 2)
        #expect(activationCount == 2)
        #expect(await metrics.snapshot()["menu.console_open_ms"] != nil)
    }

    @Test("command center presenter reuses one window instance and records open metrics")
    @MainActor
    func commandCenterPresenterReusesWindowAndRecordsMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await viewModel.start()

        let window = RecordingDesktopFoundationWindow()
        let builder = RecordingCommandCenterWindowBuilder(window: window)
        var activationCount = 0
        let presenter = CommandCenterPresenter(
            viewModel: viewModel,
            metrics: metrics,
            windowBuilder: builder,
            activateApp: { activationCount += 1 }
        )

        presenter.show()
        presenter.show()
        try await Task.sleep(for: .milliseconds(20))

        #expect(builder.buildCount == 1)
        #expect(window.showCount == 2)
        #expect(activationCount == 2)
        #expect(await metrics.snapshot()["menu.command_center_open_ms"] != nil)
    }

    @Test("live window builders create presentable workspace and command center windows")
    @MainActor
    func liveWindowBuildersCreatePresentableWindows() async throws {
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let workspaceWindow = LiveDesktopFoundationWindowBuilder().makeWindow(viewModel: viewModel)
        let commandCenterWindow = LiveCommandCenterWindowBuilder().makeWindow(viewModel: viewModel)

        #expect(workspaceWindow is LiveDesktopFoundationWindow)
        #expect(commandCenterWindow is LiveCommandCenterWindow)

        workspaceWindow.show()
        commandCenterWindow.show()
    }

    @Test("live workspace window uses Melix title and unified compact toolbar")
    @MainActor
    func liveWorkspaceWindowUsesMelixTitleAndUnifiedCompactToolbar() async throws {
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let workspaceWindow = LiveDesktopFoundationWindow(viewModel: viewModel)
        let mirror = Mirror(reflecting: workspaceWindow)
        let windowController = try #require(mirror.descendant("windowController") as? NSWindowController)
        let window = try #require(windowController.window)

        workspaceWindow.show()
        try await Task.sleep(for: .milliseconds(50))

        #expect(window.title == "Melix")
        #expect(window.toolbar != nil)
        #expect(window.toolbarStyle == .unifiedCompact)
        #expect(window.toolbar?.items.isEmpty == false)
    }
}

@MainActor
private final class RecordingDesktopFoundationWindowBuilder: DesktopFoundationWindowBuilding {
    private let window: RecordingDesktopFoundationWindow
    private(set) var buildCount = 0

    init(window: RecordingDesktopFoundationWindow) {
        self.window = window
    }

    func makeWindow(viewModel: RuntimeViewModel) -> any DesktopFoundationWindowing {
        _ = viewModel
        buildCount += 1
        return window
    }
}

@MainActor
private final class RecordingDesktopFoundationWindow: DesktopFoundationWindowing {
    private(set) var showCount = 0

    func show() {
        showCount += 1
    }
}

@MainActor
private final class RecordingCommandCenterWindowBuilder: CommandCenterWindowBuilding {
    private let window: RecordingDesktopFoundationWindow
    private(set) var buildCount = 0

    init(window: RecordingDesktopFoundationWindow) {
        self.window = window
    }

    func makeWindow(viewModel: RuntimeViewModel) -> any DesktopFoundationWindowing {
        _ = viewModel
        buildCount += 1
        return window
    }
}
