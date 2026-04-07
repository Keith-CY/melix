import AppKit
import SwiftUI

@MainActor
public protocol DesktopFoundationPresenting: AnyObject {
    func show()
}

@MainActor
public protocol DesktopFoundationWindowBuilding {
    func makeWindow(viewModel: RuntimeViewModel) -> any DesktopFoundationWindowing
}

@MainActor
public protocol CommandCenterWindowBuilding {
    func makeWindow(viewModel: RuntimeViewModel) -> any DesktopFoundationWindowing
}

@MainActor
public protocol DesktopFoundationWindowing: AnyObject {
    func show()
}

@MainActor
public final class DesktopFoundationPresenter: DesktopFoundationPresenting {
    private let viewModel: RuntimeViewModel
    private let metrics: MenuBarMetricsStore
    private let windowBuilder: any DesktopFoundationWindowBuilding
    private let activateApp: @MainActor @Sendable () -> Void
    private var window: (any DesktopFoundationWindowing)?

    public init(
        viewModel: RuntimeViewModel,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        windowBuilder: any DesktopFoundationWindowBuilding = LiveDesktopFoundationWindowBuilder(),
        activateApp: @escaping @MainActor @Sendable () -> Void = { NSApp.activate(ignoringOtherApps: true) }
    ) {
        self.viewModel = viewModel
        self.metrics = metrics
        self.windowBuilder = windowBuilder
        self.activateApp = activateApp
    }

    public func show() {
        let startedAt = Date()
        if window == nil {
            window = windowBuilder.makeWindow(viewModel: viewModel)
        }
        window?.show()
        activateApp()

        Task {
            await metrics.record(
                name: "menu.console_open_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        }
    }
}

@MainActor
public final class CommandCenterPresenter: DesktopFoundationPresenting {
    private let viewModel: RuntimeViewModel
    private let metrics: MenuBarMetricsStore
    private let windowBuilder: any CommandCenterWindowBuilding
    private let activateApp: @MainActor @Sendable () -> Void
    private var window: (any DesktopFoundationWindowing)?

    public init(
        viewModel: RuntimeViewModel,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        windowBuilder: any CommandCenterWindowBuilding = LiveCommandCenterWindowBuilder(),
        activateApp: @escaping @MainActor @Sendable () -> Void = { NSApp.activate(ignoringOtherApps: true) }
    ) {
        self.viewModel = viewModel
        self.metrics = metrics
        self.windowBuilder = windowBuilder
        self.activateApp = activateApp
    }

    public func show() {
        let startedAt = Date()
        if window == nil {
            window = windowBuilder.makeWindow(viewModel: viewModel)
        }
        window?.show()
        activateApp()

        Task {
            await metrics.record(
                name: "menu.command_center_open_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        }
    }
}

@MainActor
public struct LiveDesktopFoundationWindowBuilder: DesktopFoundationWindowBuilding {
    public init() {}

    public func makeWindow(viewModel: RuntimeViewModel) -> any DesktopFoundationWindowing {
        LiveDesktopFoundationWindow(viewModel: viewModel)
    }
}

@MainActor
public struct LiveCommandCenterWindowBuilder: CommandCenterWindowBuilding {
    public init() {}

    public func makeWindow(viewModel: RuntimeViewModel) -> any DesktopFoundationWindowing {
        LiveCommandCenterWindow(viewModel: viewModel)
    }
}

@MainActor
public final class LiveDesktopFoundationWindow: NSObject, DesktopFoundationWindowing {
    private let windowController: NSWindowController

    public init(viewModel: RuntimeViewModel) {
        let hostingController = NSHostingController(rootView: DesktopFoundationRootView(viewModel: viewModel))
        let window = NSWindow(contentViewController: hostingController)
        let toolbar = NSToolbar(identifier: "MelixWorkspaceToolbar")
        toolbar.allowsUserCustomization = false
        toolbar.autosavesConfiguration = false
        window.toolbar = toolbar
        window.toolbarStyle = .unifiedCompact
        window.title = "Melix"
        window.setContentSize(NSSize(width: 1100, height: 760))
        window.styleMask.formUnion([.titled, .closable, .miniaturizable, .resizable])
        window.isReleasedWhenClosed = false
        self.windowController = NSWindowController(window: window)
        super.init()
    }

    public func show() {
        windowController.showWindow(nil)
        windowController.window?.makeKeyAndOrderFront(nil)
    }
}

@MainActor
public final class LiveCommandCenterWindow: NSObject, DesktopFoundationWindowing {
    private let viewModel: RuntimeViewModel
    private let windowController: NSWindowController

    public init(viewModel: RuntimeViewModel) {
        self.viewModel = viewModel
        let hostingController = NSHostingController(rootView: DesktopCommandCenterView(viewModel: viewModel))
        let window = NSWindow(contentViewController: hostingController)
        window.title = "Melix Command Center"
        window.setContentSize(NSSize(width: 920, height: 680))
        window.styleMask.formUnion([.titled, .closable, .miniaturizable, .resizable])
        window.isReleasedWhenClosed = false
        self.windowController = NSWindowController(window: window)
        super.init()
    }

    public func show() {
        if let hostingController = windowController.contentViewController as? NSHostingController<DesktopCommandCenterView> {
            hostingController.rootView = DesktopCommandCenterView(viewModel: viewModel)
        }
        windowController.showWindow(nil)
        windowController.window?.makeKeyAndOrderFront(nil)
    }
}
