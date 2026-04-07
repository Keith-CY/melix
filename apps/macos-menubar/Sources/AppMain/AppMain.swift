import AppKit
import Foundation
import MelixControlPlaneCore

public enum MenuBarStartupSurface: String {
    case tray
    case console
    case commandCenter = "command-center"

    init(environmentValue: String?) {
        let normalized = environmentValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
        self = MenuBarStartupSurface(rawValue: normalized) ?? .tray
    }
}

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
    private let startupSurface: MenuBarStartupSurface
    private let desktopFoundationPresenter: any DesktopFoundationPresenting
    private let commandCenterPresenter: any DesktopFoundationPresenting
    private let statusMenu: any StatusMenuInstalling

    public init(
        client: any ControlPlaneXPCClient,
        startupSurface: MenuBarStartupSurface = .tray,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        melixHome: MelixHome = MelixHome(),
        operatorSessionStore: (any OperatorSessionStoring)? = nil,
        serverSessionAPIKeyStore: (any ServerSessionAPIKeyStoring)? = nil,
        desktopFoundationPresenterFactory: @MainActor @escaping (
            RuntimeViewModel,
            MenuBarMetricsStore
        ) -> any DesktopFoundationPresenting = { viewModel, metrics in
            DesktopFoundationPresenter(viewModel: viewModel, metrics: metrics)
        },
        commandCenterPresenterFactory: @MainActor @escaping (
            RuntimeViewModel,
            MenuBarMetricsStore
        ) -> any DesktopFoundationPresenting = { viewModel, metrics in
            CommandCenterPresenter(viewModel: viewModel, metrics: metrics)
        },
        statusMenuFactory: @MainActor @escaping (
            RuntimeViewModel,
            @escaping @MainActor @Sendable () -> Void
        ) -> any StatusMenuInstalling = { viewModel, openConsole in
            StatusMenu(viewModel: viewModel, openConsoleHandler: openConsole)
        }
    ) {
        let resolvedOperatorSessionStore = operatorSessionStore ?? OperatorSessionStore(melixHome: melixHome)
        let resolvedServerSessionAPIKeyStore = serverSessionAPIKeyStore ?? ServerSessionAPIKeyStore(melixHome: melixHome)
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: resolvedOperatorSessionStore,
            serverSessionAPIKeyStore: resolvedServerSessionAPIKeyStore
        )
        let desktopFoundationPresenter = desktopFoundationPresenterFactory(viewModel, metrics)
        let commandCenterPresenter = commandCenterPresenterFactory(viewModel, metrics)
        viewModel.openCommandCenterAction = {
            commandCenterPresenter.show()
        }
        self.viewModel = viewModel
        self.startupSurface = startupSurface
        self.desktopFoundationPresenter = desktopFoundationPresenter
        self.commandCenterPresenter = commandCenterPresenter
        self.statusMenu = statusMenuFactory(viewModel) {
            desktopFoundationPresenter.show()
        }
    }

    public func start() {
        statusMenu.install()
        switch startupSurface {
        case .tray:
            break
        case .console:
            desktopFoundationPresenter.show()
        case .commandCenter:
            commandCenterPresenter.show()
        }
        Task {
            await viewModel.start()
        }
    }

    public static func live() -> MelixMenuBarBootstrap {
        let environment = MenuBarBootstrapEnvironment(environment: ProcessInfo.processInfo.environment)
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: environment.swiftTextWorkerSocketPath
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: environment.pythonWorkerSocketPath,
            repoRoot: environment.repoRoot,
            processEnvironment: ProcessInfo.processInfo.environment
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: swiftTextWorkerClient,
            pythonCompatibilityClient: pythonCompatibilityClient,
            embeddingClient: pythonCompatibilityClient,
            rerankClient: pythonCompatibilityClient,
            modelOperationsClient: pythonCompatibilityClient,
            modelCatalog: modelCatalog
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry
        )
        let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
        return MelixMenuBarBootstrap(
            client: LocalControlPlaneXPCClient(service: service),
            startupSurface: environment.startupSurface,
            melixHome: melixHome,
            operatorSessionStore: OperatorSessionStore(melixHome: melixHome),
            serverSessionAPIKeyStore: ServerSessionAPIKeyStore(melixHome: melixHome)
        )
    }
}

struct MenuBarBootstrapEnvironment {
    let repoRoot: String
    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
    let startupSurface: MenuBarStartupSurface

    init(environment: [String: String]) {
        if let repoRoot = environment["MELIX_REPO_ROOT"], !repoRoot.isEmpty {
            self.repoRoot = repoRoot
        } else {
            self.repoRoot = MenuBarBootstrapEnvironment.inferRepoRoot()
        }
        self.pythonWorkerSocketPath = environment["MELIX_WORKER_SOCKET_PATH"] ?? "/tmp/melix-worker.sock"
        self.swiftTextWorkerSocketPath =
            environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock"
        self.startupSurface = MenuBarStartupSurface(
            environmentValue: environment["MELIX_MENU_BAR_STARTUP_SURFACE"]
        )
    }

    private static func inferRepoRoot() -> String {
        let sourceFile = URL(fileURLWithPath: #filePath)
        return sourceFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path
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
