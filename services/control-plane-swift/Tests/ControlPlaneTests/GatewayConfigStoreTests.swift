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
        #expect(listener.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
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
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
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
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
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
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
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
        command.serverSessionID = "server-session-secondary"
        command.host = "192.168.1.55"
        command.port = 19090
        command.defaultModelID = "melix-alt-text"
        command.servedModelIds = ["melix-alt-text"]
        command.rateLimitPerMinute = 180
        command.timeoutSeconds = 30
        command.modelIdleTimeoutSeconds = 120
        try await store.apply(command: command)

        var activeCommand = command
        activeCommand.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        activeCommand.host = "127.0.0.1"
        activeCommand.port = 11_434
        activeCommand.defaultModelID = "melix-dev-text"
        activeCommand.servedModelIds = ["melix-dev-text"]
        try await store.apply(command: activeCommand)

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID, "server-session-secondary"],
            runtimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434),
            fallbackDefaultModelID: "melix-dev-text"
        )
        let secondary = try #require(
            summary.listeners.first(where: { $0.serverSessionID == "server-session-secondary" })
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

    @Test("packaged environment listener remains authoritative without discarding the persisted model roster")
    func packagedEnvironmentListenerRemainsAuthoritativeWithoutDiscardingPersistedModelRoster() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-packaged-binding-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        let operatorStore = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "0.0.0.0"
        command.port = 11_434
        command.defaultModelID = "mlx-community/persisted-model"
        command.servedModelIds = ["mlx-community/persisted-model", "mlx-community/secondary-model"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60
        try await operatorStore.apply(command: command)

        let packagedStore = GatewayConfigStore(
            storeURL: storeURL,
            defaults: [
                "MELIX_HTTP_HOST": "127.0.0.1",
                "MELIX_HTTP_PORT": "12436",
                "MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY": "environment",
            ]
        )
        let binding = await packagedStore.bootstrapBinding()
        let roster = try #require(
            await packagedStore.activeModelRosterIfConfigured(runtimeBinding: binding)
        )
        let summary = await packagedStore.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            runtimeBinding: binding,
            fallbackDefaultModelID: "fallback-model"
        )
        let listener = try #require(summary.listeners.first)

        #expect(binding.host == "127.0.0.1")
        #expect(binding.port == 12_436)
        #expect(roster.defaultModelID == "mlx-community/persisted-model")
        #expect(roster.servedModelIDs == [
            "mlx-community/persisted-model",
            "mlx-community/secondary-model",
        ])
        #expect(listener.requestedHost == "0.0.0.0")
        #expect(listener.requestedPort == 11_434)
        #expect(listener.effectiveHost == "127.0.0.1")
        #expect(listener.effectivePort == 12_436)
        #expect(listener.requiresRestart)
    }

    @Test("resident stores observe and preserve sequential updates written through another store")
    func residentStoresObserveAndPreserveSequentialUpdatesWrittenThroughAnotherStore() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-cross-process-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        let residentReader = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        let residentWriter = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        let externalCLIStore = GatewayConfigStore(storeURL: storeURL, defaults: [:])

        var activeCommand = Melix_Controlplane_V1_ApplyGatewayConfig()
        activeCommand.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        activeCommand.host = "127.0.0.1"
        activeCommand.port = 12_436
        activeCommand.defaultModelID = "mlx-community/new-model"
        activeCommand.servedModelIds = ["mlx-community/new-model"]
        activeCommand.rateLimitPerMinute = 240
        activeCommand.timeoutSeconds = 90
        activeCommand.modelIdleTimeoutSeconds = 300
        try await externalCLIStore.apply(command: activeCommand)

        let binding = await residentReader.bootstrapBinding()
        let roster = await residentReader.activeModelRoster(
            runtimeBinding: binding,
            fallbackDefaultModelID: "stale-fallback",
            fallbackServedModelIDs: ["stale-fallback"]
        )
        #expect(roster.defaultModelID == "mlx-community/new-model")
        #expect(roster.servedModelIDs == ["mlx-community/new-model"])
        #expect(roster.modelIdleTimeoutSeconds == 300)
        #expect(roster.explicit)

        var secondaryCommand = activeCommand
        secondaryCommand.serverSessionID = "server-session-secondary"
        secondaryCommand.defaultModelID = "mlx-community/secondary-model"
        secondaryCommand.servedModelIds = ["mlx-community/secondary-model"]
        try await residentWriter.apply(command: secondaryCommand)

        let switchedRoster = try #require(
            await residentReader.activeModelRosterIfConfigured(runtimeBinding: binding)
        )
        #expect(switchedRoster.serverSessionID == "server-session-secondary")
        #expect(switchedRoster.defaultModelID == "mlx-community/secondary-model")
        #expect(switchedRoster.servedModelIDs == ["mlx-community/secondary-model"])

        let summary = await residentReader.summary(
            serverSessionIDs: [],
            runtimeBinding: binding,
            fallbackDefaultModelID: "stale-fallback"
        )
        #expect(summary.listeners.map(\.serverSessionID) == [
            ServerSessionRuntimeStore.defaultServerSessionID,
            "server-session-secondary",
        ])
        #expect(
            summary.listeners.first(where: { $0.serverSessionID == "server-session-secondary" })?.activeBinding
                == true
        )
        #expect(
            summary.listeners.first(where: { $0.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID })?
                .activeBinding == false
        )

        let reloadedBinding = await GatewayConfigStore(storeURL: storeURL, defaults: [:]).bootstrapBinding()
        #expect(reloadedBinding.activeServerSessionID == "server-session-secondary")
    }

    @Test("concurrent store applies preserve every listener through the sibling file lock")
    func concurrentStoreAppliesPreserveEveryListenerThroughTheSiblingFileLock() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-concurrent-writers-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        let writerCount = 32
        let barrier = GatewayConfigStoreTestBarrier(participantCount: writerCount)

        try await withThrowingTaskGroup(of: Void.self) { group in
            for index in 0..<writerCount {
                let store = GatewayConfigStore(
                    storeURL: storeURL,
                    defaults: [:],
                    nowUnixMS: { Int64(index + 1) }
                )
                group.addTask {
                    let command = makeConcurrentGatewayConfigCommand(index: index)
                    await barrier.arriveAndWait()
                    try await store.apply(command: command)
                }
            }
            try await group.waitForAll()
        }

        let reloadedStore = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        let binding = await reloadedStore.bootstrapBinding()
        let summary = await reloadedStore.summary(
            serverSessionIDs: [],
            runtimeBinding: binding,
            fallbackDefaultModelID: "fallback-model"
        )
        let expectedServerSessionIDs = Set(
            (0..<writerCount).map { "server-session-concurrent-\($0)" }
        )

        #expect(Set(summary.listeners.map(\.serverSessionID)) == expectedServerSessionIDs)
        #expect(expectedServerSessionIDs.contains(binding.activeServerSessionID))
        #expect(summary.listeners.filter { $0.activeBinding }.count == 1)
        #expect(
            summary.listeners.first(where: { $0.activeBinding })?.serverSessionID
                == binding.activeServerSessionID
        )
        #expect(FileManager.default.fileExists(atPath: storeURL.appendingPathExtension("lock").path))
    }

    @Test("a sibling lock open failure does not publish gateway config")
    func siblingLockOpenFailureDoesNotPublishGatewayConfig() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-lock-failure-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        try FileManager.default.createDirectory(
            at: storeURL.appendingPathExtension("lock"),
            withIntermediateDirectories: false
        )
        let store = GatewayConfigStore(storeURL: storeURL, defaults: [:])

        do {
            try await store.apply(command: makeConcurrentGatewayConfigCommand(index: 0))
            Issue.record("Expected the sibling lock open to fail.")
        } catch {
            #expect((error as NSError).domain == NSPOSIXErrorDomain)
        }
        #expect(FileManager.default.fileExists(atPath: storeURL.path) == false)
    }

    @Test("legacy gateway documents without an active owner retain the runtime binding fallback")
    func legacyGatewayDocumentsWithoutActiveOwnerRetainRuntimeBindingFallback() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-legacy-owner-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        let legacyDocument = Data(
            """
            {
              "schema_version": 1,
              "listeners": [
                {
                  "server_session_id": "server-session-1",
                  "host": "127.0.0.1",
                  "port": 12436,
                  "default_model_id": "legacy-model",
                  "served_model_ids": ["legacy-model"],
                  "rate_limit_per_minute": 120,
                  "timeout_seconds": 60,
                  "model_idle_timeout_seconds": 600,
                  "allowed_hosts": [],
                  "allowed_origins": [],
                  "source": 3,
                  "updated_at_unix_ms": 123
                }
              ]
            }
            """.utf8
        )
        try legacyDocument.write(to: storeURL, options: .atomic)

        let store = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        let binding = await store.bootstrapBinding()
        let roster = try #require(await store.activeModelRosterIfConfigured(runtimeBinding: binding))

        #expect(binding.activeServerSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(roster.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(roster.defaultModelID == "legacy-model")
    }

    @Test("malformed gateway documents fall back without retaining a stale active owner")
    func malformedGatewayDocumentsFallBackWithoutRetainingStaleActiveOwner() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-config-malformed-owner-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        try Data("{ malformed".utf8).write(to: storeURL, options: .atomic)

        let store = GatewayConfigStore(storeURL: storeURL, defaults: [:])
        let binding = await store.bootstrapBinding()
        let roster = await store.activeModelRoster(
            runtimeBinding: binding,
            fallbackDefaultModelID: "fallback-model",
            fallbackServedModelIDs: ["fallback-model"]
        )

        #expect(binding.activeServerSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(roster.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(roster.defaultModelID == "fallback-model")
        #expect(roster.explicit == false)
    }
}

private actor GatewayConfigStoreTestBarrier {
    private let participantCount: Int
    private var arrivedCount = 0
    private var waiters: [CheckedContinuation<Void, Never>] = []

    init(participantCount: Int) {
        self.participantCount = participantCount
    }

    func arriveAndWait() async {
        arrivedCount += 1
        if arrivedCount == participantCount {
            let waiting = waiters
            waiters.removeAll()
            for waiter in waiting {
                waiter.resume()
            }
            return
        }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }
}

private func makeConcurrentGatewayConfigCommand(
    index: Int
) -> Melix_Controlplane_V1_ApplyGatewayConfig {
    let modelID = "mlx-community/concurrent-model-\(index)"
    var command = Melix_Controlplane_V1_ApplyGatewayConfig()
    command.serverSessionID = "server-session-concurrent-\(index)"
    command.host = "127.0.0.1"
    command.port = UInt32(15_000 + index)
    command.defaultModelID = modelID
    command.servedModelIds = [modelID]
    command.rateLimitPerMinute = 120
    command.timeoutSeconds = 60
    command.modelIdleTimeoutSeconds = 600
    return command
}
