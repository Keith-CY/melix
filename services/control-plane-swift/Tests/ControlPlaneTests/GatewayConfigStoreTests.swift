import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Gateway Config Store")
struct GatewayConfigStoreTests {
    @Test("environment initializer defaults store under MelixHome config")
    func environmentInitializerDefaultsStoreUnderMelixHomeConfig() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayConfigStore(environment: [
            "HOME": temporaryRoot.path,
            "MELIX_APP_SUPPORT_DIR": temporaryRoot.appendingPathComponent("ignored-app-support").path,
        ])

        #expect(
            await store.storePath()
                == temporaryRoot.appendingPathComponent(".melix/config/gateway-config.json").path
        )
    }

    @Test("summary projects environment defaults and active binding when no operator override exists")
    func summaryProjectsEnvironmentDefaultsAndActiveBindingWhenNoOperatorOverrideExists() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-defaults-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayConfigStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
            defaults: [
                "MELIX_HTTP_HOST": "0.0.0.0",
                "MELIX_HTTP_PORT": "14567",
                "MELIX_GATEWAY_RATE_LIMIT_PER_MINUTE": "77",
                "MELIX_GATEWAY_TIMEOUT_SECONDS": "99",
                "MELIX_MODEL_IDLE_TIMEOUT_SECONDS": "321",
                "MELIX_ALLOWED_HOSTS": "operator.lan:12436, operator.lan:12436",
                "MELIX_ALLOWED_ORIGINS": "http://localhost:5173/app?debug=1, https://APP.example.test/path",
            ]
        )

        let binding = await store.bootstrapBinding()
        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            runtimeBinding: binding,
            fallbackDefaultModelID: "melix-dev-text"
        )
        let listener = try #require(summary.listeners.first)

        #expect(binding.host == "0.0.0.0")
        #expect(binding.port == 14_567)
        #expect(binding.allowedHosts == ["operator.lan"])
        #expect(binding.allowedOrigins == ["http://localhost:5173", "https://app.example.test"])
        #expect(listener.providerID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(listener.requestedHost == "0.0.0.0")
        #expect(listener.requestedPort == 14_567)
        #expect(listener.effectiveHost == "0.0.0.0")
        #expect(listener.effectivePort == 14_567)
        #expect(listener.defaultModelID == "melix-dev-text")
        #expect(listener.servedModelIds == ["melix-dev-text"])
        #expect(listener.rateLimitPerMinute == 77)
        #expect(listener.timeoutSeconds == 99)
        #expect(listener.modelIdleTimeoutSeconds == 321)
        #expect(listener.allowedHosts == ["operator.lan"])
        #expect(listener.allowedOrigins == ["http://localhost:5173", "https://app.example.test"])
        #expect(listener.source == .environmentDefaults)
        #expect(listener.activeBinding)
        #expect(listener.requiresRestart == false)
    }

    @Test("apply persists operator overrides and bootstrap binding reloads them")
    func applyPersistsOperatorOverridesAndBootstrapBindingReloadsThem() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-persist-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        let store = GatewayConfigStore(
            storeURL: storeURL,
            defaults: [:],
            nowUnixMS: { 1_717_171_717_000 }
        )

        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.providerID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "localhost"
        command.port = 18080
        command.defaultModelID = "melix-alt-text"
        command.servedModelIds = ["melix-alt-text", "melix-dev-text"]
        command.rateLimitPerMinute = 240
        command.timeoutSeconds = 45
        command.modelIdleTimeoutSeconds = 900
        command.allowedHosts = ["operator.lan:12436", "operator.lan", "192.168.1.44"]
        command.allowedOrigins = [
            "http://localhost:5173/app?debug=1",
            "http://localhost:5173",
            "https://APP.example.test/path",
        ]
        try await store.apply(command: command)

        let reloadedStore = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        let binding = await reloadedStore.bootstrapBinding()
        let summary = await reloadedStore.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            runtimeBinding: binding,
            fallbackDefaultModelID: "melix-dev-text"
        )
        let listener = try #require(summary.listeners.first)

        #expect(binding.host == "localhost")
        #expect(binding.port == 18_080)
        #expect(binding.allowedHosts == ["operator.lan", "192.168.1.44"])
        #expect(binding.allowedOrigins == ["http://localhost:5173", "https://app.example.test"])
        #expect(listener.requestedHost == "localhost")
        #expect(listener.requestedPort == 18_080)
        #expect(listener.defaultModelID == "melix-alt-text")
        #expect(listener.servedModelIds == ["melix-alt-text", "melix-dev-text"])
        #expect(listener.rateLimitPerMinute == 240)
        #expect(listener.timeoutSeconds == 45)
        #expect(listener.modelIdleTimeoutSeconds == 900)
        #expect(listener.allowedHosts == ["operator.lan", "192.168.1.44"])
        #expect(listener.allowedOrigins == ["http://localhost:5173", "https://app.example.test"])
        #expect(listener.source == .operatorOverride)
        #expect(listener.updatedAtUnixMs == 1_717_171_717_000)
    }

    @Test("apply rejects duplicate served model identifiers at the gateway boundary")
    func applyRejectsDuplicateServedModelIdentifiersAtTheGatewayBoundary() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-duplicates-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayConfigStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.providerID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "localhost"
        command.port = 18080
        command.defaultModelID = "melix-dev-text"
        command.servedModelIds = ["melix-dev-text", "melix-dev-text"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60

        await #expect(throws: GatewayConfigValidationError.duplicateServedModelID) {
            try await store.apply(command: command)
        }
        #expect(GatewayConfigValidationError.duplicateServedModelID.message.contains("gateway API boundary"))
    }

    @Test("summary marks restart required when the requested active listener differs from the runtime binding")
    func summaryMarksRestartRequiredWhenTheRequestedActiveListenerDiffersFromTheRuntimeBinding() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-restart-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayConfigStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.providerID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "0.0.0.0"
        command.port = 18081
        command.defaultModelID = "melix-dev-text"
        command.servedModelIds = ["melix-dev-text"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60
        command.modelIdleTimeoutSeconds = 600
        try await store.apply(command: command)

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            runtimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434),
            fallbackDefaultModelID: "melix-dev-text"
        )
        let listener = try #require(summary.listeners.first)

        #expect(listener.requestedHost == "0.0.0.0")
        #expect(listener.requestedPort == 18_081)
        #expect(listener.effectiveHost == "127.0.0.1")
        #expect(listener.effectivePort == 11_434)
        #expect(listener.activeBinding)
        #expect(listener.requiresRestart)
    }

    @Test("summary keeps non-active persisted listeners inspectable without claiming the active binding")
    func summaryKeepsNonActivePersistedListenersInspectableWithoutClaimingTheActiveBinding() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-inactive-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayConfigStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.providerID = "server-session-secondary"
        command.host = "192.168.1.55"
        command.port = 19090
        command.defaultModelID = "melix-alt-text"
        command.servedModelIds = ["melix-alt-text"]
        command.rateLimitPerMinute = 180
        command.timeoutSeconds = 30
        command.modelIdleTimeoutSeconds = 120
        try await store.apply(command: command)

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID, "server-session-secondary"],
            runtimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434),
            fallbackDefaultModelID: "melix-dev-text"
        )
        let secondary = try #require(
            summary.listeners.first(where: { $0.providerID == "server-session-secondary" })
        )

        #expect(secondary.requestedHost == "192.168.1.55")
        #expect(secondary.requestedPort == 19_090)
        #expect(secondary.effectiveHost == "192.168.1.55")
        #expect(secondary.effectivePort == 19_090)
        #expect(secondary.defaultModelID == "melix-alt-text")
        #expect(secondary.servedModelIds == ["melix-alt-text"])
        #expect(secondary.modelIdleTimeoutSeconds == 120)
        #expect(secondary.source == .operatorOverride)
        #expect(secondary.activeBinding == false)
        #expect(secondary.requiresRestart == false)
    }
}
