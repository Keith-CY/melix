import AppKit
import Foundation
import Testing

@testable import AppMain

@Suite("Menu Bar Bootstrap")
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
            statusMenuFactory: { _, _ in menu }
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
            statusMenuFactory: { _, _ in menu }
        )
        var retainedBootstrap: MelixMenuBarBootstrap?

        MelixMenuBarLauncher.launch(
            application: app,
            bootstrapFactory: { bootstrap },
            retain: { retainedBootstrap = $0 }
        )
        try await Task.sleep(for: .milliseconds(20))

        #expect(app.didSetAccessoryActivationPolicy)
        #expect(app.didRun)
        #expect(retainedBootstrap === bootstrap)
        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
    }

    @Test("live application delegates activation policy and run to its application controller")
    @MainActor
    func liveApplicationDelegatesToApplicationController() async throws {
        let application = RecordingNSApplication()
        let liveApplication = LiveMenuBarApplication(application: application)

        liveApplication.setAccessoryActivationPolicy()
        liveApplication.run()

        #expect(application.recordedPolicies == [.accessory])
        #expect(application.runCount == 1)
    }

    @Test("launchLive uses the shared launcher path")
    @MainActor
    func launchLiveUsesSharedLauncherPath() async throws {
        let application = RecordingApplicationLifecycle()
        let client = FakeControlPlaneXPCClient()
        let menu = RecordingInstallStatusMenu()
        let bootstrap = MelixMenuBarBootstrap(
            client: client,
            statusMenuFactory: { _, _ in menu }
        )

        MelixMenuBarApp.launchLive(
            application: application,
            bootstrapFactory: { bootstrap }
        )
        try await waitForBootstrapCondition("expected launchLive handshake to complete") {
            await client.handshakeCount == 1
        }

        #expect(application.didSetAccessoryActivationPolicy)
        #expect(application.didRun)
        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
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
            statusMenuFactory: { _, openConsole in
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
            statusMenuFactory: { _, _ in menu }
        )

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))
        capturedViewModel?.openCommandCenter()

        #expect(menu.installCount == 1)
        #expect(desktopPresenter.showCount == 0)
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
            ]
        )

        #expect(environment.repoRoot == "/tmp/melix-root")
        #expect(environment.pythonWorkerSocketPath == "/tmp/python.sock")
        #expect(environment.swiftTextWorkerSocketPath == "/tmp/swift.sock")
    }

    @Test("bootstrap environment falls back to inferred repo root and default sockets")
    @MainActor
    func bootstrapEnvironmentFallsBackToDefaults() {
        let environment = MenuBarBootstrapEnvironment(environment: [:])

        #expect(environment.repoRoot.hasSuffix("/melix"))
        #expect(environment.pythonWorkerSocketPath == "/tmp/melix-worker.sock")
        #expect(environment.swiftTextWorkerSocketPath == "/var/run/melix/swift-text-worker.sock")
    }

    @Test("MelixHome defaults to HOME/.melix when MELIX_HOME is unset")
    @MainActor
    func melixHomeDefaultsToHomeDotMelix() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tests-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await withEnvironmentValue("MELIX_HOME", nil) {
            await withEnvironmentValue("HOME", temporaryRoot.path) {
                let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
                #expect(melixHome.rootURL.path == temporaryRoot.appendingPathComponent(".melix").path)
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
            await withEnvironmentValue("MELIX_HOME", overrideHome.path) {
                let melixHome = MelixHome(environment: ProcessInfo.processInfo.environment)
                #expect(melixHome.rootURL.path == overrideHome.path)
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
            statusMenuFactory: { _, _ in RecordingInstallStatusMenu() }
        )

        #expect(type(of: bootstrap) == MelixMenuBarBootstrap.self)
    }

    @Test("MelixHome live bootstrap resolves MELIX_HOME-backed stores")
    @MainActor
    func melixHomeLiveBootstrapResolvesMelixHomeBackedStores() {
        let bootstrap = MelixMenuBarBootstrap.live()
        #expect(type(of: bootstrap) == MelixMenuBarBootstrap.self)
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

        #expect(application.didSetAccessoryActivationPolicy)
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
    private(set) var didSetAccessoryActivationPolicy = false
    private(set) var didRun = false

    func setAccessoryActivationPolicy() {
        didSetAccessoryActivationPolicy = true
    }

    func run() {
        didRun = true
    }
}

@MainActor
private final class RecordingNSApplication: NSApplicationControlling {
    private(set) var recordedPolicies: [NSApplication.ActivationPolicy] = []
    private(set) var runCount = 0

    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) -> Bool {
        recordedPolicies.append(activationPolicy)
        return true
    }

    func run() {
        runCount += 1
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
