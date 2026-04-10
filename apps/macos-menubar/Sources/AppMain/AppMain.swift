import AppKit
import Darwin
import Foundation
import MelixCLICore
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
protocol Phase8WindowUIAcceptanceRunning {
    func run() async throws -> Phase8WindowUIAcceptanceResult
}

extension Phase8WindowUIAcceptanceRunner: Phase8WindowUIAcceptanceRunning {}

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
    let viewModel: RuntimeViewModel
    let cliWorkflowRunner: (any MelixCLIWorkflowRunning)?
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
        cliWorkflowRunner: (any MelixCLIWorkflowRunning)? = nil,
        operatorCommandRunner: MelixCLIRunner? = nil,
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
        let resolvedOperatorCommandRunner = operatorCommandRunner ?? (
            cliWorkflowRunner == nil
                ? MelixCLIRunner(
                    client: client,
                    operatorSessionStore: MelixOperatorSessionStore(melixHome: melixHome)
                )
                : nil
        )
        let resolvedServerSessionAPIKeyStore = serverSessionAPIKeyStore ?? ServerSessionAPIKeyStore(melixHome: melixHome)
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: resolvedOperatorSessionStore,
            cliWorkflowRunner: cliWorkflowRunner,
            operatorCommandRunner: resolvedOperatorCommandRunner,
            serverSessionAPIKeyStore: resolvedServerSessionAPIKeyStore
        )
        let desktopFoundationPresenter = desktopFoundationPresenterFactory(viewModel, metrics)
        let commandCenterPresenter = commandCenterPresenterFactory(viewModel, metrics)
        viewModel.openCommandCenterAction = {
            commandCenterPresenter.show()
        }
        self.viewModel = viewModel
        self.cliWorkflowRunner = cliWorkflowRunner
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
        cliProcessExecutor: any MelixCLIProcessExecuting = LiveMelixCLIProcessExecutor(),
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) -> MelixMenuBarBootstrap {
        let processEnvironment = environment.cliEnvironment(base: ProcessInfo.processInfo.environment)
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: environment.swiftTextWorkerSocketPath
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: environment.pythonWorkerSocketPath,
            repoRoot: environment.repoRoot,
            processEnvironment: processEnvironment
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
        let localClient = LocalControlPlaneXPCClient(service: service)
        let melixHome = MelixHome(environment: processEnvironment)
        let cliWorkflowRunner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: environment.cliExecutablePath,
            environment: processEnvironment,
            processExecutor: cliProcessExecutor
        )
        return MelixMenuBarBootstrap(
            client: localClient,
            startupSurface: environment.startupSurface,
            melixHome: melixHome,
            operatorSessionStore: OperatorSessionStore(melixHome: melixHome),
            cliWorkflowRunner: cliWorkflowRunner,
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

    static func liveCLIRunnerBaseCommand(
        environment: [String: String],
        repoRoot: String
    ) -> [String] {
        if let publicCLIPath = environment["MELIX_PUBLIC_CLI_PATH"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           publicCLIPath.isEmpty == false {
            return [publicCLIPath]
        }
        return [
            "/usr/bin/env",
            "swift",
            "run",
            "--package-path",
            repoRoot,
            "melix",
        ]
    }

    private static func liveCLIRunner(
        client: any ControlPlaneXPCClient,
        melixHome: MelixHome,
        repoRoot: String,
        environment: [String: String]
    ) -> MelixCLIRunner {
        let executor = MelixCLIProcessExecutor(
            baseCommand: liveCLIRunnerBaseCommand(environment: environment, repoRoot: repoRoot),
            environment: environment,
            workingDirectory: repoRoot
        )
        return MelixCLIRunner(
            client: client,
            environment: environment,
            operatorSessionStore: MelixOperatorSessionStore(melixHome: melixHome),
            commandExecutor: executor.run
        )
    }
}

struct MenuBarBootstrapEnvironment {
    let repoRoot: String
    let cliExecutablePath: String
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
        self.cliExecutablePath = environment["MELIX_CLI"] ?? MenuBarBootstrapEnvironment.inferCLIExecutablePath(
            repoRoot: self.repoRoot
        )
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

    private static func inferCLIExecutablePath(repoRoot: String) -> String {
        let repoURL = URL(fileURLWithPath: repoRoot)
        let candidates = [
            repoURL.appendingPathComponent(".build/arm64-apple-macosx/debug/melix").path,
            repoURL.appendingPathComponent(".build/arm64-apple-macosx/release/melix").path,
            repoURL.appendingPathComponent(".build/debug/melix").path,
            repoURL.appendingPathComponent(".build/release/melix").path,
            "melix",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? candidates[0]
    }

    func cliEnvironment(base: [String: String]) -> [String: String] {
        var merged = base
        merged["MELIX_REPO_ROOT"] = repoRoot
        merged["MELIX_WORKER_SOCKET_PATH"] = pythonWorkerSocketPath
        merged["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = swiftTextWorkerSocketPath
        if let runtimeDirectory, runtimeDirectory.isEmpty == false {
            merged["MELIX_RUNTIME_DIR"] = runtimeDirectory
        }
        if merged["MELIX_MANAGED_MODEL_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false {
            let melixHome = MelixHome(environment: merged)
            merged["MELIX_MANAGED_MODEL_ROOT"] = melixHome.rootURL
                .appendingPathComponent("models/default-managed", isDirectory: true)
                .path
        }
        return merged
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
        main(environment: ProcessInfo.processInfo.environment)
    }

    static func main(
        environment: [String: String],
        launchLiveHandler: @escaping @MainActor () -> Void = defaultMainLaunchLiveHandler,
        phase8WindowUIAcceptanceHandler: @escaping @MainActor ([String: String]) -> Void = defaultMainPhase8WindowUIAcceptanceHandler
    ) {
        if environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE"] == "1" {
            phase8WindowUIAcceptanceHandler(environment)
            return
        }
        launchLiveHandler()
    }

    static func runPhase8WindowUIAcceptance(
        environment: [String: String],
        application: any MenuBarApplicationLifecycle = LiveMenuBarApplication(),
        bootstrapFactory: @escaping @MainActor ([String: String]) -> MelixMenuBarBootstrap = makePhase8WindowUIAcceptanceBootstrap,
        acceptanceRunnerFactory: @escaping @MainActor (
            MelixMenuBarBootstrap,
            [String: String]
        ) throws -> any Phase8WindowUIAcceptanceRunning = makePhase8WindowUIAcceptanceRunner,
        writeStandardOutput: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardOutput,
        writeStandardError: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardError,
        flushHandler: @escaping @MainActor () -> Void = flushPhase8WindowUIAcceptanceIO,
        exitHandler: @escaping @MainActor (Int32) -> Void = exitPhase8WindowUIAcceptance,
        operationScheduler: @escaping @MainActor (@escaping @MainActor @Sendable () async -> Void) -> Void = schedulePhase8WindowUIAcceptanceOperation,
        runLoopRunner: @escaping @MainActor () -> Void = runPhase8WindowUIAcceptanceLoop
    ) {
        application.setActivationPolicy(.accessory)
        operationScheduler {
            let exitCode = await executePhase8WindowUIAcceptance(
                environment: environment,
                bootstrapFactory: bootstrapFactory,
                acceptanceRunnerFactory: acceptanceRunnerFactory,
                writeStandardOutput: writeStandardOutput,
                writeStandardError: writeStandardError
            )
            flushHandler()
            exitHandler(exitCode)
        }

        runLoopRunner()
    }

    static func executePhase8WindowUIAcceptance(
        environment: [String: String],
        bootstrapFactory: @escaping @MainActor ([String: String]) -> MelixMenuBarBootstrap = makePhase8WindowUIAcceptanceBootstrap,
        acceptanceRunnerFactory: @escaping @MainActor (
            MelixMenuBarBootstrap,
            [String: String]
        ) throws -> any Phase8WindowUIAcceptanceRunning = makePhase8WindowUIAcceptanceRunner,
        writeStandardOutput: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardOutput,
        writeStandardError: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardError
    ) async -> Int32 {
        do {
            let bootstrap = bootstrapFactory(environment)
            let runner = try acceptanceRunnerFactory(bootstrap, environment)
            let result = try await runner.run()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            encoder.keyEncodingStrategy = .convertToSnakeCase
            let data = try encoder.encode(result)
            writeStandardOutput(data)
            writeStandardOutput(Data([0x0A]))
            return 0
        } catch {
            let message = error.localizedDescription + "\n"
            writeStandardError(Data(message.utf8))
            return 1
        }
    }

    private static func defaultMainLaunchLiveHandler() { launchLive() }

    private static func defaultMainPhase8WindowUIAcceptanceHandler(environment: [String: String]) {
        runPhase8WindowUIAcceptance(environment: environment)
    }

    private static func makePhase8WindowUIAcceptanceBootstrap(
        environment: [String: String]
    ) -> MelixMenuBarBootstrap {
        let bootstrapEnvironment = MenuBarBootstrapEnvironment(environment: environment)
        return MelixMenuBarBootstrap.live(environment: bootstrapEnvironment)
    }

    private static func writePhase8WindowUIAcceptanceStandardOutput(_ data: Data) {
        FileHandle.standardOutput.write(data)
    }

    private static func writePhase8WindowUIAcceptanceStandardError(_ data: Data) {
        FileHandle.standardError.write(data)
    }

    private static func flushPhase8WindowUIAcceptanceIO() {
        fflush(nil)
    }

    private static func exitPhase8WindowUIAcceptance(_ exitCode: Int32) { Darwin.exit(exitCode) }

    private static func schedulePhase8WindowUIAcceptanceOperation(
        _ operation: @escaping @MainActor @Sendable () async -> Void
    ) {
        Task { @MainActor in
            await operation()
        }
    }

    private static func runPhase8WindowUIAcceptanceLoop() { RunLoop.main.run() }

    private static func makePhase8WindowUIAcceptanceRunner(
        bootstrap: MelixMenuBarBootstrap,
        environment: [String: String]
    ) throws -> any Phase8WindowUIAcceptanceRunning {
        guard let cliWorkflowRunner = bootstrap.cliWorkflowRunner else {
            throw Phase8WindowUIAcceptanceError.missingCLIWorkflowRunner
        }

        return try Phase8WindowUIAcceptanceRunner(
            viewModel: bootstrap.viewModel,
            cliWorkflowRunner: cliWorkflowRunner,
            config: .init(environment: environment)
        )
    }
}
