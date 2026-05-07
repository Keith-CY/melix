import AppKit
import Carbon.HIToolbox
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
        self = MenuBarStartupSurface(rawValue: normalized) ?? .console
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
    private let workerProcessIDs: [pid_t]
    private let terminateApplication: @MainActor @Sendable () -> Void
    private let terminateWorkerProcess: @MainActor @Sendable (pid_t) -> Void
    private let launchDevDownScript: @MainActor @Sendable (String, String?) -> Void
    private var isTerminationRequested = false

    public init(
        mode: MenuBarTerminationMode,
        repoRoot: String,
        runtimeDirectory: String?,
        workerProcessIDs: [pid_t]? = nil,
        terminateApplication: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) },
        terminateWorkerProcess: @escaping @MainActor @Sendable (pid_t) -> Void = { pid in
            _ = Darwin.kill(pid, SIGTERM)
        },
        launchDevDownScript: (@MainActor @Sendable (String, String?) -> Void)? = nil
    ) {
        self.mode = mode
        self.repoRoot = repoRoot
        self.runtimeDirectory = runtimeDirectory
        self.workerProcessIDs = workerProcessIDs ?? MenuBarTerminationCoordinator.bundledWorkerProcessIDs()
        self.terminateApplication = terminateApplication
        self.terminateWorkerProcess = terminateWorkerProcess
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
        for workerProcessID in workerProcessIDs {
            terminateWorkerProcess(workerProcessID)
        }
        if mode == .devDownScript {
            launchDevDownScript(repoRoot, runtimeDirectory)
        }
        terminateApplication()
    }

    static func bundledWorkerProcessIDs(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> [pid_t] {
        var seenProcessIDs = Set<pid_t>()
        return [
            "MELIX_SWIFT_WORKER_PID",
            "MELIX_PYTHON_WORKER_PID",
        ].compactMap { key in
            guard
                let rawValue = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines),
                let processID = pid_t(rawValue),
                processID > 0,
                seenProcessIDs.insert(processID).inserted
            else {
                return nil
            }

            return processID
        }
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
        let sendChatItem = NSMenuItem(
            title: "Send Chat Prompt",
            action: #selector(DesktopChatShortcutController.submitChatPrompt(_:)),
            keyEquivalent: "\r"
        )
        sendChatItem.target = DesktopChatShortcutController.shared
        sendChatItem.keyEquivalentModifierMask = [.command]
        let quitItem = NSMenuItem(title: "Quit Melix", action: action, keyEquivalent: "q")
        quitItem.target = target
        quitItem.keyEquivalentModifierMask = [.command]
        appMenu.addItem(sendChatItem)
        appMenu.addItem(quitItem)
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        let editMenuItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(NSMenuItem(title: "Undo", action: Selector(("undo:")), keyEquivalent: "z"))
        let redoItem = NSMenuItem(title: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        redoItem.keyEquivalentModifierMask = [.command, .shift]
        editMenu.addItem(redoItem)
        editMenu.addItem(.separator())
        editMenu.addItem(NSMenuItem(title: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x"))
        editMenu.addItem(NSMenuItem(title: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c"))
        editMenu.addItem(NSMenuItem(title: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v"))
        editMenu.addItem(NSMenuItem(title: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a"))
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        return mainMenu
    }
}

@MainActor
final class DesktopChatShortcutController: NSObject {
    static let shared = DesktopChatShortcutController()

    struct HotKeyDescriptor: Equatable {
        let keyCode: UInt32
        let modifiers: UInt32
        let id: UInt32
    }

    static let hotKeySignature: OSType = 0x4D6C7853
    static let hotKeyDescriptors = [
        HotKeyDescriptor(
            keyCode: UInt32(DesktopChatComposerKeyPolicy.returnKeyCode),
            modifiers: UInt32(cmdKey),
            id: 1
        ),
        HotKeyDescriptor(
            keyCode: UInt32(DesktopChatComposerKeyPolicy.keypadEnterKeyCode),
            modifiers: UInt32(cmdKey),
            id: 2
        ),
    ]

    weak var viewModel: RuntimeViewModel?
    private var keyDownMonitor: Any?
    private var eventHandlerRef: EventHandlerRef?
    private var hotKeyRefs: [EventHotKeyRef] = []

    static func isChatSubmitShortcut(_ event: NSEvent) -> Bool {
        DesktopChatComposerKeyPolicy.action(
            keyCode: event.keyCode,
            modifiers: event.modifierFlags
        ) == .submit
    }

    func installShortcutHandlers() {
        installKeyDownMonitor()
        installCarbonHotKeysIfNeeded()
    }

    private func installKeyDownMonitor() {
        guard keyDownMonitor == nil else {
            return
        }
        keyDownMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self,
                  Self.isChatSubmitShortcut(event)
            else {
                return event
            }
            return self.submitChatPromptFromShortcut(playsFailureSound: false) ? nil : event
        }
    }

    private func installCarbonHotKeysIfNeeded() {
        guard eventHandlerRef == nil,
              ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil
        else {
            return
        }

        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let userData = Unmanaged.passUnretained(self).toOpaque()
        let installStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, userData in
                guard let event,
                      let userData
                else {
                    return noErr
                }
                var hotKeyID = EventHotKeyID()
                let parameterStatus = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &hotKeyID
                )
                guard parameterStatus == noErr,
                      hotKeyID.signature == DesktopChatShortcutController.hotKeySignature
                else {
                    return noErr
                }
                let controller = Unmanaged<DesktopChatShortcutController>
                    .fromOpaque(userData)
                    .takeUnretainedValue()
                Task { @MainActor in
                    _ = controller.submitChatPromptFromShortcut(playsFailureSound: false)
                }
                return noErr
            },
            1,
            &eventType,
            userData,
            &eventHandlerRef
        )
        guard installStatus == noErr else {
            eventHandlerRef = nil
            return
        }

        for descriptor in Self.hotKeyDescriptors {
            var hotKeyRef: EventHotKeyRef?
            let hotKeyID = EventHotKeyID(signature: Self.hotKeySignature, id: descriptor.id)
            let registerStatus = RegisterEventHotKey(
                descriptor.keyCode,
                descriptor.modifiers,
                hotKeyID,
                GetApplicationEventTarget(),
                0,
                &hotKeyRef
            )
            if registerStatus == noErr, let hotKeyRef {
                hotKeyRefs.append(hotKeyRef)
            }
        }
    }

    @objc
    func submitChatPrompt(_ sender: Any?) {
        _ = sender
        submitChatPromptFromShortcut(playsFailureSound: true)
    }

    @discardableResult
    private func submitChatPromptFromShortcut(playsFailureSound: Bool) -> Bool {
        guard let viewModel,
              viewModel.selectedSurface == .chat,
              viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false,
              viewModel.isChatStreaming == false,
              viewModel.selectedChatServerSession?.isInteractiveReady == true
        else {
            if playsFailureSound {
                NSSound.beep()
            }
            return false
        }
        Task { await viewModel.submitChatPrompt() }
        return true
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
        startupSurface: MenuBarStartupSurface = .console,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        melixHome: MelixHome = MelixHome(),
        operatorSessionStore: (any OperatorSessionStoring)? = nil,
        cliWorkflowRunner: (any MelixCLIWorkflowRunning)? = nil,
        operatorCommandRunner: MelixCLIRunner? = nil,
        serverSessionAPIKeyStore: (any ServerSessionAPIKeyStoring)? = nil,
        remoteServerStore: (any RemoteServerStoring)? = nil,
        evaluationPromptStore: (any EvaluationPromptStoring)? = nil,
        loraTrainingJobStore: (any LoraTrainingJobStoring)? = nil,
        huggingFaceTokenStore: (any HuggingFaceTokenStoring)? = nil,
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
        let resolvedRemoteServerStore = remoteServerStore ?? RemoteServerStore(melixHome: melixHome)
        let resolvedEvaluationPromptStore = evaluationPromptStore ?? EvaluationPromptStore(melixHome: melixHome)
        let resolvedLoraTrainingJobStore = loraTrainingJobStore ?? LoraTrainingJobStore(melixHome: melixHome)
        let resolvedHuggingFaceTokenStore = huggingFaceTokenStore ?? HuggingFaceTokenStore(melixHome: melixHome)
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: resolvedOperatorSessionStore,
            cliWorkflowRunner: cliWorkflowRunner,
            operatorCommandRunner: resolvedOperatorCommandRunner,
            serverSessionAPIKeyStore: resolvedServerSessionAPIKeyStore,
            remoteServerStore: resolvedRemoteServerStore,
            evaluationPromptStore: resolvedEvaluationPromptStore,
            loraTrainingJobStore: resolvedLoraTrainingJobStore,
            huggingFaceTokenStore: resolvedHuggingFaceTokenStore
        )
        let desktopFoundationPresenter = desktopFoundationPresenterFactory(viewModel, metrics)
        let commandCenterPresenter = commandCenterPresenterFactory(viewModel, metrics)
        viewModel.openCommandCenterAction = {
            commandCenterPresenter.show()
        }
        DesktopChatShortcutController.shared.viewModel = viewModel
        DesktopChatShortcutController.shared.installShortcutHandlers()
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
            remoteServerStore: RemoteServerStore(melixHome: melixHome),
            evaluationPromptStore: EvaluationPromptStore(melixHome: melixHome),
            loraTrainingJobStore: LoraTrainingJobStore(melixHome: melixHome),
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

    static func inferRepoRoot(anchorPath: String = #filePath) -> String {
        let anchorURL = URL(fileURLWithPath: anchorPath).deletingLastPathComponent()
        if let repoRoot = locateRepoRoot(startingAt: anchorURL) {
            return repoRoot.path
        }
        return FileManager.default.currentDirectoryPath
    }

    private static func locateRepoRoot(startingAt startURL: URL) -> URL? {
        var candidate = startURL
        while true {
            let agentsPath = candidate.appendingPathComponent("AGENTS.md").path
            let gitPath = candidate.appendingPathComponent(".git").path
            if FileManager.default.fileExists(atPath: agentsPath)
                || FileManager.default.fileExists(atPath: gitPath)
            {
                return candidate
            }
            let parent = candidate.deletingLastPathComponent()
            if parent.path == candidate.path {
                return nil
            }
            candidate = parent
        }
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
        let melixHome = MelixHome(environment: merged)
        func isMissingOrEmpty(_ key: String) -> Bool {
            merged[key]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false
        }
        if isMissingOrEmpty("MELIX_HOME") {
            merged["MELIX_HOME"] = melixHome.rootURL.path
        }
        if isMissingOrEmpty("MELIX_MANAGED_MODEL_ROOT") {
            merged["MELIX_MANAGED_MODEL_ROOT"] = melixHome.managedModelRootURL.path
        }
        if isMissingOrEmpty("MELIX_AUDIO_RUNTIME_PACK_ROOT") {
            merged["MELIX_AUDIO_RUNTIME_PACK_ROOT"] = melixHome.audioRuntimePackRootURL.path
        }
        if isMissingOrEmpty("MELIX_MODEL_OPS_JOBS_ROOT") {
            merged["MELIX_MODEL_OPS_JOBS_ROOT"] = melixHome.modelOpsJobsRootURL.path
        }
        if isMissingOrEmpty("MELIX_EVALUATION_JOBS_ROOT") {
            merged["MELIX_EVALUATION_JOBS_ROOT"] = melixHome.evaluationJobsRootURL.path
        }
        if isMissingOrEmpty("MELIX_GATEWAY_CONFIG_STORE_PATH") {
            merged["MELIX_GATEWAY_CONFIG_STORE_PATH"] = melixHome.configDirectoryURL
                .appendingPathComponent("gateway-config.json")
                .path
        }
        if isMissingOrEmpty("MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH") {
            merged["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"] = melixHome.configDirectoryURL
                .appendingPathComponent("gateway-serving-defaults.json")
                .path
        }
        if isMissingOrEmpty("MELIX_IMAGE_DEFAULTS_STORE_PATH") {
            merged["MELIX_IMAGE_DEFAULTS_STORE_PATH"] = melixHome.configDirectoryURL
                .appendingPathComponent("image-defaults.json")
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
