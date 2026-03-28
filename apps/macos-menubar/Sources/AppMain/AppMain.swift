import AppKit
import Foundation
import MelixControlPlaneCore

@MainActor
public protocol StatusMenuInstalling: AnyObject {
    func install()
}

extension StatusMenu: StatusMenuInstalling {}

@MainActor
public protocol MenuBarApplicationLifecycle {
    func setAccessoryActivationPolicy()
    func run()
}

@MainActor
public protocol NSApplicationControlling {
    @discardableResult
    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) -> Bool
    func run()
}

extension NSApplication: NSApplicationControlling {}

@MainActor
public struct LiveMenuBarApplication: MenuBarApplicationLifecycle {
    private let application: any NSApplicationControlling

    public init(application: any NSApplicationControlling = NSApplication.shared) {
        self.application = application
    }

    public func setAccessoryActivationPolicy() {
        _ = application.setActivationPolicy(.accessory)
    }

    public func run() {
        application.run()
    }
}

@MainActor
public final class MelixMenuBarBootstrap {
    private let viewModel: RuntimeViewModel
    private let desktopFoundationPresenter: any DesktopFoundationPresenting
    private let statusMenu: any StatusMenuInstalling

    public init(
        client: any ControlPlaneXPCClient,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        desktopFoundationPresenterFactory: @MainActor @escaping (
            RuntimeViewModel,
            MenuBarMetricsStore
        ) -> any DesktopFoundationPresenting = { viewModel, metrics in
            DesktopFoundationPresenter(viewModel: viewModel, metrics: metrics)
        },
        statusMenuFactory: @MainActor @escaping (
            RuntimeViewModel,
            @escaping @MainActor @Sendable () -> Void
        ) -> any StatusMenuInstalling = { viewModel, openConsole in
            StatusMenu(viewModel: viewModel, openConsoleHandler: openConsole)
        }
    ) {
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        let desktopFoundationPresenter = desktopFoundationPresenterFactory(viewModel, metrics)
        self.viewModel = viewModel
        self.desktopFoundationPresenter = desktopFoundationPresenter
        self.statusMenu = statusMenuFactory(viewModel) {
            desktopFoundationPresenter.show()
        }
    }

    public func start() {
        statusMenu.install()
        Task {
            await viewModel.start()
        }
    }

    public static func live() -> MelixMenuBarBootstrap {
        MelixMenuBarBootstrap(client: LocalControlPlaneXPCClient(service: ControlPlaneService()))
    }
}

@MainActor
enum MelixMenuBarLauncher {
    static func launch(
        application: any MenuBarApplicationLifecycle,
        bootstrapFactory: () -> MelixMenuBarBootstrap,
        retain: (MelixMenuBarBootstrap) -> Void
    ) {
        application.setAccessoryActivationPolicy()

        let bootstrap = bootstrapFactory()
        retain(bootstrap)
        bootstrap.start()

        application.run()
    }
}

@main
@MainActor
enum MelixMenuBarApp {
    private static var retainedBootstrap: MelixMenuBarBootstrap?

    static func launchLive(
        application: any MenuBarApplicationLifecycle = LiveMenuBarApplication(),
        bootstrapFactory: () -> MelixMenuBarBootstrap = { MelixMenuBarBootstrap.live() }
    ) {
        MelixMenuBarLauncher.launch(
            application: application,
            bootstrapFactory: bootstrapFactory,
            retain: { retainedBootstrap = $0 }
        )
    }

    static func main() {
        launchLive()
    }
}
