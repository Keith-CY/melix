import AppKit
import SwiftUI
import Testing

@testable import AppMain

@Suite("Desktop Foundation View")
struct DesktopFoundationViewTests {
    @Test("root view renders the desktop foundation shell")
    @MainActor
    func rootViewRendersDesktopFoundationShell() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopFoundationRootView(viewModel: viewModel))

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

    @Test("tools tab renders model information and operations state")
    @MainActor
    func toolsTabRendersModelInformationAndOperationsState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        await viewModel.quantizePrimaryModel()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("tools tab buttons dispatch inspect and model operations")
    @MainActor
    func toolsTabButtonsDispatchActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopToolsTabView(viewModel: viewModel)
        await tab.inspectPrimaryModel()
        await tab.quantizePrimaryModel()
        await tab.downloadPrimaryModel()
        await tab.uploadPrimaryModel()

        let actions = await client.recordedActions
        #expect(actions.contains("info:melix-dev-text"))
        #expect(actions.contains("operation:quantize:melix-dev-text"))
        #expect(actions.contains("operation:download:melix-dev-text"))
        #expect(actions.contains("operation:upload:melix-dev-text"))
        #expect(viewModel.selectedModelInfo?.modelID == "melix-dev-text")
        #expect(viewModel.lastModelOperation?.operation == "upload")
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
        let api = hostView(DesktopAPIReferenceTabView(foundation: foundation))

        #expect(dashboard.subviews.isEmpty == false)
        #expect(settings.subviews.isEmpty == false)
        #expect(logs.subviews.isEmpty == false)
        #expect(bench.subviews.isEmpty == false)
        #expect(api.subviews.isEmpty == false)
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
