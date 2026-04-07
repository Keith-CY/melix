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

public enum MenuBarPresentationMode: String, Equatable {
    case tray
    case dockAndTray = "dock-and-tray"

    init(environmentValue: String?) {
        let normalized = environmentValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
        self = MenuBarPresentationMode(rawValue: normalized) ?? .tray
    }

    var activationPolicy: NSApplication.ActivationPolicy {
        switch self {
        case .tray:
            return .accessory
        case .dockAndTray:
            return .regular
        }
    }
}

public enum MenuBarTerminationMode: String, Equatable {
    case terminate
    case devDownScript = "dev-down-script"

    init(environmentValue: String?) {
        let normalized = environmentValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
        self = MenuBarTerminationMode(rawValue: normalized) ?? .terminate
    }
}

@MainActor
public protocol StatusMenuInstalling: AnyObject {
    func install()
}

extension StatusMenu: StatusMenuInstalling {}

@MainActor
public protocol MenuBarApplicationLifecycle {
    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy)
    func setMainMenu(_ menu: NSMenu?)
    func run()
}

@MainActor
public protocol NSApplicationControlling {
    @discardableResult
    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) -> Bool
    func setMainMenu(_ menu: NSMenu?)
    func run()
}

extension NSApplication: NSApplicationControlling {
    public func setMainMenu(_ menu: NSMenu?) {
        mainMenu = menu
    }
}

@MainActor
public struct LiveMenuBarApplication: MenuBarApplicationLifecycle {
    private let application: any NSApplicationControlling

    public init(application: any NSApplicationControlling = NSApplication.shared) {
        self.application = application
    }

    public func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) {
        _ = application.setActivationPolicy(activationPolicy)
    }

    public func setMainMenu(_ menu: NSMenu?) {
        application.setMainMenu(menu)
    }

    public func run() {
        application.run()
    }
}

@MainActor
public final class MenuBarTerminationCoordinator: NSObject {
    private let mode: MenuBarTerminationMode
    private let repoRoot: String
    private let runtimeDirectory: String?
    private let terminateApplication: @MainActor @Sendable () -> Void
    private let launchDevDownScript: @MainActor @Sendable (String, String?) -> Void
    private var isTerminationRequested = false

    public init(
        mode: MenuBarTerminationMode,
        repoRoot: String,
        runtimeDirectory: String?,
        terminateApplication: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) },
        launchDevDownScript: (@MainActor @Sendable (String, String?) -> Void)? = nil
    ) {
        self.mode = mode
        self.repoRoot = repoRoot
        self.runtimeDirectory = runtimeDirectory
        self.terminateApplication = terminateApplication
        self.launchDevDownScript = launchDevDownScript ?? { repoRoot, runtimeDirectory in
            MenuBarTerminationCoordinator.launchDevDownProcess(
                repoRoot: repoRoot,
                runtimeDirectory: runtimeDirectory
            )
        }
    }

    @objc
    public func handleQuitMenuItem(_ sender: Any?) {
        _ = sender
        requestTermination()
    }

    public func requestTermination() {
        guard isTerminationRequested == false else {
            return
        }

        isTerminationRequested = true
        if mode == .devDownScript {
            launchDevDownScript(repoRoot, runtimeDirectory)
        }
        terminateApplication()
    }

    static func launchDevDownProcess(repoRoot: String, runtimeDirectory: String?) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [
            "-c",
            """
import os, subprocess, sys
script_path = sys.argv[1]
runtime_dir = sys.argv[2] if len(sys.argv) > 2 else ""
env = os.environ.copy()
if runtime_dir:
    env["MELIX_RUNTIME_DIR"] = runtime_dir
subprocess.Popen(
    ["/bin/bash", script_path],
    env=env,
    start_new_session=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
""",
            URL(fileURLWithPath: repoRoot)
                .appendingPathComponent("scripts/dev_down.sh")
                .path,
            runtimeDirectory ?? "",
        ]
        try? process.run()
    }
}

