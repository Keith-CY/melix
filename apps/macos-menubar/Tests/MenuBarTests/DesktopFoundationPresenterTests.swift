import Testing

@testable import AppMain

@Suite("Desktop Foundation Presenter")
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
