import AppKit
import Foundation
import Testing

@testable import AppMain
import MelixControlPlaneProtocol

@Suite("Status Menu", .serialized)
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
        let viewModel = RuntimeViewModel(
            client: client,
            productInstallStateProvider: StubProductInstallStateProvider(
                updateStatusResponse: nil,
                startupDiagnosticResponse: nil
            )
        )
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        menu.install()

        let content = try #require(renderer.lastContent)
        #expect(content.title == "Melix Error")
        #expect(content.items.contains(.error("Startup failed: menu handshake failed. Open Melix Console for details.")))
    }

    @Test("install includes packaged update status when available")
    @MainActor
    func installRendersPackagedUpdateState() async throws {
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
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        menu.install()

        let content = try #require(renderer.lastContent)
        #expect(content.items.contains(.info("Update available: 0.2.0")))
    }

    @Test("install surfaces runtime banner titles before model actions")
    @MainActor
    func installSurfacesRuntimeBannerTitles() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        menu.install()
        await client.sendServerStateChanged(state: .serverDraining)
        try await eventually("status menu should refresh with the runtime warning banner", timeout: .seconds(2)) {
            renderer.lastContent?.items.contains(.info("Runtime Needs Monitoring")) == true
        }

        let content = try #require(renderer.lastContent)
        #expect(content.items.contains(.info("Runtime Needs Monitoring")))
    }

    @Test("install surfaces download recovery titles before model actions")
    @MainActor
    func installSurfacesDownloadRecoveryTitles() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeStatusMenuNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "model-ops-0100",
                            sourceModel: "melix-dev-text",
                            status: "stalled",
                            stage: "download",
                            pct: 0.5,
                            outputDir: "/tmp/melix-downloads/melix-dev-text",
                            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
                            selectedMirror: "https://mirror.example/status-menu",
                            downloadedBytes: 1024,
                            totalBytes: 2048,
                            resumeUsed: true,
                            resumeFromBytes: 512,
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
        let renderer = RecordingStatusMenuRenderer()
        let menu = StatusMenu(viewModel: viewModel, renderer: renderer)

        await viewModel.start()
        await viewModel.refreshDownloadQueueState()
        menu.install()

        let content = try #require(renderer.lastContent)
        #expect(content.items.contains(.info("Download Recovery Available")))
    }

    @Test("perform routes primary model actions to the view model")
    @MainActor
    func performRoutesPrimaryModelActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        let menu = StatusMenu(viewModel: viewModel, renderer: RecordingStatusMenuRenderer())

        await viewModel.start()
        menu.perform(.loadPrimaryModel)
        try await eventually("load action should reach the client", timeout: .seconds(2)) {
            viewModel.primaryModel?.stateText == "Warm"
        }
        menu.perform(.unloadPrimaryModel)
        try await eventually("unload action should reach the client", timeout: .seconds(2)) {
            viewModel.primaryModel?.stateText == "Unloaded"
        }

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
        try await eventually("selector bridge should dispatch the load action", timeout: .seconds(2)) {
            viewModel.primaryModel?.stateText == "Warm"
        }
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
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
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
        #expect(statusItem.button?.title == "")
        #expect(statusItem.button?.toolTip == "Melix Ready")
        #expect(statusItem.button?.image != nil)
        #expect(statusItem.button?.image?.isTemplate == true)
        #expect(statusItem.menu?.items.count == 2)
    }

    @Test("AppKit renderer constrains the tray icon to the menu bar size")
    @MainActor
    func appKitRendererConstrainsTrayIconSize() async throws {
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
        let statusBar = NSStatusBar()
        let renderer = AppKitStatusMenuRenderer(statusBar: statusBar)
        let target = NSObject()
        let content = StatusMenuContent(
            title: "Melix Ready",
            items: [
                .info("Server: Ready"),
            ]
        )

        renderer.render(
            content: content,
            target: target,
            action: #selector(getter: NSObject.description)
        )

        let statusItem = renderer.currentStatusItem
        defer { statusBar.removeStatusItem(statusItem) }

        let iconSize = try #require(statusItem.button?.image?.size)
        #expect(iconSize.width <= statusBar.thickness)
        #expect(iconSize.height <= statusBar.thickness)
    }

    @Test("AppKit renderer keeps the tray glyph tightly framed inside the menu bar icon")
    @MainActor
    func appKitRendererKeepsTrayGlyphTightlyFramed() async throws {
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
        let statusBar = NSStatusBar()
        let renderer = AppKitStatusMenuRenderer(statusBar: statusBar)
        let target = NSObject()
        let content = StatusMenuContent(
            title: "Melix Ready",
            items: [
                .info("Server: Ready"),
            ]
        )

        renderer.render(
            content: content,
            target: target,
            action: #selector(getter: NSObject.description)
        )

        let statusItem = renderer.currentStatusItem
        defer { statusBar.removeStatusItem(statusItem) }

        let image = try #require(statusItem.button?.image)
        let glyphBounds = try #require(alphaBounds(for: image))
        #expect(glyphBounds.width / image.size.width >= 0.75)
        #expect(glyphBounds.height / image.size.height >= 0.75)
    }

    @Test("AppKit renderer compacts long error labels to keep the dropdown narrow")
    @MainActor
    func appKitRendererCompactsLongErrorLabels() async throws {
        let target = NSObject()
        let message = """
        Operator session persistence failed: Error Domain=NSCocoaErrorDomain Code=513 \
        "You don’t have permission to save the file" NSUnderlyingError=POSIX 13
        """
        let content = StatusMenuContent(
            title: "Melix Error",
            items: [
                .error(message),
            ]
        )

        let menu = AppKitStatusMenuRenderer.makeMenu(
            content: content,
            target: target,
            action: #selector(getter: NSObject.description)
        )

        #expect(menu.items.count == 1)
        #expect(menu.items[0].title == "Error: Operator session persistence failed")
        #expect(menu.items[0].toolTip == "Error: \(message)")
    }
}

private func makeStatusMenuNamedModelOperationResult(
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

@MainActor
private func eventually(
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

@MainActor
private func alphaBounds(for image: NSImage) -> NSSize? {
    guard
        let tiffRepresentation = image.tiffRepresentation,
        let bitmap = NSBitmapImageRep(data: tiffRepresentation)
    else {
        return nil
    }

    var minX = bitmap.pixelsWide
    var minY = bitmap.pixelsHigh
    var maxX = -1
    var maxY = -1

    for y in 0..<bitmap.pixelsHigh {
        for x in 0..<bitmap.pixelsWide {
            guard let color = bitmap.colorAt(x: x, y: y), color.alphaComponent > 0 else {
                continue
            }
            minX = min(minX, x)
            minY = min(minY, y)
            maxX = max(maxX, x)
            maxY = max(maxY, y)
        }
    }

    guard maxX >= minX, maxY >= minY else {
        return nil
    }

    return NSSize(
        width: CGFloat(maxX - minX + 1),
        height: CGFloat(maxY - minY + 1)
    )
}