enum MenuBarApplicationMenuBuilder {
    @MainActor
    static func makeMainMenu(
        target: AnyObject,
        action: Selector
    ) -> NSMenu {
        let mainMenu = NSMenu(title: MelixBranding.productName)
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: MelixBranding.productName)
        let quitItem = NSMenuItem(title: "Quit Melix", action: action, keyEquivalent: "q")
        quitItem.target = target
        quitItem.keyEquivalentModifierMask = [.command]
        appMenu.addItem(quitItem)
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)
        return mainMenu
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
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) },
        statusMenuFactory: @MainActor @escaping (
            RuntimeViewModel,
            @escaping @MainActor @Sendable () -> Void,
            @escaping @MainActor @Sendable () -> Void
        ) -> any StatusMenuInstalling = { viewModel, openConsole, terminationHandler in
            StatusMenu(
                viewModel: viewModel,
                openConsoleHandler: openConsole,
                terminationHandler: terminationHandler
            )
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
        self.statusMenu = statusMenuFactory(viewModel, {
            desktopFoundationPresenter.show()
        }, terminationHandler)
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

    static func live(
        environment: MenuBarBootstrapEnvironment,
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) -> MelixMenuBarBootstrap {
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
            serverSessionAPIKeyStore: ServerSessionAPIKeyStore(melixHome: melixHome),
            terminationHandler: terminationHandler
        )
    }

    public static func live(
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) -> MelixMenuBarBootstrap {
        live(
            environment: MenuBarBootstrapEnvironment(environment: ProcessInfo.processInfo.environment),
            terminationHandler: terminationHandler
        )
    }
}

struct MenuBarBootstrapEnvironment {
    let repoRoot: String
    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
    let startupSurface: MenuBarStartupSurface
    let presentationMode: MenuBarPresentationMode
    let terminationMode: MenuBarTerminationMode
    let runtimeDirectory: String?

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
        self.presentationMode = MenuBarPresentationMode(
            environmentValue: environment["MELIX_MENU_BAR_PRESENTATION_MODE"]
        )
        self.terminationMode = MenuBarTerminationMode(
            environmentValue: environment["MELIX_MENU_BAR_TERMINATION_MODE"]
        )
        self.runtimeDirectory =
            environment["MELIX_RUNTIME_DIR"]
            ?? URL(fileURLWithPath: self.pythonWorkerSocketPath).deletingLastPathComponent().path
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
        presentationMode: MenuBarPresentationMode,
        terminationCoordinator: MenuBarTerminationCoordinator = MenuBarTerminationCoordinator(
            mode: .terminate,
            repoRoot: FileManager.default.currentDirectoryPath,
            runtimeDirectory: nil
        ),
        bootstrapFactory: (@escaping @MainActor @Sendable () -> Void) -> MelixMenuBarBootstrap,
        retain: (MelixMenuBarBootstrap) -> Void
    ) {
        application.setActivationPolicy(presentationMode.activationPolicy)
        application.setMainMenu(
            MenuBarApplicationMenuBuilder.makeMainMenu(
                target: terminationCoordinator,
                action: #selector(MenuBarTerminationCoordinator.handleQuitMenuItem(_:))
            )
        )

        let bootstrap = bootstrapFactory {
            terminationCoordinator.requestTermination()
        }
        retain(bootstrap)
        bootstrap.start()

        application.run()
    }
}

@main
@MainActor
enum MelixMenuBarApp {
    private static var retainedBootstrap: MelixMenuBarBootstrap?
    private static var retainedTerminationCoordinator: MenuBarTerminationCoordinator?

    static func launchLive(
        application: any MenuBarApplicationLifecycle = LiveMenuBarApplication(),
        bootstrapFactory: ((@escaping @MainActor @Sendable () -> Void) -> MelixMenuBarBootstrap)? = nil,
        presentationMode: MenuBarPresentationMode = MenuBarBootstrapEnvironment(
            environment: ProcessInfo.processInfo.environment
        ).presentationMode
    ) {
        let environment = MenuBarBootstrapEnvironment(environment: ProcessInfo.processInfo.environment)
        let terminationCoordinator = MenuBarTerminationCoordinator(
            mode: environment.terminationMode,
            repoRoot: environment.repoRoot,
            runtimeDirectory: environment.runtimeDirectory
        )
        retainedTerminationCoordinator = terminationCoordinator

        MelixMenuBarLauncher.launch(
            application: application,
            presentationMode: presentationMode,
            terminationCoordinator: terminationCoordinator,
            bootstrapFactory: bootstrapFactory ?? { terminationHandler in
                MelixMenuBarBootstrap.live(
                    environment: environment,
                    terminationHandler: terminationHandler
                )
            },
            retain: { retainedBootstrap = $0 }
        )
    }

    static func main() {
        launchLive()
    }
}
