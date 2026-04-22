import AppKit
import Carbon.HIToolbox
import Foundation
import Testing

@testable import AppMain

@Suite("Menu Bar Bootstrap", .serialized)
struct AppMainBootstrapTests {
    @Test("default bootstrap factory creates a live status menu")
    @MainActor
    func defaultBootstrapFactoryCreatesStatusMenu() async throws {
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
        let bootstrap = MelixMenuBarBootstrap(client: FakeControlPlaneXPCClient())

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))

        #expect(type(of: bootstrap) == MelixMenuBarBootstrap.self)
    }

    @Test("bootstrap installs the status menu and starts view-model hydration")
    @MainActor
    func bootstrapStartsHydration() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let menu = RecordingInstallStatusMenu()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            metrics: metrics,
            statusMenuFactory: { _, _, _ in menu }
        )

        bootstrap.start()
        try await waitForBootstrapCondition("expected bootstrap handshake to complete") {
            await client.handshakeCount == 1
        }
        try await waitForBootstrapCondition("expected handshake metric to be recorded") {
            await metrics.snapshot()["menu.handshake_ms"] != nil
        }

        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
        #expect(await metrics.snapshot()["menu.handshake_ms"] != nil)
    }

    @Test("launcher configures the application lifecycle and retains the bootstrap")
    @MainActor
    func launcherConfiguresApplicationLifecycle() async throws {
        let app = RecordingApplicationLifecycle()
        let client = FakeControlPlaneXPCClient()
        let menu = RecordingInstallStatusMenu()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            statusMenuFactory: { _, _, _ in menu }
        )
        var retainedBootstrap: MelixMenuBarBootstrap?

        MelixMenuBarLauncher.launch(
            application: app,
            presentationMode: .tray,
            bootstrapFactory: { _ in bootstrap },
            retain: { retainedBootstrap = $0 }
        )
        try await waitForBootstrapCondition("expected launcher handshake to complete") {
            await client.handshakeCount == 1
        }

        #expect(app.recordedPolicies == [.accessory])
        #expect(app.didRun)
        #expect(retainedBootstrap === bootstrap)
        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
    }

    @Test("launcher installs application menu keyboard commands")
    @MainActor
    func launcherInstallsApplicationMenuKeyboardCommands() async throws {
        let app = RecordingApplicationLifecycle()
        let bootstrap = MelixMenuBarBootstrap(
            client: FakeControlPlaneXPCClient(),
            statusMenuFactory: { _, _, _ in RecordingInstallStatusMenu() }
        )

        MelixMenuBarLauncher.launch(
            application: app,
            presentationMode: .dockAndTray,
            bootstrapFactory: { _ in bootstrap },
            retain: { _ in }
        )

        let mainMenu = try #require(app.mainMenu)
        let appMenuItem = try #require(mainMenu.items.first)
        let appMenu = try #require(appMenuItem.submenu)
        let sendChatItem = try #require(appMenu.items.first { $0.title == "Send Chat Prompt" })
        let quitItem = try #require(appMenu.items.last)

        #expect(sendChatItem.keyEquivalent == "\r")
        #expect(sendChatItem.keyEquivalentModifierMask == [.command])
        #expect(sendChatItem.target === DesktopChatShortcutController.shared)
        #expect(quitItem.title == "Quit Melix")
        #expect(quitItem.keyEquivalent == "q")
        #expect(quitItem.keyEquivalentModifierMask == [.command])
    }

    @Test("chat shortcut controller recognizes command return")
    @MainActor
    func chatShortcutControllerRecognizesCommandReturn() throws {
        let commandReturn = try #require(
            NSEvent.keyEvent(
                with: .keyDown,
                location: .zero,
                modifierFlags: [.command],
                timestamp: 0,
                windowNumber: 0,
                context: nil,
                characters: "\r",
                charactersIgnoringModifiers: "\r",
                isARepeat: false,
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode
            )
        )
        let plainReturn = try #require(
            NSEvent.keyEvent(
                with: .keyDown,
                location: .zero,
                modifierFlags: [],
                timestamp: 0,
                windowNumber: 0,
                context: nil,
                characters: "\r",
                charactersIgnoringModifiers: "\r",
                isARepeat: false,
                keyCode: DesktopChatComposerKeyPolicy.returnKeyCode
            )
        )

        #expect(DesktopChatShortcutController.isChatSubmitShortcut(commandReturn))
        #expect(DesktopChatShortcutController.isChatSubmitShortcut(plainReturn) == false)
    }

    @Test("chat shortcut controller registers both return key codes")
    @MainActor
    func chatShortcutControllerRegistersBothReturnKeyCodes() {
        let descriptors = DesktopChatShortcutController.hotKeyDescriptors

        #expect(descriptors.map(\.keyCode).contains(UInt32(DesktopChatComposerKeyPolicy.returnKeyCode)))
        #expect(descriptors.map(\.keyCode).contains(UInt32(DesktopChatComposerKeyPolicy.keypadEnterKeyCode)))
        #expect(descriptors.allSatisfy { $0.modifiers == UInt32(cmdKey) })
        #expect(Set(descriptors.map(\.id)).count == descriptors.count)
    }

    @Test("live application delegates activation policy and run to its application controller")
    @MainActor
    func liveApplicationDelegatesToApplicationController() async throws {
        let application = RecordingNSApplication()
        let liveApplication = LiveMenuBarApplication(application: application)

        liveApplication.setActivationPolicy(.regular)
        liveApplication.run()

        #expect(application.recordedPolicies == [.regular])
        #expect(application.runCount == 1)
    }

    @Test("live application delegates main-menu updates to its application controller")
    @MainActor
    func liveApplicationDelegatesMainMenuUpdates() {
        let application = RecordingNSApplication()
        let liveApplication = LiveMenuBarApplication(application: application)
        let menu = NSMenu(title: "Melix Test")

        liveApplication.setMainMenu(menu)

        #expect(application.mainMenu === menu)
    }

    @Test("shared application controller accepts main-menu updates")
    @MainActor
    func sharedApplicationControllerAcceptsMainMenuUpdates() {
        let previousMenu = NSApplication.shared.mainMenu
        let menu = NSMenu(title: "Melix Shared Test")
        defer {
            NSApplication.shared.mainMenu = previousMenu
        }

        LiveMenuBarApplication().setMainMenu(menu)

        #expect(NSApplication.shared.mainMenu === menu)
    }

    @Test("launchLive uses the shared launcher path")
    @MainActor
    func launchLiveUsesSharedLauncherPath() async throws {
        let application = RecordingApplicationLifecycle()
        let client = FakeControlPlaneXPCClient()
        let menu = RecordingInstallStatusMenu()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            statusMenuFactory: { _, _, _ in menu }
        )

        MelixMenuBarApp.launchLive(
            application: application,
            bootstrapFactory: { _ in bootstrap }
        )
        try await waitForBootstrapCondition("expected launchLive handshake to complete") {
            await client.handshakeCount == 1
        }

        #expect(application.recordedPolicies == [.accessory])
        #expect(application.didRun)
        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
    }

    @Test("launchLive can use dock and tray presentation mode when requested")
    @MainActor
    func launchLiveCanUseDockAndTrayPresentationMode() async throws {
        let application = RecordingApplicationLifecycle()
        let client = FakeControlPlaneXPCClient()
        let menu = RecordingInstallStatusMenu()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            statusMenuFactory: { _, _, _ in menu }
        )

        MelixMenuBarApp.launchLive(
            application: application,
            bootstrapFactory: { _ in bootstrap },
            presentationMode: .dockAndTray
        )
        try await waitForBootstrapCondition("expected dock and tray launch handshake to complete") {
            await client.handshakeCount == 1
        }

        #expect(application.recordedPolicies == [.regular])
        #expect(application.didRun)
        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
    }

    @Test("main routes the phase 8 acceptance flag through the acceptance entrypoint")
    @MainActor
    func mainRoutesPhase8AcceptanceFlag() {
        var launchLiveCallCount = 0
        var capturedAcceptanceEnvironment: [String: String]?

        MelixMenuBarApp.main(
            environment: [
                "MELIX_HOME": "/tmp/melix-home",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE": "1",
            ],
            launchLiveHandler: {
                launchLiveCallCount += 1
            },
            phase8WindowUIAcceptanceHandler: { environment in
                capturedAcceptanceEnvironment = environment
            }
        )

        #expect(launchLiveCallCount == 0)
        #expect(capturedAcceptanceEnvironment?["MELIX_HOME"] == "/tmp/melix-home")
        #expect(capturedAcceptanceEnvironment?["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE"] == "1")
    }

    @Test("main routes non-acceptance launches through the live path")
    @MainActor
    func mainRoutesDefaultLaunchPath() {
        var launchLiveCallCount = 0
        var acceptanceCallCount = 0

        MelixMenuBarApp.main(
            environment: [
                "MELIX_HOME": "/tmp/melix-home",
            ],
            launchLiveHandler: {
                launchLiveCallCount += 1
            },
            phase8WindowUIAcceptanceHandler: { _ in
                acceptanceCallCount += 1
            }
        )

        #expect(launchLiveCallCount == 1)
        #expect(acceptanceCallCount == 0)
    }

    @Test("phase 8 acceptance entry writes snake_case json and exits zero")
    @MainActor
    func phase8AcceptanceEntryWritesSnakeCaseJSONAndExitsZero() async throws {
        let bootstrap = MelixMenuBarBootstrap(
            client: FakeControlPlaneXPCClient(),
            statusMenuFactory: { _, _, _ in RecordingInstallStatusMenu() }
        )
        let application = RecordingApplicationLifecycle()
        let recorder = Phase8WindowUIAcceptanceMainRecorder()

        MelixMenuBarApp.runPhase8WindowUIAcceptance(
            environment: [
                "MELIX_HOME": "/tmp/melix-home",
            ],
            application: application,
            bootstrapFactory: { _ in bootstrap },
            acceptanceRunnerFactory: { _, _ in
                SucceedingPhase8WindowUIAcceptanceMainRunner(
                    result: Phase8WindowUIAcceptanceResult(
                        bundlePath: "/tmp/window-ui/bundle.json",
                        screenshotPath: "/tmp/window-ui/window-ui.png",
                        cliEvidenceBundlePath: "/tmp/cli/bundle.json",
                        modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
                    )
                )
            },
            writeStandardOutput: { data in
                recorder.standardOutput.append(data)
            },
            writeStandardError: { data in
                recorder.standardError.append(data)
            },
            flushHandler: {
                recorder.flushCount += 1
            },
            exitHandler: { exitCode in
                recorder.exitCodes.append(exitCode)
            },
            operationScheduler: { operation in
                Task { @MainActor in
                    await operation()
                }
            },
            runLoopRunner: {
                recorder.runLoopInvocationCount += 1
            }
        )

        try await waitForBootstrapCondition("expected phase 8 acceptance entrypoint to exit") {
            recorder.exitCodes.isEmpty == false
        }

        let standardOutput = String(decoding: recorder.standardOutput, as: UTF8.self)
        let outputJSON = try #require(
            JSONSerialization.jsonObject(with: recorder.standardOutput) as? [String: String]
        )
        #expect(application.recordedPolicies == [.accessory])
        #expect(recorder.runLoopInvocationCount == 1)
        #expect(recorder.flushCount == 1)
        #expect(recorder.exitCodes == [0])
        #expect(recorder.standardError.isEmpty)
        #expect(standardOutput.hasSuffix("\n"))
        #expect(outputJSON["bundle_path"] == "/tmp/window-ui/bundle.json")
        #expect(outputJSON["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("phase 8 acceptance entry writes localized stderr when the cli runner is missing")
    @MainActor
    func phase8AcceptanceEntryWritesLocalizedStderrWhenCLIRunnerIsMissing() async {
        let bootstrap = MelixMenuBarBootstrap(
            client: FakeControlPlaneXPCClient(),
            statusMenuFactory: { _, _, _ in RecordingInstallStatusMenu() }
        )
        var standardOutput = Data()
        var standardError = Data()

        let exitCode = await MelixMenuBarApp.executePhase8WindowUIAcceptance(
            environment: [
                "MELIX_HOME": "/tmp/melix-home",
            ],
            bootstrapFactory: { _ in bootstrap },
            writeStandardOutput: { data in
                standardOutput.append(data)
            },
            writeStandardError: { data in
                standardError.append(data)
            }
        )

        #expect(exitCode == 1)
        #expect(standardOutput.isEmpty)
        #expect(
            String(decoding: standardError, as: UTF8.self)
                == "Phase 8 Window UI acceptance requires a CLI workflow runner.\n"
        )
    }

    @Test("phase 8 acceptance entry supports the default bootstrap and scheduler wiring")
    @MainActor
    func phase8AcceptanceEntrySupportsDefaultBootstrapAndSchedulerWiring() async throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-main-defaults-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let application = RecordingApplicationLifecycle()
        let recorder = Phase8WindowUIAcceptanceMainRecorder()

        MelixMenuBarApp.runPhase8WindowUIAcceptance(
            environment: [
                "MELIX_HOME": tempRoot.appendingPathComponent("melix-home", isDirectory: true).path,
                "MELIX_REPO_ROOT": FileManager.default.currentDirectoryPath,
                "MELIX_CLI": "/tmp/melix-cli",
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-worker.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ],
            application: application,
            acceptanceRunnerFactory: { _, _ in
                SucceedingPhase8WindowUIAcceptanceMainRunner(
                    result: Phase8WindowUIAcceptanceResult(
                        bundlePath: "/tmp/window-ui/defaults-bundle.json",
                        screenshotPath: "/tmp/window-ui/defaults-window-ui.png",
                        cliEvidenceBundlePath: "/tmp/cli/defaults-bundle.json",
                        modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
                    )
                )
            },
            exitHandler: { exitCode in
                recorder.exitCodes.append(exitCode)
            },
            runLoopRunner: {
                recorder.runLoopInvocationCount += 1
            }
        )

        try await waitForBootstrapCondition("expected default phase 8 acceptance entrypoint to exit") {
            recorder.exitCodes.isEmpty == false
        }

        #expect(application.recordedPolicies == [.accessory])
        #expect(recorder.runLoopInvocationCount == 1)
        #expect(recorder.exitCodes == [0])
    }

    @Test("phase 8 acceptance execution supports the default runner factory path")
    @MainActor
    func phase8AcceptanceExecutionSupportsDefaultRunnerFactoryPath() async throws {
        let fileManager = FileManager.default
        let tempRoot = fileManager.temporaryDirectory
            .appendingPathComponent("phase8-main-runner-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: tempRoot) }

        let exitCode = await MelixMenuBarApp.executePhase8WindowUIAcceptance(
            environment: [
                "MELIX_HOME": tempRoot.appendingPathComponent("melix-home", isDirectory: true).path,
                "MELIX_REPO_ROOT": FileManager.default.currentDirectoryPath,
                "MELIX_CLI": "/tmp/melix-cli",
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-worker.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ]
        )

        #expect(exitCode == 1)
    }

    @Test("bootstrap wires the desktop foundation presenter into the status menu")
    @MainActor
    func bootstrapWiresDesktopFoundationPresenter() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let menu = RecordingConsoleAwareStatusMenu()
        let presenter = RecordingDesktopFoundationPresenter()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            metrics: metrics,
            desktopFoundationPresenterFactory: { _, _ in presenter },
            statusMenuFactory: { _, openConsole, _ in
                menu.openConsole = openConsole
                return menu
            }
        )

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))
        menu.openConsole?()

        #expect(menu.installCount == 1)
        #expect(presenter.showCount == 1)
    }

    @Test("bootstrap keeps tray startup surface from auto-opening the workspace")
    @MainActor
    func bootstrapKeepsTrayStartupSurfaceFromAutoOpeningWorkspace() async throws {
        let client = FakeControlPlaneXPCClient()
        let menu = RecordingInstallStatusMenu()
        let presenter = RecordingDesktopFoundationPresenter()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            startupSurface: .tray,
            desktopFoundationPresenterFactory: { _, _ in presenter },
            statusMenuFactory: { _, _, _ in menu }
        )

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))

        #expect(menu.installCount == 1)
        #expect(presenter.showCount == 0)
    }

    @Test("bootstrap auto-opens the workspace when startup surface is console")
    @MainActor
    func bootstrapAutoOpensWorkspaceWhenStartupSurfaceIsConsole() async throws {
        let client = FakeControlPlaneXPCClient()
        let menu = RecordingInstallStatusMenu()
        let presenter = RecordingDesktopFoundationPresenter()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            startupSurface: .console,
            desktopFoundationPresenterFactory: { _, _ in presenter },
            statusMenuFactory: { _, _, _ in menu }
        )

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))

        #expect(menu.installCount == 1)
        #expect(presenter.showCount == 1)
    }

    @Test("bootstrap wires the command center presenter into the view model action")
    @MainActor
    func bootstrapWiresCommandCenterPresenter() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let menu = RecordingInstallStatusMenu()
        let desktopPresenter = RecordingDesktopFoundationPresenter()
        let commandCenterPresenter = RecordingDesktopFoundationPresenter()
        var capturedViewModel: RuntimeViewModel?
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            metrics: metrics,
            desktopFoundationPresenterFactory: { viewModel, _ in
                capturedViewModel = viewModel
                return desktopPresenter
            },
            commandCenterPresenterFactory: { viewModel, _ in
                capturedViewModel = viewModel
                return commandCenterPresenter
            },
            statusMenuFactory: { _, _, _ in menu }
        )

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))
        capturedViewModel?.openCommandCenter()

        #expect(menu.installCount == 1)
        #expect(desktopPresenter.showCount == 0)
        #expect(commandCenterPresenter.showCount == 1)
    }

    @Test("bootstrap wires command center action before creating the status menu")
    @MainActor
    func bootstrapWiresCommandCenterActionBeforeCreatingStatusMenu() {
        let menu = RecordingInstallStatusMenu()
        let commandCenterPresenter = RecordingDesktopFoundationPresenter()
        var actionWasPresentWhenStatusMenuWasCreated = false

        _ = MelixMenuBarBootstrap(
            client: FakeControlPlaneXPCClient(),
            commandCenterPresenterFactory: { _, _ in commandCenterPresenter },
            statusMenuFactory: { viewModel, _, _ in
                actionWasPresentWhenStatusMenuWasCreated = viewModel.openCommandCenterAction != nil
                viewModel.openCommandCenter()
                return menu
            }
        )

        #expect(actionWasPresentWhenStatusMenuWasCreated)
        #expect(commandCenterPresenter.showCount == 1)
    }

    @Test("bootstrap environment honors explicit overrides")
    @MainActor
    func bootstrapEnvironmentHonorsExplicitOverrides() {
        let environment = MenuBarBootstrapEnvironment(
            environment: [
                "MELIX_REPO_ROOT": "/tmp/melix-root",
                "MELIX_WORKER_SOCKET_PATH": "/tmp/python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/swift.sock",
                "MELIX_MENU_BAR_STARTUP_SURFACE": "console",
                "MELIX_MENU_BAR_PRESENTATION_MODE": "dock-and-tray",
                "MELIX_MENU_BAR_TERMINATION_MODE": "dev-down-script",
                "MELIX_RUNTIME_DIR": "/tmp/melix-runtime",
            ]
        )

        #expect(environment.repoRoot == "/tmp/melix-root")
        #expect(environment.pythonWorkerSocketPath == "/tmp/python.sock")
        #expect(environment.swiftTextWorkerSocketPath == "/tmp/swift.sock")
        #expect(environment.startupSurface == .console)
        #expect(environment.presentationMode == .dockAndTray)
        #expect(environment.terminationMode == .devDownScript)
        #expect(environment.runtimeDirectory == "/tmp/melix-runtime")
    }

    @Test("bootstrap environment falls back to inferred repo root and default sockets")
    @MainActor
    func bootstrapEnvironmentFallsBackToDefaults() {
        let environment = MenuBarBootstrapEnvironment(environment: [:])
        let expectedRepoRoot = MenuBarBootstrapEnvironment.inferRepoRoot(anchorPath: #filePath)

        #expect(environment.repoRoot == expectedRepoRoot)
        let repoRootURL = URL(fileURLWithPath: environment.repoRoot)
        #expect(FileManager.default.fileExists(atPath: repoRootURL.appendingPathComponent("Package.swift").path))
        #expect(
            FileManager.default.fileExists(
                atPath: repoRootURL.appendingPathComponent("apps/macos-menubar/Package.swift").path
            )
        )
        #expect(environment.pythonWorkerSocketPath == "/tmp/melix-worker.sock")
        #expect(environment.swiftTextWorkerSocketPath == "/var/run/melix/swift-text-worker.sock")
        #expect(environment.startupSurface == .tray)
        #expect(environment.presentationMode == .tray)
        #expect(environment.terminationMode == .terminate)
    }

    @Test("bootstrap environment infers repo root by locating repository markers")
    @MainActor
    func bootstrapEnvironmentInfersRepoRootFromAnchorPath() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let repoRoot = root.appendingPathComponent("melix-fixture")
        let anchorPath = repoRoot
            .appendingPathComponent("apps")
            .appendingPathComponent("macos-menubar")
            .appendingPathComponent("Sources")
            .appendingPathComponent("AppMain")
            .appendingPathComponent("AppMain.swift")
        try FileManager.default.createDirectory(
            at: anchorPath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data().write(to: repoRoot.appendingPathComponent("AGENTS.md"))
        defer { try? FileManager.default.removeItem(at: root) }

        let inferredRepoRoot = MenuBarBootstrapEnvironment.inferRepoRoot(anchorPath: anchorPath.path)

        #expect(inferredRepoRoot == repoRoot.path)
    }

    @Test("bootstrap cli environment injects a default managed model root under MelixHome")
    @MainActor
    func bootstrapCLIEnvironmentInjectsDefaultManagedModelRoot() {
        let environment = MenuBarBootstrapEnvironment(
            environment: [
                "MELIX_REPO_ROOT": "/tmp/melix-root",
                "MELIX_HOME": "/tmp/melix-home",
            ]
        )

        let cliEnvironment = environment.cliEnvironment(
            base: [
                "MELIX_HOME": "/tmp/melix-home",
            ]
        )

        #expect(cliEnvironment["MELIX_MANAGED_MODEL_ROOT"] == "/tmp/melix-home/models/default-managed")
    }

    @Test("bootstrap cli environment preserves an explicit managed model root override")
    @MainActor
    func bootstrapCLIEnvironmentPreservesExplicitManagedModelRoot() {
        let environment = MenuBarBootstrapEnvironment(
            environment: [
                "MELIX_REPO_ROOT": "/tmp/melix-root",
                "MELIX_HOME": "/tmp/melix-home",
            ]
        )

        let cliEnvironment = environment.cliEnvironment(
            base: [
                "MELIX_HOME": "/tmp/melix-home",
                "MELIX_MANAGED_MODEL_ROOT": "/tmp/custom-managed-root",
            ]
        )

        #expect(cliEnvironment["MELIX_MANAGED_MODEL_ROOT"] == "/tmp/custom-managed-root")
    }

    @Test("termination coordinator launches dev-down and then terminates the application")
    @MainActor
    func terminationCoordinatorLaunchesDevDownAndTerminatesApplication() async throws {
        let recorder = TerminationCoordinatorRecorder()
        let coordinator = MenuBarTerminationCoordinator(
            mode: .devDownScript,
            repoRoot: "/tmp/melix-repo",
            runtimeDirectory: "/tmp/melix-runtime",
            terminateApplication: { recorder.terminateApplicationCallCount += 1 },
            launchDevDownScript: { repoRoot, runtimeDirectory in
                recorder.devDownRequests.append((repoRoot, runtimeDirectory))
            }
        )

        coordinator.requestTermination()

        #expect(recorder.terminateApplicationCallCount == 1)
        #expect(recorder.devDownRequests.count == 1)
        #expect(recorder.devDownRequests.first?.0 == "/tmp/melix-repo")
        #expect(recorder.devDownRequests.first?.1 == "/tmp/melix-runtime")
    }

    @Test("termination coordinator routes quit menu actions once")
    @MainActor
    func terminationCoordinatorRoutesQuitMenuActionsOnce() {
        let recorder = TerminationCoordinatorRecorder()
        let coordinator = MenuBarTerminationCoordinator(
            mode: .devDownScript,
            repoRoot: "/tmp/melix-repo",
            runtimeDirectory: "/tmp/melix-runtime",
            terminateApplication: { recorder.terminateApplicationCallCount += 1 },
            launchDevDownScript: { repoRoot, runtimeDirectory in
                recorder.devDownRequests.append((repoRoot, runtimeDirectory))
            }
        )

        coordinator.handleQuitMenuItem(nil)
        coordinator.handleQuitMenuItem(nil)

        #expect(recorder.terminateApplicationCallCount == 1)
        #expect(recorder.devDownRequests.count == 1)
    }

    @Test("dev-down launcher spawns the shutdown script with MELIX_RUNTIME_DIR")
    @MainActor
    func devDownLauncherSpawnsShutdownScriptWithRuntimeDirectory() async throws {
        let repoRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-dev-down-\(UUID().uuidString)")
        let scriptsDirectory = repoRoot.appendingPathComponent("scripts")
        let outputFile = repoRoot.appendingPathComponent("dev-down-output.txt")
        let completionFile = repoRoot.appendingPathComponent("dev-down-finished.txt")
        let scriptURL = scriptsDirectory.appendingPathComponent("dev_down.sh")
        try FileManager.default.createDirectory(at: scriptsDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repoRoot) }

        try """
        #!/bin/bash
        set -eu
        printf '%s\n' "${MELIX_RUNTIME_DIR:-}" > '\(outputFile.path)'
        touch '\(completionFile.path)'
        """.write(to: scriptURL, atomically: true, encoding: .utf8)

        MenuBarTerminationCoordinator.launchDevDownProcess(
            repoRoot: repoRoot.path,
            runtimeDirectory: "/tmp/melix-runtime"
        )

        try await waitForBootstrapCondition("expected dev_down.sh to finish") {
            FileManager.default.fileExists(atPath: completionFile.path)
        }

        let recordedRuntimeDirectory = try String(contentsOf: outputFile, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        #expect(recordedRuntimeDirectory == "/tmp/melix-runtime")
    }

    @Test("MelixHome defaults to HOME/.melix when MELIX_HOME and app support are unset")
    @MainActor
    func melixHomeDefaultsToHomeDotMelix() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tests-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await withEnvironmentValue("MELIX_HOME", nil) {
            await withEnvironmentValue("MELIX_APP_SUPPORT_DIR", nil) {
                await withEnvironmentValue("HOME", temporaryRoot.path) {
                    let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
                    #expect(melixHome.rootURL.path == temporaryRoot.appendingPathComponent(".melix").path)
                }
            }
        }
    }

    @Test("MelixHome uses app support as packaged app home when MELIX_HOME is unset")
    @MainActor
    func melixHomeUsesAppSupportWhenMelixHomeUnset() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tests-app-support-\(UUID().uuidString)")
        let appSupportHome = temporaryRoot.appendingPathComponent("Application Support/Melix", isDirectory: true)
        try FileManager.default.createDirectory(at: appSupportHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await withEnvironmentValue("MELIX_HOME", nil) {
            await withEnvironmentValue("MELIX_APP_SUPPORT_DIR", appSupportHome.path) {
                await withEnvironmentValue("HOME", temporaryRoot.path) {
                    let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
                    #expect(melixHome.rootURL.path == appSupportHome.path)
                    #expect(
                        melixHome.operatorSessionFileURL.path
                            == appSupportHome.appendingPathComponent("state/operator-session.json").path
                    )
                }
            }
        }
    }

    @Test("MelixHome honors MELIX_HOME override")
    @MainActor
    func melixHomeHonorsMelixHomeOverride() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tests-override-\(UUID().uuidString)")
        let overrideHome = temporaryRoot.appendingPathComponent("custom-home")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await withEnvironmentValue("HOME", temporaryRoot.path) {
            await withEnvironmentValue("MELIX_APP_SUPPORT_DIR", temporaryRoot.appendingPathComponent("ignored").path) {
                await withEnvironmentValue("MELIX_HOME", overrideHome.path) {
                    let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
                    #expect(melixHome.rootURL.path == overrideHome.path)
                }
            }
        }
    }

    @Test("MelixHome creates state and secrets artifacts with secure permissions")
    @MainActor
    func melixHomeCreatesStateAndSecretsArtifactsWithSecurePermissions() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tests-permissions-\(UUID().uuidString)")
        let melixHomePath = temporaryRoot.appendingPathComponent("melix-home")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try await withEnvironmentValue("MELIX_HOME", melixHomePath.path) {
            let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
            let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
            let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
            let serverSession = DesktopServerSessionState(
                id: "server-session-1",
                title: "Primary Server",
                modelID: "melix-dev-text"
            )

            try operatorSessionStore.save(
                OperatorSessionState(
                    selectedSurface: .server,
                    selectedServerSessionID: serverSession.id,
                    serverSessions: [serverSession]
                )
            )
            try apiKeyStore.savePrimaryKey(
                serverSessionID: serverSession.id,
                primaryKey: "melix_sk_test_primary"
            )

            #expect(try posixPermissions(at: melixHome.rootURL) == 0o700)
            #expect(try posixPermissions(at: melixHome.stateDirectoryURL) == 0o700)
            #expect(try posixPermissions(at: melixHome.secretsDirectoryURL) == 0o700)
            #expect(try posixPermissions(at: melixHome.operatorSessionFileURL) == 0o600)
            #expect(try posixPermissions(at: melixHome.serverSessionAPIKeysFileURL) == 0o600)
        }
    }

    @Test("MelixHome bootstrap initializer resolves default persistence stores")
    @MainActor
    func melixHomeBootstrapInitializerResolvesDefaultPersistenceStores() {
        let bootstrap = MelixMenuBarBootstrap(
            client: FakeControlPlaneXPCClient(),
            melixHome: MelixHome(environment: ProcessInfo.processInfo.environment),
            operatorSessionStore: nil,
            serverSessionAPIKeyStore: nil,
            statusMenuFactory: { _, _, _ in RecordingInstallStatusMenu() }
        )

        #expect(type(of: bootstrap) == MelixMenuBarBootstrap.self)
    }

    @Test("MelixHome live bootstrap resolves MELIX_HOME-backed stores")
    @MainActor
    func melixHomeLiveBootstrapResolvesMelixHomeBackedStores() {
        let bootstrap = MelixMenuBarBootstrap.live()
        #expect(type(of: bootstrap) == MelixMenuBarBootstrap.self)
    }

    @Test("live bootstrap injects the subprocess cli workflow runner")
    @MainActor
    func liveBootstrapInjectsSubprocessCLIWorkflowRunner() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        let environment = MenuBarBootstrapEnvironment(
            environment: [
                "MELIX_REPO_ROOT": FileManager.default.currentDirectoryPath,
                "MELIX_CLI": "/tmp/melix-cli",
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-worker.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ]
        )

        let bootstrap = MelixMenuBarBootstrap.live(
            environment: environment,
            cliProcessExecutor: processExecutor
        )

        #expect(bootstrap.viewModel.cliWorkflowRunnerSurface == .subprocess)
    }

    @Test("launchLive can use the default live bootstrap factory")
    @MainActor
    func launchLiveCanUseDefaultBootstrapFactory() async throws {
        guard !MenuBarTestEnvironment.isHeadlessCI else { return }
        let application = RecordingApplicationLifecycle()

        try await withEnvironmentValue("MELIX_REPO_ROOT", FileManager.default.currentDirectoryPath) {
            try await withEnvironmentValue("MELIX_WORKER_SOCKET_PATH", "/tmp/melix-worker.sock") {
                try await withEnvironmentValue("MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH", "/tmp/melix-swift.sock") {
                    MelixMenuBarApp.launchLive(application: application)
                    try await Task.sleep(for: .milliseconds(20))
                }
            }
        }

        #expect(application.recordedPolicies == [.accessory])
        #expect(application.didRun)
    }

    @Test("launcher routes bootstrap termination callbacks through the termination coordinator")
    @MainActor
    func launcherRoutesBootstrapTerminationCallbacksThroughTerminationCoordinator() {
        let application = RecordingApplicationLifecycle()
        let recorder = TerminationCoordinatorRecorder()
        let coordinator = MenuBarTerminationCoordinator(
            mode: .devDownScript,
            repoRoot: "/tmp/melix-repo",
            runtimeDirectory: "/tmp/melix-runtime",
            terminateApplication: { recorder.terminateApplicationCallCount += 1 },
            launchDevDownScript: { repoRoot, runtimeDirectory in
                recorder.devDownRequests.append((repoRoot, runtimeDirectory))
            }
        )
        let bootstrap = MelixMenuBarBootstrap(
            client: FakeControlPlaneXPCClient(),
            statusMenuFactory: { _, _, _ in RecordingInstallStatusMenu() }
        )

        MelixMenuBarLauncher.launch(
            application: application,
            presentationMode: .tray,
            terminationCoordinator: coordinator,
            bootstrapFactory: { terminationHandler in
                terminationHandler()
                return bootstrap
            },
            retain: { _ in }
        )

        #expect(recorder.terminateApplicationCallCount == 1)
        #expect(recorder.devDownRequests.count == 1)
        #expect(application.didRun)
    }
}

