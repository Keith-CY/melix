import AppKit
import Foundation
import Testing

@testable import AppMain

@Suite("Status Menu")
struct StatusMenuTests {
    @Test("install renders server and model state through the renderer")
    @MainActor
    func installRendersCurrentState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        menu.install()

        let content = try #require(renderer.lastContent)
        #expect(content.title == "Melix Ready")
        #expect(
            content.items == [
                .info("Server: Ready"),
                .info("melix-dev-text: Discovered"),
                .action("Load", .loadPrimaryModel),
                .action("Open Melix Console", .openConsole),
                .separator,
                .action("Quit Melix", .quit),
            ]
        )
    }

    @Test("install includes error state when present")
    @MainActor
    func installRendersErrorState() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(handshake: MenuBarTestError(description: "menu handshake failed"))
        let viewModel = RuntimeViewModel(client: client)
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        menu.install()

        let content = try #require(renderer.lastContent)
        #expect(content.title == "Melix Error")
        #expect(content.items.contains(.error("menu handshake failed")))
    }

    @Test("perform routes primary model actions to the view model")
    @MainActor
    func performRoutesPrimaryModelActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let menu = StatusMenu(viewModel: viewModel, renderer: RecordingStatusMenuRenderer())

        await viewModel.start()
        menu.perform(.loadPrimaryModel)
        try await Task.sleep(for: .milliseconds(20))
        menu.perform(.unloadPrimaryModel)
        try await Task.sleep(for: .milliseconds(20))

        #expect(await client.recordedActions == ["load:melix-dev-text", "unload:melix-dev-text"])
    }

    @Test("recognized menu actions dispatch through the selector bridge")
    @MainActor
    func recognizedMenuActionsDispatchThroughSelectorBridge() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let menu = StatusMenu(viewModel: viewModel, renderer: RecordingStatusMenuRenderer())

        await viewModel.start()
        let menuItem = NSMenuItem(title: "Load", action: nil, keyEquivalent: "")
        menuItem.representedObject = StatusMenuAction.loadPrimaryModel.rawValue
        menu.handleMenuAction(menuItem)
        try await Task.sleep(for: .milliseconds(20))

        #expect(await client.recordedActions == ["load:melix-dev-text"])
    }

    @Test("perform quit calls the injected termination handler")
    @MainActor
    func performQuitCallsTerminationHandler() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let termination = TerminationRecorder()
        let menu = StatusMenu(
            viewModel: viewModel,
            renderer: RecordingStatusMenuRenderer(),
            terminationHandler: { termination.terminate() }
        )

        menu.perform(.quit)

        #expect(termination.wasCalled)
    }

    @Test("perform open console calls the injected console handler")
    @MainActor
    func performOpenConsoleCallsInjectedHandler() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let recorder = OpenConsoleRecorder()
        let menu = StatusMenu(
            viewModel: viewModel,
            renderer: RecordingStatusMenuRenderer(),
            openConsoleHandler: { recorder.open() }
        )

        menu.perform(.openConsole)

        #expect(recorder.wasCalled)
    }

    @Test("default console handler is safe to invoke")
    @MainActor
    func defaultConsoleHandlerIsSafeToInvoke() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let menu = StatusMenu(viewModel: viewModel, renderer: RecordingStatusMenuRenderer())

        menu.perform(.openConsole)

        #expect(await client.recordedActions.isEmpty)
    }

    @Test("handle menu action ignores unrecognized menu items")
    @MainActor
    func handleMenuActionIgnoresUnknownItems() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let menu = StatusMenu(viewModel: viewModel, renderer: RecordingStatusMenuRenderer())

        let menuItem = NSMenuItem(title: "Unknown", action: nil, keyEquivalent: "")
        menuItem.representedObject = "not-a-real-action"
        menu.handleMenuAction(menuItem)

        #expect(await client.recordedActions.isEmpty)
    }

    @Test("AppKit renderer builds disabled info items and action items")
    @MainActor
    func appKitRendererBuildsExpectedMenuItems() async throws {
        let target = NSObject()
        let content = StatusMenuContent(
            title: "Melix Ready",
            items: [
                .info("Server: Ready"),
                .action("Load", .loadPrimaryModel),
                .error("boom"),
                .separator,
                .action("Quit Melix", .quit),
            ]
        )

        let menu = AppKitStatusMenuRenderer.makeMenu(
            content: content,
            target: target,
            action: #selector(getter: NSObject.description)
        )

        #expect(menu.items.count == 5)
        #expect(menu.items[0].title == "Server: Ready")
        #expect(menu.items[0].isEnabled == false)
        #expect(menu.items[1].title == "Load")
        #expect(menu.items[1].representedObject as? String == StatusMenuAction.loadPrimaryModel.rawValue)
        #expect(menu.items[2].title == "Error: boom")
        #expect(menu.items[2].isEnabled == false)
        #expect(menu.items[3].isSeparatorItem)
        #expect(menu.items[4].representedObject as? String == StatusMenuAction.quit.rawValue)
    }

    @Test("install re-renders when the view model publishes state changes")
    @MainActor
    func installRerendersOnViewModelStateChanges() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        menu.install()
        await client.sendModelStateChanged(state: .modelPinned)
        try await Task.sleep(for: .milliseconds(20))

        let content = try #require(renderer.lastContent)
        #expect(content.items.contains(.info("melix-dev-text: Pinned")))
        #expect(content.items.contains(.action("Unload", .unloadPrimaryModel)))
    }

    @Test("AppKit renderer applies menu content to the status item")
    @MainActor
    func appKitRendererAppliesContentToStatusItem() async throws {
        let statusBar = NSStatusBar()
        let renderer = AppKitStatusMenuRenderer(statusBar: statusBar)
        let target = NSObject()
        let content = StatusMenuContent(
            title: "Melix Ready",
            items: [
                .info("Server: Ready"),
                .action("Quit Melix", .quit),
            ]
        )

        renderer.render(
            content: content,
            target: target,
            action: #selector(getter: NSObject.description)
        )

        let statusItem = renderer.currentStatusItem
        defer { statusBar.removeStatusItem(statusItem) }
        #expect(statusItem.button?.title == "Melix Ready")
        #expect(statusItem.menu?.items.count == 2)
    }
}

@MainActor
private final class RecordingStatusMenuRenderer: StatusMenuRendering {
    private(set) var lastContent: StatusMenuContent?

    func render(content: StatusMenuContent, target: AnyObject, action: Selector) {
        _ = target
        _ = action
        lastContent = content
    }
}

@MainActor
private final class TerminationRecorder {
    private(set) var wasCalled = false

    func terminate() {
        wasCalled = true
    }
}

@MainActor
private final class OpenConsoleRecorder {
    private(set) var wasCalled = false

    func open() {
        wasCalled = true
    }
}
