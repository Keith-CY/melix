import AppKit
import Foundation
import Testing

@testable import AppMain

@Suite("Menu Bar Bootstrap")
struct AppMainBootstrapTests {
    @Test("default bootstrap factory creates a live status menu")
    @MainActor
    func defaultBootstrapFactoryCreatesStatusMenu() async throws {
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
            statusMenuFactory: { _ in menu }
        )

        bootstrap.start()
        try await Task.sleep(for: .milliseconds(20))

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
            statusMenuFactory: { _ in menu }
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
            statusMenuFactory: { _ in menu }
        )

        MelixMenuBarApp.launchLive(
            application: application,
            bootstrapFactory: { bootstrap }
        )
        try await Task.sleep(for: .milliseconds(20))

        #expect(application.didSetAccessoryActivationPolicy)
        #expect(application.didRun)
        #expect(menu.installCount == 1)
        #expect(await client.handshakeCount == 1)
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