@MainActor
private final class RecordingInstallStatusMenu: StatusMenuInstalling {
    private(set) var installCount = 0

    func install() {
        installCount += 1
    }
}

@MainActor
private final class RecordingConsoleAwareStatusMenu: StatusMenuInstalling {
    private(set) var installCount = 0
    var openConsole: (@MainActor @Sendable () -> Void)?

    func install() {
        installCount += 1
    }
}

@MainActor
private final class RecordingDesktopFoundationPresenter: DesktopFoundationPresenting {
    private(set) var showCount = 0

    func show() {
        showCount += 1
    }
}

@MainActor
private final class RecordingApplicationLifecycle: MenuBarApplicationLifecycle {
    private(set) var recordedPolicies: [NSApplication.ActivationPolicy] = []
    private(set) var didRun = false
    private(set) var mainMenu: NSMenu?

    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) {
        recordedPolicies.append(activationPolicy)
    }

    func setMainMenu(_ menu: NSMenu?) {
        mainMenu = menu
    }

    func run() {
        didRun = true
    }
}

@MainActor
private final class RecordingNSApplication: NSApplicationControlling {
    private(set) var recordedPolicies: [NSApplication.ActivationPolicy] = []
    private(set) var runCount = 0
    private(set) var mainMenu: NSMenu?

    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) -> Bool {
        recordedPolicies.append(activationPolicy)
        return true
    }

    func setMainMenu(_ menu: NSMenu?) {
        mainMenu = menu
    }

    func run() {
        runCount += 1
    }
}

@MainActor
private final class TerminationCoordinatorRecorder {
    var terminateApplicationCallCount = 0
    var devDownRequests: [(String, String?)] = []
}

@MainActor
private final class Phase8WindowUIAcceptanceMainRecorder {
    var standardOutput = Data()
    var standardError = Data()
    var flushCount = 0
    var exitCodes: [Int32] = []
    var runLoopInvocationCount = 0
}

@MainActor
private struct SucceedingPhase8WindowUIAcceptanceMainRunner: Phase8WindowUIAcceptanceRunning {
    let result: Phase8WindowUIAcceptanceResult

    func run() async throws -> Phase8WindowUIAcceptanceResult {
        result
    }
}

@MainActor
private func withEnvironmentValue(
    _ key: String,
    _ value: String?,
    operation: @MainActor @Sendable () async throws -> Void
) async rethrows {
    let previousValue = ProcessInfo.processInfo.environment[key]
    if let value {
        setenv(key, value, 1)
    } else {
        unsetenv(key)
    }
    defer {
        if let previousValue {
            setenv(key, previousValue, 1)
        } else {
            unsetenv(key)
        }
    }
    try await operation()
}

private func posixPermissions(at url: URL) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    return (attributes[.posixPermissions] as? NSNumber)?.intValue ?? -1
}

@MainActor
private func waitForBootstrapCondition(
    _ description: String,
    timeout: Duration = .seconds(2),
    pollInterval: Duration = .milliseconds(10),
    condition: @escaping @MainActor () async -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }

    throw MenuBarTestError(description: description)
}
