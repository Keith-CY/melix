import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Control Plane Service")
struct ControlPlaneServiceTests {
    @Test("handshake returns a typed snapshot")
    func handshakeReturnsTypedSnapshot() async throws {
        let service = ControlPlaneService()

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-1"

        let response = try await service.handshake(request)

        #expect(response.protocolVersion == "melix.controlplane.v1")
        #expect(!response.serverVersion.isEmpty)
        #expect(!response.daemonInstanceID.isEmpty)
        #expect(response.snapshot.serverState == .serverReady)
        #expect(response.snapshot.runtimeSessions.first?.serverSessionID == "server-session-1")
        #expect(response.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(response.features.contains("cache-metadata"))
        #expect(response.features.contains("session-graph"))
        #expect(response.features.contains("server-session-runtime"))
        #expect(response.features.contains("image-jobs"))
    }

    @Test("handshake exposes MCP tool catalog state in features and snapshot")
    func handshakeExposesMCPToolCatalogStateInFeaturesAndSnapshot() async throws {
        let service = ControlPlaneService(
            mcpToolCatalog: MCPToolCatalog(
                configPath: "/tmp/mcp-tools.json",
                defaultParserMode: .json,
                sources: [
                    .init(
                        sourceID: "filesystem",
                        enabled: true,
                        namespaces: ["tools.fs.read", "tools.fs.write"]
                    ),
                    .init(
                        sourceID: "disabled-search",
                        enabled: false,
                        namespaces: ["tools.search"]
                    ),
                ]
            )
        )

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-mcp"

        let response = try await service.handshake(request)

        #expect(response.features.contains("mcp-tools"))
        #expect(response.snapshot.mcpTools.configPath == "/tmp/mcp-tools.json")
        #expect(response.snapshot.mcpTools.defaultParserMode == "json")
        #expect(response.snapshot.mcpTools.enabledSourceCount == 1)
        #expect(response.snapshot.mcpTools.resolvedToolCount == 2)
        #expect(response.snapshot.mcpTools.sources.count == 3)
        #expect(response.snapshot.mcpTools.sources[0].sourceID == "config-discovery")
        #expect(response.snapshot.mcpTools.sources[0].namespaces == ["explicit"])
        #expect(response.snapshot.mcpTools.sources[0].policyState == "explicit_or_melix_home_only")
        #expect(response.snapshot.mcpTools.sources[1].sourceID == "disabled-search")
        #expect(response.snapshot.mcpTools.sources[2].sourceID == "filesystem")
        #expect(response.snapshot.mcpTools.sources[2].namespaces == ["tools.fs.read", "tools.fs.write"])
    }

    @Test("handshake exposes typed tooling settings state")
    func handshakeExposesTypedToolingSettingsState() async throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let gatewayConfigStore = GatewayConfigStore(
            storeURL: tempDirectory.appendingPathComponent("gateway-config.json"),
            defaults: [:]
        )
        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: tempDirectory.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        let imageDefaultsStore = ImageDefaultsStore(
            storeURL: tempDirectory.appendingPathComponent("image-defaults.json"),
            defaults: [:]
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            mcpToolCatalog: MCPToolCatalog(
                configPath: "/tmp/mcp-tools.json",
                defaultParserMode: .json,
                sources: [
                    .init(sourceID: "filesystem", enabled: true, namespaces: ["tools.fs.read"])
                ]
            ),
            gatewayConfigStore: gatewayConfigStore,
            gatewayServingDefaultsStore: servingDefaultsStore,
            imageDefaultsStore: imageDefaultsStore,
            environment: [
                "MELIX_CONTROL_PLANE_METRICS_PATH": "/tmp/control-plane-metrics.json"
            ],
            launchArguments: [
                "melix-control-plane",
                "--config",
                "/tmp/melix.json",
                "--verbose",
            ]
        )

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-tooling"

        let response = try await service.handshake(request)

        #expect(response.snapshot.toolingSettings.embedding.modelID == "melix-dev-embed")
        #expect(response.snapshot.toolingSettings.embedding.loaded == false)
        #expect(response.snapshot.toolingSettings.embedding.preloaded == false)
        #expect(response.snapshot.toolingSettings.builtinToolParserModes.contains("json"))
        #expect(response.snapshot.toolingSettings.builtinToolParserModes.contains("qwen"))
        #expect(response.snapshot.toolingSettings.mcpDefaultParserMode == "json")
        #expect(response.snapshot.toolingSettings.mcpConfigPath == "/tmp/mcp-tools.json")
        #expect(response.snapshot.toolingSettings.additionalArguments == ["--config", "/tmp/melix.json", "--verbose"])
        let configPaths = Dictionary(
            uniqueKeysWithValues: response.snapshot.toolingSettings.configPaths.map { ($0.pathID, $0.path) }
        )
        #expect(configPaths["gateway_config_store_path"] == tempDirectory.appendingPathComponent("gateway-config.json").path)
        #expect(configPaths["gateway_serving_defaults_store_path"] == tempDirectory.appendingPathComponent("gateway-serving-defaults.json").path)
        #expect(configPaths["image_defaults_store_path"] == tempDirectory.appendingPathComponent("image-defaults.json").path)
        #expect(configPaths["control_plane_metrics_path"] == "/tmp/control-plane-metrics.json")
    }

    @Test("handshake exposes typed API onboarding state")
    func handshakeExposesTypedAPIOnboardingState() async throws {
        let service = ControlPlaneService()

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-api-onboarding"

        let response = try await service.handshake(request)
        let surfaces = Dictionary(
            uniqueKeysWithValues: response.snapshot.apiOnboarding.surfaces.map { ($0.surfaceID, $0) }
        )
        let endpoints = Dictionary(
            uniqueKeysWithValues: response.snapshot.apiOnboarding.endpoints.map { ($0.endpointID, $0) }
        )

        #expect(surfaces["local_service"]?.status == .shipped)
        #expect(surfaces["openai_compatible"]?.status == .shipped)
        #expect(surfaces["anthropic_messages"]?.status == .shipped)
        #expect(surfaces["ollama_compatibility"]?.status == .compatibilityOnly)
        #expect(
            surfaces["ollama_compatibility"]?.compatibilityNote
                .contains("Native /api/chat") == true
        )
        #expect(endpoints["health"]?.path == "/health")
        #expect(endpoints["health"]?.summary.contains("liveness") == true)
        #expect(endpoints["health_diagnostics"]?.path == "/v1/melix/health")
        #expect(endpoints["cache_stats"]?.path == "/v1/cache/stats")
        #expect(endpoints["responses"]?.streaming == true)
        #expect(endpoints["messages"]?.surfaceID == "anthropic_messages")
        #expect(endpoints["images_generations"]?.method == "POST")
    }

    @Test("gateway access policy normalizes shared-access configuration and rejects invalid keys")
    func gatewayAccessPolicyNormalizesSharedAccessConfigurationAndRejectsInvalidKeys() {
        let leakedToken = "sk-operator-b"
        let rejectedToken = "sk-rejected"
        let policy = GatewayAccessPolicy.load(
            environment: [
                "MELIX_GATEWAY_AUTH_MODE": "api_keys",
                "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
                "MELIX_GATEWAY_API_KEYS_JSON": """
                [
                  {"id":"operator-a","label":"Operator A","token_hint":"operator-a","token":"sk-operator-a"},
                  {"id":"operator-a","label":"Duplicate","token_hint":"duplicate","token":"sk-operator-a-2"},
                  {"id":"empty-token","label":"Empty Token","token_hint":"empty-token","token":"   "},
                  {"id":"operator-b","label":"Operator B \(leakedToken)","token_hint":"operator-b \(leakedToken)","token":"\(leakedToken)"},
                  {"id":"secret-\(rejectedToken)","label":"Rejected","token_hint":"Rejected","token":"\(rejectedToken)"}
                ]
                """,
            ]
        )

        #expect(policy.mode == .apiKeys)
        #expect(policy.sharedAccessEnabled)
        #expect(policy.sharedAccessReady)
        #expect(policy.acceptedAPIKeyCount == 2)
        #expect(policy.summary.acceptedApiKeyCount == 2)
        #expect(policy.summary.keys.map(\.keyID) == ["operator-a", "operator-b"])
        #expect(policy.summary.keys.map(\.label) == ["operator-a", "operator-b"])
        #expect(policy.summary.keys.map(\.tokenHint) == ["operator-a", "operator-b"])
        #expect(policy.summary.keys.contains(where: { $0.keyID.contains(leakedToken) }) == false)
        #expect(policy.summary.keys.contains(where: { $0.label.contains(leakedToken) }) == false)
        #expect(policy.summary.keys.contains(where: { $0.tokenHint.contains(leakedToken) }) == false)
    }

    @Test("gateway access policy normalizes bearer-token environment metadata without leaking secrets")
    func gatewayAccessPolicyNormalizesBearerTokenEnvironmentMetadataWithoutLeakingSecrets() {
        let leakedToken = "sk-bearer-secret"
        let policy = GatewayAccessPolicy.load(
            environment: [
                "MELIX_GATEWAY_AUTH_MODE": "bearer_token",
                "MELIX_GATEWAY_BEARER_TOKEN": leakedToken,
                "MELIX_GATEWAY_BEARER_TOKEN_ID": "primary",
                "MELIX_GATEWAY_BEARER_TOKEN_LABEL": "Primary \(leakedToken)",
                "MELIX_GATEWAY_BEARER_TOKEN_HINT": "Hint \(leakedToken)",
            ]
        )

        #expect(policy.mode == .bearerToken)
        #expect(policy.summary.keys.map(\.keyID) == ["primary"])
        #expect(policy.summary.keys.map(\.label) == ["primary"])
        #expect(policy.summary.keys.map(\.tokenHint) == ["primary"])
        #expect(policy.summary.keys.contains(where: { $0.keyID.contains(leakedToken) }) == false)
        #expect(policy.summary.keys.contains(where: { $0.label.contains(leakedToken) }) == false)
        #expect(policy.summary.keys.contains(where: { $0.tokenHint.contains(leakedToken) }) == false)
    }

    @Test("handshake projects gateway access summary without leaking raw secrets")
    func handshakeProjectsGatewayAccessSummaryWithoutLeakingRawSecrets() async throws {
        let service = ControlPlaneService(
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(
                        keyID: "desktop-agent",
                        label: "Desktop Agent",
                        tokenHint: "desktop-agent",
                        token: "sk-desktop-agent"
                    ),
                    .init(
                        keyID: "codex",
                        label: "Codex",
                        tokenHint: "codex",
                        token: "sk-codex"
                    ),
                ]
            )
        )

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-shared-access"

        let response = try await service.handshake(request)

        #expect(response.snapshot.hasGatewayAccess)
        #expect(response.snapshot.gatewayAccess.mode == .apiKeys)
        #expect(response.snapshot.gatewayAccess.sharedAccessEnabled)
        #expect(response.snapshot.gatewayAccess.sharedAccessReady)
        #expect(response.snapshot.gatewayAccess.requiredHeader == .xApiKey)
        #expect(response.snapshot.gatewayAccess.acceptedApiKeyCount == 2)
        #expect(response.snapshot.gatewayAccess.keys.map(\.tokenHint) == ["desktop-agent", "codex"])
        #expect(response.snapshot.gatewayAccess.keys.contains(where: { $0.tokenHint == "sk-desktop-agent" }) == false)
        #expect(response.snapshot.gatewayAccess.keys.contains(where: { $0.tokenHint == "sk-codex" }) == false)
    }

    @Test("persistent auth session restore prunes expired and malformed records while keeping active remembered sessions")
    func persistentAuthSessionRestorePrunesExpiredAndMalformedRecordsWhileKeepingActiveRememberedSessions() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-restore-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("persistent-auth-sessions.json")
        let payload = """
        {
          "schema_version": 1,
          "sessions": [
            {
              "created_at_unix_ms": 1000,
              "expires_at_unix_ms": 60000,
              "key_id": "codex",
              "last_restored_at_unix_ms": 0,
              "remember_me": true,
              "revoked_at_unix_ms": 0,
              "session_id": "session-active",
              "token_hash": "hash-active"
            },
            {
              "created_at_unix_ms": 1000,
              "expires_at_unix_ms": 1500,
              "key_id": "expired",
              "last_restored_at_unix_ms": 0,
              "remember_me": true,
              "revoked_at_unix_ms": 0,
              "session_id": "session-expired",
              "token_hash": "hash-expired"
            },
            "malformed-entry"
          ]
        }
        """
        try #require(payload.data(using: .utf8)).write(to: storeURL)

        let metricsStore = MetricsStore()
        let store = PersistentAuthSessionStore(
            storeURL: storeURL,
            metricsStore: metricsStore,
            retentionTTLSeconds: 3600,
            nowUnixMs: { 2_000 }
        )

        let result = try await store.restorePersistedSessions()

        #expect(result.restoredSessionCount == 1)
        #expect(result.expiredSessionCount == 1)
        #expect(result.malformedRecordCount == 1)
        #expect(await metricsStore.value(forKey: "persistent_session.active_session_count") == 1)
        #expect(await metricsStore.value(forKey: "persistent_session.remembered_session_count") == 1)
        #expect(await metricsStore.value(forKey: "persistent_session.expired_session_count") == 1)
        #expect(await metricsStore.value(forKey: "persistent_session.retention_ttl_seconds") == 3600)
    }

    @Test("applying a new gateway policy revokes remembered sessions that no longer match the keyring")
    func applyingANewGatewayPolicyRevokesRememberedSessionsThatNoLongerMatchTheKeyring() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-reconcile-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let metricsStore = MetricsStore()
        let store = PersistentAuthSessionStore(
            storeURL: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json"),
            metricsStore: metricsStore,
            retentionTTLSeconds: 3600,
            nowUnixMs: { 10_000 }
        )
        let issued = try await store.issueSession(keyID: "desktop-agent", rememberMe: true)
        let service = ControlPlaneService(
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                ]
            ),
            persistentAuthSessionStore: store
        )

        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "apply-gateway-access"
        request.commandType = "server.apply_gateway_access"
        request.targetID = "server-session-1"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyGatewayAccess = Melix_Controlplane_V1_ApplyGatewayAccess()
        request.server.applyGatewayAccess.serverSessionID = "server-session-1"
        request.server.applyGatewayAccess.mode = .none
        request.server.applyGatewayAccess.sharedAccessEnabled = false
        let response = try await service.execute(request)
        let validation = await store.validateSessionToken(
            issued.token,
            policy: GatewayAccessPolicy.localTrust
        )

        #expect(response.ok)
        #expect(validation == .failure(.revokedSession(sessionID: issued.metadata.sessionID, keyID: "desktop-agent", rememberMe: true)))
    }

    @Test("execute handles server.get_snapshot")
    func executeHandlesServerSnapshot() async throws {
        let service = ControlPlaneService()
        let request = makeServerSnapshotRequest()

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.requestID == request.requestID)
        #expect(response.commandType == request.commandType)
        #expect(response.server.snapshot.serverState == .serverReady)
        #expect(response.server.snapshot.runtimeSessions.first?.serverSessionID == "server-session-1")
        #expect(response.server.snapshot.runtimeSessions.first?.powerState == .active)
    }

    @Test("execute syncs imported registry models before server snapshots")
    func executeSyncsImportedRegistryModelsBeforeServerSnapshots() async throws {
        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let importedModelPath = "/tmp/managed-root/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": importedModelID,
                    "model_path": importedModelPath,
                    "model_kind": "text",
                    "revision": "main",
                    "tokenizer_hash": "hf.mlx-community.Qwen3.5-0.8B-OptiQ-4bit",
                    "quant_profile_id": "",
                    "parser_mode": "text",
                    "reasoning_mode": "off",
                    "max_context": 8192,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/managed-root",
                        "melix.registry_relative_path": "huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main",
                        "melix.model_path": importedModelPath,
                        "melix.hf_repo_id": importedModelID,
                        "melix.capability.class": "text",
                        "melix.capability.route_kind": "swift_text",
                        "melix.capability.supported_modalities": "text",
                        "melix.capability.supported_tasks": "generate",
                    ],
                ],
            ]
        )
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeServerSnapshotRequest())
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)
        let imported = try #require(
            response.server.snapshot.models.first(where: { $0.modelID == importedModelID })
        )

        #expect(response.ok)
        #expect(lastRequest.ext["operation"] == "registry_snapshot")
        #expect(lastRequest.ext["melix.registry_rescan"] == "true")
        #expect(imported.kind == "text")
        #expect(imported.settings.ext["melix.model_path"] == importedModelPath)
    }

    @Test("execute projects typed gateway config state through server snapshots")
    func executeProjectsTypedGatewayConfigStateThroughServerSnapshots() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-gateway-snapshot-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let gatewayStore = GatewayConfigStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
            defaults: [:],
            nowUnixMS: { 1_717_171_717_000 }
        )
        try await gatewayStore.apply(command: makeApplyGatewayConfigCommand(
            host: "0.0.0.0",
            port: 18_080,
            defaultModelID: "melix-dev-text",
            rateLimitPerMinute: 180,
            timeoutSeconds: 45
        ))
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            gatewayConfigStore: gatewayStore,
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434)
        )

        let response = try await service.execute(makeServerSnapshotRequest())
        let listener = try #require(response.server.snapshot.gatewayConfig.listeners.first)

        #expect(response.ok)
        #expect(listener.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(listener.requestedHost == "0.0.0.0")
        #expect(listener.requestedPort == 18_080)
        #expect(listener.effectiveHost == "127.0.0.1")
        #expect(listener.effectivePort == 11_434)
        #expect(listener.defaultModelID == "melix-dev-text")
        #expect(listener.rateLimitPerMinute == 180)
        #expect(listener.timeoutSeconds == 45)
        #expect(listener.source == .operatorOverride)
        #expect(listener.activeBinding)
        #expect(listener.requiresRestart)
    }

    @Test("execute applies gateway config and returns a hydrated snapshot")
    func executeAppliesGatewayConfigAndReturnsAHydratedSnapshot() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-gateway-apply-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let metricsStore = MetricsStore()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            metricsStore: metricsStore,
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:],
                nowUnixMS: { 1_717_171_717_100 }
            ),
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434)
        )

        let response = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-alt-text",
                rateLimitPerMinute: 240,
                timeoutSeconds: 90
            )
        )
        let listener = try #require(response.server.snapshot.gatewayConfig.listeners.first)

        #expect(response.ok)
        #expect(listener.requestedHost == "127.0.0.1")
        #expect(listener.requestedPort == 11_434)
        #expect(listener.effectiveHost == "127.0.0.1")
        #expect(listener.effectivePort == 11_434)
        #expect(listener.defaultModelID == "melix-alt-text")
        #expect(listener.rateLimitPerMinute == 240)
        #expect(listener.timeoutSeconds == 90)
        #expect(listener.requiresRestart == false)
        #expect(await metricsStore.value(forKey: "gateway.config_apply_ms") >= 0)
        #expect(await metricsStore.value(forKey: "gateway.config_requires_restart_count") == 0)
    }

    @Test("execute snapshots gateway config even when no catalog model is available")
    func executeSnapshotsGatewayConfigEvenWhenNoCatalogModelIsAvailable() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-gateway-empty-catalog-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:]
            ),
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434)
        )

        let response = try await service.execute(makeServerSnapshotRequest())
        let listener = try #require(response.server.snapshot.gatewayConfig.listeners.first)

        #expect(response.ok)
        #expect(listener.defaultModelID == "")
        #expect(listener.requestedHost == "127.0.0.1")
        #expect(listener.requestedPort == UInt32(MelixGatewayDefaults.port))
    }

    @Test("execute rejects gateway config target mismatches and typed payload validation failures")
    func executeRejectsGatewayConfigTargetMismatchesAndTypedPayloadValidationFailures() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let mismatchedTarget = try await service.execute(
            makeApplyGatewayConfigRequest(
                targetID: "server-session-other",
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-dev-text",
                rateLimitPerMinute: 120,
                timeoutSeconds: 60
            )
        )
        let missingHost = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "",
                port: 11_434,
                defaultModelID: "melix-dev-text",
                rateLimitPerMinute: 120,
                timeoutSeconds: 60
            )
        )
        let invalidPort = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 0,
                defaultModelID: "melix-dev-text",
                rateLimitPerMinute: 120,
                timeoutSeconds: 60
            )
        )
        let missingServedModel = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "",
                rateLimitPerMinute: 120,
                timeoutSeconds: 60
            )
        )
        let invalidRateLimit = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-dev-text",
                rateLimitPerMinute: 0,
                timeoutSeconds: 60
            )
        )
        let invalidTimeout = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-dev-text",
                rateLimitPerMinute: 120,
                timeoutSeconds: 0
            )
        )

        #expect(!mismatchedTarget.ok)
        #expect(mismatchedTarget.error.code == "invalid_argument")
        #expect(missingHost.error.code == GatewayConfigValidationError.missingHost.code)
        #expect(invalidPort.error.code == GatewayConfigValidationError.invalidPort.code)
        #expect(missingServedModel.error.code == GatewayConfigValidationError.missingDefaultModelID.code)
        #expect(invalidRateLimit.error.code == GatewayConfigValidationError.invalidRateLimit.code)
        #expect(invalidTimeout.error.code == GatewayConfigValidationError.invalidTimeout.code)
    }

    @Test("execute surfaces gateway config persistence failures with typed metrics")
    func executeSurfacesGatewayConfigPersistenceFailuresWithTypedMetrics() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-gateway-persist-failure-\(UUID().uuidString)")
        let storeURL = temporaryRoot.appendingPathComponent("gateway-config-directory")
        try FileManager.default.createDirectory(at: storeURL, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let metricsStore = MetricsStore()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            metricsStore: metricsStore,
            gatewayConfigStore: GatewayConfigStore(storeURL: storeURL, defaults: [:]),
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434)
        )

        let response = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "0.0.0.0",
                port: 18_080,
                defaultModelID: "melix-dev-text",
                rateLimitPerMinute: 180,
                timeoutSeconds: 45
            )
        )

        #expect(!response.ok)
        #expect(response.error.code == "gateway_config_persist_failed")
        #expect(await metricsStore.value(forKey: "gateway.config_persist_failures") == 1)
    }

    @Test("execute projects typed serving defaults state through server snapshots")
    func executeProjectsTypedServingDefaultsStateThroughServerSnapshots() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-serving-defaults-snapshot-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }
        var speculativeReadyTextModel = ModelCatalog.devTextModel()
        speculativeReadyTextModel.settings.defaultAccelerationMode = .unspecified

        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:],
            nowUnixMS: { 1_717_181_920_000 }
        )
        try await servingDefaultsStore.apply(command: makeApplyServingDefaultsCommand(
            temperature: 0.33,
            topP: 0.9,
            maxTokens: 640,
            streamIntervalTokens: 4,
            maxConcurrentRequests: 6,
            concurrentProcessingEnabled: true,
            prefillBatchSize: 3,
            completionBatchSize: 2,
            accelerationMode: .speculativeDecode,
            draftModelID: "melix-dev-text",
            numDraftTokens: 6
        ))
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: [speculativeReadyTextModel]),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:]
            ),
            gatewayServingDefaultsStore: servingDefaultsStore,
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434)
        )

        let response = try await service.execute(makeServerSnapshotRequest())
        let session = try #require(response.server.snapshot.servingDefaults.sessions.first)

        #expect(response.ok)
        #expect(session.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(session.requestedTemperature == 0.33)
        #expect(session.requestedTopP == 0.9)
        #expect(session.requestedMaxTokens == 640)
        #expect(session.requestedStreamIntervalTokens == 4)
        #expect(session.requestedMaxConcurrentRequests == 6)
        #expect(session.requestedConcurrentProcessingEnabled)
        #expect(session.requestedPrefillBatchSize == 3)
        #expect(session.requestedCompletionBatchSize == 2)
        #expect(session.requestedAccelerationMode == .speculativeDecode)
        #expect(session.requestedDraftModelID == "melix-dev-text")
        #expect(session.requestedNumDraftTokens == 6)
        #expect(session.effectiveMaxConcurrentRequests == 2)
        #expect(session.effectivePrefillBatchSize == 2)
        #expect(session.effectiveCompletionBatchSize == 2)
        #expect(session.effectiveAccelerationMode == .speculativeDecode)
        #expect(session.effectiveDraftModelID == "melix-dev-text")
        #expect(session.effectiveNumDraftTokens == 6)
        #expect(session.source == .operatorOverride)
    }

    @Test("execute applies serving defaults and returns a hydrated snapshot")
    func executeAppliesServingDefaultsAndReturnsAHydratedSnapshot() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-serving-defaults-apply-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }
        var speculativeReadyTextModel = ModelCatalog.devTextModel()
        speculativeReadyTextModel.settings.defaultAccelerationMode = .unspecified

        let metricsStore = MetricsStore()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: [speculativeReadyTextModel]),
            metricsStore: metricsStore,
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:]
            ),
            gatewayServingDefaultsStore: GatewayServingDefaultsStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
                defaults: [:],
                nowUnixMS: { 1_717_181_930_000 }
            ),
            gatewaySupportsSpeculativeDefaults: true
        )

        let response = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.41,
                topP: 0.87,
                maxTokens: 512,
                streamIntervalTokens: 2,
                maxConcurrentRequests: 5,
                concurrentProcessingEnabled: true,
                prefillBatchSize: 4,
                completionBatchSize: 2,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-text",
                numDraftTokens: 5
            )
        )
        let session = try #require(response.server.snapshot.servingDefaults.sessions.first)

        #expect(response.ok)
        #expect(session.requestedTemperature == 0.41)
        #expect(session.requestedTopP == 0.87)
        #expect(session.requestedMaxTokens == 512)
        #expect(session.requestedStreamIntervalTokens == 2)
        #expect(session.requestedMaxConcurrentRequests == 5)
        #expect(session.requestedConcurrentProcessingEnabled)
        #expect(session.requestedPrefillBatchSize == 4)
        #expect(session.requestedCompletionBatchSize == 2)
        #expect(session.requestedAccelerationMode == .speculativeDecode)
        #expect(session.requestedDraftModelID == "melix-dev-text")
        #expect(session.requestedNumDraftTokens == 5)
        #expect(session.effectiveMaxConcurrentRequests == 2)
        #expect(session.effectivePrefillBatchSize == 2)
        #expect(session.effectiveCompletionBatchSize == 2)
        #expect(session.effectiveAccelerationMode == .speculativeDecode)
        #expect(session.effectiveDraftModelID == "melix-dev-text")
        #expect(session.effectiveNumDraftTokens == 5)
        #expect(await metricsStore.value(forKey: "gateway.serving_defaults_apply_ms") >= 0)
        #expect(await metricsStore.value(forKey: "gateway.speculative_config_apply_ms") >= 0)
    }

    @Test("execute rejects serving defaults target mismatches and typed payload validation failures")
    func executeRejectsServingDefaultsTargetMismatchesAndTypedPayloadValidationFailures() async throws {
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            gatewaySupportsSpeculativeDefaults: true
        )

        let mismatchedTarget = try await service.execute(
            makeApplyServingDefaultsRequest(
                targetID: "server-session-other",
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4
            )
        )
        let invalidTopP = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.2,
                topP: 0,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4
            )
        )
        let invalidStreamInterval = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 256,
                streamIntervalTokens: 0,
                maxConcurrentRequests: 4
            )
        )

        let invalidPrefillBatchSize = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4,
                prefillBatchSize: 0
            )
        )
        let invalidAccelerationMode = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4,
                accelerationMode: .acceleratedPrefill
            )
        )
        let missingDraftModelID = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4,
                accelerationMode: .speculativeDecode,
                draftModelID: "   ",
                numDraftTokens: 4
            )
        )
        let invalidNumDraftTokens = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-text",
                numDraftTokens: 0
            )
        )

        #expect(!mismatchedTarget.ok)
        #expect(mismatchedTarget.error.code == "invalid_argument")
        #expect(invalidTopP.error.code == ServingDefaultsValidationError.invalidTopP.code)
        #expect(invalidStreamInterval.error.code == ServingDefaultsValidationError.invalidStreamIntervalTokens.code)
        #expect(invalidPrefillBatchSize.error.code == ServingDefaultsValidationError.invalidPrefillBatchSize.code)
        #expect(invalidAccelerationMode.error.code == ServingDefaultsValidationError.invalidAccelerationMode.code)
        #expect(missingDraftModelID.error.code == ServingDefaultsValidationError.missingDraftModelID.code)
        #expect(invalidNumDraftTokens.error.code == ServingDefaultsValidationError.invalidNumDraftTokens.code)
    }

    @Test("execute rejects speculative serving defaults for unsupported backends and unsupported models")
    func executeRejectsSpeculativeServingDefaultsForUnsupportedBackendsAndUnsupportedModels() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-speculative-serving-defaults-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let backendUnsupportedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config-backend.json"),
                defaults: [:]
            ),
            gatewaySupportsSpeculativeDefaults: false
        )
        let backendUnsupported = try await backendUnsupportedService.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.3,
                topP: 0.91,
                maxTokens: 384,
                streamIntervalTokens: 2,
                maxConcurrentRequests: 4,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-text",
                numDraftTokens: 6
            )
        )
        var forcedBackendUnsupportedRequest = makeApplyServingDefaultsRequest(
            temperature: 0.3,
            topP: 0.91,
            maxTokens: 384,
            streamIntervalTokens: 2,
            maxConcurrentRequests: 4,
            accelerationMode: .speculativeDecode,
            draftModelID: "melix-dev-text",
            numDraftTokens: 6
        )
        forcedBackendUnsupportedRequest.server.applyServingDefaults.speculativeRoutePolicy = "force"
        let forcedBackendUnsupported = try await backendUnsupportedService.execute(
            forcedBackendUnsupportedRequest
        )

        let servedModelUnsupportedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config-served.json"),
                defaults: [:]
            ),
            gatewaySupportsSpeculativeDefaults: true
        )
        _ = try await servedModelUnsupportedService.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-dev-ocr",
                rateLimitPerMinute: 120,
                timeoutSeconds: 60
            )
        )
        let servedModelUnsupported = try await servedModelUnsupportedService.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.3,
                topP: 0.91,
                maxTokens: 384,
                streamIntervalTokens: 2,
                maxConcurrentRequests: 4,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-text",
                numDraftTokens: 6
            )
        )

        let draftModelUnsupportedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config-draft.json"),
                defaults: [:]
            ),
            gatewaySupportsSpeculativeDefaults: true
        )
        let draftModelUnsupported = try await draftModelUnsupportedService.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.3,
                topP: 0.91,
                maxTokens: 384,
                streamIntervalTokens: 2,
                maxConcurrentRequests: 4,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-ocr",
                numDraftTokens: 6
            )
        )

        #expect(backendUnsupported.error.code == ServingDefaultsValidationError.speculativeBackendUnsupported.code)
        #expect(forcedBackendUnsupported.error.code == ServingDefaultsValidationError.speculativeBackendUnsupported.code)
        #expect(forcedBackendUnsupported.error.details["disabled_reason"] == "unsupported_route")
        #expect(forcedBackendUnsupported.error.details["route_policy"] == "force")
        #expect(servedModelUnsupported.error.code == ServingDefaultsValidationError.speculativeServedModelUnsupported.code)
        #expect(draftModelUnsupported.error.code == ServingDefaultsValidationError.speculativeDraftModelUnsupported.code)
    }

    @Test("execute rejects unsupported forced multimodal route policies")
    func executeRejectsUnsupportedForcedMultimodalRoutePolicies() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-serving-defaults-force-route-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devTextModel()]),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:]
            ),
            gatewayServingDefaultsStore: servingDefaultsStore,
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434)
        )

        var request = makeApplyServingDefaultsRequest(
            temperature: 0.4,
            topP: 0.9,
            maxTokens: 256,
            streamIntervalTokens: 1,
            maxConcurrentRequests: 2
        )
        request.server.applyServingDefaults.multimodalRoutePolicy = "force"

        let response = try await service.execute(request)
        let summary = await servingDefaultsStore.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [:],
            modelSettingsByModelID: [:]
        )

        #expect(!response.ok)
        #expect(response.error.code == "unsupported_multimodal_route_policy")
        #expect(response.error.details["disabled_reason"] == "unsupported_route")
        #expect(response.error.details["route_policy"] == "force")
        let session = try #require(summary.sessions.first)
        #expect(session.source == .builtInDefaults)
        #expect(session.updatedAtUnixMs == 0)
    }

    @Test("execute persists disabled route policies without speculative compatibility checks")
    func executePersistsDisabledRoutePoliciesWithoutSpeculativeCompatibilityChecks() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-serving-defaults-off-route-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devTextModel()]),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:]
            ),
            gatewayServingDefaultsStore: servingDefaultsStore,
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434),
            gatewaySupportsSpeculativeDefaults: false
        )

        var request = makeApplyServingDefaultsRequest(
            temperature: 0.4,
            topP: 0.9,
            maxTokens: 256,
            streamIntervalTokens: 1,
            maxConcurrentRequests: 2,
            accelerationMode: .speculativeDecode,
            draftModelID: "missing-draft",
            numDraftTokens: 6
        )
        request.server.applyServingDefaults.multimodalRoutePolicy = "off"
        request.server.applyServingDefaults.speculativeRoutePolicy = "off"

        let response = try await service.execute(request)
        let summary = await servingDefaultsStore.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [:],
            modelSettingsByModelID: [:]
        )
        let session = try #require(summary.sessions.first)

        #expect(response.ok)
        #expect(session.source == .operatorOverride)
        #expect(session.multimodalRoutePolicy == "off")
        #expect(session.speculativeRoutePolicy == "off")
        #expect(session.effectiveMultimodalRoute == "off")
        #expect(session.effectiveSpeculativeMode == "baseline")
        #expect(session.speculativeDisabledReason == "operator_disabled")
    }

    @Test("execute validates speculative serving defaults against the default model only")
    func executeValidatesSpeculativeServingDefaultsAgainstTheDefaultModelOnly() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-speculative-serving-defaults-default-only-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        var speculativeReadyTextModel = ModelCatalog.devTextModel()
        speculativeReadyTextModel.settings.defaultAccelerationMode = .unspecified
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: [speculativeReadyTextModel, ModelCatalog.devOCRModel()]),
            gatewayConfigStore: GatewayConfigStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-config.json"),
                defaults: [:]
            ),
            gatewayServingDefaultsStore: GatewayServingDefaultsStore(
                storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
                defaults: [:]
            ),
            gatewaySupportsSpeculativeDefaults: true
        )
        _ = try await service.execute(
            makeApplyGatewayConfigRequest(
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-dev-text",
                servedModelIDs: ["melix-dev-text", "melix-dev-ocr"],
                rateLimitPerMinute: 120,
                timeoutSeconds: 60
            )
        )

        let response = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.3,
                topP: 0.91,
                maxTokens: 384,
                streamIntervalTokens: 2,
                maxConcurrentRequests: 4,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-text",
                numDraftTokens: 6
            )
        )

        #expect(response.ok)
    }

    @Test("execute surfaces serving defaults persistence failures with typed metrics")
    func executeSurfacesServingDefaultsPersistenceFailuresWithTypedMetrics() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-serving-defaults-persist-failure-\(UUID().uuidString)")
        let storeURL = temporaryRoot.appendingPathComponent("gateway-serving-defaults-directory")
        try FileManager.default.createDirectory(at: storeURL, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let metricsStore = MetricsStore()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            metricsStore: metricsStore,
            gatewayServingDefaultsStore: GatewayServingDefaultsStore(storeURL: storeURL, defaults: [:])
        )

        let response = try await service.execute(
            makeApplyServingDefaultsRequest(
                temperature: 0.3,
                topP: 0.91,
                maxTokens: 384,
                streamIntervalTokens: 2,
                maxConcurrentRequests: 3
            )
        )

        #expect(!response.ok)
        #expect(response.error.code == "serving_defaults_persist_failed")
        #expect(await metricsStore.value(forKey: "gateway.serving_defaults_persist_failures") == 1)
    }

    @Test("execute projects image defaults state through server snapshots")
    func executeProjectsImageDefaultsStateThroughServerSnapshots() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-image-defaults-snapshot-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let imageDefaultsStore = ImageDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("image-defaults.json"),
            defaults: [:],
            nowUnixMS: { 1_717_181_940_000 }
        )
        try await imageDefaultsStore.apply(
            command: makeApplyImageDefaultsCommand(
                generateModelID: "melix-dev-image",
                editModelID: "melix-dev-image",
                size: "1536x1024",
                steps: 40,
                guidance: 6.25,
                strength: 0.7,
                negativePrompt: "noise"
            ),
            models: ModelCatalog.phaseSevenContractSeedModels()
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            imageDefaultsStore: imageDefaultsStore
        )

        let response = try await service.execute(makeServerSnapshotRequest())
        let summary = response.server.snapshot.imageDefaults

        #expect(response.ok)
        #expect(summary.requestedGenerateModelID == "melix-dev-image")
        #expect(summary.requestedEditModelID == "melix-dev-image")
        #expect(summary.requestedSize == "1536x1024")
        #expect(summary.requestedSteps == 40)
        #expect(summary.requestedGuidance == 6.25)
        #expect(summary.requestedStrength == 0.7)
        #expect(summary.requestedNegativePrompt == "noise")
        #expect(summary.effectiveGenerateModelID == "melix-dev-image")
        #expect(summary.effectiveEditModelID == "melix-dev-image")
        #expect(summary.effectiveSize == "1536x1024")
        #expect(summary.effectiveSteps == 40)
        #expect(summary.effectiveGuidance == 6.25)
        #expect(summary.effectiveStrength == 0.7)
        #expect(summary.effectiveNegativePrompt == "noise")
        #expect(summary.source == .operatorOverride)
        #expect(summary.updatedAtUnixMs == 1_717_181_940_000)
    }

    @Test("execute applies image defaults and returns a hydrated summary")
    func executeAppliesImageDefaultsAndReturnsAHydratedSummary() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-image-defaults-apply-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let metricsStore = MetricsStore()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            metricsStore: metricsStore,
            imageDefaultsStore: ImageDefaultsStore(
                storeURL: temporaryRoot.appendingPathComponent("image-defaults.json"),
                defaults: [:],
                nowUnixMS: { 1_717_181_950_000 }
            )
        )

        let response = try await service.execute(
            makeApplyImageDefaultsRequest(
                generateModelID: "melix-dev-image",
                editModelID: "melix-dev-image",
                size: "1536x1024",
                steps: 36,
                guidance: 6.5,
                strength: 0.65,
                negativePrompt: "blur"
            )
        )
        let summary = response.image.imageDefaults

        #expect(response.ok)
        #expect(summary.requestedGenerateModelID == "melix-dev-image")
        #expect(summary.requestedEditModelID == "melix-dev-image")
        #expect(summary.requestedSize == "1536x1024")
        #expect(summary.requestedSteps == 36)
        #expect(summary.requestedGuidance == 6.5)
        #expect(summary.requestedStrength == 0.65)
        #expect(summary.requestedNegativePrompt == "blur")
        #expect(summary.effectiveGenerateModelID == "melix-dev-image")
        #expect(summary.effectiveEditModelID == "melix-dev-image")
        #expect(summary.source == .operatorOverride)
        #expect(await metricsStore.value(forKey: "images.defaults_apply_latency_ms") >= 0)
    }

    @Test("execute rejects invalid image defaults payloads and unsupported workflow models")
    func executeRejectsInvalidImageDefaultsPayloadsAndUnsupportedWorkflowModels() async throws {
        var qwen = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        ])
        qwen.modelID = "melix-qwen-image"
        var fill = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        ])
        fill.modelID = "melix-fill-image"
        let text = ModelCatalog.devTextModel()
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: [qwen, fill, text]))

        let invalidSize = try await service.execute(
            makeApplyImageDefaultsRequest(
                generateModelID: qwen.modelID,
                editModelID: fill.modelID,
                size: "wide",
                steps: 28,
                guidance: 7.5,
                strength: 0.8
            )
        )
        let invalidStrength = try await service.execute(
            makeApplyImageDefaultsRequest(
                generateModelID: qwen.modelID,
                editModelID: fill.modelID,
                size: "1024x1024",
                steps: 28,
                guidance: 7.5,
                strength: 1.2
            )
        )
        let unsupportedGenerate = try await service.execute(
            makeApplyImageDefaultsRequest(
                generateModelID: fill.modelID,
                editModelID: fill.modelID,
                size: "1024x1024",
                steps: 28,
                guidance: 7.5,
                strength: 0.8
            )
        )
        let unsupportedEdit = try await service.execute(
            makeApplyImageDefaultsRequest(
                generateModelID: qwen.modelID,
                editModelID: qwen.modelID,
                size: "1024x1024",
                steps: 28,
                guidance: 7.5,
                strength: 0.8
            )
        )

        #expect(invalidSize.error.code == ImageDefaultsValidationError.invalidSize.code)
        #expect(invalidStrength.error.code == ImageDefaultsValidationError.invalidStrength.code)
        #expect(unsupportedGenerate.error.code == ImageDefaultsValidationError.unsupportedGenerateModel.code)
        #expect(unsupportedEdit.error.code == ImageDefaultsValidationError.unsupportedEditModel.code)
    }

    @Test("execute handles server lifecycle controls and derives server state")
    func executeHandlesServerLifecycleControlsAndDerivesServerState() async throws {
        let service = ControlPlaneService()

        let pauseResponse = try await service.execute(makeServerPauseRequest())
        let wakeResponse = try await service.execute(makeServerWakeRequest())
        let resumeResponse = try await service.execute(makeServerResumeRequest())
        let stopResponse = try await service.execute(makeServerStopRequest())
        let startResponse = try await service.execute(makeServerStartRequest())
        let restartResponse = try await service.execute(makeServerRestartRequest())

        #expect(pauseResponse.ok)
        #expect(pauseResponse.server.snapshot.serverState == .serverDegraded)
        #expect(pauseResponse.server.snapshot.runtimeSessions.first?.lifecycleState == .paused)

        #expect(wakeResponse.ok)
        #expect(wakeResponse.server.snapshot.serverState == .serverReady)
        #expect(wakeResponse.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(wakeResponse.server.snapshot.runtimeSessions.first?.wakeReason == .operatorResume)

        #expect(resumeResponse.ok)
        #expect(resumeResponse.server.snapshot.serverState == .serverReady)
        #expect(resumeResponse.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(resumeResponse.server.snapshot.runtimeSessions.first?.wakeReason == .operatorResume)

        #expect(stopResponse.ok)
        #expect(stopResponse.server.snapshot.serverState == .serverStopped)
        #expect(stopResponse.server.snapshot.runtimeSessions.first?.lifecycleState == .stopped)
        #expect(stopResponse.server.snapshot.runtimeSessions.first?.powerState == .stopped)

        #expect(startResponse.ok)
        #expect(startResponse.server.snapshot.serverState == .serverReady)
        #expect(startResponse.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(startResponse.server.snapshot.runtimeSessions.first?.wakeReason == .operatorResume)

        #expect(restartResponse.ok)
        #expect(restartResponse.server.snapshot.serverState == .serverReady)
        #expect(restartResponse.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(restartResponse.server.snapshot.runtimeSessions.first?.wakeReason == .operatorResume)
    }

    @Test("execute handles server idle policy updates")
    func executeHandlesServerIdlePolicyUpdates() async throws {
        let service = ControlPlaneService()

        let response = try await service.execute(
            makeServerSetIdlePolicyRequest(
                autoSleepEnabled: true,
                lightSleepAfterSeconds: 60,
                deepSleepAfterSeconds: 600
            )
        )

        #expect(response.ok)
        #expect(response.server.snapshot.serverState == .serverReady)
        #expect(response.server.snapshot.runtimeSessions.first?.autoSleepEnabled == true)
        #expect(response.server.snapshot.runtimeSessions.first?.lightSleepAfterSeconds == 60)
        #expect(response.server.snapshot.runtimeSessions.first?.deepSleepAfterSeconds == 600)
    }

    @Test("execute rejects invalid server idle policy thresholds")
    func executeRejectsInvalidServerIdlePolicyThresholds() async throws {
        let service = ControlPlaneService()

        let response = try await service.execute(
            makeServerSetIdlePolicyRequest(
                autoSleepEnabled: true,
                lightSleepAfterSeconds: 600,
                deepSleepAfterSeconds: 60
            )
        )

        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message == "deep_sleep_after_seconds must be greater than or equal to light_sleep_after_seconds.")
    }

    @Test("server lifecycle requests reject mismatched target and payload session ids")
    func serverLifecycleRequestsRejectMismatchedTargetAndPayloadSessionIDs() async throws {
        let service = ControlPlaneService()
        var request = makeServerPauseRequest(serverSessionID: "server-session-1")
        request.targetID = "server-session-2"

        let response = try await service.execute(request)

        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message == "Target server session does not match the command payload.")
    }

    @Test("serving activity blocks paused sessions and wakes sleeping sessions")
    func servingActivityBlocksPausedSessionsAndWakesSleepingSessions() async throws {
        var pausedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        pausedSession.lifecycleState = .paused
        let pausedService = ControlPlaneService(
            serverSessionRuntimeStore: ServerSessionRuntimeStore(runtimeSessions: [pausedSession], nowUnixMS: { 2_000 })
        )

        let pausedResponse = try await pausedService.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "bench",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(!pausedResponse.ok)
        #expect(pausedResponse.error.code == "server_paused")

        var sleepingSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        sleepingSession.lifecycleState = .sleeping
        sleepingSession.powerState = .deepSleep
        let sleepingStore = ServerSessionRuntimeStore(runtimeSessions: [sleepingSession], nowUnixMS: { 3_000 })
        let sleepingService = ControlPlaneService(serverSessionRuntimeStore: sleepingStore)

        let wakingResponse = try await sleepingService.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-wake",
                modelID: "melix-dev-image",
                prompt: "bench",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshotAfterWake = try await sleepingService.execute(makeServerSnapshotRequest())

        #expect(!wakingResponse.ok)
        #expect(wakingResponse.error.code == "not_ready")
        #expect(snapshotAfterWake.server.snapshot.serverState == .serverReady)
        #expect(snapshotAfterWake.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(snapshotAfterWake.server.snapshot.runtimeSessions.first?.powerState == .active)
        #expect(snapshotAfterWake.server.snapshot.runtimeSessions.first?.wakeReason == .requestActivity)
    }

    @Test("startChat blocks paused sessions and wakes sleeping sessions before dispatch")
    func startChatBlocksPausedSessionsAndWakesSleepingSessionsBeforeDispatch() async throws {
        var pausedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        pausedSession.lifecycleState = .paused
        let pausedService = ControlPlaneService(
            serverSessionRuntimeStore: ServerSessionRuntimeStore(runtimeSessions: [pausedSession], nowUnixMS: { 2_000 }),
            workerRegistry: WorkerRegistry(defaultTextClient: NullWorkerClient())
        )

        do {
            _ = try await pausedService.startChat(
                ControlPlaneChatRequest(
                    modelID: "melix-dev-text",
                    messages: [.init(role: "user", content: "hello")]
                )
            )
            Issue.record("Expected paused Server Session to block chat dispatch")
        } catch let error as ControlPlaneChatExecutionError {
            #expect(String(describing: error).contains("server_paused"))
        } catch {
            Issue.record("Unexpected error: \(error)")
        }

        var sleepingSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        sleepingSession.lifecycleState = .sleeping
        sleepingSession.powerState = .deepSleep
        let sleepingStore = ServerSessionRuntimeStore(runtimeSessions: [sleepingSession], nowUnixMS: { 3_000 })
        let modelCatalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await modelCatalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::local")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-server-wake"),
            makeCompletedExecuteEvent(
                requestID: "chat-server-wake",
                finishReason: "stop",
                assistant: "awake",
                reasoning: ""
            ),
        ])
        let sleepingService = ControlPlaneService(
            modelCatalog: modelCatalog,
            serverSessionRuntimeStore: sleepingStore,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-server-wake" })
        )

        let execution = try await sleepingService.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "wake the server")]
            )
        )
        _ = try await Array(execution.stream)
        let snapshotAfterWake = try await sleepingService.execute(makeServerSnapshotRequest())

        #expect(snapshotAfterWake.server.snapshot.serverState == .serverReady)
        #expect(snapshotAfterWake.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(snapshotAfterWake.server.snapshot.runtimeSessions.first?.powerState == .active)
        #expect(snapshotAfterWake.server.snapshot.runtimeSessions.first?.wakeReason == .requestActivity)
    }

    @Test("startChat syncs managed registry models before lazy load")
    func startChatSyncsManagedRegistryModelsBeforeLazyLoad() async throws {
        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let importedModelPath = "/tmp/managed-root/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": importedModelID,
                    "model_path": importedModelPath,
                    "model_kind": "text",
                    "revision": "main",
                    "tokenizer_hash": "hf.mlx-community.Qwen3.5-0.8B-OptiQ-4bit",
                    "quant_profile_id": "",
                    "parser_mode": "text",
                    "reasoning_mode": "off",
                    "max_context": 8192,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/managed-root",
                        "melix.registry_relative_path": "huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main",
                        "melix.model_path": importedModelPath,
                        "melix.hf_repo_id": importedModelID,
                        "melix.capability.class": "text",
                        "melix.capability.route_kind": "python_text_compatibility",
                        "melix.capability.supported_modalities": "text",
                        "melix.capability.supported_tasks": "generate",
                    ],
                ],
            ]
        )
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-managed-registry"),
            makeCompletedExecuteEvent(
                requestID: "chat-managed-registry",
                finishReason: "stop",
                assistant: "managed local response",
                reasoning: ""
            ),
        ])
        let catalog = ModelCatalog(seedModels: [])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            ),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-managed-registry" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: importedModelID,
                messages: [.init(role: "user", content: "test")]
            )
        )
        _ = try await Array(execution.stream)
        let lastConvertRequest = try #require(await modelOpsClient.lastConvertRequest)
        let lastLoadRequest = try #require(await textClient.lastLoadModelRequest)

        #expect(lastConvertRequest.ext["operation"] == "registry_snapshot")
        #expect(lastConvertRequest.ext["melix.registry_rescan"] == "true")
        #expect(lastLoadRequest.model.modelID == importedModelID)
        #expect(lastLoadRequest.model.modelPath == importedModelPath)
        #expect(await catalog.dispatchHandle(for: importedModelID) == importedModelID)
    }

    @Test("server pause and stop require quiescence while requests are active")
    func serverPauseAndStopRequireQuiescenceWhileRequestsAreActive() async throws {
        let schedulerReadModel = SchedulerReadModel()
        _ = await schedulerReadModel.recordAdmitted(
            requestID: "req-inflight",
            laneHint: "text.decode.interactive",
            priority: 100,
            workerID: "swift-text-worker",
            admissionLatencyMs: 1
        )
        let service = ControlPlaneService(schedulerReadModel: schedulerReadModel)

        let pauseResponse = try await service.execute(makeServerPauseRequest())
        let stopResponse = try await service.execute(makeServerStopRequest())

        #expect(!pauseResponse.ok)
        #expect(pauseResponse.error.code == "conflict")
        #expect(!stopResponse.ok)
        #expect(stopResponse.error.code == "conflict")
    }

    @Test("image edit serving respects paused sleeping stopped and failed server sessions")
    func imageEditServingRespectsPausedSleepingStoppedAndFailedServerSessions() async throws {
        var pausedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        pausedSession.lifecycleState = .paused
        let pausedService = ControlPlaneService(
            serverSessionRuntimeStore: ServerSessionRuntimeStore(runtimeSessions: [pausedSession], nowUnixMS: { 2_000 })
        )
        let pausedResponse = try await pausedService.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-paused",
                modelID: "melix-dev-image",
                prompt: "pause",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 0.5
            )
        )

        var sleepingSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        sleepingSession.lifecycleState = .sleeping
        sleepingSession.powerState = .deepSleep
        let sleepingStore = ServerSessionRuntimeStore(runtimeSessions: [sleepingSession], nowUnixMS: { 3_000 })
        let sleepingService = ControlPlaneService(serverSessionRuntimeStore: sleepingStore)
        let wakingResponse = try await sleepingService.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-wake",
                modelID: "melix-dev-image",
                prompt: "wake",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 0.5
            )
        )
        let wakingSnapshot = try await sleepingService.execute(makeServerSnapshotRequest())

        var stoppedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        stoppedSession.lifecycleState = .stopped
        stoppedSession.powerState = .stopped
        let stoppedService = ControlPlaneService(
            serverSessionRuntimeStore: ServerSessionRuntimeStore(runtimeSessions: [stoppedSession], nowUnixMS: { 4_000 })
        )
        let stoppedResponse = try await stoppedService.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-stopped",
                modelID: "melix-dev-image",
                prompt: "stop",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 0.5
            )
        )

        var failedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        failedSession.lifecycleState = .error
        let failedService = ControlPlaneService(
            serverSessionRuntimeStore: ServerSessionRuntimeStore(runtimeSessions: [failedSession], nowUnixMS: { 5_000 })
        )
        let failedResponse = try await failedService.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-failed",
                modelID: "melix-dev-image",
                prompt: "failed",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 0.5
            )
        )

        #expect(!pausedResponse.ok)
        #expect(pausedResponse.error.code == "server_paused")
        #expect(!wakingResponse.ok)
        #expect(wakingResponse.error.code == "not_ready")
        #expect(wakingSnapshot.server.snapshot.runtimeSessions.first?.lifecycleState == .ready)
        #expect(wakingSnapshot.server.snapshot.runtimeSessions.first?.powerState == .active)
        #expect(!stoppedResponse.ok)
        #expect(stoppedResponse.error.code == "server_stopped")
        #expect(!failedResponse.ok)
        #expect(failedResponse.error.code == "server_failed")
    }

    @Test("applying gateway access publishes server runtime session metadata")
    func applyingGatewayAccessPublishesServerRuntimeSessionMetadata() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()

        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "apply-gateway-access-runtime"
        request.commandType = "server.apply_gateway_access"
        request.targetID = "server-session-1"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyGatewayAccess = Melix_Controlplane_V1_ApplyGatewayAccess()
        request.server.applyGatewayAccess.serverSessionID = "server-session-1"
        request.server.applyGatewayAccess.mode = .none
        request.server.applyGatewayAccess.sharedAccessEnabled = false

        let response = try await service.execute(request)

        var iterator = subscription.stream.makeAsyncIterator()
        let event = await iterator.next()
        await service.unsubscribe(subscription.subscriptionID)

        #expect(response.ok)
        #expect(event?.eventType == "server.state_changed")
        #expect(event?.source == "server_runtime")
        #expect(event?.serverState.runtimeSessions.first?.serverSessionID == "server-session-1")
        #expect(event?.serverState.runtimeSessions.first?.wakeReason == .policyApply)
        #expect(event?.serverState.runtimeSessions.first?.lifecycleState == .ready)
    }

    @Test("execute handles model.list")
    func executeHandlesModelList() async throws {
        let service = ControlPlaneService()
        let request = makeListModelsRequest()

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.model.models.count == 1)
        #expect(response.model.models.first?.modelID == "melix-dev-text")
        #expect(response.model.models.first?.state == .modelDiscovered)
    }

    @Test("execute handles model.list by syncing registry snapshot models from the model-operations worker")
    func executeHandlesModelListBySyncingRegistrySnapshotModelsFromTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "registry-snapshot-1"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/registry_snapshot.json"
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            )
        )

        let response = try await service.execute(makeListModelsRequest())
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)
        let discovered = try #require(
            response.model.models.first(where: { $0.modelID == "mlx-community/Qwen2.5-7B-Instruct/4bit" })
        )

        #expect(response.ok)
        #expect(lastRequest.ext["operation"] == "registry_snapshot")
        #expect(lastRequest.ext["melix.registry_rescan"] == "true")
        #expect(lastRequest.generateManifest)
        #expect(discovered.state == .modelDiscovered)
        #expect(discovered.routeClass == .workerRouteSwiftText)
        #expect(discovered.settings.ext["melix.capability.route_kind"] == "swift_text")
        #expect(discovered.maxContext == 16384)
        #expect(discovered.settings.ext["melix.registry_root_id"] == "root-1")
        #expect(discovered.settings.ext["melix.registry_relative_path"] == "mlx-community/Qwen2.5-7B-Instruct/4bit")
        #expect(discovered.settings.ext["melix.model_path"] == "/tmp/registry-root/mlx-community/Qwen2.5-7B-Instruct/4bit")
    }

    @Test("execute handles model.list by syncing activated derived models from registry snapshots")
    func executeHandlesModelListBySyncingActivatedDerivedModelsFromRegistrySnapshots() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [],
            derivedModels: [
                [
                    "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit-lora-acbb3307",
                    "model_path": "/tmp/melix-derived/model",
                    "source_model": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "source_model_revision": "registry",
                    "derived_model_alias": "melix-qwen35-acceptance",
                    "adapter_set_hash": "acbb330795d89f65",
                    "activation_mode": "adapter_backed_runtime",
                    "adapter_manifest_path": "/tmp/melix-adapters/train_lora.adapter.json",
                    "adapter_weights_path": "/tmp/melix-adapters/weights/adapters.safetensors",
                    "remove_supported": true,
                    "status": "activated",
                ],
            ]
        )
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "registry-snapshot-derived-1"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/registry_snapshot.json"
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            )
        )

        let response = try await service.execute(makeListModelsRequest())
        let derived = try #require(
            response.model.models.first(where: { $0.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit-lora-acbb3307" })
        )

        #expect(response.ok)
        #expect(derived.kind == "text")
        #expect(derived.routeClass == .workerRouteSwiftText)
        #expect(derived.capabilityClass == .modelCapabilityText)
        #expect(derived.supportedTasks == ["generate"])
        #expect(derived.settings.ext["melix.model_path"] == "/tmp/melix-derived/model")
        #expect(derived.settings.ext["melix.derived_from_adapter"] == "true")
        #expect(derived.settings.ext["melix.derived_from_model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(derived.settings.ext["melix.derived_model_alias"] == "melix-qwen35-acceptance")
        #expect(derived.settings.ext["melix.adapter_set_hash"] == "acbb330795d89f65")
        #expect(derived.settings.ext["melix.activation_mode"] == "adapter_backed_runtime")
        // Module 1 promotes the activation mode onto ModelSummary.runtime_mode
        // so CLI models list + show can render the serving mode as a
        // first-class summary field rather than digging through ext strings.
        #expect(derived.runtimeMode == "adapter_backed_runtime")
        #expect(derived.settings.ext["melix.adapter_manifest_path"] == "/tmp/melix-adapters/train_lora.adapter.json")
        #expect(derived.settings.ext["melix.adapter_weights_path"] == "/tmp/melix-adapters/weights/adapters.safetensors")
        #expect(derived.settings.ext["melix.derived_from_model_revision"] == "registry")
        #expect(derived.settings.ext["melix.remove_supported"] == "true")
    }

    @Test("registry snapshot text families preserve compatibility routing and parser metadata")
    func registrySnapshotTextFamiliesPreserveCompatibilityRoutingAndParserMetadata() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": "mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
                    "model_path": "/tmp/registry-root/mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
                    "model_kind": "text",
                    "revision": "registry",
                    "tokenizer_hash": "tok-registry",
                    "quant_profile_id": "q4",
                    "parser_mode": "text",
                    "reasoning_mode": "off",
                    "max_context": 32768,
                    "ext": [
                        "text_backend_id": "mlx_lm",
                        "text_family_id": "qwen3moe",
                        "model_architecture": "qwen3_moe",
                        "detected_architecture": "qwen3_moe",
                        "detected_family_id": "qwen3moe",
                        "detected_identity_source": "config.model_type",
                        "melix.adapter_set_hash": "text-family-qwen3moe",
                        "melix.capability.route_kind": "python_text_compatibility",
                        "melix.capability.class": "text",
                        "melix.capability.supported_modalities": "text",
                        "melix.capability.supported_tasks": "generate",
                        "melix.capability.supported_parsers": "text,qwen",
                        "tool_parser_mode": "qwen",
                        "tool_parser_namespaces": "tools.text",
                        "tool_parser_xml_fallback": "true",
                        "melix.text.attention_profile": "gqa",
                        "melix.text.rope_profile": "yarn_interleaved",
                        "melix.text.moe.enabled": "true",
                        "melix.text.moe.expert_count": "128",
                        "melix.text.moe.gate_dequant": "true",
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/registry-root",
                        "melix.registry_relative_path": "mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
                        "melix.model_path": "/tmp/registry-root/mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
                    ],
                ],
            ]
        )
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeListModelsRequest())
        let discovered = try #require(
            response.model.models.first(where: { $0.modelID == "mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit" })
        )

        #expect(discovered.routeClass == .workerRoutePythonTextCompatibility)
        #expect(discovered.capabilityClass == .modelCapabilityText)
        #expect(discovered.supportedModalities == ["text"])
        #expect(discovered.supportedTasks == ["generate"])
        #expect(discovered.settings.ext["text_family_id"] == "qwen3moe")
        #expect(discovered.settings.ext["melix.capability.route_kind"] == "python_text_compatibility")
        #expect(discovered.settings.ext["melix.capability.supported_parsers"] == "text,qwen")
        #expect(discovered.settings.ext["tool_parser_mode"] == "qwen")
        #expect(discovered.settings.ext["melix.text.rope_profile"] == "yarn_interleaved")
        #expect(discovered.settings.ext["melix.text.moe.expert_count"] == "128")
    }

    @Test("execute handles model.list by keeping the current catalog when registry sync throws")
    func executeHandlesModelListByKeepingTheCurrentCatalogWhenRegistrySyncThrows() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertError(WorkerClientError.unavailable)

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devTextModel()]),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeListModelsRequest())
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(response.model.models.map(\.modelID) == ["melix-dev-text"])
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(lastRequest.ext["operation"] == "registry_snapshot")
    }

    @Test("execute handles model.list by ignoring failed and malformed registry snapshots")
    func executeHandlesModelListByIgnoringFailedAndMalformedRegistrySnapshots() async throws {
        let failedClient = ScriptedModelOperationsWorkerClient()
        await failedClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.failed = Melix_Worker_V1_ConvertFailed()
                return event
            }(),
        ])
        let failedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: failedClient
            )
        )

        let failedResponse = try await failedService.execute(makeListModelsRequest())

        #expect(failedResponse.ok)
        #expect(failedResponse.model.models.contains(where: { $0.modelID == "melix-dev-text" }))
        #expect(!failedResponse.model.models.contains(where: { $0.modelID == "mlx-community/Qwen2.5-7B-Instruct/4bit" }))

        let malformedClient = ScriptedModelOperationsWorkerClient()
        await malformedClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = "{not-json"
                return event
            }(),
        ])
        let malformedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: malformedClient
            )
        )

        let malformedResponse = try await malformedService.execute(makeListModelsRequest())

        #expect(malformedResponse.ok)
        #expect(malformedResponse.model.models.contains(where: { $0.modelID == "melix-dev-text" }))
        #expect(!malformedResponse.model.models.contains(where: { $0.modelID == "mlx-community/Qwen2.5-7B-Instruct/4bit" }))
    }

    @Test("execute handles model.list by normalizing registry defaults and filtering invalid rows")
    func executeHandlesModelListByNormalizingRegistryDefaultsAndFilteringInvalidRows() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_kind": "text",
                    "model_path": "/tmp/registry-root/ignored",
                ],
                [
                    "model_id": "mlx-community/Mxbai-Embed/8bit",
                    "model_path": "/tmp/registry-root/mlx-community/Mxbai-Embed/8bit",
                    "model_kind": "embedding",
                    "quant_profile_id": "q8",
                    "max_context": "4096",
                    "ext": [
                        "": "ignored",
                        "melix.capability.class": "embedding",
                        "melix.capability.route_kind": "python_embedding",
                        "melix.capability.supported_modalities": "text",
                        "melix.capability.supported_tasks": "embed",
                    ],
                ],
                [
                    "model_id": "mlx-community/Speech/1",
                    "model_path": "/tmp/registry-root/mlx-community/Speech/1",
                    "model_kind": "speech",
                ],
            ]
        )
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])

        let textClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeListModelsRequest())
        let embedding = try #require(response.model.models.first(where: { $0.modelID == "mlx-community/Mxbai-Embed/8bit" }))
        let speech = try #require(response.model.models.first(where: { $0.modelID == "mlx-community/Speech/1" }))

        #expect(response.ok)
        #expect(!response.model.models.contains(where: { $0.settings.ext["melix.model_path"] == "/tmp/registry-root/ignored" && $0.modelID.isEmpty }))
        #expect(embedding.maxContext == 4096)
        #expect(embedding.capabilityClass == .modelCapabilityEmbedding)
        #expect(embedding.routeClass == .workerRoutePythonEmbedding)
        #expect(embedding.supportedModalities == ["text"])
        #expect(embedding.supportedTasks == ["embed"])
        #expect(embedding.settings.ext["melix.model_path"] == "/tmp/registry-root/mlx-community/Mxbai-Embed/8bit")
        #expect(embedding.settings.ext[""] == nil)
        #expect(speech.capabilityClass == .modelCapabilitySpeech)
        #expect(speech.routeClass == .workerRoutePythonSpeech)
        #expect(speech.supportedModalities == ["text", "audio"])
        #expect(speech.supportedTasks == ["speak"])
        #expect(speech.maxContext == 0)
        #expect(speech.settings.ext["melix.model_path"] == "/tmp/registry-root/mlx-community/Speech/1")
    }

    @Test("registry snapshot operations persist configured roots and reuse them for subsequent model.list syncs")
    func registrySnapshotOperationsPersistConfiguredRootsAndReuseThemForSubsequentModelListSyncs() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            )
        )
        let overrideJSON = #"["/tmp/root-b","/tmp/root-a"]"#

        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "registry_snapshot",
                outputDir: "",
                ext: [
                    "melix.registry_roots_json": overrideJSON,
                    "melix.registry_rescan": "true",
                ]
            )
        )
        let operationRequest = try #require(await modelOpsClient.lastConvertRequest)
        let operationState = await catalog.registrySnapshotState()

        #expect(operationResponse.ok)
        #expect(operationRequest.ext["melix.registry_roots_json"] == overrideJSON)
        #expect(operationRequest.ext["melix.registry_rescan"] == "true")
        #expect(operationState.hasConfiguredRootOverride)
        #expect(operationState.configuredRootPaths == ["/tmp/root-b", "/tmp/root-a"])
        #expect(operationState.roots.first?.rootID == "root-1")

        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])

        let listResponse = try await service.execute(makeListModelsRequest())
        let listRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(listResponse.ok)
        #expect(listRequest.ext["melix.registry_roots_json"] == overrideJSON)
        #expect(listRequest.ext["melix.registry_rescan"] == "true")
    }

    @Test("model.list preserves an explicit empty registry-root override instead of falling back to environment roots")
    func modelListPreservesExplicitEmptyRegistryRootOverrideInsteadOfFallingBackToEnvironmentRoots() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([])
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        await catalog.updateConfiguredRegistryRoots([])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            )
        )

        _ = try await service.execute(makeListModelsRequest())
        let request = try #require(await modelOpsClient.lastConvertRequest)

        #expect(request.ext["melix.registry_roots_json"] == "[]")
    }

    @Test("registry snapshot operations reuse stored configured roots when the request omits an explicit override")
    func registrySnapshotOperationsReuseStoredConfiguredRootsWhenOverrideIsOmitted() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        await catalog.updateConfiguredRegistryRoots(["/tmp/root-b", "/tmp/root-a"])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "registry_snapshot",
                outputDir: "",
                ext: [:]
            )
        )
        let request = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(request.ext["melix.registry_roots_json"] == #"["/tmp/root-b","/tmp/root-a"]"#)
    }

    @Test("synthetic dataset operations are allowed without a catalog model when required inputs are present")
    func syntheticDatasetOperationsAreAllowedWithoutCatalogModelWhenRequiredInputsArePresent() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = #"{"operation":"generate_synthetic_dataset","dataset_id":"synthetic.chat.v1"}"#
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix/synthetic/samples.jsonl"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )
        let ext = [
            "synthetic_dataset_id": "synthetic.chat.v1",
            "provider_endpoint": "http://127.0.0.1:12436/v1",
            "model": "melix-dev-text",
        ]

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-datasets",
                operation: "generate_synthetic_dataset",
                outputDir: "/tmp/melix/synthetic",
                ext: ext
            )
        )
        let request = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(response.model.operation.operation == "generate_synthetic_dataset")
        #expect(response.model.operation.outputPath == "/tmp/melix/synthetic/samples.jsonl")
        #expect(request.sourceModel == "melix-datasets")
        #expect(request.outputDir == "/tmp/melix/synthetic")
        #expect(request.ext["operation"] == "generate_synthetic_dataset")
        #expect(request.ext["synthetic_dataset_id"] == "synthetic.chat.v1")
    }

    @Test("synthetic dataset operations require the managed import discriminator inputs")
    func syntheticDatasetOperationsRequireManagedImportDiscriminatorInputs() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-datasets",
                operation: "generate_synthetic_dataset",
                outputDir: "/tmp/melix/synthetic",
                ext: [
                    "synthetic_dataset_id": "synthetic.chat.v1",
                    "provider_endpoint": "http://127.0.0.1:12436/v1",
                ]
            )
        )

        let requests = await modelOpsClient.convertRequests
        #expect(!response.ok)
        #expect(response.error.code == "not_found")
        #expect(requests.allSatisfy { $0.ext["operation"] != "generate_synthetic_dataset" })
    }

    @Test("execute handles model.load on the local fast path")
    func executeHandlesLocalModelLoad() async throws {
        let service = ControlPlaneService()

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.state == .modelWarm)
        #expect(response.model.models.first?.state == .modelWarm)
    }

    @Test("execute workerless model.load falls back to local catalog success")
    func executeWorkerlessModelLoadFallsBackToLocalCatalogSuccess() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let service = ControlPlaneService(modelCatalog: catalog)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(model.state == .modelWarm)
        #expect(model.residency.transitionReason == "operator_load")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::local")
    }

    @Test("execute model.load reports a missing managed Hugging Face cache before worker load")
    func executeModelLoadReportsMissingManagedHuggingFaceCacheBeforeWorkerLoad() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.ext["melix.model_path_missing"] = "true"
        model.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        model.settings.ext["melix.registry_descriptor_path"] = "/tmp/melix-managed/huggingface/mlx-community/Qwen3/main"
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = ModelLifecycleWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        )

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let failedModel = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok == false)
        #expect(response.error.code == "model_runtime_missing")
        #expect(response.error.message == "Hugging Face cache files are missing. Re-download this model to restore it.")
        #expect(failedModel.state == .modelFailed)
        #expect(failedModel.residency.transitionReason == "operator_load_model_runtime_missing")
        #expect(await workerClient.loadRequests.isEmpty)
    }

    @Test("execute syncs registry models before worker-backed model.load resolves a discovered model")
    func executeSyncsRegistryModelsBeforeWorkerBackedModelLoad() async throws {
        let registryModelID = "Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": registryModelID,
                    "model_path": "/tmp/registry-root/Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot",
                    "model_kind": "text",
                    "quant_profile_id": "snapshot",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/registry-root",
                        "melix.registry_relative_path": "Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot",
                        "melix.model_path": "/tmp/registry-root/Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot",
                        "melix.source_repo": "Brooooooklyn/Qwen3.5-9B-unsloth-mlx",
                    ],
                ],
            ]
        )
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])

        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "\(registryModelID)::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        let catalog = ModelCatalog(seedModels: [])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: workerClient,
                modelOperationsClient: modelOpsClient,
                modelCatalog: catalog
            )
        )

        let response = try await service.execute(makeLoadModelRequest(modelID: registryModelID))
        let lastConvertRequest = try #require(await modelOpsClient.lastConvertRequest)
        let lastLoadRequest = try #require(await workerClient.loadRequests.last)

        #expect(response.ok)
        #expect(lastConvertRequest.sourceModel == "melix-dev-text")
        #expect(lastConvertRequest.ext["operation"] == "registry_snapshot")
        #expect(lastLoadRequest.model.modelID == registryModelID)
        #expect(response.model.model.modelID == registryModelID)
        #expect(response.model.model.state == .modelWarm)
        #expect(await catalog.dispatchHandle(for: registryModelID) == "\(registryModelID)::swift")
    }

    @Test("execute workerless model.load rejects unsupported disk streaming modes")
    func executeWorkerlessModelLoadRejectsUnsupportedDiskStreamingModes() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.diskStreamingMode = .diskStreamingRequireDisk
        let catalog = ModelCatalog(seedModels: [model])
        let runtimeStore = ServerSessionRuntimeStore()
        let service = ControlPlaneService(
            modelCatalog: catalog,
            serverSessionRuntimeStore: runtimeStore
        )

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let failedModel = try #require(await catalog.model(id: "melix-dev-text"))
        let runtimeSessions = await runtimeStore.snapshot()

        #expect(!response.ok)
        #expect(response.error.code == "disk_streaming_unsupported")
        #expect(failedModel.state == .modelFailed)
        #expect(failedModel.residency.transitionReason == "operator_load_disk_streaming_unsupported")
        #expect(runtimeSessions.first?.requestedDiskStreamingMode == .diskStreamingRequireDisk)
        #expect(runtimeSessions.first?.effectiveDiskStreamingMode == .diskStreamingDisabled)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute handles model.unload on the local fast path")
    func executeHandlesLocalModelUnload() async throws {
        let service = ControlPlaneService()
        _ = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.state == .modelUnloaded)
        #expect(response.model.models.first?.state == .modelUnloaded)
    }

    @Test("execute handles worker-backed model.load with loading and warm transitions")
    func executeHandlesWorkerBackedModelLoadWithIntermediateTransitions() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        await service.unsubscribe(subscription.subscriptionID)

        #expect(response.ok)
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelWarm])
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::swift")
    }

    @Test("execute worker-backed model.load succeeds without explicit error mapping")
    func executeWorkerBackedModelLoadSucceedsWithoutExplicitErrorMapping() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(model.state == .modelWarm)
        #expect(model.residency.transitionReason == "operator_load")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::swift")
    }

    @Test("execute worker-backed model.load forwards adapter-set hash from model settings")
    func executeWorkerBackedModelLoadForwardsAdapterSetHashFromModelSettings() async throws {
        var seeded = ModelCatalog.devTextModel()
        seeded.settings.ext["melix.adapter_set_hash"] = "adapter-alpha"

        let catalog = ModelCatalog(seedModels: [seeded])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let loadRequest = try #require(await workerClient.loadRequests.first)

        #expect(response.ok)
        #expect(loadRequest.model.modelID == "melix-dev-text")
        #expect(loadRequest.model.ext["melix.adapter_set_hash"] == "adapter-alpha")
    }

    @Test("execute worker-backed audio model load prefers managed local model path")
    func executeWorkerBackedAudioModelLoadPrefersManagedLocalModelPath() async throws {
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-audio-load-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        let localModelDirectory = melixHomeDirectory
            .appendingPathComponent(
                "models/default-managed/hf/mlx-community/whisper-large-v3-turbo-asr-fp16/main",
                isDirectory: true
            )
        try FileManager.default.createDirectory(at: localModelDirectory, withIntermediateDirectories: true)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-stt", "audio-tts"]
        )
        try assetManager.recordManagedModel(
            modelID: "melix-whisper-mlx",
            revision: "main",
            sourceModelPath: "mlx-community/whisper-large-v3-turbo-asr-fp16",
            localModelPath: localModelDirectory.path
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxWhisperModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-whisper-mlx::python"
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(
            defaultTextClient: workerClient,
            pythonCompatibilityClient: workerClient,
            modelCatalog: catalog
        )
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: registry,
            audioAssetManager: assetManager
        )

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-whisper-mlx"))
        let loadRequest = try #require(await workerClient.loadRequests.first)

        #expect(response.ok)
        #expect(loadRequest.model.modelPath == localModelDirectory.path)
    }

    @Test("execute returns unavailable and records failed state when worker-backed model.load fails")
    func executeReturnsUnavailableAndRecordsFailedStateWhenWorkerBackedModelLoadFails() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        await workerClient.setLoadError(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))
        await service.unsubscribe(subscription.subscriptionID)

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelFailed])
        #expect(model.state == .modelFailed)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute worker-backed model.load maps thrown worker failures to failed state")
    func executeWorkerBackedModelLoadMapsThrownWorkerFailuresToFailedState() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        await workerClient.setLoadError(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "operator_load_failed")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute returns unavailable when worker-backed model.load returns a non-ready response")
    func executeReturnsUnavailableWhenWorkerBackedModelLoadReturnsNonReadyResponse() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))
        await service.unsubscribe(subscription.subscriptionID)

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelFailed])
        #expect(model.state == .modelFailed)
    }

    @Test("execute surfaces explicit memory budget rejections from worker-backed model.load")
    func executeSurfacesExplicitMemoryBudgetRejectionsFromWorkerBackedModelLoad() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        loadResponse.error.code = "memory_budget_exceeded"
        loadResponse.error.message = "Projected resident memory would exceed the process budget."
        loadResponse.error.details = [
            "budget_bytes": "4500",
            "headroom_bytes": "1024",
            "required_bytes": "5120",
        ]
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))
        await service.unsubscribe(subscription.subscriptionID)

        #expect(!response.ok)
        #expect(response.error.code == "memory_budget_exceeded")
        #expect(response.error.message == "Projected resident memory would exceed the process budget.")
        #expect(response.error.details["budget_bytes"] == "4500")
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelFailed])
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "operator_load_memory_budget_exceeded")
        #expect(model.residency.memoryBudgetBytes == 4_500)
        #expect(model.residency.memoryHeadroomBytes == 1_024)
        #expect(model.residency.requiredBytes == 5_120)
    }

    @Test("execute forwards explicit load memory budgets to worker-backed model.load")
    func executeForwardsExplicitLoadMemoryBudgetsToWorkerBackedModelLoad() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(
            makeLoadModelRequest(modelID: "melix-dev-text", memoryBudgetBytes: 65_536)
        )
        let lastRequest = try #require(await workerClient.loadRequests.last)

        #expect(response.ok)
        #expect(lastRequest.memoryBudgetBytes == 65_536)
    }

    @Test("execute surfaces explicit disk-streaming rejections from worker-backed model.load")
    func executeSurfacesExplicitDiskStreamingRejectionsFromWorkerBackedModelLoad() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.diskStreamingMode = .diskStreamingPreferDisk
        let catalog = ModelCatalog(seedModels: [model])
        let runtimeStore = ServerSessionRuntimeStore()
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        loadResponse.error.code = "disk_streaming_unsupported"
        loadResponse.error.message = "The selected runtime does not support disk-streaming mode."
        loadResponse.error.details = [
            "model_id": "melix-dev-text",
            "requested_mode": "disk_streaming_prefer_disk",
        ]
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(
            modelCatalog: catalog,
            serverSessionRuntimeStore: runtimeStore,
            workerRegistry: registry
        )

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let failedModel = try #require(await catalog.model(id: "melix-dev-text"))
        let loadRequest = try #require(await workerClient.loadRequests.first)
        let runtimeSessions = await runtimeStore.snapshot()

        #expect(!response.ok)
        #expect(response.error.code == "disk_streaming_unsupported")
        #expect(loadRequest.diskStreamingMode == .diskStreamingPreferDisk)
        #expect(failedModel.state == .modelFailed)
        #expect(failedModel.residency.transitionReason == "operator_load_disk_streaming_unsupported")
        #expect(runtimeSessions.first?.requestedDiskStreamingMode == .diskStreamingPreferDisk)
        #expect(runtimeSessions.first?.effectiveDiskStreamingMode == .diskStreamingDisabled)
    }

    @Test("execute sanitizes explicit worker error codes before recording failure transitions")
    func executeSanitizesExplicitWorkerErrorCodesBeforeRecordingFailureTransitions() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        loadResponse.error.code = "memory-budget.exceeded"
        loadResponse.error.message = "Projected resident memory would exceed the process budget."
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "memory-budget.exceeded")
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "operator_load_memory_budget_exceeded")
    }

    @Test("execute handles worker-backed model.unload with evicting and unloaded transitions")
    func executeHandlesWorkerBackedModelUnloadWithIntermediateTransitions() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-text", dispatchHandle: "melix-dev-text::swift")

        let workerClient = ModelLifecycleWorkerClient()
        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = true
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        await service.unsubscribe(subscription.subscriptionID)

        #expect(response.ok)
        #expect(events.map(\.modelState.state) == [.modelEvicting, .modelUnloaded])
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute returns unavailable and records failed state when worker-backed model.unload fails")
    func executeReturnsUnavailableAndRecordsFailedStateWhenWorkerBackedModelUnloadFails() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-text", dispatchHandle: "melix-dev-text::swift")

        let workerClient = ModelLifecycleWorkerClient()
        await workerClient.setUnloadError(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))
        await service.unsubscribe(subscription.subscriptionID)

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelEvicting, .modelFailed])
        #expect(model.state == .modelFailed)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute falls back to local success when a worker-backed unload loses its registry")
    func executeFallsBackToLocalSuccessWhenWorkerBackedUnloadLosesItsRegistry() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let service = ControlPlaneService(modelCatalog: catalog)

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-embed"))
        let model = try #require(await catalog.model(id: "melix-dev-embed"))

        #expect(response.ok)
        #expect(model.state == .modelUnloaded)
        #expect(model.residency.transitionReason == "operator_unload")
    }

    @Test("execute returns unavailable when worker-backed model.unload returns a non-ok response")
    func executeReturnsUnavailableWhenWorkerBackedModelUnloadReturnsNonOkResponse() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-text", dispatchHandle: "melix-dev-text::swift")

        let workerClient = ModelLifecycleWorkerClient()
        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = false
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))
        await service.unsubscribe(subscription.subscriptionID)

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelEvicting, .modelFailed])
        #expect(model.state == .modelFailed)
    }

    @Test("execute model.load opportunistically evicts ttl-expired residents before operator loads")
    func executeModelLoadEvictsTTLExpiredResidentsBeforeOperatorLoads() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 100_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextCatalogModel(
                    id: "melix-old-text",
                    state: .modelWarm,
                    ttlSeconds: 60
                ),
                ModelCatalog.devTextModel(),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        clock.nowUnixMs += 61_000

        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = true
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let metrics = try await service.execute(makeMetricsRequest())
        let operations = await workerClient.recordedOperations
        let evicted = try #require(await catalog.model(id: "melix-old-text"))
        let loaded = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(operations == [
            "unload:melix-old-text::local",
            "load:melix-dev-text",
        ])
        #expect(evicted.state == .modelUnloaded)
        #expect(evicted.residency.transitionReason == "ttl_expired")
        #expect(loaded.state == .modelWarm)
        #expect(loaded.residency.transitionReason == "operator_load")
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_ttl_count"] == 1)
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_success_count"] == 1)
    }

    @Test("startChat evicts ttl-expired residents before reusing a ready text model")
    func startChatEvictsTTLExpiredResidentsBeforeReusingReadyTextModel() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 200_000)
        let readyText = makeTextCatalogModel(id: "melix-dev-text", state: .modelWarm)
        let expiredText = makeTextCatalogModel(
            id: "melix-old-text",
            state: .modelWarm,
            ttlSeconds: 60
        )
        let catalog = ModelCatalog(
            seedModels: [expiredText, readyText],
            nowUnixMs: { clock.nowUnixMs }
        )
        clock.nowUnixMs += 61_000

        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-ready-eviction"),
            makeTokenExecuteEvent(requestID: "chat-ready-eviction", text: "assistant"),
            makeCompletedExecuteEvent(
                requestID: "chat-ready-eviction",
                finishReason: "stop",
                assistant: "assistant",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: catalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-ready-eviction" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        _ = try await Array(execution.stream)

        let unloadRequests = await textClient.unloadRequests
        let generated = try #require(await textClient.lastGenerateRequest)
        let evicted = try #require(await catalog.model(id: "melix-old-text"))
        let ready = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(unloadRequests.map(\.modelHandle) == ["melix-old-text::local"])
        #expect(generated.execution.modelHandle == "melix-dev-text::local")
        #expect(evicted.state == .modelUnloaded)
        #expect(evicted.residency.transitionReason == "ttl_expired")
        #expect(ready.state == .modelWarm)
    }

    @Test("execute model.load records pinned protection and lru eviction metrics")
    func executeModelLoadRecordsPinnedProtectionAndLruEvictionMetrics() async throws {
        let catalog = ModelCatalog(
            seedModels: [
                makeTextCatalogModel(id: "melix-lru-text", state: .modelWarm),
                makeTextCatalogModel(id: "melix-pinned-text", state: .modelPinned, pinOnLoad: true),
                ModelCatalog.devTextModel(),
            ]
        )
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = true
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let metrics = try await service.execute(makeMetricsRequest())
        let pinned = try #require(await catalog.model(id: "melix-pinned-text"))
        let evicted = try #require(await catalog.model(id: "melix-lru-text"))

        #expect(response.ok)
        #expect(pinned.state == .modelPinned)
        #expect(evicted.state == .modelUnloaded)
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_lru_same_capability_count"] == 1)
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_pinned_protected_count"] == 1)
        #expect(await service.evictionMetricKey(for: "custom_reason") == "control_plane.model_eviction_other_count")
    }

    @Test("startChat returns unavailable when lazy text loading cannot prepare the model")
    func startChatReturnsUnavailableWhenLazyTextLoadingCannotPrepareTheModel() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let service = ControlPlaneService(modelCatalog: catalog)

        do {
            _ = try await service.startChat(
                ControlPlaneChatRequest(
                    modelID: "melix-dev-text",
                    messages: [.init(role: "user", content: "hello")]
                )
            )
            Issue.record("Expected missing request coordinator to block chat dispatch")
        } catch let error as ControlPlaneChatExecutionError {
            #expect(String(describing: error).contains("request coordinator is not configured"))
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("startChat reports a friendly missing cache error before lazy load")
    func startChatReportsFriendlyMissingCacheErrorBeforeLazyLoad() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.ext["melix.model_path_missing"] = "true"
        model.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        let catalog = ModelCatalog(seedModels: [model])
        let textClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: catalog)
        )

        do {
            _ = try await service.startChat(
                ControlPlaneChatRequest(
                    modelID: "melix-dev-text",
                    messages: [.init(role: "user", content: "hello")]
                )
            )
            Issue.record("Expected missing Hugging Face cache to block chat dispatch")
        } catch let error as ControlPlaneChatExecutionError {
            #expect(error == .requestFailed(
                code: "model_runtime_missing",
                message: "Hugging Face cache files are missing. Re-download this model to restore it."
            ))
        } catch {
            Issue.record("Unexpected error: \(error)")
        }

        #expect(await textClient.lastLoadModelRequest == nil)
        #expect(await textClient.lastGenerateRequest == nil)
    }

    @Test("execute handles model.set_policy and updates typed model settings")
    func executeHandlesModelSetPolicyAndUpdatesTypedModelSettings() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "alias": "Melix Text Turbo",
                    "pin_on_load": "true",
                    "memory_policy": "pinned",
                    "disk_streaming_mode": "prefer_disk",
                    "cache_mode": "hybrid",
                    "cache_memory_budget_bytes": "4096",
                    "cache_memory_budget_pct": "25",
                    "cache_block_size_tokens": "64",
                    "cache_directory": "/tmp/melix-cache",
                    "multimodal_cache_budget_bytes": "2048",
                    "default_acceleration_mode": "speculative_decode",
                    "acceleration_profile_id": "draft-q4",
                    "trust_remote_code": "true",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.settings.alias == "Melix Text Turbo")
        #expect(response.model.model.settings.pinOnLoad)
        #expect(response.model.model.settings.memoryPolicy == .memoryResidencyPinned)
        #expect(response.model.model.settings.diskStreamingMode == .diskStreamingPreferDisk)
        #expect(response.model.model.settings.cacheMode == .hybrid)
        #expect(response.model.model.settings.cacheMemoryBudgetBytes == 4_096)
        #expect(response.model.model.settings.cacheMemoryBudgetPct == 25)
        #expect(response.model.model.settings.cacheBlockSizeTokens == 64)
        #expect(response.model.model.settings.cacheDirectory == "/tmp/melix-cache")
        #expect(response.model.model.settings.multimodalCacheBudgetBytes == 2_048)
        #expect(response.model.model.settings.defaultAccelerationMode == .speculativeDecode)
        #expect(response.model.model.settings.accelerationProfileID == "draft-q4")
        #expect(response.model.model.settings.loadTrustMode == .modelLoadTrustTrustRemoteCode)
    }

    @Test("execute normalizes and clears model-load trust policy settings")
    func executeNormalizesAndClearsModelLoadTrustPolicySettings() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let defaultSafe = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["load_trust_mode": "default-safe"]
            )
        )
        let trusted = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["model_load_trust_mode": "trust_remote_code"]
            )
        )
        let cleared = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["trust_remote_code": ""]
            )
        )

        #expect(defaultSafe.ok)
        #expect(defaultSafe.model.model.settings.loadTrustMode == .modelLoadTrustDefaultSafe)
        #expect(trusted.ok)
        #expect(trusted.model.model.settings.loadTrustMode == .modelLoadTrustTrustRemoteCode)
        #expect(cleared.ok)
        #expect(cleared.model.model.settings.loadTrustMode == .unspecified)
    }

    @Test("execute normalizes cache mode labels and clears cache policy settings")
    func executeNormalizesCacheModeLabelsAndClearsCachePolicySettings() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let rotatingResponse = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["cache_mode": "rotating"]
            )
        )
        let defaultResponse = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["cache_mode": "default"]
            )
        )
        let clearedResponse = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "cache_mode": "not-a-real-mode",
                    "cache_memory_budget_bytes": "",
                    "cache_memory_budget_pct": "",
                    "cache_block_size_tokens": "",
                    "cache_directory": "",
                    "multimodal_cache_budget_bytes": "",
                ]
            )
        )

        #expect(rotatingResponse.ok)
        #expect(rotatingResponse.model.model.settings.cacheMode == .rotating)
        #expect(defaultResponse.ok)
        #expect(defaultResponse.model.model.settings.cacheMode == .tiered)
        #expect(clearedResponse.ok)
        #expect(clearedResponse.model.model.settings.cacheMode == .unspecified)
        #expect(clearedResponse.model.model.settings.cacheMemoryBudgetBytes == 0)
        #expect(clearedResponse.model.model.settings.cacheMemoryBudgetPct == 0)
        #expect(clearedResponse.model.model.settings.cacheBlockSizeTokens == 0)
        #expect(clearedResponse.model.model.settings.cacheDirectory.isEmpty)
        #expect(clearedResponse.model.model.settings.multimodalCacheBudgetBytes == 0)
    }

    @Test("execute normalizes require and fallback disk-streaming policy strings")
    func executeNormalizesRequireAndFallbackDiskStreamingPolicyStrings() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let requireResponse = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["disk_streaming_mode": "require-disk"]
            )
        )
        let fallbackResponse = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: ["disk_streaming_mode": "not-a-real-mode"]
            )
        )

        #expect(requireResponse.ok)
        #expect(requireResponse.model.model.settings.diskStreamingMode == .diskStreamingRequireDisk)
        #expect(fallbackResponse.ok)
        #expect(fallbackResponse.model.model.settings.diskStreamingMode == .diskStreamingDisabled)
    }

    @Test("execute handles model.get_info through the model-operations worker")
    func executeHandlesModelGetInfoThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = true
            response.modelKind = "text"
            response.maxContext = 8192
            response.supportedParsers = ["text", "json"]
            response.supportedModalities = ["text"]
            response.supportedTasks = ["generate", "chat"]
            response.backendID = "mlx_lm"
            response.familyID = "llama-v1"
            response.modelPath = "/tmp/models/melix-dev-text"
            response.modelRevision = "dev"
            response.defaultWorkflowRole = "chat"
            response.detectedIdentitySource = "explicit_override"
            return response
        }())
        let textClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let lastRequest = try #require(await modelOpsClient.lastInfoRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(response.model.info.ok)
        #expect(response.model.info.modelKind == "text")
        #expect(response.model.info.maxContext == 8192)
        #expect(response.model.info.supportedParsers == ["text", "json"])
        #expect(response.model.info.supportedTasks == ["generate", "chat"])
        #expect(response.model.info.backendID == "mlx_lm")
        #expect(response.model.info.familyID == "llama-v1")
        #expect(response.model.info.modelPath == "/tmp/models/melix-dev-text")
        #expect(response.model.info.modelRevision == "dev")
        #expect(response.model.info.defaultWorkflowRole == "chat")
        #expect(response.model.info.detectedIdentitySource == "explicit_override")
    }

    @Test("execute syncs imported registry models before model.get_info")
    func executeSyncsImportedRegistryModelsBeforeModelGetInfo() async throws {
        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let importedModelPath = "/tmp/managed-root/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
        let registryManifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": importedModelID,
                    "model_path": importedModelPath,
                    "model_kind": "text",
                    "revision": "main",
                    "tokenizer_hash": "hf.mlx-community.Qwen3.5-0.8B-OptiQ-4bit",
                    "quant_profile_id": "",
                    "parser_mode": "text",
                    "reasoning_mode": "off",
                    "max_context": 8192,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/managed-root",
                        "melix.registry_relative_path": "huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main",
                        "melix.model_path": importedModelPath,
                        "melix.hf_repo_id": importedModelID,
                        "melix.capability.class": "text",
                        "melix.capability.supported_modalities": "text",
                        "melix.capability.supported_tasks": "generate",
                    ],
                ],
            ]
        )
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = registryManifestJSON
                return event
            }(),
        ])
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = true
            response.modelKind = "text"
            response.maxContext = 8192
            response.supportedModalities = ["text"]
            response.supportedTasks = ["generate", "chat"]
            response.backendID = "mlx_lm"
            response.modelPath = importedModelPath
            response.modelRevision = "main"
            return response
        }())

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedChatWorkerClient(events: []),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeGetModelInfoRequest(modelID: importedModelID))
        let lastConvertRequest = try #require(await modelOpsClient.lastConvertRequest)
        let lastInfoRequest = try #require(await modelOpsClient.lastInfoRequest)

        #expect(response.ok)
        #expect(lastConvertRequest.sourceModel == "melix-dev-text")
        #expect(lastConvertRequest.ext["operation"] == "registry_snapshot")
        #expect(lastConvertRequest.ext["melix.registry_rescan"] == "true")
        #expect(lastInfoRequest.sourceModel == importedModelID)
        #expect(response.model.info.ok)
        #expect(response.model.info.modelKind == "text")
        #expect(response.model.info.modelPath == importedModelPath)
    }

    @Test("execute handles model.run_operation through the model-operations worker")
    func executeHandlesModelRunOperationThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.progress = Melix_Worker_V1_ConvertProgress()
                event.progress.stage = "write_artifact"
                event.progress.pct = 0.75
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = #"{"operation":"quantize"}"#
                event.manifest.quantProfile = Melix_Worker_V1_QuantizationProfile()
                event.manifest.quantProfile.algorithm = "oq"
                event.manifest.quantProfile.schemaVersion = "melix.quant_profile.v1"
                event.manifest.quantProfile.quantProfileID = "q4"
                event.manifest.quantProfile.weightQuant = "q4"
                event.manifest.quantProfile.kvQuant = "q8"
                event.manifest.artifact = Melix_Worker_V1_QuantizedArtifact()
                event.manifest.artifact.schemaVersion = "melix.quantized_bundle.v1"
                event.manifest.artifact.artifactKind = "quantized_model_bundle"
                event.manifest.artifact.manifestPath = "/tmp/melix-ops/quantize.artifact/manifest.json"
                event.manifest.artifact.bundlePath = "/tmp/melix-ops/quantize.artifact"
                event.manifest.artifact.artifactBytes = 256
                event.manifest.artifact.manifestBytes = 128
                event.manifest.artifact.servingCompatible = true
                event.manifest.artifact.smokeTestRequested = true
                event.manifest.artifact.smokeTestPassed = true
                event.manifest.artifact.runtime = "mlx_text"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-ops/quantize.artifact"
                event.completed.quantProfile = Melix_Worker_V1_QuantizationProfile()
                event.completed.quantProfile.algorithm = "oq"
                event.completed.quantProfile.schemaVersion = "melix.quant_profile.v1"
                event.completed.quantProfile.quantProfileID = "q4"
                event.completed.quantProfile.weightQuant = "q4"
                event.completed.quantProfile.kvQuant = "q8"
                event.completed.artifact = Melix_Worker_V1_QuantizedArtifact()
                event.completed.artifact.schemaVersion = "melix.quantized_bundle.v1"
                event.completed.artifact.artifactKind = "quantized_model_bundle"
                event.completed.artifact.manifestPath = "/tmp/melix-ops/quantize.artifact/manifest.json"
                event.completed.artifact.bundlePath = "/tmp/melix-ops/quantize.artifact"
                event.completed.artifact.artifactBytes = 256
                event.completed.artifact.manifestBytes = 128
                event.completed.artifact.servingCompatible = true
                event.completed.artifact.smokeTestRequested = true
                event.completed.artifact.smokeTestPassed = true
                event.completed.artifact.runtime = "mlx_text"
                return event
            }(),
        ])
        let textClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8",
                ext: ["target_repo": "melix/upload-target"]
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(lastRequest.ext["operation"] == "quantize")
        #expect(lastRequest.weightQuant == "q4")
        #expect(lastRequest.kvQuant == "q8")
        #expect(lastRequest.quantProfile.algorithm == "oq")
        #expect(lastRequest.quantProfile.schemaVersion == "melix.quant_profile.v1")
        #expect(lastRequest.quantProfile.quantProfileID == "q4")
        #expect(lastRequest.quantProfile.weightQuant == "q4")
        #expect(lastRequest.quantProfile.kvQuant == "q8")
        #expect(lastRequest.ext["target_repo"] == "melix/upload-target")
        #expect(response.model.operation.ok)
        #expect(response.model.operation.operation == "quantize")
        #expect(response.model.operation.jobID == "job-123")
        #expect(response.model.operation.stage == "write_artifact")
        #expect(response.model.operation.outputPath == "/tmp/melix-ops/quantize.artifact")
        #expect(response.model.operation.manifestJson == #"{"operation":"quantize"}"#)
        #expect(response.model.operation.quantProfile.algorithm == "oq")
        #expect(response.model.operation.quantProfile.quantProfileID == "q4")
        #expect(response.model.operation.quantProfile.kvQuant == "q8")
        #expect(response.model.operation.artifact.artifactKind == "quantized_model_bundle")
        #expect(response.model.operation.artifact.manifestPath == "/tmp/melix-ops/quantize.artifact/manifest.json")
        #expect(response.model.operation.artifact.bundlePath == "/tmp/melix-ops/quantize.artifact")
        #expect(response.model.operation.artifact.artifactBytes == 256)
        #expect(response.model.operation.artifact.manifestBytes == 128)
        #expect(response.model.operation.artifact.smokeTestRequested)
        #expect(response.model.operation.artifact.smokeTestPassed)
    }

    @Test("execute allows managed hub import downloads for unknown model ids")
    func executeAllowsManagedHubImportDownloadsForUnknownModelIDs() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-hub-import-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/managed-root/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                operation: "download",
                outputDir: "/tmp/melix-downloads/qwen35",
                ext: [
                    "melix.source_kind": "hub_repo",
                    "melix.hf_repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "melix.hf_revision": "main",
                    "melix.managed_import": "true",
                ]
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(lastRequest.ext["operation"] == "download")
        #expect(lastRequest.ext["melix.source_kind"] == "hub_repo")
        #expect(lastRequest.ext["melix.hf_repo_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(lastRequest.ext["melix.hf_revision"] == "main")
        #expect(lastRequest.ext["melix.managed_import"] == "true")
        #expect(response.model.operation.operation == "download")
        #expect(response.model.operation.jobID == "job-hub-import-123")
        #expect(response.model.operation.outputPath == "/tmp/managed-root/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main")
    }

    @Test("execute allows local import operations for unknown model ids")
    func executeAllowsLocalImportOperationsForUnknownModelIDs() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-local-import-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/managed-root/local/melix-dev-qwen-local/main"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-qwen-local",
                operation: "local_import",
                outputDir: "",
                ext: [
                    "source_path": "/tmp/qwen-local-model",
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/qwen-local-model",
                    "melix.model_kind": "text",
                    "melix.revision": "main",
                    "melix.managed_root": "/tmp/managed-root",
                ]
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-qwen-local")
        #expect(lastRequest.ext["operation"] == "local_import")
        #expect(lastRequest.ext["source_path"] == "/tmp/qwen-local-model")
        #expect(lastRequest.ext["melix.source_kind"] == "local_path")
        #expect(lastRequest.ext["melix.source_locator"] == "/tmp/qwen-local-model")
        #expect(lastRequest.ext["melix.model_kind"] == "text")
        #expect(lastRequest.ext["melix.revision"] == "main")
        #expect(lastRequest.ext["melix.managed_root"] == "/tmp/managed-root")
        #expect(response.model.operation.operation == "local_import")
        #expect(response.model.operation.jobID == "job-local-import-123")
        #expect(response.model.operation.outputPath == "/tmp/managed-root/local/melix-dev-qwen-local/main")
    }

    @Test("execute prefers explicit quant profile selection for quantize operations")
    func executePrefersExplicitQuantProfileSelectionForQuantizeOperations() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-q6"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-ops/quantize.artifact"
                return event
            }(),
        ])
        let textClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                quantProfileID: "q6",
                weightQuant: "",
                kvQuant: "q8"
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.quantProfile.quantProfileID == "q6")
        #expect(lastRequest.quantProfile.weightQuant == "q6")
        #expect(lastRequest.quantProfile.kvQuant == "q8")
        #expect(lastRequest.weightQuant.isEmpty)
    }

    @Test("execute registers activated derived models into the catalog")
    func executeRegistersActivatedDerivedModelsIntoTheCatalog() async throws {
        let manifestJSON = """
        {"schema_version":"melix.derived_text_model.v1","activation_mode":"fused_derived_model","source_model":"melix-dev-text","source_model_revision":"dev","adapter_name":"melix-dev-adapter","adapter_set_hash":"adapter-alpha","derived_model_id":"melix-dev-text-lora-adapter","derived_model_path":"/tmp/melix-derived/model"}
        """

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-activate-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-derived/model/manifest.json"
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "activate_adapter",
                outputDir: "/tmp/melix-derived",
                ext: ["artifact_path": "/tmp/melix-train/train_lora.adapter.json"]
            )
        )
        let derived = try #require(await catalog.model(id: "melix-dev-text-lora-adapter"))

        #expect(response.ok)
        #expect(response.model.operation.operation == "activate_adapter")
        #expect(response.model.operation.manifestJson == manifestJSON)
        #expect(derived.routeClass == .workerRouteSwiftText)
        #expect(derived.capabilityClass == .modelCapabilityText)
        #expect(derived.settings.ext["melix.model_path"] == "/tmp/melix-derived/model")
        #expect(derived.settings.ext["melix.adapter_set_hash"] == "adapter-alpha")
        #expect(derived.settings.ext["melix.derived_from_adapter"] == "true")
        #expect(derived.settings.ext["melix.derived_from_model_id"] == "melix-dev-text")
        // Fused derived models surface as runtime_mode="fused_derived_model"
        // on the ModelSummary so CLI listings distinguish them from
        // adapter-backed derived models at a glance.
        #expect(derived.runtimeMode == "fused_derived_model")
    }

    @Test("execute registers adapter-backed derived models into the catalog with compatibility routing")
    func executeRegistersAdapterBackedDerivedModelsIntoTheCatalogWithCompatibilityRouting() async throws {
        let manifestJSON = """
        {"schema_version":"melix.derived_text_model.v1","activation_mode":"adapter_backed_runtime","source_model":"melix-dev-text","source_model_revision":"dev","adapter_name":"melix-dev-adapter","adapter_set_hash":"adapter-beta","derived_model_id":"melix-dev-text-lora-adapter-runtime","derived_model_path":"models/dev-text","adapter_manifest_path":"/tmp/melix-train/train_lora.adapter.json","adapter_weights_path":"/tmp/melix-train/weights/adapters.safetensors","derived_model_alias":"Runtime Alias"}
        """

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-activate-runtime-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-derived/runtime/manifest.json"
                return event
            }(),
        ])

        var sourceModel = ModelCatalog.devTextModel()
        sourceModel.settings.loadTrustMode = .modelLoadTrustTrustRemoteCode
        sourceModel.loadTrust = {
            var policy = Melix_Controlplane_V1_ModelLoadTrustPolicy()
            policy.requestedMode = .modelLoadTrustTrustRemoteCode
            policy.effectiveMode = .modelLoadTrustTrustRemoteCode
            policy.policySource = "model_settings"
            policy.routeClass = .workerRoutePythonTextCompatibility
            policy.loaderFamily = "mlx_lm"
            return policy
        }()
        let catalog = ModelCatalog(seedModels: [sourceModel])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "activate_adapter",
                outputDir: "/tmp/melix-derived-runtime",
                ext: [
                    "artifact_path": "/tmp/melix-train/train_lora.adapter.json",
                    "activation_mode": "adapter_backed_runtime",
                ]
            )
        )
        let derived = try #require(await catalog.model(id: "melix-dev-text-lora-adapter-runtime"))

        #expect(response.ok)
        #expect(response.model.operation.operation == "activate_adapter")
        #expect(derived.routeClass == .workerRoutePythonTextCompatibility)
        #expect(derived.capabilityClass == .modelCapabilityText)
        #expect(derived.settings.alias == "Runtime Alias")
        #expect(derived.settings.ext["melix.model_path"] == "models/dev-text")
        #expect(derived.settings.ext["melix.activation_mode"] == "adapter_backed_runtime")
        #expect(derived.runtimeMode == "adapter_backed_runtime")
        #expect(derived.settings.ext["melix.adapter_manifest_path"] == "/tmp/melix-train/train_lora.adapter.json")
        #expect(derived.settings.ext["melix.adapter_weights_path"] == "/tmp/melix-train/weights/adapters.safetensors")
        #expect(derived.settings.ext["melix.derived_model_alias"] == "Runtime Alias")
        #expect(derived.settings.ext["melix.derived_from_model_id"] == "melix-dev-text")
        #expect(derived.settings.loadTrustMode == .unspecified)
        #expect(derived.hasLoadTrust == false)
    }

    @Test("execute prunes removed derived models from the catalog after remove-derived completes")
    func executePrunesRemovedDerivedModelsFromTheCatalogAfterRemoveDerivedCompletes() async throws {
        let removalManifestJSON = """
        {"schema_version":"melix.derived_model_removal.v1","operation":"remove_derived_model","source_model":"melix-dev-text","derived_model_id":"melix-dev-text-lora-adapter","activation_mode":"fused_derived_model","activation_job_id":"job-activate-123","activation_manifest_path":"/tmp/melix-derived/model/manifest.json","adapter_manifest_path":"/tmp/melix-train/train_lora.adapter.json"}
        """

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-remove-derived-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = removalManifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-remove/remove_derived_model.lifecycle.json"
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        var derived = ModelCatalog.devTextModel()
        derived.modelID = "melix-dev-text-lora-adapter"
        derived.settings.alias = "Derived Adapter"
        derived.settings.ext["melix.model_path"] = "/tmp/melix-derived/model"
        derived.settings.ext["melix.derived_from_adapter"] = "true"
        derived.settings.ext["melix.activation_mode"] = "fused_derived_model"
        await catalog.registerModel(derived, reason: "test_setup")

        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "remove_derived_model",
                outputDir: "/tmp/melix-remove",
                ext: ["derived_model_id": "melix-dev-text-lora-adapter"]
            )
        )

        #expect(response.ok)
        #expect(response.model.operation.operation == "remove_derived_model")
        #expect(await catalog.model(id: "melix-dev-text-lora-adapter") == nil)
    }

    @Test("execute preserves download operation state when the worker returns a terminal failure")
    func executePreservesDownloadOperationStateWhenTheWorkerReturnsATerminalFailure() async throws {
        let manifestJSON = """
        {"schema_version":"melix.download_job.v1","status":"stalled","terminal_state":"stalled","selected_mirror":"https://mirror.example/hf","downloaded_bytes":512,"total_bytes":2048,"stall_reason":"no_progress_timeout","retry_count":1}
        """

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-download-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.progress = Melix_Worker_V1_ConvertProgress()
                event.progress.stage = "download"
                event.progress.pct = 0.25
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.failed = Melix_Worker_V1_ConvertFailed()
                event.failed.error.code = "download_stalled"
                event.failed.error.message = "Download stalled without progress."
                return event
            }(),
        ])
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "download",
                outputDir: "/tmp/melix-download"
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "download_stalled")
        #expect(response.error.message == "Download stalled without progress.")
        #expect(response.model.operation.operation == "download")
        #expect(response.model.operation.jobID == "job-download-123")
        #expect(response.model.operation.stage == "download")
        #expect(response.model.operation.pct == 0.25)
        #expect(response.model.operation.manifestJson == manifestJSON)
    }

    @Test("execute syncs imported registry models before train_lora operations")
    func executeSyncsImportedRegistryModelsBeforeTrainLoraOperations() async throws {
        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let importedModelPath = "/tmp/managed-root/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
        let registryManifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": importedModelID,
                    "model_path": importedModelPath,
                    "model_kind": "text",
                    "revision": "main",
                    "tokenizer_hash": "hf.mlx-community.Qwen3.5-0.8B-OptiQ-4bit",
                    "quant_profile_id": "",
                    "parser_mode": "text",
                    "reasoning_mode": "off",
                    "max_context": 8192,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/managed-root",
                        "melix.registry_relative_path": "huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main",
                        "melix.model_path": importedModelPath,
                        "melix.hf_repo_id": importedModelID,
                        "melix.capability.class": "text",
                        "melix.capability.route_kind": "python_text_compatibility",
                        "melix.capability.supported_modalities": "text",
                        "melix.capability.supported_tasks": "generate",
                    ],
                ],
            ]
        )

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = registryManifestJSON
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-train-lora-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-train/train_lora.adapter.json"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: importedModelID,
                operation: "train_lora",
                outputDir: "/tmp/melix-train",
                ext: [
                    "dataset_source_kind": "hf_dataset",
                    "hf_dataset_path": "neuralmagic/ultrachat_2k",
                    "hf_train_split": "train_sft",
                    "chat_feature": "messages",
                ]
            )
        )
        let requests = await modelOpsClient.convertRequests
        #expect(requests.count == 2)
        let syncRequest = try #require(requests.first)
        let lastRequest = try #require(requests.last)

        #expect(response.ok)
        #expect(syncRequest.sourceModel == "melix-dev-model-ops")
        #expect(syncRequest.ext["operation"] == "registry_snapshot")
        #expect(syncRequest.ext["melix.registry_rescan"] == "true")
        #expect(lastRequest.sourceModel == importedModelID)
        #expect(lastRequest.ext["operation"] == "train_lora")
        #expect(response.model.operation.jobID == "job-train-lora-123")
        #expect(response.model.operation.outputPath == "/tmp/melix-train/train_lora.adapter.json")
    }

    @Test("execute install_audio_runtime records shared audio runtime pack metadata")
    func executeInstallAudioRuntimeRecordsSharedAudioRuntimePackMetadata() async throws {
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-audio-runtime-install-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-install-audio"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-audio-runtime/install_audio_runtime.artifact.json"
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxWhisperModel()])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            ),
            audioAssetManager: assetManager
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-whisper-mlx",
                operation: "install_audio_runtime",
                outputDir: "/tmp/melix-audio-runtime"
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)
        let listResponse = try await service.execute(makeListModelsRequest())
        let runtimePackRecord = try #require(assetManager.runtimePackRecord(for: "audio-stt"))
        let model = try #require(listResponse.model.models.first(where: { $0.modelID == "melix-whisper-mlx" }))

        #expect(response.ok)
        #expect(lastRequest.ext["operation"] == "install_audio_runtime")
        #expect(runtimePackRecord.packID == "melix-audio-runtime-pack")
        #expect(runtimePackRecord.profiles == ["audio-stt", "audio-tts"])
        #expect(response.model.operation.outputPath.contains("/runtime-packs/audio/melix-audio-runtime-pack/"))
        #expect(model.settings.ext["melix.audio.runtime_pack_state"] == "installed")
        #expect(model.settings.ext["melix.audio.runtime_pack_id"] == "melix-audio-runtime-pack")
    }

    @Test("execute download records managed local audio model metadata")
    func executeDownloadRecordsManagedLocalAudioModelMetadata() async throws {
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-audio-model-download-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-download-audio"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-audio-models/download.artifact.json"
                return event
            }(),
        ])

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxWhisperModel()])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            ),
            audioAssetManager: assetManager
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-whisper-mlx",
                operation: "download",
                outputDir: "/tmp/melix-audio-models"
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)
        let listResponse = try await service.execute(makeListModelsRequest())
        let managedRecord = try #require(assetManager.managedModelRecord(for: "melix-whisper-mlx"))
        let model = try #require(listResponse.model.models.first(where: { $0.modelID == "melix-whisper-mlx" }))

        #expect(response.ok)
        #expect(lastRequest.ext["operation"] == "download")
        #expect(managedRecord.localModelPath.contains("/models/default-managed/"))
        #expect(response.model.operation.outputPath == managedRecord.localModelPath)
        #expect(model.settings.ext["melix.audio.model_state"] == "managed_local")
        #expect(model.settings.ext["melix.model_path"] == managedRecord.localModelPath)
    }

    @Test("execute handles ops.run_doctor through the model-operations worker")
    func executeHandlesOpsRunDoctorThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setDoctorResponse({
            var response = Melix_Worker_V1_RunDoctorResponse()
            response.ok = true
            response.reportMarkdown = "# Melix Doctor\n\n- worker_state: idle\n"
            response.healthStatus = .healthy
            response.findings = []
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunDoctorRequest())
        let lastRequest = try #require(await modelOpsClient.lastDoctorRequest)

        #expect(response.ok)
        #expect(lastRequest.includeCacheDiagnostics)
        #expect(lastRequest.includeMemoryReport)
        #expect(response.ops.reportMarkdown.contains("Melix Doctor"))
        #expect(response.ops.doctor.markdown.contains("Melix Doctor"))
        #expect(response.ops.doctor.healthStatus == .healthy)
        #expect(response.ops.doctor.findings.isEmpty)
    }

    @Test("execute maps typed doctor health findings from the worker")
    func executeMapsTypedDoctorHealthFindingsFromTheWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setDoctorResponse({
            var response = Melix_Worker_V1_RunDoctorResponse()
            response.ok = true
            response.reportMarkdown = "# Melix Doctor\n\n- worker_state: degraded\n"
            response.healthStatus = .warning

            var degraded = Melix_Worker_V1_DoctorFinding()
            degraded.code = "model_not_loaded"
            degraded.severity = .degraded
            degraded.summary = "Model missing from registry"
            degraded.detail = "The requested handle was not found."

            var failed = Melix_Worker_V1_DoctorFinding()
            failed.code = "worker_failed"
            failed.severity = .failed
            failed.summary = "Worker failed"
            failed.detail = "Worker state is failed."

            var unknown = Melix_Worker_V1_DoctorFinding()
            unknown.code = "cache_unavailable"
            unknown.severity = .unspecified
            unknown.summary = "Cache unavailable"
            unknown.detail = "The cache report did not contain resident bytes."

            response.findings = [degraded, failed, unknown]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunDoctorRequest())

        #expect(response.ok)
        #expect(response.ops.doctor.healthStatus == .warning)
        #expect(response.ops.doctor.findings.count == 3)
        #expect(response.ops.doctor.findings[0].code == "model_not_loaded")
        #expect(response.ops.doctor.findings[0].severity == .degraded)
        #expect(response.ops.doctor.findings[0].detail.contains("requested handle"))
        #expect(response.ops.doctor.findings[1].severity == .failed)
        #expect(response.ops.doctor.findings[2].severity == .unspecified)
    }

    @Test("execute handles ops.search_hub_models through the model-operations worker")
    func executeHandlesOpsSearchHubModelsThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubSearchResponse({
            var response = Melix_Worker_V1_SearchHubModelsResponse()
            response.ok = true
            response.nextCursor = "cursor:page-2"
            var model = Melix_Worker_V1_HubModelSummary()
            model.repoID = "mlx-community/Qwen2.5-7B-Instruct-4bit"
            model.author = "mlx-community"
            model.modelName = "Qwen2.5-7B-Instruct-4bit"
            model.summary = "MLX text-generation build"
            model.pipelineTag = "text-generation"
            model.tags = ["mlx", "chat"]
            model.downloads = 321
            model.likes = 12
            model.mlxCompatible = true
            model.libraryName = "transformers"
            model.siblingFiles = ["README.md", "config.json"]
            model.lastModified = "2025-01-26T19:49:28Z"
            model.localFitStatus = "good"
            model.localFitReasons = [
                "MLX-compatible Hub metadata found.",
                "Estimated resident bytes are within the memory comfort budget.",
            ]
            model.estimatedArtifactBytes = 4_200_000_000
            model.estimatedResidentBytes = 5_670_000_000
            model.parameterCount = 7_000_000_000
            model.quantizationSummary = "4-bit"
            model.gated = false
            model.recommendedAction = "download"
            response.models = [model]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeSearchHubModelsRequest(
                query: "qwen",
                pageSize: 5,
                cursor: "cursor:page-1",
                mlxOnly: true
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastHubSearchRequest)

        #expect(response.ok)
        #expect(lastRequest.query == "qwen")
        #expect(lastRequest.pageSize == 5)
        #expect(lastRequest.cursor == "cursor:page-1")
        #expect(lastRequest.mlxOnly)
        #expect(response.ops.hubSearch.nextCursor == "cursor:page-2")
        #expect(response.ops.hubSearch.models.count == 1)
        #expect(response.ops.hubSearch.models[0].repoID == "mlx-community/Qwen2.5-7B-Instruct-4bit")
        #expect(response.ops.hubSearch.models[0].author == "mlx-community")
        #expect(response.ops.hubSearch.models[0].pipelineTag == "text-generation")
        #expect(response.ops.hubSearch.models[0].mlxCompatible)
        #expect(response.ops.hubSearch.models[0].siblingFiles == ["README.md", "config.json"])
        #expect(response.ops.hubSearch.models[0].localFitStatus == "good")
        #expect(response.ops.hubSearch.models[0].localFitReasons == [
            "MLX-compatible Hub metadata found.",
            "Estimated resident bytes are within the memory comfort budget.",
        ])
        #expect(response.ops.hubSearch.models[0].estimatedArtifactBytes == 4_200_000_000)
        #expect(response.ops.hubSearch.models[0].estimatedResidentBytes == 5_670_000_000)
        #expect(response.ops.hubSearch.models[0].parameterCount == 7_000_000_000)
        #expect(response.ops.hubSearch.models[0].quantizationSummary == "4-bit")
        #expect(response.ops.hubSearch.models[0].gated == false)
        #expect(response.ops.hubSearch.models[0].recommendedAction == "download")
    }

    @Test("execute handles ops.get_hub_model_card through the model-operations worker")
    func executeHandlesOpsGetHubModelCardThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse({
            var response = Melix_Worker_V1_GetHubModelCardResponse()
            response.ok = true
            response.card.repoID = "mlx-community/Qwen2.5-7B-Instruct-4bit"
            response.card.author = "mlx-community"
            response.card.modelName = "Qwen2.5-7B-Instruct-4bit"
            response.card.summary = "MLX text-generation build"
            response.card.license = "apache-2.0"
            response.card.pipelineTag = "text-generation"
            response.card.tags = ["mlx", "chat"]
            response.card.downloads = 321
            response.card.likes = 12
            response.card.mlxCompatible = true
            response.card.libraryName = "transformers"
            response.card.siblingFiles = ["README.md", "config.json", "model.safetensors"]
            response.card.baseModels = ["Qwen/Qwen2.5-7B-Instruct"]
            response.card.lastModified = "2025-01-26T19:49:28Z"
            response.card.localFitStatus = "heavy"
            response.card.localFitReasons = [
                "MLX-compatible Hub metadata found.",
                "Estimated resident bytes exceed the memory comfort budget.",
            ]
            response.card.estimatedArtifactBytes = 52_000_000_000
            response.card.estimatedResidentBytes = 70_200_000_000
            response.card.parameterCount = 72_000_000_000
            response.card.quantizationSummary = "4-bit"
            response.card.gated = false
            response.card.recommendedAction = "review_risk"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeGetHubModelCardRequest(repoID: "mlx-community/Qwen2.5-7B-Instruct-4bit")
        )
        let lastRequest = try #require(await modelOpsClient.lastHubModelCardRequest)

        #expect(response.ok)
        #expect(lastRequest.repoID == "mlx-community/Qwen2.5-7B-Instruct-4bit")
        #expect(response.ops.hubModelCard.repoID == "mlx-community/Qwen2.5-7B-Instruct-4bit")
        #expect(response.ops.hubModelCard.author == "mlx-community")
        #expect(response.ops.hubModelCard.license == "apache-2.0")
        #expect(response.ops.hubModelCard.pipelineTag == "text-generation")
        #expect(response.ops.hubModelCard.mlxCompatible)
        #expect(response.ops.hubModelCard.baseModels == ["Qwen/Qwen2.5-7B-Instruct"])
        #expect(response.ops.hubModelCard.siblingFiles == ["README.md", "config.json", "model.safetensors"])
        #expect(response.ops.hubModelCard.localFitStatus == "heavy")
        #expect(response.ops.hubModelCard.localFitReasons == [
            "MLX-compatible Hub metadata found.",
            "Estimated resident bytes exceed the memory comfort budget.",
        ])
        #expect(response.ops.hubModelCard.estimatedArtifactBytes == 52_000_000_000)
        #expect(response.ops.hubModelCard.estimatedResidentBytes == 70_200_000_000)
        #expect(response.ops.hubModelCard.parameterCount == 72_000_000_000)
        #expect(response.ops.hubModelCard.quantizationSummary == "4-bit")
        #expect(response.ops.hubModelCard.gated == false)
        #expect(response.ops.hubModelCard.recommendedAction == "review_risk")
    }

    @Test("execute returns unavailable for hub ops when the model-operations worker is missing")
    func executeReturnsUnavailableForHubOpsWithoutModelOperationsWorker() async throws {
        let service = ControlPlaneService()

        let searchResponse = try await service.execute(
            makeSearchHubModelsRequest(query: "qwen", pageSize: 5, cursor: "", mlxOnly: true)
        )
        let cardResponse = try await service.execute(
            makeGetHubModelCardRequest(repoID: "mlx-community/Qwen2.5-7B-Instruct-4bit")
        )

        #expect(searchResponse.ok == false)
        #expect(searchResponse.error.code == "unavailable")
        #expect(searchResponse.error.message == "Model operations worker is unavailable.")
        #expect(cardResponse.ok == false)
        #expect(cardResponse.error.code == "unavailable")
        #expect(cardResponse.error.message == "Model operations worker is unavailable.")
    }

    @Test("execute normalizes worker-declared hub op failures")
    func executeNormalizesWorkerDeclaredHubOpFailures() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubSearchResponse({
            var response = Melix_Worker_V1_SearchHubModelsResponse()
            response.ok = false
            return response
        }())
        await modelOpsClient.setHubModelCardResponse({
            var response = Melix_Worker_V1_GetHubModelCardResponse()
            response.ok = false
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let searchResponse = try await service.execute(
            makeSearchHubModelsRequest(query: "qwen", pageSize: 5, cursor: "", mlxOnly: true)
        )
        let cardResponse = try await service.execute(
            makeGetHubModelCardRequest(repoID: "mlx-community/Qwen2.5-7B-Instruct-4bit")
        )

        #expect(searchResponse.ok == false)
        #expect(searchResponse.error.code == "unknown")
        #expect(searchResponse.error.message == "Hub search failed.")
        #expect(cardResponse.ok == false)
        #expect(cardResponse.error.code == "unknown")
        #expect(cardResponse.error.message == "Hub model card request failed.")
    }

    @Test("execute returns unavailable when hub worker requests throw")
    func executeReturnsUnavailableWhenHubWorkerRequestsThrow() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubSearchError(WorkerClientError.unavailable)
        await modelOpsClient.setHubModelCardError(WorkerClientError.unavailable)
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let searchResponse = try await service.execute(
            makeSearchHubModelsRequest(query: "qwen", pageSize: 5, cursor: "", mlxOnly: true)
        )
        let cardResponse = try await service.execute(
            makeGetHubModelCardRequest(repoID: "mlx-community/Qwen2.5-7B-Instruct-4bit")
        )

        #expect(searchResponse.ok == false)
        #expect(searchResponse.error.code == "unavailable")
        #expect(searchResponse.error.message.contains("Hub search worker request failed"))
        #expect(cardResponse.ok == false)
        #expect(cardResponse.error.code == "unavailable")
        #expect(cardResponse.error.message.contains("Hub model card worker request failed"))
    }

    @Test("execute handles ops.run_bench through the model-operations worker")
    func executeHandlesOpsRunBenchThroughTheModelOperationsWorker() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-report.md").path
        let evidencePath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-run-evidence.json").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.progress = Melix_Worker_V1_BenchProgress()
                event.progress.suite = "smoke"
                event.progress.pct = 0.5
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.metric = Melix_Worker_V1_BenchMetric()
                event.metric.name = "bench.smoke.ttft_ms"
                event.metric.value = 24.45
                event.metric.unit = "ms"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
                event.completed.evidencePath = evidencePath
                return event
            }(),
        ])
        let textClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(modelID: "melix-dev-text"))
        let lastRequest = try #require(await modelOpsClient.lastBenchRequest)
        let snapshot = try await service.execute(makeMetricsRequest())

        #expect(response.ok)
        #expect(lastRequest.suites == ["smoke", "latency"])
        #expect(lastRequest.parameters["require_live_model"] == nil)
        #expect(response.ops.reportPath == reportPath)
        #expect(response.ops.evidencePath == evidencePath)
        #expect(response.ops.reportMarkdown.contains("Melix Bench"))
        #expect(response.ops.metrics.values["bench.smoke.ttft_ms"] == 24.45)
        #expect(response.ops.benchmarkJob.schemaVersion == "melix.serving_benchmark_job.v1")
        #expect(response.ops.benchmarkJob.jobID == "bench-123")
        #expect(response.ops.benchmarkJob.modelID == "melix-dev-text")
        #expect(response.ops.benchmarkJob.suites == ["smoke", "latency"])
        #expect(response.ops.benchmarkJob.status == "completed")
        #expect(response.ops.benchmarkResults.count == 1)
        #expect(response.ops.benchmarkResults[0].schemaVersion == "melix.serving_benchmark_result.v1")
        #expect(response.ops.benchmarkResults[0].jobID == "bench-123")
        #expect(response.ops.benchmarkResults[0].suite == "smoke")
        #expect(response.ops.benchmarkResults[0].metrics.count == 1)
        #expect(response.ops.benchmarkResults[0].metrics[0].name == "bench.smoke.ttft_ms")
        #expect(response.ops.benchmarkResults[0].metrics[0].unit == "ms")
        #expect(response.ops.benchmarkResults[0].metrics[0].value == 24.45)
        #expect(response.ops.benchmarkResults[0].evidencePath == evidencePath)
        #expect(snapshot.ops.metrics.values["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("execute forwards canonical bench request fields to the worker request")
    func executeForwardsCanonicalBenchRequestFieldsToTheWorkerRequest() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-canonical-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-canonical"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
                return event
            }(),
        ])
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        _ = try await service.execute(
            makeRunBenchRequest(
                contextLengths: [4096, 1024],
                batchSizes: [4, 2]
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(lastRequest.contextLengths == [1024, 4096])
        #expect(lastRequest.generationLength == 128)
        #expect(lastRequest.batchSizes == [2, 4])
        #expect(lastRequest.repeats == 3)
        #expect(lastRequest.cacheProfile == "partial_prefix")
        #expect(lastRequest.reasoningMode == "enabled")
        #expect(lastRequest.structuredOutputMode == "json_schema")
    }

    @Test("execute handles ops.run_bench_matrix through the model-operations worker")
    func executeHandlesOpsRunBenchMatrixThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchMatrixResponse(
            makeBenchmarkMatrixResponse(jobID: "bench-matrix-123", modelID: "melix-dev-text")
        )
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchMatrixRequest())
        let lastRequest = try #require(await modelOpsClient.lastBenchMatrixRequest)

        #expect(response.ok)
        #expect(lastRequest.modelHandle == "melix-dev-text::explicit")
        #expect(lastRequest.suiteIds == ["smoke"])
        #expect(lastRequest.requests == 24)
        #expect(response.ops.benchmarkMatrixJob.jobID == "bench-matrix-123")
        #expect(response.ops.benchmarkMatrixJob.benchmarkMode == "matrix")
        #expect(response.ops.benchmarkMatrixSummaryRows.count == 1)
        #expect(response.ops.benchmarkMatrixSummaryRows[0].ttftMeanMs == 24.45)
    }

    @Test("execute forwards canonical bench matrix request fields to the worker request")
    func executeForwardsCanonicalBenchMatrixRequestFieldsToTheWorkerRequest() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchMatrixResponse(
            makeBenchmarkMatrixResponse(jobID: "bench-matrix-canonical", modelID: "melix-dev-text")
        )
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        _ = try await service.execute(
            makeRunBenchMatrixRequest(
                suites: ["latency", "smoke"],
                contextLengths: [4096, 1024],
                generationLengths: [256, 128],
                batchSizes: [4, 2],
                cacheProfiles: ["warm", "cold"],
                reasoningModes: ["enabled", "disabled"],
                structuredOutputModes: ["json_schema", "plain_text"],
                concurrencyLevels: [8, 1],
                repeats: 1,
                requests: 0,
                durationSeconds: 30,
                allowLargeMatrix: true
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastBenchMatrixRequest)

        #expect(lastRequest.suiteIds == ["latency", "smoke"])
        #expect(lastRequest.contextLengths == [1024, 4096])
        #expect(lastRequest.generationLengths == [128, 256])
        #expect(lastRequest.batchSizes == [2, 4])
        #expect(lastRequest.cacheProfiles == ["cold", "warm"])
        #expect(lastRequest.reasoningModes == ["disabled", "enabled"])
        #expect(lastRequest.structuredOutputModes == ["json_schema", "plain_text"])
        #expect(lastRequest.concurrencyLevels == [1, 8])
        #expect(lastRequest.repeats == 1)
        #expect(lastRequest.requests == 0)
        #expect(lastRequest.durationSeconds == 30)
        #expect(lastRequest.allowLargeMatrix)
    }

    @Test("execute rejects ops.run_bench_matrix when load budget is missing")
    func executeRejectsOpsRunBenchMatrixWhenLoadBudgetIsMissing() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchMatrixRequest(requests: 0, durationSeconds: 0)
        )

        #expect(response.ok == false)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("Exactly one of requests or duration_seconds"))
        #expect(await modelOpsClient.lastBenchMatrixRequest == nil)
    }

    @Test("execute rejects ops.run_bench_matrix when repeats fall below the product limit")
    func executeRejectsOpsRunBenchMatrixWhenRepeatsFallBelowTheProductLimit() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchMatrixRequest(repeats: 0, requests: 4)
        )

        #expect(response.ok == false)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("Benchmark repeats"))
        #expect(await modelOpsClient.lastBenchMatrixRequest == nil)
    }

    @Test("execute rejects ops.run_bench_matrix when repeats exceed the product limit")
    func executeRejectsOpsRunBenchMatrixWhenRepeatsExceedTheProductLimit() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchMatrixRequest(repeats: 21, requests: 4)
        )

        #expect(response.ok == false)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("Benchmark repeats"))
        #expect(await modelOpsClient.lastBenchMatrixRequest == nil)
    }

    @Test("execute rejects bench matrix validation failures for required dimensions and cache profiles")
    func executeRejectsBenchMatrixValidationFailuresForRequiredDimensionsAndCacheProfiles() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        var request = makeRunBenchMatrixRequest(suites: [])
        var response = try await service.execute(request)
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("matrix benchmark suite"))

        request = makeRunBenchMatrixRequest(contextLengths: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("context length"))

        request = makeRunBenchMatrixRequest(generationLengths: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("generation length"))

        request = makeRunBenchMatrixRequest(batchSizes: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("batch size"))

        request = makeRunBenchMatrixRequest(cacheProfiles: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("cache profile"))

        request = makeRunBenchMatrixRequest(reasoningModes: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("reasoning mode"))

        request = makeRunBenchMatrixRequest(structuredOutputModes: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("structured output mode"))

        request = makeRunBenchMatrixRequest(concurrencyLevels: [])
        response = try await service.execute(request)
        #expect(response.error.message.contains("concurrency level"))

        request = makeRunBenchMatrixRequest(cacheProfiles: ["ancient"])
        response = try await service.execute(request)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("partial_prefix"))
    }

    @Test("execute rejects bench matrix targets that are unsupported or too large")
    func executeRejectsBenchMatrixTargetsThatAreUnsupportedOrTooLarge() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        var response = try await service.execute(makeRunBenchMatrixRequest(modelID: "melix-dev-image"))
        #expect(!response.ok)
        #expect(response.error.code == "unsupported_task_family")
        #expect(response.error.message.contains("text-generation, image-to-text, and image-text-to-text"))

        response = try await service.execute(
            makeRunBenchMatrixRequest(
                suites: ["latency", "smoke"],
                contextLengths: [512, 1024, 2048, 4096],
                generationLengths: [64, 128, 256, 512],
                batchSizes: [1, 2, 4, 8],
                cacheProfiles: ["cold", "warm"],
                reasoningModes: ["disabled", "enabled"],
                structuredOutputModes: ["json_schema", "plain_text"],
                concurrencyLevels: [1, 2]
            )
        )
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("allow_large_matrix"))
    }

    @Test("execute maps bench matrix availability resolution and worker failures")
    func executeMapsBenchMatrixAvailabilityResolutionAndWorkerFailures() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")

        let unavailableService = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(defaultTextClient: NullWorkerClient())
        )
        var response = try await unavailableService.execute(makeRunBenchMatrixRequest())
        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("worker is unavailable"))

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        response = try await service.execute(makeRunBenchMatrixRequest(modelID: "missing-model"))
        #expect(!response.ok)
        #expect(response.error.code == "not_found")
        #expect(response.error.message.contains("missing-model"))

        let unloadedCatalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let unloadedService = ControlPlaneService(
            modelCatalog: unloadedCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )
        response = try await unloadedService.execute(makeRunBenchMatrixRequest())
        #expect(!response.ok)
        #expect(response.error.code == "not_found")
        #expect(response.error.message.contains("No loaded benchmark target is available for melix-dev-text."))

        await modelOpsClient.setBenchMatrixError(WorkerClientError.unavailable)
        response = try await service.execute(makeRunBenchMatrixRequest())
        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Matrix benchmark worker request failed"))
    }

    @Test("execute routes ops.run_bench to the explicit requested model when model_id is provided")
    func executeRoutesOpsRunBenchToExplicitRequestedModel() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-explicit-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-explicit"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
                return event
            }(),
        ])
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(modelID: "melix-dev-text"))
        let lastRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastRequest.modelHandle == "melix-dev-text::explicit")
        #expect(lastRequest.parameters["require_live_model"] == nil)
        #expect(response.ops.benchmarkJob.jobID == "bench-explicit")
        #expect(response.ops.benchmarkJob.modelID == "melix-dev-text")
    }

    @Test("execute syncs registry models before ops.run_bench resolves an explicit discovered model")
    func executeSyncsRegistryModelsBeforeRunBenchResolution() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-registry-sync-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let registryModelID = "Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot"
        let registrySourceRepo = "Brooooooklyn/Qwen3.5-9B-unsloth-mlx"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": registryModelID,
                    "model_path": "/tmp/registry-root/Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot",
                    "model_kind": "text",
                    "quant_profile_id": "snapshot",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/registry-root",
                        "melix.registry_relative_path": "Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot",
                        "melix.model_path": "/tmp/registry-root/Brooooooklyn/Qwen3.5-9B-unsloth-mlx/snapshot",
                        "melix.source_repo": registrySourceRepo,
                        "melix.task_kind": "text-generation",
                    ],
                ],
            ]
        )

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-registry-sync", reportPath: reportPath))

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedChatWorkerClient(events: []),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(
                modelID: registryModelID,
                suites: ["smoke"],
                contextLengths: [256],
                generationLength: 8,
                batchSizes: [1],
                repeats: 1,
                cacheProfile: "cold",
                reasoningMode: "disabled",
                structuredOutputMode: "plain_text"
            )
        )
        let lastConvertRequest = try #require(await modelOpsClient.lastConvertRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastConvertRequest.sourceModel == "melix-dev-text")
        #expect(lastConvertRequest.ext["operation"] == "registry_snapshot")
        #expect(lastBenchRequest.modelHandle == registryModelID)
        #expect(lastBenchRequest.taskKind == "text-generation")
        #expect(lastBenchRequest.sourceRepo == registrySourceRepo)
        #expect(response.ops.benchmarkJob.jobID == "bench-registry-sync")
        #expect(response.ops.benchmarkJob.modelID == registryModelID)
    }

    @Test("execute tags catalog hub repo benchmark targets with hub live-model source")
    func executeTagsCatalogHubRepoBenchmarkTargetsWithHubLiveModelSource() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-hub-catalog-report.md").path
        try "# Hub Catalog Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        var hubModel = ModelCatalog.devTextModel()
        hubModel.modelID = "local-qwen-hub"
        hubModel.settings.ext["melix.source_kind"] = "hub_repo"
        hubModel.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        hubModel.settings.ext["melix.task_kind"] = "text-generation"

        let catalog = ModelCatalog(seedModels: [hubModel])
        _ = await catalog.loadModel(id: "local-qwen-hub", dispatchHandle: "local-qwen-hub::hub")
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-hub-catalog", reportPath: reportPath))
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(
                modelID: "local-qwen-hub",
                suites: ["smoke"],
                contextLengths: [256],
                generationLength: 8,
                batchSizes: [1],
                repeats: 1,
                cacheProfile: "cold",
                reasoningMode: "disabled",
                structuredOutputMode: "plain_text"
            )
        )
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastBenchRequest.parameters["require_live_model"] == "true")
        #expect(lastBenchRequest.parameters["live_model_source"] == "hub_repo")
        #expect(lastBenchRequest.sourceRepo == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("execute does not require live-model evidence for local-path benchmark targets")
    func executeDoesNotRequireLiveModelEvidenceForLocalPathBenchmarkTargets() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-local-path-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let localModelID = "melix-dev-qwen-local"
        let localModelPath = "/tmp/melix-local-model"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": localModelID,
                    "model_path": localModelPath,
                    "model_kind": "text",
                    "quant_profile_id": "local",
                    "max_context": 32768,
                    "ext": [
                        "melix.source_kind": "local_path",
                        "melix.model_path": localModelPath,
                        "melix.source_repo": localModelPath,
                        "melix.task_kind": "text-generation",
                    ],
                ],
            ]
        )

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-local-path", reportPath: reportPath))

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedChatWorkerClient(events: []),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(modelID: localModelID))
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastBenchRequest.sourceRepo == localModelPath)
        #expect(lastBenchRequest.parameters["require_live_model"] == nil)
    }

    @Test("execute does not tag local catalog benchmark targets as live model evidence")
    func executeDoesNotTagLocalCatalogBenchmarkTargetsAsLiveModelEvidence() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-local-catalog-report.md").path
        try "# Local Catalog Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        var localModel = ModelCatalog.devTextModel()
        localModel.modelID = "mlx-community/local-cache-model"
        localModel.settings.ext["melix.source_kind"] = "local_path"
        localModel.settings.ext["melix.model_path"] = "/tmp/melix/local-cache-model"
        localModel.settings.ext["melix.task_kind"] = "text-generation"

        let catalog = ModelCatalog(seedModels: [localModel])
        _ = await catalog.loadModel(id: "mlx-community/local-cache-model", dispatchHandle: "local-cache::loaded")
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-local-catalog", reportPath: reportPath))
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(
                modelID: "mlx-community/local-cache-model",
                suites: ["smoke"],
                contextLengths: [256],
                generationLength: 8,
                batchSizes: [1],
                repeats: 1,
                cacheProfile: "cold",
                reasoningMode: "disabled",
                structuredOutputMode: "plain_text"
            )
        )
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastBenchRequest.parameters["require_live_model"] == nil)
        #expect(lastBenchRequest.parameters["live_model_source"] == nil)
        #expect(lastBenchRequest.sourceRepo == "/tmp/melix/local-cache-model")
    }

    @Test("execute allows deterministic runtime evidence override for dev benchmark targets")
    func executeAllowsDeterministicRuntimeEvidenceOverrideForDevBenchmarkTargets() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-dev-override-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-dev-override", reportPath: reportPath))

        var model = ModelCatalog.devTextModel()
        model.settings.ext["melix.source_repo"] = "mlx-community/Qwen3-dev-fixture"
        let catalog = ModelCatalog(seedModels: [model])
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(
                modelID: "melix-dev-text",
                parameters: ["allow_deterministic_runtime": "true"]
            )
        )
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastBenchRequest.sourceRepo == "mlx-community/Qwen3-dev-fixture")
        #expect(lastBenchRequest.parameters["allow_deterministic_runtime"] == "true")
        #expect(lastBenchRequest.parameters["require_live_model"] == nil)
    }

    @Test("execute imports a direct Hugging Face benchmark target and routes gemma4 to the VLM benchmark path")
    func executeImportsDirectHFBenchmarkTargetForGemma4() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-gemma4-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse({
            var response = Melix_Worker_V1_GetHubModelCardResponse()
            response.ok = true
            response.card = Melix_Worker_V1_HubModelCard()
            response.card.repoID = "unsloth/gemma-4-E4B-it-MLX-8bit"
            response.card.author = "unsloth"
            response.card.modelName = "gemma-4-E4B-it-MLX-8bit"
            response.card.pipelineTag = "image-text-to-text"
            response.card.mlxCompatible = true
            response.card.tags = ["gemma4", "image-text-to-text", "mlx"]
            response.card.siblingFiles = [
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "model.safetensors.index.json",
            ]
            return response
        }())
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-gemma4"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
                return event
            }(),
        ])
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(
                hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                parameters: ["allow_deterministic_runtime": "true"]
            )
        )
        let lastCardRequest = try #require(await modelOpsClient.lastHubModelCardRequest)
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastCardRequest.repoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(lastLoadRequest.model.modelID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(lastLoadRequest.model.modelKind == "vlm")
        #expect(lastLoadRequest.model.ext["melix.capability.route_kind"] == "python_vlm")
        #expect(lastLoadRequest.model.ext["melix.benchmark.task_kind"] == "text-generation")
        #expect(lastLoadRequest.model.ext["melix.vlm.execution_mode"] == "text_backed")
        #expect(lastLoadRequest.model.ext["vision_family_id"] == "gemma4-v1")
        #expect(lastBenchRequest.taskKind == "text-generation")
        #expect(lastBenchRequest.sourceRepo == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(lastBenchRequest.parameters["allow_deterministic_runtime"] == "true")
        #expect(lastBenchRequest.parameters["require_live_model"] == "true")
        #expect(lastBenchRequest.parameters["live_model_source"] == "hf_repo")
        #expect(response.ops.benchmarkJob.modelID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(response.ops.benchmarkJob.taskKind == "text-generation")
        #expect(response.ops.benchmarkJob.sourceRepo == "unsloth/gemma-4-E4B-it-MLX-8bit")
    }

    @Test("execute imports Qwen3.5 benchmark targets with missing pipeline tag as text generation")
    func executeImportsQwen35BenchmarkTargetWithMissingPipelineTag() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-qwen35-report.md").path
        try "# Qwen3.5 Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/Qwen3.5-9B-MLX-8bit",
                modelName: "Qwen3.5-9B-MLX-8bit",
                pipelineTag: "",
                tags: ["mlx", "qwen3_5", "vision-language-model"],
                siblingFiles: [
                    "config.json",
                    "processor_config.json",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "model.safetensors.index.json",
                ]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-qwen35", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/Qwen3.5-9B-MLX-8bit")
        )
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastLoadRequest.model.modelID == "mlx-community/Qwen3.5-9B-MLX-8bit")
        #expect(lastLoadRequest.model.modelKind == "text")
        #expect(lastLoadRequest.model.ext["melix.task_kind"] == "text-generation")
        #expect(lastLoadRequest.model.ext["melix.capability.route_kind"] == "python_text_compatibility")
        #expect(lastBenchRequest.taskKind == "text-generation")
        #expect(lastBenchRequest.sourceRepo == "mlx-community/Qwen3.5-9B-MLX-8bit")
        #expect(response.ops.benchmarkJob.taskKind == "text-generation")
    }

    @Test("execute imports Qwen3.6 benchmark targets with multimodal-looking metadata as text generation")
    func executeImportsQwen36BenchmarkTargetWithProcessorMetadataAsText() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-qwen36-report.md").path
        try "# Qwen3.6 Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit",
                modelName: "Qwen3.6-35B-A3B-UD-MLX-4bit",
                pipelineTag: "image-text-to-text",
                tags: ["mlx", "qwen3.6", "vision-language-model"],
                siblingFiles: [
                    "config.json",
                    "processor_config.json",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "model.safetensors.index.json",
                ]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-qwen36", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit")
        )
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastLoadRequest.model.modelID == "unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit")
        #expect(lastLoadRequest.model.modelKind == "text")
        #expect(lastLoadRequest.model.ext["melix.task_kind"] == "text-generation")
        #expect(lastLoadRequest.model.ext["melix.capability.route_kind"] == "python_text_compatibility")
        #expect(lastLoadRequest.model.ext["melix.benchmark.task_kind"] == nil)
        #expect(lastLoadRequest.model.ext["melix.vlm.execution_mode"] == nil)
        #expect(lastBenchRequest.taskKind == "text-generation")
        #expect(lastBenchRequest.sourceRepo == "unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit")
        #expect(response.ops.benchmarkJob.taskKind == "text-generation")
    }

    @Test("execute resolves Qwen3.6 any-to-any benchmark targets as text generation")
    func executeImportsQwen36AnyToAnyBenchmarkTargetAsText() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-qwen36-any-report.md").path
        try "# Qwen3.6 Any-to-Any Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                modelName: "Qwen3.6-35B-A3B-4bit",
                pipelineTag: "any-to-any",
                tags: ["mlx", "qwen3_6", "multimodal"],
                siblingFiles: [
                    "config.json",
                    "processor_config.json",
                    "tokenizer.json",
                    "model.safetensors.index.json",
                ]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-qwen36-any", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit")
        )
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastLoadRequest.model.modelKind == "text")
        #expect(lastBenchRequest.taskKind == "text-generation")
        #expect(response.ops.benchmarkJob.taskKind == "text-generation")
    }

    @Test("execute prefers a matching Hugging Face cache snapshot before importing a direct benchmark target")
    func executePrefersMatchingHFCacheSnapshotBeforeDirectBenchmarkImport() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-hf-cache-report.md").path
        try "# HF Cache Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let repoID = "unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit"
        let snapshotModelID = "hf-cache/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/abc123"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": snapshotModelID,
                    "model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/abc123",
                    "model_kind": "text",
                    "quant_profile_id": "mlx-4bit",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "hf-cache",
                        "melix.registry_root_path": "/tmp/huggingface/hub",
                        "melix.registry_relative_path": "models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/abc123",
                        "melix.source_kind": "hf_cache_snapshot",
                        "melix.hf_repo_id": repoID,
                        "melix.source_repo": repoID,
                        "melix.model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/abc123",
                        "melix.task_kind": "text-generation",
                    ],
                ],
                [
                    "model_id": repoID,
                    "model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/exact",
                    "model_kind": "text",
                    "quant_profile_id": "mlx-4bit",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "hf-cache",
                        "melix.registry_root_path": "/tmp/huggingface/hub",
                        "melix.registry_relative_path": "models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/exact",
                        "melix.source_kind": "hf_cache_snapshot",
                        "melix.model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/exact",
                        "melix.task_kind": "text-generation",
                    ],
                ],
                [
                    "model_id": "hf-cache/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/vlm-text-backed",
                    "model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/vlm-text-backed",
                    "model_kind": "vlm",
                    "quant_profile_id": "mlx-4bit",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "hf-cache",
                        "melix.registry_root_path": "/tmp/huggingface/hub",
                        "melix.source_kind": "hf_cache_snapshot",
                        "melix.hf_repo_id": repoID,
                        "melix.source_repo": repoID,
                        "melix.model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/vlm-text-backed",
                        "melix.task_kind": "text-generation",
                    ],
                ],
                [
                    "model_id": "hf-cache/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/vlm",
                    "model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/vlm",
                    "model_kind": "vlm",
                    "quant_profile_id": "mlx-4bit",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "hf-cache",
                        "melix.registry_root_path": "/tmp/huggingface/hub",
                        "melix.source_kind": "hf_cache_snapshot",
                        "melix.hf_repo_id": repoID,
                        "melix.source_repo": repoID,
                        "melix.model_path": "/tmp/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit/snapshots/vlm",
                        "melix.task_kind": "image-text-to-text",
                    ],
                ],
                [
                    "model_id": "hf-cache/other/snapshots/not-this-repo",
                    "model_path": "/tmp/huggingface/hub/models--other--Model/snapshots/not-this-repo",
                    "model_kind": "text",
                    "quant_profile_id": "mlx-4bit",
                    "max_context": 4096,
                    "ext": [
                        "melix.registry_root_id": "hf-cache",
                        "melix.registry_root_path": "/tmp/huggingface/hub",
                        "melix.source_kind": "hf_cache_snapshot",
                        "melix.hf_repo_id": "mlx-community/Other-Model",
                        "melix.source_repo": "mlx-community/Other-Model",
                        "melix.model_path": "/tmp/huggingface/hub/models--other--Model/snapshots/not-this-repo",
                        "melix.task_kind": "text-generation",
                    ],
                ],
            ]
        )

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = manifestJSON
                return event
            }(),
        ])
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: repoID,
                modelName: "Qwen3.6-35B-A3B-UD-MLX-4bit",
                pipelineTag: "image-text-to-text",
                tags: ["mlx", "qwen3.6", "vision-language-model"],
                siblingFiles: ["config.json", "processor_config.json", "tokenizer.json"]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-hf-cache", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: repoID)
        )
        let convertRequest = try #require(await modelOpsClient.lastConvertRequest)
        let loadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let benchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(convertRequest.ext["melix.registry_rescan"] == "true")
        #expect(await modelOpsClient.lastHubModelCardRequest == nil)
        #expect(loadRequest.model.modelID == snapshotModelID)
        #expect(loadRequest.model.modelKind == "text")
        #expect(benchRequest.modelHandle == snapshotModelID)
        #expect(benchRequest.taskKind == "text-generation")
        #expect(benchRequest.sourceRepo == repoID)
        #expect(benchRequest.parameters["live_model_source"] == "hf_cache_snapshot")
        #expect(response.ops.benchmarkJob.modelID == snapshotModelID)
        #expect(response.ops.benchmarkJob.taskKind == "text-generation")
    }

    @Test("execute surfaces direct benchmark worker load rejection instead of masking it as not found")
    func executeSurfacesDirectBenchmarkWorkerLoadRejection() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                modelName: "Qwen3.6-35B-A3B-4bit",
                pipelineTag: "text-generation",
                tags: ["mlx", "qwen3.6"],
                siblingFiles: ["config.json", "tokenizer.json", "model.safetensors.index.json"]
            )
        )
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        await pythonRuntimeClient.setLoadModelResponse({
            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = false
            response.error.code = "memory_budget_exceeded"
            response.error.message = "Required memory exceeds available headroom."
            response.error.details = [
                "required_bytes": "42000000000",
                "headroom_bytes": "16000000000",
            ]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "memory_budget_exceeded")
        #expect(response.error.message == "Required memory exceeds available headroom.")
        #expect(response.error.details["required_bytes"] == "42000000000")
        #expect(await modelOpsClient.lastBenchRequest == nil)
    }

    @Test("execute retries direct benchmark load with a Hugging Face cache snapshot discovered after hub import fails")
    func executeRetriesDirectBenchmarkLoadWithHFCacheSnapshotAfterHubImportFailure() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-hf-cache-retry-report.md").path
        try "# HF Cache Retry Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let repoID = "mlx-community/Qwen3.6-35B-A3B-4bit"
        let snapshotModelID = "hf-cache/mlx-community/Qwen3.6-35B-A3B-4bit/snapshots/recovered"
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": snapshotModelID,
                    "model_path": "/tmp/huggingface/hub/models--mlx-community--Qwen3.6-35B-A3B-4bit/snapshots/recovered",
                    "model_kind": "text",
                    "quant_profile_id": "mlx-4bit",
                    "max_context": 32768,
                    "ext": [
                        "melix.registry_root_id": "hf-cache",
                        "melix.registry_root_path": "/tmp/huggingface/hub",
                        "melix.registry_relative_path": "models--mlx-community--Qwen3.6-35B-A3B-4bit/snapshots/recovered",
                        "melix.source_kind": "hf_cache_snapshot",
                        "melix.hf_repo_id": repoID,
                        "melix.source_repo": repoID,
                        "melix.model_path": "/tmp/huggingface/hub/models--mlx-community--Qwen3.6-35B-A3B-4bit/snapshots/recovered",
                        "melix.task_kind": "text-generation",
                    ],
                ],
            ]
        )
        let manifestEvent = {
            var event = Melix_Worker_V1_ConvertModelEvent()
            event.manifest = Melix_Worker_V1_ConvertManifest()
            event.manifest.manifestJson = manifestJSON
            return event
        }()

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEventBatches([[], [manifestEvent]])
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: repoID,
                modelName: "Qwen3.6-35B-A3B-4bit",
                pipelineTag: "text-generation",
                tags: ["mlx", "qwen3.6"],
                siblingFiles: ["config.json", "tokenizer.json", "model.safetensors.index.json"]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-hf-cache-retry", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        await pythonRuntimeClient.setLoadModelResponses([
            {
                var response = Melix_Worker_V1_LoadModelResponse()
                response.ok = false
                response.error.code = "load_failed"
                response.error.message = "Hub import path did not produce a local runtime handle."
                return response
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: pythonRuntimeClient,
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(hfRepoID: repoID))
        let loadRequests = await pythonRuntimeClient.loadModelRequests
        let benchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(await modelOpsClient.convertRequests.count == 2)
        #expect(loadRequests.map { $0.model.modelID } == [repoID, snapshotModelID])
        #expect(benchRequest.modelHandle == snapshotModelID)
        #expect(benchRequest.taskKind == "text-generation")
        #expect(benchRequest.parameters["live_model_source"] == "hf_cache_snapshot")
        #expect(response.ops.benchmarkJob.modelID == snapshotModelID)
    }

    @Test("execute surfaces missing runtime cache for benchmark targets before worker load")
    func executeSurfacesMissingRuntimeCacheForBenchmarkTargetsBeforeWorkerLoad() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.ext["melix.model_path_missing"] = "true"
        model.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3.6-35B-A3B-4bit"
        let catalog = ModelCatalog(seedModels: [model])
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(modelID: "melix-dev-text"))

        #expect(response.ok == false)
        #expect(response.error.code == ModelRuntimeAvailability.missingRuntimeCacheCode)
        #expect(response.error.message == ModelRuntimeAvailability.missingRuntimeCacheMessage)
        #expect(response.error.details["model_id"] == "melix-dev-text")
        #expect(await pythonRuntimeClient.lastLoadModelRequest == nil)
        #expect(await modelOpsClient.lastBenchRequest == nil)
    }

    @Test("execute infers missing pipeline tags from explicit modality metadata")
    func executeInfersMissingPipelineTagsFromExplicitModalityMetadata() async throws {
        let cases: [(repoID: String, modelName: String, tags: [String], siblingFiles: [String], expectedTaskKind: String, expectedModelKind: String)] = [
            (
                repoID: "google/paligemma2-3b-ft-docci-448",
                modelName: "paligemma2-3b-ft-docci-448",
                tags: ["mlx", "image_to_text", "paligemma"],
                siblingFiles: ["config.json", "processor_config.json", "tokenizer.json"],
                expectedTaskKind: "image-to-text",
                expectedModelKind: "vlm"
            ),
            (
                repoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                modelName: "gemma-4-E4B-it-MLX-8bit",
                tags: ["mlx", "vision-language-model", "gemma4"],
                siblingFiles: ["config.json", "processor_config.json", "tokenizer.json", "model.safetensors.index.json"],
                expectedTaskKind: "image-text-to-text",
                expectedModelKind: "vlm"
            ),
            (
                repoID: "mlx-community/FLUX.1-schnell-4bit",
                modelName: "FLUX.1-schnell-4bit",
                tags: ["mlx", "text-to-image"],
                siblingFiles: ["config.json"],
                expectedTaskKind: "text-to-image",
                expectedModelKind: "image"
            ),
            (
                repoID: "mlx-community/sdxl-edit",
                modelName: "sdxl-edit",
                tags: ["mlx", "image-text-to-image"],
                siblingFiles: ["config.json"],
                expectedTaskKind: "image-text-to-image",
                expectedModelKind: "image"
            ),
        ]

        for testCase in cases {
            let reportPath = URL(fileURLWithPath: NSTemporaryDirectory())
                .appendingPathComponent("melix-bench-missing-pipeline-\(testCase.expectedTaskKind).md")
                .path
            try "# Missing Pipeline Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

            let modelOpsClient = ScriptedModelOperationsWorkerClient()
            await modelOpsClient.setHubModelCardResponse(
                makeBenchmarkHubModelCardResponse(
                    repoID: testCase.repoID,
                    modelName: testCase.modelName,
                    pipelineTag: " ",
                    tags: testCase.tags,
                    siblingFiles: testCase.siblingFiles
                )
            )
            await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-\(testCase.expectedTaskKind)", reportPath: reportPath))
            let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
            let service = ControlPlaneService(
                modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
                workerRegistry: WorkerRegistry(
                    defaultTextClient: NullWorkerClient(),
                    pythonCompatibilityClient: pythonRuntimeClient,
                    modelOperationsClient: modelOpsClient
                )
            )

            let response = try await service.execute(
                makeRunBenchRequest(hfRepoID: testCase.repoID)
            )
            let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
            let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

            #expect(response.ok)
            #expect(lastLoadRequest.model.modelKind == testCase.expectedModelKind)
            #expect(lastBenchRequest.taskKind == testCase.expectedTaskKind)
            #expect(response.ops.benchmarkJob.taskKind == testCase.expectedTaskKind)
        }
    }

    @Test("execute imports image-to-text benchmark targets as OCR-capable VLM models")
    func executeImportsDirectImageToTextBenchmarkTarget() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-ocr-report.md").path
        try "# OCR Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "google/paligemma2-3b-ft-docci-448",
                modelName: "paligemma2-3b-ft-docci-448",
                pipelineTag: "image-to-text",
                tags: ["paligemma", "image-to-text", "mlx"],
                siblingFiles: [
                    "config.json",
                    "processor_config.json",
                    "tokenizer.json",
                ]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-ocr", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "google/paligemma2-3b-ft-docci-448")
        )
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastLoadRequest.model.modelKind == "vlm")
        #expect(lastLoadRequest.model.ext["vision_family_id"] == "paligemma-v1")
        #expect(lastLoadRequest.model.ext["vision_prompt_profile_id"] == "paligemma-caption-v1")
        #expect(lastLoadRequest.model.ext["vision_tokenization_mode"] == "prefix")
        #expect(lastLoadRequest.model.ext["vision_supports_tool_calls"] == "false")
        #expect(lastBenchRequest.taskKind == "image-to-text")
        #expect(lastBenchRequest.sourceRepo == "google/paligemma2-3b-ft-docci-448")
        #expect(lastBenchRequest.parameters["require_live_model"] == "true")
        #expect(response.ops.benchmarkJob.taskKind == "image-to-text")
    }

    @Test("execute imports text-to-image benchmark targets through the image route")
    func executeImportsDirectTextToImageBenchmarkTarget() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-t2i-report.md").path
        try "# T2I Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/FLUX.1-schnell-4bit",
                modelName: "FLUX.1-schnell-4bit",
                pipelineTag: "text-to-image",
                tags: ["flux", "text-to-image", "mlx"],
                siblingFiles: ["config.json"]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-t2i", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/FLUX.1-schnell-4bit")
        )
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastLoadRequest.model.modelKind == "image")
        #expect(lastLoadRequest.model.ext["melix.image.backend_id"] == "deterministic")
        #expect(lastLoadRequest.model.ext["melix.image.task_kind"] == "text-to-image")
        #expect(lastBenchRequest.taskKind == "text-to-image")
        #expect(response.ops.benchmarkJob.taskKind == "text-to-image")
    }

    @Test("execute imports supported gemma4 any-to-any evaluation targets as image-text-to-text VLM models")
    func executeImportsGemma4AnyToAnyEvaluationTarget() async throws {
        let importedEvalClient = ScriptedModelOperationsWorkerClient()
        await importedEvalClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/gemma-4-e2b-it-4bit",
                modelName: "gemma-4-e2b-it-4bit",
                pipelineTag: "any-to-any",
                tags: ["gemma4", "mlx", "vision"],
                siblingFiles: [
                    "config.json",
                    "tokenizer.json",
                    "model.safetensors.index.json",
                ]
            )
        )
        await importedEvalClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job.jobID = "eval-gemma4-any"
            response.job.modelID = "mlx-community/gemma-4-e2b-it-4bit"
            response.job.taskKind = "image-text-to-text"
            response.job.sourceRepo = "mlx-community/gemma-4-e2b-it-4bit"
            response.job.suiteID = "imagenette"
            response.job.datasetID = "imagenette.dev.v1"
            response.job.sampleSize = 1
            response.job.status = "completed"
            return response
        }())
        let importedRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: importedRuntimeClient,
                modelOperationsClient: importedEvalClient
            )
        )

        let response = try await service.execute(
            makeRunEvaluationRequest(
                modelID: "",
                hfRepoID: "mlx-community/gemma-4-e2b-it-4bit",
                suiteID: "imagenette",
                datasetID: "imagenette.dev.v1"
            )
        )
        let loadRequest = try #require(await importedRuntimeClient.lastLoadModelRequest)
        let evalRequest = try #require(await importedEvalClient.lastEvaluationRequest)

        #expect(response.ok == true)
        #expect(loadRequest.model.modelKind == "vlm")
        #expect(loadRequest.model.ext["melix.task_kind"] == "image-text-to-text")
        #expect(loadRequest.model.ext["melix.vlm.execution_mode"] == nil)
        #expect(loadRequest.model.ext["vision_family_id"] == "gemma4-v1")
        #expect(evalRequest.taskKind == "image-text-to-text")
        #expect(evalRequest.sourceRepo == "mlx-community/gemma-4-e2b-it-4bit")
        #expect(evalRequest.parameters["require_live_model"] == "true")
        #expect(evalRequest.parameters["live_model_source"] == "hf_repo")
        #expect(response.ops.evaluationJob.taskKind == "image-text-to-text")
    }

    @Test("execute tags catalog hub repo evaluation targets with hub live-model source")
    func executeTagsCatalogHubRepoEvaluationTargetsWithHubLiveModelSource() async throws {
        var hubModel = ModelCatalog.devTextModel()
        hubModel.modelID = "local-eval-qwen-hub"
        hubModel.settings.ext["melix.source_kind"] = "hub_repo"
        hubModel.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        hubModel.settings.ext["melix.task_kind"] = "text-generation"

        let catalog = ModelCatalog(seedModels: [hubModel])
        _ = await catalog.loadModel(id: "local-eval-qwen-hub", dispatchHandle: "local-eval-qwen-hub::hub")
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job.jobID = "eval-hub-catalog"
            response.job.modelID = "local-eval-qwen-hub"
            response.job.taskKind = "text-generation"
            response.job.sourceRepo = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
            response.job.suiteID = "qa_smoke"
            response.job.datasetID = "qa_smoke.dev.v1"
            response.job.sampleSize = 8
            response.job.status = "completed"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunEvaluationRequest(
                modelID: "local-eval-qwen-hub",
                suiteID: "qa_smoke",
                datasetID: "qa_smoke.dev.v1"
            )
        )
        let evalRequest = try #require(await modelOpsClient.lastEvaluationRequest)

        #expect(response.ok)
        #expect(evalRequest.parameters["require_live_model"] == "true")
        #expect(evalRequest.parameters["live_model_source"] == "hub_repo")
        #expect(evalRequest.sourceRepo == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("execute rejects unsupported any-to-any evaluation targets that are not gemma4 vision imports")
    func executeRejectsUnsupportedAnyToAnyEvaluationTarget() async throws {
        let importedEvalClient = ScriptedModelOperationsWorkerClient()
        await importedEvalClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/audio-any-model",
                modelName: "audio-any-model",
                pipelineTag: "any-to-any",
                tags: ["mlx", "audio"],
                siblingFiles: [
                    "config.json",
                    "model.safetensors.index.json",
                ]
            )
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: importedEvalClient
            )
        )

        let response = try await service.execute(
            makeRunEvaluationRequest(
                modelID: "",
                hfRepoID: "mlx-community/audio-any-model",
                suiteID: "imagenette",
                datasetID: "imagenette.dev.v1"
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unsupported_task_family")
        #expect(response.error.message.contains("pipeline_tag=any-to-any"))
    }

    @Test("execute imports image-text-to-image benchmark targets through the image route")
    func executeImportsDirectImageEditBenchmarkTarget() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-edit-report.md").path
        try "# Edit Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/sdxl-edit",
                modelName: "sdxl-edit",
                pipelineTag: "image-text-to-image",
                tags: ["sdxl", "edit", "mlx"],
                siblingFiles: ["config.json"]
            )
        )
        await modelOpsClient.setBenchEvents(makeBenchmarkLifecycleEvents(jobID: "bench-edit", reportPath: reportPath))
        let pythonRuntimeClient = ScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: pythonRuntimeClient,
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/sdxl-edit")
        )
        let lastLoadRequest = try #require(await pythonRuntimeClient.lastLoadModelRequest)
        let lastBenchRequest = try #require(await modelOpsClient.lastBenchRequest)

        #expect(response.ok)
        #expect(lastLoadRequest.model.modelKind == "image")
        #expect(lastLoadRequest.model.ext["melix.image.task_kind"] == "image-text-to-image")
        #expect(lastBenchRequest.taskKind == "image-text-to-image")
        #expect(response.ops.benchmarkJob.taskKind == "image-text-to-image")
    }

    @Test("execute rejects non-MLX benchmark hub targets during direct import")
    func executeRejectsNonMLXBenchmarkHubTargets() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "openai/non-mlx-model",
                modelName: "non-mlx-model",
                pipelineTag: "text-generation",
                mlxCompatible: false
            )
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunBenchRequest(hfRepoID: "openai/non-mlx-model")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unsupported_model_family")
        #expect(response.error.message == "Hub repo openai/non-mlx-model is not MLX-compatible.")
    }

    @Test("execute rejects unsupported direct benchmark task families and surfaces worker failures")
    func executeRejectsUnsupportedBenchmarkTaskFamiliesAndHubFailures() async throws {
        let unsupportedClient = ScriptedModelOperationsWorkerClient()
        await unsupportedClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/image-classifier",
                modelName: "image-classifier",
                pipelineTag: "image-classification"
            )
        )
        let unsupportedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: unsupportedClient
            )
        )

        let unsupportedResponse = try await unsupportedService.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/image-classifier")
        )

        #expect(unsupportedResponse.ok == false)
        #expect(unsupportedResponse.error.code == "unsupported_task_family")
        #expect(unsupportedResponse.error.message.contains("pipeline_tag=image-classification"))

        let missingPipelineClient = ScriptedModelOperationsWorkerClient()
        await missingPipelineClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/metadata-light-model",
                modelName: "metadata-light-model",
                pipelineTag: "",
                tags: ["mlx"],
                siblingFiles: ["config.json"]
            )
        )
        let missingPipelineService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: missingPipelineClient
            )
        )

        let missingPipelineResponse = try await missingPipelineService.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/metadata-light-model")
        )

        #expect(missingPipelineResponse.ok == false)
        #expect(missingPipelineResponse.error.code == "unsupported_task_family")
        #expect(missingPipelineResponse.error.message.contains("pipeline_tag=."))

        let failedClient = ScriptedModelOperationsWorkerClient()
        await failedClient.setHubModelCardError(WorkerClientError.unavailable)
        let failedService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: failedClient
            )
        )

        let failedResponse = try await failedService.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/failing-target")
        )

        #expect(failedResponse.ok == false)
        #expect(failedResponse.error.code == "unavailable")
        #expect(failedResponse.error.message.contains("Hub model card worker request failed"))

        let workerDeclaredFailureClient = ScriptedModelOperationsWorkerClient()
        await workerDeclaredFailureClient.setHubModelCardResponse({
            var response = Melix_Worker_V1_GetHubModelCardResponse()
            response.ok = false
            return response
        }())
        let workerDeclaredFailureService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: workerDeclaredFailureClient
            )
        )

        let workerDeclaredFailureResponse = try await workerDeclaredFailureService.execute(
            makeRunBenchRequest(hfRepoID: "mlx-community/blank-card-error")
        )

        #expect(workerDeclaredFailureResponse.ok == false)
        #expect(workerDeclaredFailureResponse.error.code == "unknown")
        #expect(workerDeclaredFailureResponse.error.message == "Hub model card request failed.")
    }

    @Test("execute rejects ops.run_bench when the requested model is not loaded")
    func executeRejectsOpsRunBenchWhenRequestedModelIsNotLoaded() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(modelID: "missing-model"))

        #expect(!response.ok)
        #expect(response.error.code == "not_found")
        #expect(response.error.message.contains("missing-model"))
        #expect(await modelOpsClient.lastBenchRequest == nil)
    }

    @Test("execute rejects ops.run_bench when no preferred benchmark target exists")
    func executeRejectsOpsRunBenchWhenNoPreferredTargetExists() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: []),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest())

        #expect(!response.ok)
        #expect(response.error.code == "not_found")
        #expect(response.error.message.contains("preferred benchmark model"))
        #expect(await modelOpsClient.lastBenchRequest == nil)
    }

    @Test("execute surfaces failed benchmark jobs with the explicit benchmark model id")
    func executeSurfacesFailedBenchmarkJobs() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-failed"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.failed = Melix_Worker_V1_BenchFailed()
                event.failed.error.code = "runtime_error"
                event.failed.error.message = "benchmark failed"
                return event
            }(),
        ])
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest(modelID: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "runtime_error")
        #expect(response.ops.benchmarkJob.jobID == "bench-failed")
        #expect(response.ops.benchmarkJob.modelID == "melix-dev-text")
        #expect(response.ops.benchmarkJob.status == "failed")
    }

    @Test("execute handles ops.run_evaluation through the model-operations worker")
    func executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job.schemaVersion = "melix.evaluation_job.v1"
            response.job.jobID = "eval-123"
            response.job.modelID = "melix-dev-text"
            response.job.taskKind = "text-generation"
            response.job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
            response.job.suiteID = "qa_smoke"
            response.job.datasetID = "qa_smoke.dev.v1"
            response.job.sampleSize = 8
            response.job.scoringMode = "deterministic_accuracy"
            response.job.parameters = ["judge": "deterministic"]
            response.job.status = "completed"
            response.job.outputDir = "/tmp/melix/evaluation/runs/eval-123"
            response.job.createdAtUnixMs = 1712400000000
            response.job.updatedAtUnixMs = 1712400005000
            var result = Melix_Worker_V1_WorkerEvaluationResult()
            result.schemaVersion = "melix.evaluation_result.v1"
            result.jobID = "eval-123"
            result.suiteID = "qa_smoke"
            result.datasetID = "qa_smoke.dev.v1"
            result.sampleSize = 8
            var metric = Melix_Worker_V1_EvaluationMetricValue()
            metric.name = "eval.qa_smoke.accuracy"
            metric.value = 1.0
            result.metrics = [metric]
            result.reportPath = "/tmp/melix-evaluation.json"
            result.evidencePath = "/tmp/melix-evaluation-run-evidence.json"
            response.results = [result]
            return response
        }())
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::explicit")
        let response = try await service.execute(makeRunEvaluationRequest())
        #expect(response.ok, "response error: \(response.error.code) \(response.error.message)")
        let lastRequest = try #require(await modelOpsClient.lastEvaluationRequest)

        #expect(response.ok)
        #expect(lastRequest.taskKind == "text-generation")
        #expect(lastRequest.suiteID == "qa_smoke")
        #expect(lastRequest.datasetID == "qa_smoke.dev.v1")
        #expect(lastRequest.sampleSize == 8)
        #expect(lastRequest.parameters["judge"] == "deterministic")
        #expect(response.ops.evaluationJob.schemaVersion == "melix.evaluation_job.v1")
        #expect(response.ops.evaluationJob.jobID == "eval-123")
        #expect(response.ops.evaluationJob.suiteID == "qa_smoke")
        #expect(response.ops.evaluationJob.datasetID == "qa_smoke.dev.v1")
        #expect(response.ops.evaluationJob.sampleSize == 8)
        #expect(response.ops.evaluationJob.taskKind == "text-generation")
        #expect(response.ops.evaluationJob.sourceRepo == "HuggingFaceH4/ultrachat_200k")
        #expect(response.ops.evaluationJob.outputDir == "/tmp/melix/evaluation/runs/eval-123")
        #expect(response.ops.evaluationJob.parameters["judge"] == "deterministic")
        #expect(response.ops.evaluationResults.count == 1)
        #expect(response.ops.evaluationResults[0].schemaVersion == "melix.evaluation_result.v1")
        #expect(response.ops.evaluationResults[0].jobID == "eval-123")
        #expect(response.ops.evaluationResults[0].suiteID == "qa_smoke")
        #expect(response.ops.evaluationResults[0].datasetID == "qa_smoke.dev.v1")
        #expect(response.ops.evaluationResults[0].sampleSize == 8)
        #expect(response.ops.evaluationResults[0].metrics.count == 1)
        #expect(response.ops.evaluationResults[0].metrics[0].name == "eval.qa_smoke.accuracy")
        #expect(response.ops.evaluationResults[0].metrics[0].value == 1.0)
        #expect(response.ops.evaluationResults[0].evidencePath == "/tmp/melix-evaluation-run-evidence.json")
    }

    @Test("execute forwards canonical evaluation request fields to the worker request")
    func executeForwardsCanonicalEvaluationRequestFieldsToTheWorkerRequest() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job = Melix_Worker_V1_WorkerEvaluationJob()
            response.job.jobID = "eval-canonical"
            response.job.modelID = "melix-dev-text"
            response.job.suiteID = "qa_smoke"
            response.job.datasetID = "qa_smoke.dev.v1"
            response.job.sampleSize = 8
            response.job.scoringMode = "multiple_choice_accuracy"
            response.job.parameters = ["judge": "deterministic"]
            response.job.status = "completed"
            response.job.outputDir = "/tmp/melix/evaluation/runs/eval-canonical"
            response.results = []
            return response
        }())
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        _ = try await service.execute(makeRunEvaluationRequest())
        let lastRequest = try #require(await modelOpsClient.lastEvaluationRequest)

        #expect(lastRequest.fewShot == 4)
        #expect(lastRequest.seed == 7)
        #expect(lastRequest.scoringMode == "multiple_choice_accuracy")
        #expect(lastRequest.codeExecPolicy == "sandboxed")
    }

    @Test("execute forwards remote evaluation target without persisting secret into parameters")
    func executeForwardsRemoteEvaluationTargetWithoutPersistingSecretIntoParameters() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job = Melix_Worker_V1_WorkerEvaluationJob()
            response.job.jobID = "eval-remote"
            response.job.modelID = "gemini-2.5-flash"
            response.job.suiteID = "event_extraction"
            response.job.datasetID = "top200"
            response.job.sampleSize = 3
            response.job.scoringMode = "event_extraction_weighted_f1"
            response.job.parameters = [
                "remote_server_id": "sub2api",
                "remote_model_id": "gemini-2.5-flash",
            ]
            response.job.status = "completed"
            response.results = []
            return response
        }())
        let service = ControlPlaneService(
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        var request = makeRunEvaluationRequest(modelID: "", suiteID: "event_extraction", datasetID: "top200")
        request.ops.runEvaluation.scoringMode = "event_extraction_weighted_f1"
        request.ops.runEvaluation.source.localJsonl.path = "/tmp/top200.jsonl"
        request.ops.runEvaluation.remoteTarget.remoteServerID = "sub2api"
        request.ops.runEvaluation.remoteTarget.providerKind = "openai-compatible"
        request.ops.runEvaluation.remoteTarget.baseURL = "https://sub2api.example/v1"
        request.ops.runEvaluation.remoteTarget.apiKey = "sk-secret"
        request.ops.runEvaluation.remoteTarget.modelID = "gemini-2.5-flash"
        request.ops.runEvaluation.remoteTarget.timeoutSeconds = 60
        request.ops.runEvaluation.remoteTarget.rateLimitPerMinute = 30

        _ = try await service.execute(request)
        let lastRequest = try #require(await modelOpsClient.lastEvaluationRequest)

        #expect(lastRequest.remoteTarget.remoteServerID == "sub2api")
        #expect(lastRequest.remoteTarget.providerKind == "openai-compatible")
        #expect(lastRequest.remoteTarget.baseURL == "https://sub2api.example/v1")
        #expect(lastRequest.remoteTarget.apiKey == "sk-secret")
        #expect(lastRequest.remoteTarget.modelID == "gemini-2.5-flash")
        guard case .localJsonl(let source)? = lastRequest.source.kind else {
            Issue.record("Expected remote evaluation to keep the local JSONL source.")
            return
        }
        #expect(source.path == "/tmp/top200.jsonl")
        #expect(lastRequest.parameters["remote_server_id"] == "sub2api")
        #expect(lastRequest.parameters["remote_model_id"] == "gemini-2.5-flash")
        #expect(lastRequest.parameters.values.contains("sk-secret") == false)
    }

    @Test("execute validates remote evaluation targets before dispatch")
    func executeValidatesRemoteEvaluationTargetsBeforeDispatch() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let service = ControlPlaneService(
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        func remoteEvaluationRequest(
            providerKind: String = "openai-compatible",
            baseURL: String = "https://sub2api.example/v1",
            apiKey: String = "sk-secret",
            modelID: String = "gemini-2.5-flash"
        ) -> Melix_Controlplane_V1_ControlPlaneRequest {
            var request = makeRunEvaluationRequest(modelID: "", suiteID: "event_extraction", datasetID: "top200")
            request.ops.runEvaluation.remoteTarget.remoteServerID = "sub2api"
            request.ops.runEvaluation.remoteTarget.providerKind = providerKind
            request.ops.runEvaluation.remoteTarget.baseURL = baseURL
            request.ops.runEvaluation.remoteTarget.apiKey = apiKey
            request.ops.runEvaluation.remoteTarget.modelID = modelID
            return request
        }

        let missingProvider = try await service.execute(remoteEvaluationRequest(providerKind: " "))
        let missingBaseURL = try await service.execute(remoteEvaluationRequest(baseURL: " "))
        let missingAPIKey = try await service.execute(remoteEvaluationRequest(apiKey: " "))
        let missingModel = try await service.execute(remoteEvaluationRequest(modelID: " "))

        #expect(missingProvider.error.code == "invalid_argument")
        #expect(missingProvider.error.message == "Remote evaluation target is missing provider_kind.")
        #expect(missingBaseURL.error.code == "invalid_argument")
        #expect(missingBaseURL.error.message == "Remote evaluation target is missing base_url.")
        #expect(missingAPIKey.error.code == "invalid_argument")
        #expect(missingAPIKey.error.message == "Remote evaluation target is missing an API key.")
        #expect(missingModel.error.code == "invalid_argument")
        #expect(missingModel.error.message == "Remote evaluation target is missing model_id.")
        #expect(await modelOpsClient.lastEvaluationRequest == nil)
    }

    @Test("execute maps remote evaluation worker failures")
    func executeMapsRemoteEvaluationWorkerFailures() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = false
            response.error.code = "provider_timeout"
            response.error.message = "Remote provider timed out."
            return response
        }())
        let service = ControlPlaneService(
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )
        var request = makeRunEvaluationRequest(modelID: "", suiteID: "event_extraction", datasetID: "top200")
        request.ops.runEvaluation.remoteTarget.remoteServerID = "sub2api"
        request.ops.runEvaluation.remoteTarget.providerKind = "openai-compatible"
        request.ops.runEvaluation.remoteTarget.baseURL = "https://sub2api.example/v1"
        request.ops.runEvaluation.remoteTarget.apiKey = "sk-secret"
        request.ops.runEvaluation.remoteTarget.modelID = "gemini-2.5-flash"

        let workerError = try await service.execute(request)
        #expect(workerError.error.code == "provider_timeout")
        #expect(workerError.error.message == "Remote provider timed out.")

        await modelOpsClient.setEvaluationError(WorkerClientError.unavailable)
        let thrownError = try await service.execute(request)
        #expect(thrownError.error.code == "unavailable")
        #expect(thrownError.error.message.contains("Evaluation worker request failed"))
    }

    @Test("execute forwards structured evaluation source profile and mapping to the worker request")
    func executeForwardsStructuredEvaluationSourceProfileAndMappingToTheWorkerRequest() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job = Melix_Worker_V1_WorkerEvaluationJob()
            response.job.jobID = "eval-structured"
            response.job.modelID = "melix-dev-text"
            response.job.suiteID = "capital"
            response.job.datasetID = "capital.dev.v1"
            response.job.sampleSize = 1
            response.job.status = "completed"
            response.results = []
            return response
        }())
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        var request = makeRunEvaluationRequest(
            modelID: "melix-dev-text",
            suiteID: "capital",
            datasetID: "capital.dev.v1"
        )
        request.ops.runEvaluation.source.localCsv.path = "/tmp/eval/capital.csv"
        request.ops.runEvaluation.fieldMapping.systemPath = "system_prompt"
        request.ops.runEvaluation.fieldMapping.inputTextPath = "question"
        request.ops.runEvaluation.fieldMapping.targetPath = "gold_answer"
        request.ops.runEvaluation.fieldMapping.sampleIDPath = "sample_id"
        request.ops.runEvaluation.profile.profileType = "final_result"
        request.ops.runEvaluation.profile.resultKind = "text"
        request.ops.runEvaluation.profile.extractionMode = "heuristic_final"
        request.ops.runEvaluation.profile.scoringMode = "normalized_exact_match"
        request.ops.runEvaluation.profile.threshold = 1.0

        _ = try await service.execute(request)
        let lastRequest = try #require(await modelOpsClient.lastEvaluationRequest)

        guard case .localCsv(let source)? = lastRequest.source.kind else {
            Issue.record("Expected the worker request to carry a localCsv evaluation source.")
            return
        }

        #expect(source.path == "/tmp/eval/capital.csv")
        #expect(lastRequest.fieldMapping.systemPath == "system_prompt")
        #expect(lastRequest.fieldMapping.inputTextPath == "question")
        #expect(lastRequest.fieldMapping.targetPath == "gold_answer")
        #expect(lastRequest.fieldMapping.sampleIDPath == "sample_id")
        #expect(lastRequest.profile.profileType == "final_result")
        #expect(lastRequest.profile.resultKind == "text")
        #expect(lastRequest.profile.extractionMode == "heuristic_final")
        #expect(lastRequest.profile.scoringMode == "normalized_exact_match")
        #expect(lastRequest.profile.threshold == 1.0)
    }

    @Test("local control-plane xpc client forwards canonical bench and evaluation request fields")
    func localControlPlaneXPCClientForwardsCanonicalBenchAndEvaluationRequestFields() async throws {
        actor RecordingService: ControlPlaneExecuting {
            private(set) var lastBenchRequest: Melix_Controlplane_V1_RunBench?
            private(set) var lastBenchMatrixRequest: Melix_Controlplane_V1_RunBenchMatrix?
            private(set) var lastEvaluationRequest: Melix_Controlplane_V1_RunEvaluation?
            private(set) var lastImageEditRequest: Melix_Controlplane_V1_EditImage?
            private(set) var lastLoadRequest: Melix_Controlplane_V1_LoadModel?
            private(set) var lastServerRequest: Melix_Controlplane_V1_ControlPlaneRequest?

            func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse {
                _ = request
                return Melix_Controlplane_V1_HandshakeResponse()
            }

            func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription {
                _ = request
                return ControlPlaneSubscription(
                    subscriptionID: "subscription",
                    stream: AsyncStream { continuation in
                        continuation.finish()
                    }
                )
            }

            func unsubscribe(_ subscriptionID: String) async {
                _ = subscriptionID
            }

            func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
                _ = request
                return ControlPlaneChatExecution(
                    requestID: "chat",
                    modelID: "melix-dev-text",
                    stream: AsyncThrowingStream { continuation in
                        continuation.finish()
                    }
                )
            }

            func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
                var response = Melix_Controlplane_V1_ControlPlaneResponse()
                response.requestID = request.requestID
                response.commandType = request.commandType
                response.ok = true
                switch request.command {
                case .image:
                    lastImageEditRequest = request.image.edit
                    response.image.job = Melix_Controlplane_V1_ImageJobSummary()
                    response.image.job.jobID = "image-job"
                case .model:
                    lastLoadRequest = request.model.load
                    response.model.model = Melix_Controlplane_V1_ModelSummary()
                    response.model.model.modelID = request.model.load.modelID
                case .server:
                    lastServerRequest = request
                    response.server.snapshot = Melix_Controlplane_V1_ServerSnapshot()
                    response.server.snapshot.serverState = .serverReady
                    var runtime = Melix_Controlplane_V1_ServerSessionRuntimeState()
                    runtime.serverSessionID = request.targetID.isEmpty ? ServerSessionRuntimeStore.defaultServerSessionID : request.targetID
                    runtime.lifecycleState = .ready
                    runtime.powerState = .active
                    runtime.wakeReason = .operatorResume
                    response.server.snapshot.runtimeSessions = [runtime]
                case .ops(let command):
                    switch command.kind {
                    case .runDoctor:
                        var report = Melix_Controlplane_V1_DoctorReport()
                        report.markdown = "# Doctor\n"
                        report.healthStatus = .warning
                        response.ops.doctor = report
                    case .runBench(let bench):
                        lastBenchRequest = bench
                        response.ops.reportPath = "/tmp/melix/bench/report.md"
                        response.ops.reportMarkdown = "# Bench\n"
                    case .runBenchMatrix(let matrix):
                        lastBenchMatrixRequest = matrix
                        var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
                        job.schemaVersion = "melix.benchmark_matrix_job.v1"
                        job.jobID = "bench-matrix-1"
                        job.modelID = "melix-dev-text"
                        job.taskKind = "text-generation"
                        job.sourceRepo = "melix-dev-text"
                        job.suiteIds = ["smoke"]
                        job.benchmarkMode = "matrix"
                        job.status = "completed"
                        job.outputDir = "/tmp/melix/bench/matrix-runs/bench-matrix-1"
                        job.createdAtUnixMs = 1712200000000
                        job.updatedAtUnixMs = 1712200005000
                        response.ops.benchmarkMatrixJob = job
                    case .runEvaluation(let evaluation):
                        lastEvaluationRequest = evaluation
                        var job = Melix_Controlplane_V1_EvaluationJobSummary()
                        job.jobID = "eval-1"
                        response.ops.evaluationJob = job
                    default:
                        break
                    }
                default:
                    break
                }
                return response
            }
        }

        let service = RecordingService()
        let client = LocalControlPlaneXPCClient(service: service)

        _ = try await service.handshake(Melix_Controlplane_V1_HandshakeRequest())
        let subscription = await service.subscribe(Melix_Controlplane_V1_SubscribeRequest())
        await service.unsubscribe(subscription.subscriptionID)
        let chatExecution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        #expect(chatExecution.requestID == "chat")
        #expect(chatExecution.modelID == "melix-dev-text")
        _ = try await service.execute(makeExportResultsRequest())

        _ = try await client.runBench(
            ControlPlaneBenchRequest(
                modelID: "melix-dev-text",
                suites: ["smoke"],
                contextLengths: [4096, 1024],
                generationLength: 128,
                batchSizes: [4, 2],
                repeats: 0,
                cacheProfile: "partial_prefix",
                reasoningMode: "enabled",
                structuredOutputMode: "json_schema",
                parameters: [
                    "sample_size": "8",
                    "batch_factor": "2",
                ]
            )
        )
        let benchRequest = try #require(await service.lastBenchRequest)

        #expect(benchRequest.contextLengths == [1024, 4096])
        #expect(benchRequest.generationLength == 128)
        #expect(benchRequest.batchSizes == [2, 4])
        #expect(benchRequest.repeats == 1)
        #expect(benchRequest.cacheProfile == "partial_prefix")
        #expect(benchRequest.reasoningMode == "enabled")
        #expect(benchRequest.structuredOutputMode == "json_schema")

        let doctorReport = try await client.runDoctor()
        #expect(doctorReport.markdown == "# Doctor\n")
        #expect(doctorReport.healthStatus == .warning)

        let defaultLoaded = try await client.loadModel(modelID: "melix-dev-text")
        #expect(defaultLoaded.modelID == "melix-dev-text")
        var loadRequest = try #require(await service.lastLoadRequest)
        #expect(loadRequest.modelID == "melix-dev-text")
        #expect(loadRequest.memoryBudgetBytes == 0)

        let explicitLoaded = try await client.loadModel(
            modelID: "melix-dev-text",
            memoryBudgetBytes: 65_536
        )
        #expect(explicitLoaded.modelID == "melix-dev-text")
        loadRequest = try #require(await service.lastLoadRequest)
        #expect(loadRequest.modelID == "melix-dev-text")
        #expect(loadRequest.memoryBudgetBytes == 65_536)

        _ = try await client.runBenchMatrix(
            ControlPlaneBenchMatrixRequest(
                modelID: "melix-dev-text",
                suites: ["smoke"],
                contextLengths: [4096, 1024],
                generationLengths: [256, 128],
                batchSizes: [4, 2],
                cacheProfiles: ["warm", "cold"],
                reasoningModes: ["enabled", "disabled"],
                structuredOutputModes: ["json_schema", "plain_text"],
                concurrencyLevels: [8, 1],
                repeats: 0,
                requests: 24
            )
        )
        let matrixRequest = try #require(await service.lastBenchMatrixRequest)

        #expect(matrixRequest.contextLengths == [1024, 4096])
        #expect(matrixRequest.generationLengths == [128, 256])
        #expect(matrixRequest.batchSizes == [2, 4])
        #expect(matrixRequest.cacheProfiles == ["cold", "warm"])
        #expect(matrixRequest.reasoningModes == ["disabled", "enabled"])
        #expect(matrixRequest.structuredOutputModes == ["json_schema", "plain_text"])
        #expect(matrixRequest.concurrencyLevels == [1, 8])
        #expect(matrixRequest.repeats == 1)
        #expect(matrixRequest.requests == 24)

        _ = try await client.runEvaluation(
            ControlPlaneEvaluationRequest(
                modelID: "melix-dev-text",
                suiteID: "qa_smoke",
                datasetID: "qa_smoke.dev.v1",
                sampleSize: 8,
                source: .localCSV(path: "/tmp/eval/qa_smoke.csv"),
                fieldMapping: .init(
                    systemPath: "system_prompt",
                    inputTextPath: "question",
                    targetPath: "gold_answer",
                    sampleIDPath: "sample_id"
                ),
                profile: .init(
                    profileType: "final_result",
                    resultKind: "text",
                    extractionMode: "heuristic_final",
                    scoringMode: "normalized_exact_match",
                    threshold: 1.0
                ),
                parameters: [
                    "few_shot": "4",
                    "seed": "7",
                    "scoring_mode": "multiple_choice_accuracy",
                    "code_exec_policy": "sandboxed",
                ],
                remoteTarget: .init(
                    remoteServerID: "sub2api",
                    providerKind: "openai-compatible",
                    baseURL: "https://sub2api.example/v1",
                    apiKey: "sk-secret",
                    modelID: "gemini-2.5-flash",
                    timeoutSeconds: 45,
                    rateLimitPerMinute: 12
                )
            )
        )
        let evaluationRequest = try #require(await service.lastEvaluationRequest)

        #expect(evaluationRequest.fewShot == 4)
        #expect(evaluationRequest.seed == 7)
        #expect(evaluationRequest.scoringMode == "multiple_choice_accuracy")
        #expect(evaluationRequest.codeExecPolicy == "sandboxed")
        guard case .localCsv(let source)? = evaluationRequest.source.kind else {
            Issue.record("Expected the local client to emit a localCsv evaluation source.")
            return
        }
        #expect(source.path == "/tmp/eval/qa_smoke.csv")
        #expect(evaluationRequest.fieldMapping.systemPath == "system_prompt")
        #expect(evaluationRequest.fieldMapping.inputTextPath == "question")
        #expect(evaluationRequest.fieldMapping.targetPath == "gold_answer")
        #expect(evaluationRequest.fieldMapping.sampleIDPath == "sample_id")
        #expect(evaluationRequest.profile.profileType == "final_result")
        #expect(evaluationRequest.profile.resultKind == "text")
        #expect(evaluationRequest.profile.extractionMode == "heuristic_final")
        #expect(evaluationRequest.profile.scoringMode == "normalized_exact_match")
        #expect(evaluationRequest.profile.threshold == 1.0)
        #expect(evaluationRequest.remoteTarget.remoteServerID == "sub2api")
        #expect(evaluationRequest.remoteTarget.providerKind == "openai-compatible")
        #expect(evaluationRequest.remoteTarget.baseURL == "https://sub2api.example/v1")
        #expect(evaluationRequest.remoteTarget.apiKey == "sk-secret")
        #expect(evaluationRequest.remoteTarget.modelID == "gemini-2.5-flash")
        #expect(evaluationRequest.remoteTarget.timeoutSeconds == 45)
        #expect(evaluationRequest.remoteTarget.rateLimitPerMinute == 12)

        let imageJob = try await client.editImage(
            ControlPlaneImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "",
                imageURL: "",
                sourceArtifactID: "artifact-source",
                promptDelta: "make the colors warmer",
                mode: .iterate,
                strength: 0.65
            )
        )
        let imageEditRequest = try #require(await service.lastImageEditRequest)

        #expect(imageJob.jobID == "image-job")
        #expect(imageEditRequest.modelID == "melix-dev-image")
        #expect(imageEditRequest.sourceArtifactID == "artifact-source")
        #expect(imageEditRequest.promptDelta == "make the colors warmer")
        #expect(imageEditRequest.editMode == .iterate)
        #expect(imageEditRequest.imageUri.isEmpty)

        _ = try await client.startServerSession(serverSessionID: "server-session-2")
        var serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.start")
        #expect(serverRequest.targetID == "server-session-2")
        #expect(serverRequest.server.start.serverSessionID == "server-session-2")

        _ = try await client.pauseServerSession(serverSessionID: "server-session-2")
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.pause")
        #expect(serverRequest.server.pause.serverSessionID == "server-session-2")

        _ = try await client.resumeServerSession(serverSessionID: "server-session-2")
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.resume")
        #expect(serverRequest.server.resume.serverSessionID == "server-session-2")

        _ = try await client.wakeServerSession(serverSessionID: "server-session-2")
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.wake")
        #expect(serverRequest.server.wake.serverSessionID == "server-session-2")

        _ = try await client.stopServerSession(serverSessionID: "server-session-2")
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.stop")
        #expect(serverRequest.server.stop.serverSessionID == "server-session-2")

        _ = try await client.updateServerIdlePolicy(
            serverSessionID: "server-session-2",
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 60,
            deepSleepAfterSeconds: 600
        )
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.set_idle_policy")
        #expect(serverRequest.server.setIdlePolicy.serverSessionID == "server-session-2")
        #expect(serverRequest.server.setIdlePolicy.autoSleepEnabled == true)
        #expect(serverRequest.server.setIdlePolicy.lightSleepAfterSeconds == 60)
        #expect(serverRequest.server.setIdlePolicy.deepSleepAfterSeconds == 600)

        let gatewaySnapshot = try await client.applyServerSessionGatewayConfig(
            serverSessionID: "server-session-2",
            host: "0.0.0.0",
            port: 18_080,
            defaultModelID: "melix-dev-text",
            servedModelIDs: ["melix-dev-text", "melix-alt-text"],
            rateLimitPerMinute: 240,
            timeoutSeconds: 90,
            modelIdleTimeoutSeconds: 300
        )
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.apply_gateway_config")
        #expect(serverRequest.targetID == "server-session-2")
        #expect(serverRequest.server.applyGatewayConfig.serverSessionID == "server-session-2")
        #expect(serverRequest.server.applyGatewayConfig.host == "0.0.0.0")
        #expect(serverRequest.server.applyGatewayConfig.port == 18_080)
        #expect(serverRequest.server.applyGatewayConfig.defaultModelID == "melix-dev-text")
        #expect(serverRequest.server.applyGatewayConfig.servedModelIds == ["melix-dev-text", "melix-alt-text"])
        #expect(serverRequest.server.applyGatewayConfig.rateLimitPerMinute == 240)
        #expect(serverRequest.server.applyGatewayConfig.timeoutSeconds == 90)
        #expect(serverRequest.server.applyGatewayConfig.modelIdleTimeoutSeconds == 300)
        #expect(gatewaySnapshot.runtimeSessions.first?.serverSessionID == "server-session-2")

        let servingDefaultsSnapshot = try await client.applyServerSessionServingDefaults(
            serverSessionID: "server-session-2",
            temperature: 0.42,
            topP: 0.91,
            maxTokens: 768,
            streamIntervalTokens: 3,
            maxConcurrentRequests: 8,
            concurrentProcessingEnabled: true,
            prefillBatchSize: 4,
            completionBatchSize: 4,
            accelerationMode: .speculativeDecode,
            draftModelID: "melix-dev-draft",
            numDraftTokens: 6,
            accelerationProfile: "throughput"
        )
        serverRequest = try #require(await service.lastServerRequest)
        #expect(serverRequest.commandType == "server.apply_serving_defaults")
        #expect(serverRequest.targetID == "server-session-2")
        #expect(serverRequest.server.applyServingDefaults.serverSessionID == "server-session-2")
        #expect(serverRequest.server.applyServingDefaults.temperature == 0.42)
        #expect(serverRequest.server.applyServingDefaults.topP == 0.91)
        #expect(serverRequest.server.applyServingDefaults.maxTokens == 768)
        #expect(serverRequest.server.applyServingDefaults.streamIntervalTokens == 3)
        #expect(serverRequest.server.applyServingDefaults.maxConcurrentRequests == 8)
        #expect(serverRequest.server.applyServingDefaults.concurrentProcessingEnabled)
        #expect(serverRequest.server.applyServingDefaults.prefillBatchSize == 4)
        #expect(serverRequest.server.applyServingDefaults.completionBatchSize == 4)
        #expect(serverRequest.server.applyServingDefaults.accelerationMode == .speculativeDecode)
        #expect(serverRequest.server.applyServingDefaults.draftModelID == "melix-dev-draft")
        #expect(serverRequest.server.applyServingDefaults.numDraftTokens == 6)
        #expect(serverRequest.server.applyServingDefaults.accelerationProfile == "throughput")
        #expect(servingDefaultsSnapshot.runtimeSessions.first?.serverSessionID == "server-session-2")
    }

    @Test("control-plane xpc client server lifecycle defaults surface unimplemented errors")
    func controlPlaneXPCClientServerLifecycleDefaultsSurfaceUnimplementedErrors() async throws {
        actor FallbackClient: ControlPlaneXPCClient {
            func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse { .init() }
            func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
                _ = lastSeenSeq
                return AsyncStream { continuation in
                    continuation.finish()
                }
            }
            func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot { .init() }
            func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary { .init() }
            func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary { .init() }
            func updateModelSettings(modelID: String, values: [String: String]) async throws -> Melix_Controlplane_V1_ModelSummary { .init() }
            func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo { .init() }
            func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
                _ = request
                return ControlPlaneChatExecution(
                    requestID: "chat",
                    modelID: "melix-dev-text",
                    stream: AsyncThrowingStream { continuation in continuation.finish() }
                )
            }
            func runModelOperation(modelID: String, operation: String, outputDir: String, quantProfileID: String, weightQuant: String, kvQuant: String, ext: [String: String]) async throws -> Melix_Controlplane_V1_ModelOperationResult { .init() }
            func generateImage(_ request: ControlPlaneImageGenerationRequest) async throws -> Melix_Controlplane_V1_ImageJobSummary { .init() }
            func editImage(_ request: ControlPlaneImageEditRequest) async throws -> Melix_Controlplane_V1_ImageJobSummary { .init() }
            func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
                _ = request
                return ControlPlaneBenchResult(reportPath: "", reportMarkdown: "", metrics: [:])
            }
            func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
                _ = request
                return ControlPlaneBenchMatrixResult(
                    job: .init(),
                    summaryRows: []
                )
            }
            func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
                _ = request
                return ControlPlaneEvaluationResult(job: .init(), results: [])
            }
            func exportResults(outputDir: String) async throws -> ControlPlaneExportResult {
                _ = outputDir
                return ControlPlaneExportResult(exportBundleJSON: "{}")
            }
            func cancelRequest(requestID: String) async throws -> Bool {
                _ = requestID
                return false
            }
            func applyServerSessionGatewayAccess(
                serverSessionID: String,
                primaryKey: String,
                keyID: String,
                label: String,
                tokenHint: String
            ) async throws {
                _ = serverSessionID
                _ = primaryKey
                _ = keyID
                _ = label
                _ = tokenHint
            }
            func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
                _ = serverSessionID
            }
        }

        let client = FallbackClient()

        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Doctor is not implemented for this control-plane client."
        )) {
            _ = try await client.runDoctor()
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server start is not implemented for this control-plane client."
        )) {
            _ = try await client.startServerSession(serverSessionID: "server-session-1")
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server pause is not implemented for this control-plane client."
        )) {
            _ = try await client.pauseServerSession(serverSessionID: "server-session-1")
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server resume is not implemented for this control-plane client."
        )) {
            _ = try await client.resumeServerSession(serverSessionID: "server-session-1")
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server wake is not implemented for this control-plane client."
        )) {
            _ = try await client.wakeServerSession(serverSessionID: "server-session-1")
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server stop is not implemented for this control-plane client."
        )) {
            _ = try await client.stopServerSession(serverSessionID: "server-session-1")
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server idle-policy updates are not implemented for this control-plane client."
        )) {
            _ = try await client.updateServerIdlePolicy(
                serverSessionID: "server-session-1",
                autoSleepEnabled: true,
                lightSleepAfterSeconds: 60,
                deepSleepAfterSeconds: 600
            )
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Gateway config apply is not implemented for this control-plane client."
        )) {
            _ = try await client.applyServerSessionGatewayConfig(
                serverSessionID: "server-session-1",
                host: "127.0.0.1",
                port: 11_434,
                defaultModelID: "melix-dev-text",
                servedModelIDs: ["melix-dev-text"],
                rateLimitPerMinute: 120,
                timeoutSeconds: 60,
                modelIdleTimeoutSeconds: 600
            )
        }
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Serving defaults apply is not implemented for this control-plane client."
        )) {
            _ = try await client.applyServerSessionServingDefaults(
                serverSessionID: "server-session-1",
                temperature: 0.7,
                topP: 1.0,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4,
                concurrentProcessingEnabled: true,
                prefillBatchSize: 2,
                completionBatchSize: 2,
                accelerationMode: .baseline,
                draftModelID: "",
                numDraftTokens: 0,
                accelerationProfile: "balanced"
            )
        }

        let loaded = try await client.loadModel(
            modelID: "melix-dev-text",
            memoryBudgetBytes: 98_304
        )
        #expect(loaded.modelID == "")
    }

    @Test("execute rejects canonical bench request validation failures")
    func executeRejectsCanonicalBenchRequestValidationFailures() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        _ = await catalog.loadModel(id: "melix-dev-text", dispatchHandle: "melix-dev-text::explicit")
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        var request = makeRunBenchRequest(modelID: "melix-dev-text")

        request.ops.runBench.suites = []
        var response = try await service.execute(request)
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("benchmark suite"))

        request = makeRunBenchRequest(modelID: "melix-dev-text")
        request.ops.runBench.contextLengths = []
        response = try await service.execute(request)
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("benchmark context length"))

        request = makeRunBenchRequest(modelID: "melix-dev-text")
        request.ops.runBench.repeats = 0
        response = try await service.execute(request)
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("Benchmark repeats"))

        request = makeRunBenchRequest(modelID: "melix-dev-text")
        request.ops.runBench.repeats = 21
        response = try await service.execute(request)
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("Benchmark repeats"))

        request = makeRunBenchRequest(modelID: "melix-dev-text")
        request.ops.runBench.cacheProfile = "ancient"
        response = try await service.execute(request)
        #expect(!response.ok)
        #expect(response.error.code == "invalid_argument")
        #expect(response.error.message.contains("partial_prefix"))
    }

    @Test("execute rejects unsupported evaluation task families and unresolved targets")
    func executeRejectsUnsupportedEvaluationTaskFamiliesAndUnresolvedTargets() async throws {
        let unsupportedClient = ScriptedModelOperationsWorkerClient()
        await unsupportedClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "google/paligemma2-3b-ft-docci-448",
                modelName: "paligemma2-3b-ft-docci-448",
                pipelineTag: "image-to-text",
                tags: ["paligemma", "image-to-text", "mlx"],
                siblingFiles: [
                    "config.json",
                    "processor_config.json",
                    "tokenizer.json",
                ]
            )
        )
        let importedImageEvalClient = ScriptedModelOperationsWorkerClient()
        await importedImageEvalClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "google/paligemma2-3b-ft-docci-448",
                modelName: "paligemma2-3b-ft-docci-448",
                pipelineTag: "image-to-text",
                tags: ["paligemma", "image-to-text", "mlx"],
                siblingFiles: [
                    "config.json",
                    "processor_config.json",
                    "tokenizer.json",
                ]
            )
        )
        await importedImageEvalClient.setEvaluationResponse({
            var response = Melix_Worker_V1_RunEvaluationResponse()
            response.ok = true
            response.job.jobID = "eval-image-1"
            response.job.modelID = "google/paligemma2-3b-ft-docci-448"
            response.job.taskKind = "image-to-text"
            response.job.sourceRepo = "google/paligemma2-3b-ft-docci-448"
            response.job.suiteID = "mmlu"
            response.job.datasetID = "mmlu.vision.dev.v1"
            response.job.sampleSize = 1
            response.job.status = "completed"
            return response
        }())
        let importedImageRuntimeClient = ScriptedChatWorkerClient(events: [])
        let importedImageEvalService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: importedImageRuntimeClient,
                modelOperationsClient: importedImageEvalClient
            )
        )

        let importedImageResponse = try await importedImageEvalService.execute(
            makeRunEvaluationRequest(
                modelID: "",
                hfRepoID: "google/paligemma2-3b-ft-docci-448",
                suiteID: "mmlu",
                datasetID: "mmlu.vision.dev.v1"
            )
        )
        let importedImageLoadRequest = try #require(await importedImageRuntimeClient.lastLoadModelRequest)
        let importedImageEvalRequest = try #require(await importedImageEvalClient.lastEvaluationRequest)

        #expect(importedImageResponse.ok == true)
        #expect(importedImageLoadRequest.model.modelKind == "vlm")
        #expect(importedImageLoadRequest.model.ext["vision_family_id"] == "paligemma-v1")
        #expect(importedImageEvalRequest.taskKind == "image-to-text")
        #expect(importedImageEvalRequest.sourceRepo == "google/paligemma2-3b-ft-docci-448")
        #expect(importedImageEvalRequest.parameters["require_live_model"] == "true")
        #expect(importedImageEvalRequest.parameters["live_model_source"] == "hf_repo")
        #expect(importedImageResponse.ops.evaluationJob.taskKind == "image-to-text")

        let unsupportedImageGenerationClient = ScriptedModelOperationsWorkerClient()
        await unsupportedImageGenerationClient.setHubModelCardResponse(
            makeBenchmarkHubModelCardResponse(
                repoID: "mlx-community/FLUX.1-schnell-4bit",
                modelName: "FLUX.1-schnell-4bit",
                pipelineTag: "text-to-image",
                tags: ["mlx", "text-to-image"],
                siblingFiles: [
                    "config.json",
                    "model.safetensors",
                ]
            )
        )
        let unsupportedImageGenerationService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: unsupportedImageGenerationClient
            )
        )

        let unsupportedImageGenerationResponse = try await unsupportedImageGenerationService.execute(
            makeRunEvaluationRequest(
                modelID: "",
                hfRepoID: "mlx-community/FLUX.1-schnell-4bit"
            )
        )

        #expect(unsupportedImageGenerationResponse.ok == false)
        #expect(unsupportedImageGenerationResponse.error.code == "unsupported_task_family")
        #expect(
            unsupportedImageGenerationResponse.error.message
                .contains("Evaluation supports only text-generation, image-to-text, and image-text-to-text targets.")
        )

        let missingService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: ScriptedModelOperationsWorkerClient()
            )
        )
        let missingResponse = try await missingService.execute(
            makeRunEvaluationRequest(modelID: "missing-model")
        )

        #expect(missingResponse.ok == false)
        #expect(missingResponse.error.code == "not_found")
        #expect(missingResponse.error.message.contains("missing-model"))
    }

    @Test("execute surfaces missing evaluation handles when the target cannot be loaded")
    func executeSurfacesMissingEvaluationHandlesWhenTargetCannotBeLoaded() async throws {
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: ScriptedModelOperationsWorkerClient()
            )
        )

        let response = try await service.execute(makeRunEvaluationRequest(modelID: "melix-dev-text"))

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message.contains("No loaded evaluation target is available for melix-dev-text"))
    }

    @Test("execute handles ops.export_results through the model-operations worker")
    func executeHandlesOpsExportResultsThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setExportResponse({
            var response = Melix_Worker_V1_ExportResultsResponse()
            response.ok = true
            response.exportJson = """
            {"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[{"job_id":"bench-123"}]}
            """
            response.exportPath = "/tmp/melix-export-bundle.json"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeExportResultsRequest())
        let lastRequest = try #require(await modelOpsClient.lastExportRequest)

        #expect(response.ok)
        #expect(lastRequest.outputDir == "/tmp/melix-export")
        #expect(response.ops.exportBundleJson.contains("\"export_schema_version\":\"melix.benchmark_export.v1\""))
    }

    @Test("execute prefers streamed ops.export_results when the worker supports it")
    func executePrefersStreamedOpsExportResultsWhenTheWorkerSupportsIt() async throws {
        let modelOpsClient = ScriptedStreamingExportResultsWorkerClient()
        await modelOpsClient.setStreamResponse({
            var response = Melix_Worker_V1_ExportResultsResponse()
            response.ok = true
            response.exportJson = """
            {"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[{"job_id":"bench-stream"}]}
            """
            response.exportPath = "/tmp/melix-export-bundle.json"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeExportResultsRequest())
        let streamRequests = await modelOpsClient.streamRequests
        let unaryRequests = await modelOpsClient.unaryRequests

        #expect(response.ok)
        #expect(streamRequests.map(\.outputDir) == ["/tmp/melix-export"])
        #expect(unaryRequests.isEmpty)
        #expect(response.ops.exportBundleJson.contains("bench-stream"))
    }

    @Test("execute preserves typed streamed ops.export_results worker errors")
    func executePreservesTypedStreamedOpsExportResultsWorkerErrors() async throws {
        let modelOpsClient = ScriptedStreamingExportResultsWorkerClient()
        await modelOpsClient.setStreamError(
            WorkerClientError.requestFailed(
                code: "resource_exhausted",
                message: "export bundle exceeded receive budget"
            )
        )
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeExportResultsRequest())

        #expect(response.ok == false)
        #expect(response.error.code == "resource_exhausted")
        #expect(response.error.message == "export bundle exceeded receive budget")
    }

    @Test("execute handles ops.submit_results through the model-operations worker")
    func executeHandlesOpsSubmitResultsThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setSubmitResponse({
            var response = Melix_Worker_V1_SubmitResultsResponse()
            response.ok = true
            response.submissionJson = """
            {"schema_version":"melix.submission.v1","device":{"chip":"Apple M4"}}
            """
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeSubmitResultsRequest())
        let lastRequest = try #require(await modelOpsClient.lastSubmitRequest)

        #expect(response.ok)
        #expect(lastRequest.outputDir == "/tmp/melix-export")
        #expect(lastRequest.deviceMetadata["melix_version"] == "0.1.0")
        #expect(response.ops.submissionJson.contains("\"schema_version\":\"melix.submission.v1\""))
    }

    @Test("execute handles image.generate through the image worker and records the image job")
    func executeHandlesImageGenerateThroughTheImageWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [makeWorkerArtifact(jobID: "req-image-generate::image-generate")]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a neon fox",
                size: "512x512",
                n: 2
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageGenerateRequest)
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(response.ok)
        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Draw a neon fox")
        #expect(forwardedRequest.size == "512x512")
        #expect(forwardedRequest.n == 2)
        #expect(response.image.job.jobID == "req-image-generate::image-generate")
        #expect(response.image.job.state == .imageJobCompleted)
        #expect(response.image.job.recipe.prompt == "Draw a neon fox")
        #expect(response.image.job.recipe.size == "512x512")
        #expect(response.image.job.timeoutSeconds == 1_800)
        #expect(snapshot.server.snapshot.imageJobs.contains(where: { $0.jobID == "req-image-generate::image-generate" }))
    }

    @Test("execute handles image.edit through the image worker and records artifact metadata")
    func executeHandlesImageEditThroughTheImageWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "req-image-edit"
            response.job.jobID = "req-image-edit::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactEditSource, artifactID: "source"),
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactMask, artifactID: "mask"),
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactGenerated, artifactID: "output"),
            ]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "file:///tmp/mask.png",
                strength: 0.6
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageEditRequest)

        #expect(response.ok)
        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Replace the sky")
        #expect(forwardedRequest.imageUri == "file:///tmp/source.png")
        #expect(forwardedRequest.maskUri == "file:///tmp/mask.png")
        #expect(forwardedRequest.strength == 0.6)
        #expect(response.image.job.jobID == "req-image-edit::image-edit")
        #expect(response.image.job.artifacts.count == 3)
        #expect(response.image.job.artifacts.last?.role == .imageArtifactGenerated)
    }

    @Test("execute image requests fall back to persisted defaults and role-aware model selections")
    func executeImageRequestsFallBackToPersistedDefaultsAndRoleAwareModelSelections() async throws {
        var qwen = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        ])
        qwen.modelID = "melix-qwen-image"
        var fill = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        ])
        fill.modelID = "melix-fill-image"
        let modelCatalog = ModelCatalog(seedModels: [qwen, fill])
        _ = await modelCatalog.loadModel(id: qwen.modelID, dispatchHandle: "\(qwen.modelID)::python")
        _ = await modelCatalog.loadModel(id: fill.modelID, dispatchHandle: "\(fill.modelID)::python")

        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-image-default-routing-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let imageDefaultsStore = ImageDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("image-defaults.json"),
            defaults: [:]
        )
        try await imageDefaultsStore.apply(
            command: makeApplyImageDefaultsCommand(
                generateModelID: qwen.modelID,
                editModelID: fill.modelID,
                size: "1536x1024",
                steps: 40,
                guidance: 6.25,
                strength: 0.7,
                negativePrompt: "noise"
            ),
            models: [qwen, fill]
        )

        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-default-generate"
            response.job.jobID = "req-image-default-generate::image-generate"
            response.job.modelHandle = "\(qwen.modelID)::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            return response
        }())
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "req-image-default-edit"
            response.job.jobID = "req-image-default-edit::image-edit"
            response.job.modelHandle = "\(fill.modelID)::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            ),
            imageDefaultsStore: imageDefaultsStore
        )

        var generateRequest = makeImageGenerateRequest(
            requestID: "req-image-default-generate",
            modelID: "",
            prompt: "Draw a skyline",
            size: "",
            n: 0
        )
        generateRequest.image.generate.steps = 0
        generateRequest.image.generate.guidance = 0
        generateRequest.image.generate.negativePrompt = ""
        let generateResponse = try await service.execute(generateRequest)

        var editRequest = makeImageEditRequest(
            requestID: "req-image-default-edit",
            modelID: "",
            prompt: "Adjust the skyline",
            imageURI: "file:///tmp/source.png",
            maskURI: "",
            strength: 0
        )
        editRequest.image.edit.size = ""
        editRequest.image.edit.steps = 0
        editRequest.image.edit.guidance = 0
        editRequest.image.edit.negativePrompt = ""
        let editResponse = try await service.execute(editRequest)

        let forwardedGenerateRequest = try #require(await imageClient.lastImageGenerateRequest)
        let forwardedEditRequest = try #require(await imageClient.lastImageEditRequest)

        #expect(generateResponse.ok)
        #expect(generateResponse.image.job.modelID == qwen.modelID)
        #expect(forwardedGenerateRequest.modelHandle == "\(qwen.modelID)::python")
        #expect(forwardedGenerateRequest.size == "1536x1024")
        #expect(forwardedGenerateRequest.ext["melix.image.steps"] == "40")
        #expect(forwardedGenerateRequest.ext["melix.image.guidance"] == "6.25")
        #expect(forwardedGenerateRequest.ext["melix.image.negative_prompt"] == "noise")
        #expect(editResponse.ok)
        #expect(editResponse.image.job.modelID == fill.modelID)
        #expect(forwardedEditRequest.modelHandle == "\(fill.modelID)::python")
        #expect(forwardedEditRequest.size == "1536x1024")
        #expect(forwardedEditRequest.strength == 0.7)
        #expect(forwardedEditRequest.ext["melix.image.steps"] == "40")
        #expect(forwardedEditRequest.ext["melix.image.guidance"] == "6.25")
        #expect(forwardedEditRequest.ext["melix.image.negative_prompt"] == "noise")
        #expect(forwardedEditRequest.ext["melix.image.strength"] == "0.7")
    }

    @Test("execute resolves iterate image edits from a prior artifact and preserves lineage")
    func executeResolvesIterateImageEditsFromPriorArtifact() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")

        let imageJobReadModel = ImageJobReadModel()
        var sourceArtifact = Melix_Controlplane_V1_ImageArtifactRef()
        sourceArtifact.artifactID = "artifact-source"
        sourceArtifact.jobID = "job-source"
        sourceArtifact.role = .imageArtifactGenerated
        sourceArtifact.mimeType = "image/png"
        sourceArtifact.format = "png"
        sourceArtifact.width = 1024
        sourceArtifact.height = 1024
        sourceArtifact.byteLength = 1024
        sourceArtifact.storageUri = "file:///tmp/source-origin.png"
        sourceArtifact.variantIndex = 0
        await imageJobReadModel.recordQueued(
            requestID: "req-source",
            jobID: "job-source",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        await imageJobReadModel.recordCompleted(jobID: "job-source", artifacts: [sourceArtifact])

        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "req-image-iterate"
            response.job.jobID = "req-image-iterate::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_iterate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.sourceArtifactID = "artifact-source"
            response.job.sourceJobID = "job-source"
            response.job.promptDelta = "make the colors warmer"
            response.job.editMode = .iterate
            var generated = makeWorkerArtifact(
                jobID: "req-image-iterate::image-edit",
                role: .imageArtifactGenerated,
                artifactID: "output"
            )
            generated.parentArtifactID = "artifact-source"
            response.job.artifacts = [generated]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        var request = makeImageEditRequest(
            requestID: "req-image-iterate",
            modelID: "melix-dev-image",
            prompt: "",
            imageURI: "",
            maskURI: "",
            strength: 0.6
        )
        request.image.edit.sourceArtifactID = "artifact-source"
        request.image.edit.promptDelta = "make the colors warmer"
        request.image.edit.editMode = .iterate

        let response = try await service.execute(request)
        let forwardedRequest = try #require(await imageClient.lastImageEditRequest)
        let recordedJob = try #require(await imageJobReadModel.job(requestID: "req-image-iterate"))

        #expect(response.ok)
        #expect(forwardedRequest.image.isEmpty)
        #expect(forwardedRequest.imageUri == "file:///tmp/source-origin.png")
        #expect(forwardedRequest.prompt == "make the colors warmer")
        #expect(forwardedRequest.sourceArtifactID == "artifact-source")
        #expect(forwardedRequest.promptDelta == "make the colors warmer")
        #expect(forwardedRequest.editMode == .iterate)
        #expect(forwardedRequest.ext["melix.image.source_job_id"] == "job-source")
        #expect(response.image.job.operation == "image_iterate")
        #expect(response.image.job.sourceArtifactID == "artifact-source")
        #expect(response.image.job.sourceJobID == "job-source")
        #expect(response.image.job.promptDelta == "make the colors warmer")
        #expect(response.image.job.editMode == Melix_Controlplane_V1_ImageEditMode.iterate)
        #expect(response.image.job.artifacts.first?.parentArtifactID == "artifact-source")
        #expect(recordedJob.operation == "image_iterate")
        #expect(recordedJob.sourceArtifactID == "artifact-source")
        #expect(recordedJob.sourceJobID == "job-source")
        #expect(recordedJob.promptDelta == "make the colors warmer")
        #expect(recordedJob.editMode == .iterate)
    }

    @Test("execute returns unimplemented for image commands without a kind")
    func executeReturnsUnimplementedForEmptyImageCommands() async throws {
        let service = ControlPlaneService()
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-image-empty"
        request.commandType = "image.empty"
        request.image = Melix_Controlplane_V1_ImageCommand()

        let response = try await service.execute(request)

        #expect(response.ok == false)
        #expect(response.error.code == "unimplemented")
    }

    @Test("execute returns not_ready when image generation is requested before the model is loaded")
    func executeReturnsNotReadyForImageGenerateWithoutLoadedModel() async throws {
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_ready")
    }

    @Test("execute returns unavailable when the image worker is missing")
    func executeReturnsUnavailableForImageGenerateWithoutWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(modelCatalog: modelCatalog)

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
    }

    @Test("execute returns invalid_argument when image edits omit the source image")
    func executeReturnsInvalidArgumentForImageEditWithoutSource() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "",
                maskURI: "",
                strength: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "invalid_argument")
    }

    @Test("execute validates variation and iterate image edit lineage inputs")
    func executeValidatesVariationAndIterateImageEditLineageInputs() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: ImageJobReadModel(),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        var missingSource = makeImageEditRequest(
            requestID: "req-image-variation-missing-source",
            modelID: "melix-dev-image",
            prompt: "keep composition",
            imageURI: "",
            maskURI: "",
            strength: 1
        )
        missingSource.image.edit.editMode = .variation
        let missingSourceResponse = try await service.execute(missingSource)

        var invalidPromptDelta = makeImageEditRequest(
            requestID: "req-image-edit-invalid-prompt-delta",
            modelID: "melix-dev-image",
            prompt: "replace the sky",
            imageURI: "file:///tmp/source.png",
            maskURI: "",
            strength: 1
        )
        invalidPromptDelta.image.edit.promptDelta = "make it warmer"
        let invalidPromptDeltaResponse = try await service.execute(invalidPromptDelta)

        var iterateWithoutDelta = makeImageEditRequest(
            requestID: "req-image-iterate-missing-delta",
            modelID: "melix-dev-image",
            prompt: "",
            imageURI: "",
            maskURI: "",
            strength: 1
        )
        iterateWithoutDelta.image.edit.sourceArtifactID = "artifact-source"
        iterateWithoutDelta.image.edit.editMode = .iterate
        let iterateWithoutDeltaResponse = try await service.execute(iterateWithoutDelta)

        var mixedSourceInputs = makeImageEditRequest(
            requestID: "req-image-iterate-mixed-source",
            modelID: "melix-dev-image",
            prompt: "",
            imageURI: "file:///tmp/source.png",
            maskURI: "",
            strength: 1
        )
        mixedSourceInputs.image.edit.sourceArtifactID = "artifact-source"
        mixedSourceInputs.image.edit.promptDelta = "make it warmer"
        mixedSourceInputs.image.edit.editMode = .iterate
        let mixedSourceInputsResponse = try await service.execute(mixedSourceInputs)

        #expect(missingSourceResponse.ok == false)
        #expect(missingSourceResponse.error.code == "invalid_argument")
        #expect(missingSourceResponse.error.message.contains("source_artifact_id is required"))
        #expect(invalidPromptDeltaResponse.ok == false)
        #expect(invalidPromptDeltaResponse.error.code == "invalid_argument")
        #expect(invalidPromptDeltaResponse.error.message.contains("prompt_delta is only supported"))
        #expect(iterateWithoutDeltaResponse.ok == false)
        #expect(iterateWithoutDeltaResponse.error.code == "invalid_argument")
        #expect(iterateWithoutDeltaResponse.error.message.contains("prompt_delta is required"))
        #expect(mixedSourceInputsResponse.ok == false)
        #expect(mixedSourceInputsResponse.error.code == "invalid_argument")
        #expect(mixedSourceInputsResponse.error.message.contains("cannot be combined"))
    }

    @Test("execute surfaces worker image.generate failures and records the failed job state")
    func executeSurfacesImageGenerateWorkerFailures() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobFailed
            response.job.error.code = "runtime_error"
            response.job.error.message = "GPU pressure"
            response.error.code = "runtime_error"
            response.error.message = "GPU pressure"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "runtime_error")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "runtime_error")
    }

    @Test("execute records a failed image generate when the worker throws")
    func executeRecordsFailedImageGenerateWhenWorkerThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateError(ImageWorkerFailure.synthetic)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(recordedJob.jobID == "req-image-generate::image-generate")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute maps image generate deadline_exceeded failures into explicit timeout state")
    func executeMapsImageGenerateDeadlineExceededFailuresIntoTimeoutState() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateError(
            WorkerClientError.requestFailed(code: "DEADLINE_EXCEEDED", message: "image generate timed out")
        )
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-image-timeout-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            ),
            imageDefaultsStore: ImageDefaultsStore(
                storeURL: temporaryRoot.appendingPathComponent("image-defaults.json"),
                defaults: ["MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS": "600"]
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-timeout",
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(
            snapshot.server.snapshot.imageJobs.first(where: { $0.requestID == "req-image-generate-timeout" })
        )

        #expect(response.ok == false)
        #expect(response.error.code == "deadline_exceeded")
        #expect(response.error.message.contains("600-second creative workflow deadline"))
        #expect(recordedJob.state == Melix_Controlplane_V1_ImageJobState.imageJobFailed)
        #expect(recordedJob.progress.stage == "timed_out")
        #expect(recordedJob.error.code == "deadline_exceeded")
        #expect(recordedJob.timeoutSeconds == 600)
        #expect(recordedJob.recipe.prompt == "Draw a fox")
    }

    @Test("execute falls back to request mapped image jobs when worker job identifiers drift")
    func executeFallsBackToRequestMappedImageJobsWhenWorkerJobIdentifiersDrift() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate-fallback"
            response.job.jobID = "worker-generated-image-job"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [makeWorkerArtifact(jobID: "worker-generated-image-job")]
            return response
        }())
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "req-image-edit-fallback"
            response.job.jobID = "worker-edited-image-job"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [makeWorkerArtifact(jobID: "worker-edited-image-job")]
            return response
        }())
        let imageJobReadModel = ImageJobReadModel()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let generateResponse = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-fallback",
                modelID: "melix-dev-image",
                prompt: "Draw a fallback fox",
                size: "1024x1024",
                n: 1
            )
        )
        let editResponse = try await service.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-fallback",
                modelID: "melix-dev-image",
                prompt: "Adjust the fallback fox",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 1
            )
        )

        #expect(generateResponse.ok)
        #expect(generateResponse.image.job.jobID == "req-image-generate-fallback::image-generate")
        #expect(generateResponse.image.job.requestID == "req-image-generate-fallback")
        #expect(editResponse.ok)
        #expect(editResponse.image.job.jobID == "req-image-edit-fallback::image-edit")
        #expect(editResponse.image.job.requestID == "req-image-edit-fallback")
    }

    @Test("execute maps image worker availability cancellation empty and passthrough bridge errors")
    func executeMapsImageWorkerAvailabilityCancellationEmptyAndPassthroughBridgeErrors() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let cases: [(String, Error, String, String)] = [
            ("req-image-generate-unavailable", WorkerClientError.unavailable, "unavailable", "Image worker request failed"),
            ("req-image-generate-cancelled", WorkerClientError.requestFailed(code: "cancelled", message: "operator stop"), "cancelled", "operator stop"),
            ("req-image-generate-empty", WorkerClientError.requestFailed(code: "", message: ""), "unavailable", "Image worker request failed."),
            ("req-image-generate-resource", WorkerClientError.requestFailed(code: "RESOURCE_EXHAUSTED", message: "queue full"), "resource_exhausted", "queue full"),
        ]

        for (requestID, error, expectedCode, expectedMessageFragment) in cases {
            await imageClient.setImageGenerateError(error)
            let response = try await service.execute(
                makeImageGenerateRequest(
                    requestID: requestID,
                    modelID: "melix-dev-image",
                    prompt: "Draw a typed failure",
                    size: "1024x1024",
                    n: 1
                )
            )

            #expect(response.ok == false)
            #expect(response.error.code == expectedCode)
            #expect(response.error.message.contains(expectedMessageFragment))
        }
    }

    @Test("execute fills an implicit image job identifier when the worker omits one")
    func executeFillsImplicitImageJobIdentifier() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate-empty-job"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok)
        #expect(response.image.job.jobID == "req-image-generate::image-generate")
    }

    @Test("execute records failed image phases when the worker reports imageJobFailed without an error payload")
    func executeRecordsFailedImagePhaseWithoutWorkerErrorPayload() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate-failed-phase"
            response.job.jobID = "req-image-generate-failed-phase::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobFailed
            response.job.progress.stage = "failed"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-failed-phase",
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok)
        #expect(response.image.job.state == .imageJobFailed)
        #expect(recordedJob.state == .imageJobFailed)
    }

    @Test("execute records a failed image edit when the worker throws")
    func executeRecordsFailedImageEditWhenWorkerThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditError(ImageWorkerFailure.synthetic)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "file:///tmp/mask.png",
                strength: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(recordedJob.jobID == "req-image-edit::image-edit")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute returns unavailable when image.generate admission fails generically")
    func executeReturnsUnavailableWhenImageGenerateAdmissionFailsGenerically() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(acquireError: ImageWorkerFailure.synthetic),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-admission-failure",
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let recordedJob = try #require(await imageJobReadModel.job(requestID: "req-image-generate-admission-failure"))

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Image admission failed"))
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute returns unavailable when image.edit admission fails generically")
    func executeReturnsUnavailableWhenImageEditAdmissionFailsGenerically() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(acquireError: ImageWorkerFailure.synthetic),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-admission-failure",
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 1
            )
        )
        let recordedJob = try #require(await imageJobReadModel.job(requestID: "req-image-edit-admission-failure"))

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Image admission failed"))
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute records runtime_error when the image worker returns a non-terminal generate state")
    func executeMarksInvalidGenerateTerminalStatesAsRuntimeErrors() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobRunning
            response.job.progress.stage = "render"
            response.job.progress.pct = 0.4
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok)
        #expect(response.image.job.state == .imageJobFailed)
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "runtime_error")
    }

    @Test("ops.cancel_request cancels queued image work before it reaches the worker")
    func cancelRequestCancelsQueuedImageWorkBeforeWorkerDispatch() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-generate-1",
                    modelID: "melix-dev-image",
                    prompt: "Draw a fox",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["req-image-generate-1"]
        }

        let queuedTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-generate-2",
                    modelID: "melix-dev-image",
                    prompt: "Draw another fox",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await Task.sleep(for: .milliseconds(50))

        let cancelResponse = try await service.execute(
            makeCancelRequest(requestID: "req-image-generate-2")
        )
        let queuedResponse = try await queuedTask.value
        await imageClient.finishGenerate(requestID: "req-image-generate-1")
        _ = try await firstTask.value
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(cancelResponse.ok)
        #expect(queuedResponse.ok == false)
        #expect(queuedResponse.error.code == "cancelled")
        #expect(await imageClient.startedRequestIDs == ["req-image-generate-1"])
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-generate-2" && $0.state == .imageJobCanceled
        })
    }

    @Test("image.edit returns cancelled when queued admission is aborted before execution")
    func executeReturnsCancelledWhenQueuedImageEditAdmissionIsAborted() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-edit-cancel-active",
                    modelID: "melix-dev-image",
                    prompt: "Hold the image worker",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected active image request to start") {
            await imageClient.startedRequestIDs == ["req-image-edit-cancel-active"]
        }

        let queuedTask = Task {
            try await service.execute(
                makeImageEditRequest(
                    requestID: "req-image-edit-cancel-queued",
                    modelID: "melix-dev-image",
                    prompt: "Cancel this edit",
                    imageURI: "file:///tmp/source.png",
                    maskURI: "",
                    strength: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected queued image edit") {
            await imageJobReadModel.job(requestID: "req-image-edit-cancel-queued")?.state == .imageJobQueued
        }

        let disposition = await admissionController.cancel(requestID: "req-image-edit-cancel-queued")
        let queuedResponse = try await queuedTask.value
        let cancelledJob = try #require(await imageJobReadModel.job(requestID: "req-image-edit-cancel-queued"))

        await imageClient.finishGenerate(requestID: "req-image-edit-cancel-active")
        _ = try await firstTask.value

        #expect(disposition == .queued)
        #expect(queuedResponse.ok == false)
        #expect(queuedResponse.error.code == "cancelled")
        #expect(cancelledJob.state == .imageJobCanceled)
    }

    @Test("ops.cancel_request aborts running image work through the worker")
    func cancelRequestAbortsRunningImageWorkThroughWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let runningTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-running",
                    modelID: "melix-dev-image",
                    prompt: "Draw a wolf",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected image request to start") {
            await imageClient.startedRequestIDs == ["req-image-running"]
        }

        let cancelResponse = try await service.execute(
            makeCancelRequest(requestID: "req-image-running")
        )
        let runningResponse = try await runningTask.value
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(cancelResponse.ok)
        #expect(runningResponse.ok == false)
        #expect(runningResponse.error.code == "cancelled")
        #expect(await imageClient.abortedRequestIDs == ["req-image-running"])
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-running" && $0.state == .imageJobCanceled
        })
    }

    @Test("ops.cancel_request returns not_found when the image request is unknown")
    func cancelRequestReturnsNotFoundForUnknownImageWork() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-missing")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message == "Unknown request ID.")
    }

    @Test("ops.cancel_request returns unavailable when a running image job loses its worker")
    func cancelRequestReturnsUnavailableWhenRunningImageWorkHasNoWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        await imageJobReadModel.recordQueued(
            requestID: "req-image-orphaned",
            jobID: "req-image-orphaned::image-generate",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        try await admissionController.acquire(
            requestID: "req-image-orphaned",
            laneHint: "image.generate.background",
            workerID: "image-worker-1"
        )
        await imageJobReadModel.recordRunning(
            jobID: "req-image-orphaned::image-generate",
            workerID: "image-worker-1",
            pct: 0.25
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-orphaned")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message == "Image worker is unavailable.")
    }

    @Test("ops.cancel_request returns not_found when the image worker says the request is no longer active")
    func cancelRequestReturnsNotFoundWhenImageAbortReturnsFalse() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        await imageJobReadModel.recordQueued(
            requestID: "req-image-stale",
            jobID: "req-image-stale::image-generate",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        try await admissionController.acquire(
            requestID: "req-image-stale",
            laneHint: "image.generate.background",
            workerID: "image-worker-1"
        )
        await imageJobReadModel.recordRunning(
            jobID: "req-image-stale::image-generate",
            workerID: "image-worker-1",
            pct: 0.5
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: AbortFalseImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-stale")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message == "Image request is no longer active.")
    }

    @Test("ops.cancel_request returns unavailable when the running image worker abort throws")
    func cancelRequestReturnsUnavailableWhenImageAbortThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        await imageJobReadModel.recordQueued(
            requestID: "req-image-running-throws",
            jobID: "job-image-running-throws",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        try await admissionController.acquire(
            requestID: "req-image-running-throws",
            laneHint: "image.generate.background",
            workerID: "image-worker-1"
        )
        await imageJobReadModel.recordRunning(
            jobID: "job-image-running-throws",
            workerID: "image-worker-1",
            pct: 0.5
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ThrowingAbortImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-running-throws")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Image cancel failed"))
    }

    @Test("ops.cancel_request returns not_found when the image admission controller no longer tracks the request")
    func cancelRequestReturnsNotFoundWhenImageAdmissionControllerNoLongerTracksRequest() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        await imageJobReadModel.recordQueued(
            requestID: "req-image-lost",
            jobID: "job-image-lost",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(cancelDisposition: .notFound),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-lost")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message == "Image request is no longer active.")
    }

    @Test("ops.cancel_request returns ok when the text request coordinator cancels an active request")
    func cancelRequestReturnsOkWhenTextCoordinatorCancelsActiveRequest() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = BlockingAbortTextWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog)
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "cancel this")]
            )
        )
        try await waitForControlPlaneCondition("expected text request to start") {
            await textClient.startedRequestIDs.contains(execution.requestID)
        }

        let response = try await service.execute(makeCancelRequest(requestID: execution.requestID))

        #expect(response.ok)
        #expect(response.ops.reportMarkdown == "cancel_requested")
    }

    @Test("ops.cancel_request returns unavailable when the text request coordinator abort throws")
    func cancelRequestReturnsUnavailableWhenTextCoordinatorAbortThrows() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = BlockingAbortTextWorkerClient(abortError: WorkerClientError.unavailable)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog)
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "cancel this")]
            )
        )
        try await waitForControlPlaneCondition("expected text request to start") {
            await textClient.startedRequestIDs.contains(execution.requestID)
        }

        let response = try await service.execute(makeCancelRequest(requestID: execution.requestID))

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Cancel request failed"))
    }

    @Test("image.generate returns resource_exhausted when the background queue is saturated")
    func executeReturnsResourceExhaustedWhenImageGenerateQueueIsSaturated() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 0),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-saturated-1",
                    modelID: "melix-dev-image",
                    prompt: "Hold the image worker",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["req-image-saturated-1"]
        }

        let saturatedResponse = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-saturated-2",
                modelID: "melix-dev-image",
                prompt: "This request should saturate",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        await imageClient.finishGenerate(requestID: "req-image-saturated-1")
        _ = try await firstTask.value

        #expect(saturatedResponse.ok == false)
        #expect(saturatedResponse.error.code == "resource_exhausted")
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-saturated-2" &&
            $0.state == .imageJobFailed &&
            $0.error.code == "resource_exhausted"
        })
    }

    @Test("image.edit returns resource_exhausted when the background queue is saturated")
    func executeReturnsResourceExhaustedWhenImageEditQueueIsSaturated() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 0),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-edit-saturated-1",
                    modelID: "melix-dev-image",
                    prompt: "Keep the image worker busy",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["req-image-edit-saturated-1"]
        }

        let saturatedResponse = try await service.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-saturated-2",
                modelID: "melix-dev-image",
                prompt: "This edit should saturate",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 0.7
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        await imageClient.finishGenerate(requestID: "req-image-edit-saturated-1")
        _ = try await firstTask.value

        #expect(saturatedResponse.ok == false)
        #expect(saturatedResponse.error.code == "resource_exhausted")
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-edit-saturated-2" &&
            $0.state == .imageJobFailed &&
            $0.error.code == "resource_exhausted"
        })
    }

    @Test("startChat reuses the request coordinator and streams typed chat events")
    func startChatReusesTheRequestCoordinatorAndStreamsTypedChatEvents() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-service"),
            makeTokenExecuteEvent(requestID: "chat-service", text: "assistant"),
            makeReasoningExecuteEvent(requestID: "chat-service", text: "trace"),
            makeToolExecuteEvent(requestID: "chat-service", callID: "tool-1", toolName: "search", arguments: #"{"q":"melix"}"#),
            makeUsageExecuteEvent(requestID: "chat-service", promptTokens: 3, completionTokens: 5),
            makeCompletedExecuteEvent(requestID: "chat-service", finishReason: "stop", assistant: "assistant", reasoning: "trace"),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient)
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        var events: [ControlPlaneChatStreamEvent] = []
        for try await event in execution.stream {
            events.append(event)
        }

        #expect(execution.modelID == "melix-dev-text")
        #expect(events.contains(where: {
            if case .queued(let lane, _, _) = $0 { return lane == "text.decode.interactive" }
            return false
        }))
        #expect(events.contains(where: {
            if case .reasoningDelta("trace") = $0 { return true }
            return false
        }))
        #expect(events.contains(where: {
            if case .toolCallDelta(let callID, let toolName, _) = $0 {
                return callID == "tool-1" && toolName == "search"
            }
            return false
        }))
    }

    @Test("startChat routes remote server targets through the remote provider client")
    func startChatRoutesRemoteServerTargetsThroughTheRemoteProviderClient() async throws {
        let remoteClient = ScriptedRemoteProviderChatClient(events: [
            .tokenDelta("remote"),
            .completed(finishReason: "stop", assistantText: "remote"),
        ])
        let service = ControlPlaneService(remoteProviderClient: remoteClient)

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "",
                messages: [.init(role: "user", content: "hello")],
                remoteTarget: .init(
                    serverID: "sub2api",
                    providerKind: "openai-compatible",
                    baseURL: "https://sub2api.example/v1",
                    apiKey: "sk-secret",
                    modelID: "gemini-2.5-flash",
                    timeoutSeconds: 30,
                    rateLimitPerMinute: 60
                )
            )
        )
        var events: [ControlPlaneChatStreamEvent] = []
        for try await event in execution.stream {
            events.append(event)
        }

        let lastRequest = try #require(await remoteClient.lastRequest)
        #expect(execution.modelID == "gemini-2.5-flash")
        #expect(lastRequest.serverID == "sub2api")
        #expect(lastRequest.baseURL == "https://sub2api.example/v1")
        #expect(lastRequest.apiKey == "sk-secret")
        #expect(lastRequest.modelID == "gemini-2.5-flash")
        #expect(events == [
            .tokenDelta("remote"),
            .completed(finishReason: "stop", assistantText: "remote", reasoningText: ""),
        ])
    }

    @Test("startChat can resume a disconnected request through resumeRequestID")
    func startChatCanResumeADisconnectedRequestThroughResumeRequestID() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = BlockingAbortTextWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient)
        )

        let initial = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        let initialConsumer = Task {
            do {
                for try await _ in initial.stream {
                }
            } catch {
            }
        }
        await Task.yield()
        initialConsumer.cancel()
        _ = await initialConsumer.result

        let resumed = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")],
                resumeRequestID: initial.requestID
            )
        )
        let resumedCollector = Task {
            var events: [ControlPlaneChatStreamEvent] = []
            for try await event in resumed.stream {
                events.append(event)
            }
            return events
        }

        await textClient.emitToken(requestID: initial.requestID, text: "resumed")
        await textClient.finishDecode(requestID: initial.requestID, assistantText: "resumed")

        let resumedEvents = try await resumedCollector.value

        #expect(resumed.requestID == initial.requestID)
        #expect(resumedEvents.contains(where: {
            if case .tokenDelta("resumed") = $0 { return true }
            return false
        }))
    }

    @Test("startChat applies model OCR defaults for OCR models")
    func startChatAppliesModelOCRDefaultsForOCRModels() async throws {
        var ocrModel = ModelCatalog.devOCRModel()
        ocrModel.state = .modelWarm
        let modelCatalog = ModelCatalog(seedModels: [ocrModel])
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-ocr-service"),
            makeCompletedExecuteEvent(
                requestID: "chat-ocr-service",
                finishReason: "stop",
                assistant: "done",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-ocr-service" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-ocr",
                messages: [.init(role: "user", content: "Read this image.")]
            )
        )
        _ = try await Array(execution.stream)
        let generated = try #require(await textClient.lastGenerateRequest)

        #expect(execution.modelID == "melix-dev-ocr")
        #expect(generated.execution.modelHandle == "melix-dev-ocr")
        #expect(generated.sampling.stop == ["<ocr:end>"])
        #expect(generated.execution.ext["melix.ocr.prompt_profile_id"] == "ocr-default-v1")
        #expect(generated.execution.ext["melix.ocr.prompt_source"] == "request")
        #expect(generated.execution.ext["melix.ocr.sampling_source"] == "model")
    }

    @Test("startChat applies gateway serving defaults to worker requests")
    func startChatAppliesGatewayServingDefaultsToWorkerRequests() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-control-plane-chat-serving-defaults-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        try await servingDefaultsStore.apply(command: makeApplyServingDefaultsCommand(
            temperature: 0.44,
            topP: 0.93,
            maxTokens: 320,
            streamIntervalTokens: 3,
            maxConcurrentRequests: 5,
            concurrentProcessingEnabled: false,
            prefillBatchSize: 4,
            completionBatchSize: 3
        ))

        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-serving-defaults"),
            makeCompletedExecuteEvent(
                requestID: "chat-serving-defaults",
                finishReason: "stop",
                assistant: "done",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-serving-defaults" }),
            gatewayServingDefaultsStore: servingDefaultsStore
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")]
            )
        )
        _ = try await Array(execution.stream)
        let generated = try #require(await textClient.lastGenerateRequest)

        #expect(generated.sampling.temperature == 0.44)
        #expect(generated.sampling.topP == 0.93)
        #expect(generated.sampling.maxOutputTokens == 320)
        #expect(generated.execution.ext["melix.stream.interval_tokens"] == "3")
        #expect(generated.execution.ext["melix.gateway.max_concurrent_requests"] == "1")
        #expect(generated.execution.ext["melix.gateway.concurrent_processing"] == "false")
        #expect(generated.execution.ext["melix.gateway.prefill_batch_size"] == "1")
        #expect(generated.execution.ext["melix.gateway.completion_batch_size"] == "1")
        #expect(
            generated.execution.ext["melix.gateway.suppressed_overrides"]
                == "max_concurrent_requests,prefill_batch_size,completion_batch_size"
        )
        #expect(generated.execution.ext["melix.gateway.batch.disabled_reason"] == "incompatible_batch_size")
    }

    @Test("startChat propagates explicit reasoning and template flags before worker dispatch")
    func startChatPropagatesExplicitReasoningAndTemplateFlagsBeforeWorkerDispatch() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-reasoning-template"),
            makeCompletedExecuteEvent(
                requestID: "chat-reasoning-template",
                finishReason: "stop",
                assistant: "done",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-reasoning-template" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "Use explicit prompt policy.")],
                enableThinking: true,
                reasoningEffort: " high ",
                chatTemplateKwargs: ChatTemplateRequestConfiguration(values: [
                    "enable_thinking": .bool(false),
                    "chat_template": .string("operator-template"),
                ])
            )
        )

        _ = try await Array(execution.stream)
        let generated = try #require(await textClient.lastGenerateRequest)

        #expect(generated.execution.reasoning.enabled)
        #expect(generated.execution.reasoning.mode == "enabled")
        #expect(generated.execution.reasoning.modeSource == "request")
        #expect(generated.execution.reasoning.effort == "high")
        #expect(generated.execution.ext["melix.reasoning.mode_source"] == "request")
        #expect(generated.execution.ext["melix.reasoning.effort"] == "high")
        #expect(generated.execution.ext["melix.chat_template_kwargs.source"] == "request")
        #expect(
            generated.execution.ext["melix.chat_template_kwargs.effective_json"]
                == "{\"chat_template\":\"operator-template\",\"enable_thinking\":false}"
        )
        #expect(generated.execution.scope.reasoningMode == "enabled")
        #expect(generated.execution.scope.reasoningEffort == "high")
        #expect(generated.execution.scope.chatTemplateKwargsHash ==
            generated.execution.ext["melix.cache.fingerprint.chat_template_kwargs"])
    }

    @Test("startChat auto injects MCP tool metadata into worker requests")
    func startChatAutoInjectsMCPToolMetadataIntoWorkerRequests() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-mcp-service"),
            makeCompletedExecuteEvent(
                requestID: "chat-mcp-service",
                finishReason: "stop",
                assistant: "done",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-mcp-service" }),
            mcpToolCatalog: MCPToolCatalog(
                configPath: "/tmp/mcp-tools.json",
                defaultParserMode: .json,
                sources: [
                    .init(
                        sourceID: "filesystem",
                        enabled: true,
                        namespaces: ["tools.fs.read"]
                    ),
                    .init(
                        sourceID: "math",
                        enabled: true,
                        namespaces: ["tools.math"]
                    ),
                ]
            )
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "Call configured tools.")]
            )
        )
        _ = try await Array(execution.stream)
        let generated = try #require(await textClient.lastGenerateRequest)

        #expect(generated.execution.ext["melix.tool_parser.mode"] == "json")
        #expect(generated.execution.ext["melix.tool_parser.source"] == "mcp")
        #expect(generated.execution.ext["melix.tool_parser.namespaces"] == "tools.fs.read,tools.math")
        #expect(generated.execution.ext["melix.mcp.source_ids"] == "filesystem,math")
    }

    @Test("startChat lazily loads a discovered text model before streaming")
    func startChatLazilyLoadsDiscoveredTextModel() async throws {
        let modelCatalog = ModelCatalog()
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-lazy"),
            makeTokenExecuteEvent(requestID: "chat-lazy", text: "assistant"),
            makeCompletedExecuteEvent(
                requestID: "chat-lazy",
                finishReason: "stop",
                assistant: "assistant",
                reasoning: ""
            )
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-lazy" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        let loadRequest = try #require(await textClient.lastLoadModelRequest)
        let generated = try #require(await textClient.lastGenerateRequest)
        let model = await modelCatalog.model(id: "melix-dev-text")

        _ = try await Array(execution.stream)

        #expect(loadRequest.model.modelID == "melix-dev-text")
        #expect(loadRequest.pinOnLoad == false)
        #expect(generated.execution.modelHandle == "melix-dev-text")
        #expect(model?.state == .modelWarm)
    }

    @Test("startChat lazily loads text-capable VLM models before streaming")
    func startChatLazilyLoadsTextCapableVLMModel() async throws {
        let modelCatalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devVLMModel()])
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-vlm-lazy"),
            makeTokenExecuteEvent(requestID: "chat-vlm-lazy", text: "vlm"),
            makeCompletedExecuteEvent(
                requestID: "chat-vlm-lazy",
                finishReason: "stop",
                assistant: "vlm",
                reasoning: ""
            )
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelCatalog: modelCatalog
            ),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-vlm-lazy" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-vlm",
                messages: [.init(role: "user", content: "hello")]
            )
        )

        _ = try await Array(execution.stream)

        let loadRequest = try #require(await textClient.lastLoadModelRequest)
        let generated = try #require(await textClient.lastGenerateRequest)
        let model = await modelCatalog.model(id: "melix-dev-vlm")

        #expect(loadRequest.model.modelID == "melix-dev-vlm")
        #expect(loadRequest.model.modelKind == "vlm")
        #expect(loadRequest.model.ext["melix.capability.route_kind"] == "swift_text")
        // ScriptedChatWorkerClient echoes the loaded handle; loader tests cover suffixed Python handles.
        #expect(generated.execution.modelHandle == "melix-dev-vlm")
        #expect(model?.state == .modelWarm)
    }

    @Test("startChat lazy text loads preserve adapter-set hash in worker requests")
    func startChatLazyTextLoadsPreserveAdapterSetHashInWorkerRequests() async throws {
        var seeded = ModelCatalog.devTextModel()
        seeded.state = .modelDiscovered
        seeded.settings.ext["melix.adapter_set_hash"] = "adapter-alpha"

        let modelCatalog = ModelCatalog(seedModels: [seeded])
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-lazy-adapter"),
            makeCompletedExecuteEvent(
                requestID: "chat-lazy-adapter",
                finishReason: "stop",
                assistant: "assistant",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-lazy-adapter" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )

        _ = try await Array(execution.stream)
        let loadRequest = try #require(await textClient.lastLoadModelRequest)

        #expect(loadRequest.model.ext["melix.adapter_set_hash"] == "adapter-alpha")
    }

    @Test("execute maps fallback model policy values")
    func executeMapsFallbackModelPolicyValues() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "type_override": "mlx-text",
                    "ttl_seconds": "600",
                    "pin_on_load": "no",
                    "memory_policy": "ttl",
                    "default_acceleration_mode": "active_kv_quantized",
                    "custom_hint": "prefetch",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.typeOverride == "mlx-text")
        #expect(response.model.model.settings.ttlSeconds == 600)
        #expect(response.model.model.settings.pinOnLoad == false)
        #expect(response.model.model.settings.memoryPolicy == .memoryResidencyTtl)
        #expect(response.model.model.settings.defaultAccelerationMode == .activeKvQuantized)
        #expect(response.model.model.settings.ext["custom_hint"] == "prefetch")
    }

    @Test("execute maps sparse prefill model policy values")
    func executeMapsSparsePrefillModelPolicyValues() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "default_acceleration_mode": "sparse_prefill",
                    "acceleration_profile_id": "structured-user",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.defaultAccelerationMode == .sparsePrefill)
        #expect(response.model.model.settings.accelerationProfileID == "structured-user")
    }

    @Test("execute maps adaptive thinking and parser fallback model policy values")
    func executeMapsAdaptiveThinkingAndParserFallbackModelPolicyValues() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "adaptive_thinking_mode": "adaptive",
                    "adaptive_thinking_budget_tokens": "192",
                    "tool_parser_xml_fallback": "true",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.adaptiveThinking.mode == "adaptive")
        #expect(response.model.model.settings.adaptiveThinking.budgetTokens == 192)
        #expect(response.model.model.settings.ext["tool_parser_xml_fallback"] == "true")
    }

    @Test("execute clears ttl and adaptive thinking budgets when model policy drafts are empty")
    func executeClearsTTLandAdaptiveThinkingBudgetsWhenDraftsAreEmpty() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "ttl_seconds": "",
                    "adaptive_thinking_mode": "off",
                    "adaptive_thinking_budget_tokens": "",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.ttlSeconds == 0)
        #expect(response.model.model.settings.adaptiveThinking.mode == "off")
        #expect(response.model.model.settings.adaptiveThinking.budgetTokens == 0)
    }

    @Test("execute maps memory budget model policy values and clears them when drafts are empty")
    func executeMapsMemoryBudgetModelPolicyValuesAndClearsThemWhenDraftsAreEmpty() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let configured = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "memory_budget_bytes": "65536",
                ]
            )
        )
        let cleared = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "memory_budget_bytes": "",
                ]
            )
        )

        #expect(configured.ok)
        #expect(configured.model.model.settings.memoryBudgetBytes == 65_536)
        #expect(cleared.ok)
        #expect(cleared.model.model.settings.memoryBudgetBytes == 0)
    }

    @Test("execute surfaces structured errors for missing or unavailable model tools")
    func executeSurfacesStructuredErrorsForMissingOrUnavailableModelTools() async throws {
        let unavailableService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(defaultTextClient: NullWorkerClient())
        )

        let missingPolicy = try await unavailableService.execute(
            makeSetModelPolicyRequest(modelID: "missing-model", values: [:])
        )
        let missingInfo = try await unavailableService.execute(
            makeGetModelInfoRequest(modelID: "missing-model")
        )
        let unavailableInfo = try await unavailableService.execute(
            makeGetModelInfoRequest(modelID: "melix-dev-text")
        )
        let unavailableOperation = try await unavailableService.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8"
            )
        )

        #expect(!missingPolicy.ok)
        #expect(missingPolicy.error.code == "not_found")
        #expect(!missingInfo.ok)
        #expect(missingInfo.error.code == "not_found")
        #expect(!unavailableInfo.ok)
        #expect(unavailableInfo.error.code == "unavailable")
        #expect(!unavailableOperation.ok)
        #expect(unavailableOperation.error.code == "unavailable")
    }

    @Test("execute surfaces worker-side failures for model info and model operations")
    func executeSurfacesWorkerSideFailuresForModelInfoAndOperations() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = false
            response.error = Melix_Worker_V1_ErrorStatus()
            response.error.code = "invalid_model"
            response.error.message = "Model metadata unavailable."
            return response
        }())
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-failed"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.failed = Melix_Worker_V1_ConvertFailed()
                event.failed.error = Melix_Worker_V1_ErrorStatus()
                event.failed.error.code = "convert_failed"
                event.failed.error.message = "Quantization failed."
                event.failed.error.retriable = false
                return event
            }(),
            Melix_Worker_V1_ConvertModelEvent(),
        ])

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let infoResponse = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8"
            )
        )

        #expect(!infoResponse.ok)
        #expect(infoResponse.error.code == "invalid_model")
        #expect(infoResponse.error.message == "Model metadata unavailable.")
        #expect(!operationResponse.ok)
        #expect(operationResponse.error.code == "convert_failed")
        #expect(operationResponse.error.message == "Quantization failed.")
    }

    @Test("execute surfaces thrown model info and operation worker errors")
    func executeSurfacesThrownModelInfoAndOperationWorkerErrors() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoError(TestWorkerError(description: "info transport down"))
        await modelOpsClient.setConvertError(TestWorkerError(description: "operation transport down"))

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let infoResponse = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "upload",
                outputDir: "/tmp/melix-upload",
                weightQuant: "",
                kvQuant: ""
            )
        )

        #expect(!infoResponse.ok)
        #expect(infoResponse.error.code == "unavailable")
        #expect(infoResponse.error.message.contains("info transport down"))
        #expect(!operationResponse.ok)
        #expect(operationResponse.error.code == "unavailable")
        #expect(operationResponse.error.message.contains("operation transport down"))
    }

    @Test("execute returns not found for unknown model operations")
    func executeReturnsNotFoundForUnknownModelOperations() async throws {
        let service = ControlPlaneService()

        let loadResponse = try await service.execute(makeLoadModelRequest(modelID: "missing-model"))
        let unloadResponse = try await service.execute(makeUnloadModelRequest(modelID: "missing-model"))

        #expect(!loadResponse.ok)
        #expect(loadResponse.error.code == "not_found")
        #expect(!unloadResponse.ok)
        #expect(unloadResponse.error.code == "not_found")
    }

    @Test("execute handles ops.get_metrics")
    func executeHandlesOpsMetrics() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makeMetricsRequest())

        #expect(response.ok)
        #expect(response.ops.metrics.values["requests.inflight"] == 0)
        #expect(response.ops.metrics.values["workers.connected"] == 0)
    }

    @Test("execute handles cache.get_snapshot with typed cache metadata")
    func executeHandlesCacheSnapshot() async throws {
        let cacheStore = CacheMetadataStore(snapshot: makeCacheSnapshot())
        let service = ControlPlaneService(cacheMetadataStore: cacheStore)

        let response = try await service.execute(makeCacheSnapshotRequest())

        #expect(response.ok)
        #expect(response.cache.summary.blockCount == 4)
        #expect(response.cache.summary.compressionRatio == 2.5)
        #expect(response.cache.snapshot.scopes.count == 1)
        #expect(response.cache.snapshot.hotPrefixes.count == 1)
        #expect(response.cache.snapshot.snapshots.first?.snapshotID == "snap-1")
    }

    @Test("execute handles session.get_state with typed branch metadata")
    func executeHandlesSessionState() async throws {
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let response = try await service.execute(makeSessionStateRequest(sessionID: "session-1"))

        #expect(response.ok)
        #expect(response.session.session.sessionID == "session-1")
        #expect(response.session.session.activeBranchID == "branch-main")
        #expect(response.session.session.branches.count == 2)
        #expect(response.session.session.availableSnapshots.first?.snapshotID == "snap-1")
        #expect(response.session.session.branches.first?.headCacheKey.scope.modelID == "melix-dev-text")
    }

    @Test("execute returns not found for unknown session state")
    func executeReturnsNotFoundForUnknownSessionState() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makeSessionStateRequest(sessionID: "missing-session"))

        #expect(!response.ok)
        #expect(response.error.code == "not_found")
    }

    @Test("execute handles session lifecycle mutations and publishes typed state events")
    func executeHandlesSessionLifecycleMutations() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()

        let created = try await service.execute(makeSessionCreateRequest())
        #expect(created.ok)
        let sessionID = created.session.session.sessionID
        #expect(!sessionID.isEmpty)
        #expect(created.session.session.activeBranchID == "branch-main")

        let branched = try await service.execute(
            makeCreateBranchRequest(sessionID: sessionID, parentBranchID: "branch-main")
        )
        #expect(branched.ok)
        #expect(branched.session.session.branches.count == 2)
        let derivedBranchID = branched.session.session.activeBranchID
        #expect(!derivedBranchID.isEmpty)
        #expect(derivedBranchID != "branch-main")

        var iterator = subscription.stream.makeAsyncIterator()
        let firstEvent = await iterator.next()
        let secondEvent = await iterator.next()
        await service.unsubscribe(subscription.subscriptionID)
        #expect(firstEvent?.eventType == "session.state_changed")
        #expect(firstEvent?.source == "session_graph")
        #expect(secondEvent?.eventType == "session.state_changed")
        #expect(secondEvent?.source == "session_graph")
        #expect(secondEvent?.sessionState.state.activeBranchID == derivedBranchID)
    }

    @Test("execute handles tool registration, resume, and close for sessions")
    func executeHandlesToolResumeAndCloseForSessions() async throws {
        let sessionStore = SessionGraphStore(
            sessions: [makeSessionState()],
            nowUnixMs: { 5_000 }
        )
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let registered = try await service.execute(
            makeRegisterToolResultRequest(
                sessionID: "session-1",
                branchID: "branch-alt",
                toolCallID: "tool-99"
            )
        )
        #expect(registered.ok)
        #expect(registered.session.session.activeBranchID == "branch-alt")
        #expect(registered.session.session.latestToolCallID == "tool-99")

        let resumed = try await service.execute(
            makeResumeAfterToolRequest(
                sessionID: "session-1",
                branchID: "branch-alt",
                snapshotID: "snap-tool"
            )
        )
        #expect(resumed.ok)
        #expect(resumed.session.session.latestSnapshotID == "snap-tool")
        #expect(resumed.session.session.branches.last?.resumeSnapshotID == "snap-tool")

        let closed = try await service.execute(makeCloseSessionRequest(sessionID: "session-1"))
        #expect(closed.ok)
        #expect(closed.session.session.sessionID == "session-1")

        let missing = try await service.execute(makeSessionStateRequest(sessionID: "session-1"))
        #expect(!missing.ok)
        #expect(missing.error.code == "not_found")
    }

    @Test("execute returns not found for invalid session mutation requests")
    func executeReturnsNotFoundForInvalidSessionMutations() async throws {
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let missingSession = try await service.execute(
            makeCreateBranchRequest(sessionID: "missing-session", parentBranchID: "branch-main")
        )
        let missingBranch = try await service.execute(
            makeRegisterToolResultRequest(
                sessionID: "session-1",
                branchID: "branch-missing",
                toolCallID: "tool-404"
            )
        )
        let missingResumeBranch = try await service.execute(
            makeResumeAfterToolRequest(
                sessionID: "session-1",
                branchID: "branch-missing",
                snapshotID: "snap-404"
            )
        )
        let missingClose = try await service.execute(makeCloseSessionRequest(sessionID: "missing-session"))

        #expect(!missingSession.ok)
        #expect(missingSession.error.code == "not_found")
        #expect(!missingBranch.ok)
        #expect(missingBranch.error.code == "not_found")
        #expect(!missingResumeBranch.ok)
        #expect(missingResumeBranch.error.code == "not_found")
        #expect(!missingClose.ok)
        #expect(missingClose.error.code == "not_found")
    }

    @Test("session mutation responses preserve correlation metadata")
    func sessionMutationResponsesPreserveCorrelationMetadata() async throws {
        let service = ControlPlaneService()
        var request = makeSessionCreateRequest()
        request.correlationID = "corr-session"
        request.causationID = "cause-session"

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.requestID == request.requestID)
        #expect(response.commandType == request.commandType)
        #expect(response.correlationID == "corr-session")
        #expect(response.causationID == "cause-session")
    }

    @Test("handshake includes live scheduler queue summary")
    func handshakeIncludesLiveSchedulerQueueSummary() async throws {
        let schedulerReadModel = SchedulerReadModel()
        _ = await schedulerReadModel.recordAdmitted(
            requestID: "req-live-queue",
            laneHint: "text.decode.interactive",
            priority: 100,
            workerID: "swift-text-worker",
            admissionLatencyMs: 3
        )
        let service = ControlPlaneService(schedulerReadModel: schedulerReadModel)

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-live-queue"

        let response = try await service.handshake(request)
        let interactiveLane = response.snapshot.queues.lanes.first { lane in
            lane.laneID == "text.decode.interactive"
        }

        #expect(response.snapshot.queues.activeRequests == 1)
        #expect(response.snapshot.queues.admittedRequests == 1)
        #expect(response.snapshot.queues.admissionLatencyMs == 3)
        #expect(response.snapshot.queues.backpressure == 1)
        #expect(interactiveLane?.activeRequests == 1)
        #expect(interactiveLane?.backpressure == 1)
    }

    @Test("handshake includes cache summary and session summaries")
    func handshakeIncludesCacheAndSessionSummaries() async throws {
        let cacheStore = CacheMetadataStore(snapshot: makeCacheSnapshot())
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(
            cacheMetadataStore: cacheStore,
            sessionGraphStore: sessionStore
        )

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-session-cache"

        let response = try await service.handshake(request)

        #expect(response.snapshot.cache.blockCount == 4)
        #expect(response.snapshot.cache.hotPrefixes.count == 1)
        #expect(response.snapshot.sessions.count == 1)
        #expect(response.snapshot.sessions.first?.sessionID == "session-1")
        #expect(response.snapshot.sessions.first?.branchCount == 2)
    }

    @Test("execute returns unimplemented for unsupported command families")
    func executeReturnsUnimplementedForUnsupportedCommandFamilies() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makePresetRequest())

        #expect(!response.ok)
        #expect(response.requestID == "req-preset-list")
        #expect(response.commandType == "preset.list")
        #expect(response.error.code == "unimplemented")
    }

    @Test("execute returns unimplemented for unsupported model and ops variants")
    func executeReturnsUnimplementedForUnsupportedVariants() async throws {
        let service = ControlPlaneService()

        let modelResponse = try await service.execute(makeModelPinRequest())
        let opsResponse = try await service.execute(makeOpsTraceRequest())

        #expect(!modelResponse.ok)
        #expect(modelResponse.error.code == "unimplemented")
        #expect(!opsResponse.ok)
        #expect(opsResponse.error.code == "unimplemented")
    }

    @Test("unsubscribe closes the subscription stream")
    func unsubscribeClosesSubscriptionStream() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()
        await service.unsubscribe(subscription.subscriptionID)

        var iterator = subscription.stream.makeAsyncIterator()
        let next = await iterator.next()

        #expect(next == nil)
    }

    private func makeServerSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-snapshot"
        request.commandType = "server.get_snapshot"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.getSnapshot = Melix_Controlplane_V1_GetServerSnapshot()
        return request
    }

    private func makeServerStartRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-start-\(serverSessionID)"
        request.commandType = "server.start"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.start = Melix_Controlplane_V1_StartServer()
        request.server.start.serverSessionID = serverSessionID
        return request
    }

    private func makeServerPauseRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-pause-\(serverSessionID)"
        request.commandType = "server.pause"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.pause = Melix_Controlplane_V1_PauseServer()
        request.server.pause.serverSessionID = serverSessionID
        return request
    }

    private func makeServerResumeRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-resume-\(serverSessionID)"
        request.commandType = "server.resume"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.resume = Melix_Controlplane_V1_ResumeServer()
        request.server.resume.serverSessionID = serverSessionID
        return request
    }

    private func makeServerWakeRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-wake-\(serverSessionID)"
        request.commandType = "server.wake"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.wake = Melix_Controlplane_V1_WakeServer()
        request.server.wake.serverSessionID = serverSessionID
        return request
    }

    private func makeServerStopRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-stop-\(serverSessionID)"
        request.commandType = "server.stop"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.stop = Melix_Controlplane_V1_StopServer()
        request.server.stop.serverSessionID = serverSessionID
        return request
    }

    private func makeServerRestartRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-restart-\(serverSessionID)"
        request.commandType = "server.restart"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.restart = Melix_Controlplane_V1_RestartServer()
        request.server.restart.serverSessionID = serverSessionID
        return request
    }

    private func makeServerSetIdlePolicyRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-idle-policy-\(serverSessionID)"
        request.commandType = "server.set_idle_policy"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.setIdlePolicy = Melix_Controlplane_V1_SetServerIdlePolicy()
        request.server.setIdlePolicy.serverSessionID = serverSessionID
        request.server.setIdlePolicy.autoSleepEnabled = autoSleepEnabled
        request.server.setIdlePolicy.lightSleepAfterSeconds = lightSleepAfterSeconds
        request.server.setIdlePolicy.deepSleepAfterSeconds = deepSleepAfterSeconds
        return request
    }

    private func makeApplyGatewayConfigRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        targetID: String? = nil,
        host: String,
        port: UInt32,
        defaultModelID: String,
        servedModelIDs: [String]? = nil,
        rateLimitPerMinute: UInt32,
        timeoutSeconds: UInt32,
        modelIdleTimeoutSeconds: UInt32 = 600
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-apply-gateway-config-\(serverSessionID)"
        request.commandType = "server.apply_gateway_config"
        request.targetID = targetID ?? serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyGatewayConfig = makeApplyGatewayConfigCommand(
            serverSessionID: serverSessionID,
            host: host,
            port: port,
            defaultModelID: defaultModelID,
            servedModelIDs: servedModelIDs ?? (defaultModelID.isEmpty ? [] : [defaultModelID]),
            rateLimitPerMinute: rateLimitPerMinute,
            timeoutSeconds: timeoutSeconds,
            modelIdleTimeoutSeconds: modelIdleTimeoutSeconds
        )
        return request
    }

    private func makeApplyServingDefaultsRequest(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        targetID: String? = nil,
        temperature: Double,
        topP: Double,
        maxTokens: UInt32,
        streamIntervalTokens: UInt32,
        maxConcurrentRequests: UInt32,
        concurrentProcessingEnabled: Bool = true,
        prefillBatchSize: UInt32 = 2,
        completionBatchSize: UInt32 = 2,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode = .baseline,
        draftModelID: String = "",
        numDraftTokens: UInt32 = 0
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-apply-serving-defaults-\(serverSessionID)"
        request.commandType = "server.apply_serving_defaults"
        request.targetID = targetID ?? serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyServingDefaults = makeApplyServingDefaultsCommand(
            serverSessionID: serverSessionID,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: maxConcurrentRequests,
            concurrentProcessingEnabled: concurrentProcessingEnabled,
            prefillBatchSize: prefillBatchSize,
            completionBatchSize: completionBatchSize,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens
        )
        return request
    }

    private func makeApplyImageDefaultsRequest(
        generateModelID: String,
        editModelID: String,
        size: String,
        steps: UInt32,
        guidance: Float,
        strength: Float,
        negativePrompt: String = ""
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-apply-image-defaults"
        request.commandType = "image.apply_defaults"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.applyDefaults = makeApplyImageDefaultsCommand(
            generateModelID: generateModelID,
            editModelID: editModelID,
            size: size,
            steps: steps,
            guidance: guidance,
            strength: strength,
            negativePrompt: negativePrompt
        )
        return request
    }

    private func makeApplyGatewayConfigCommand(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        host: String,
        port: UInt32,
        defaultModelID: String,
        servedModelIDs: [String]? = nil,
        rateLimitPerMinute: UInt32,
        timeoutSeconds: UInt32,
        modelIdleTimeoutSeconds: UInt32 = 600
    ) -> Melix_Controlplane_V1_ApplyGatewayConfig {
        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.serverSessionID = serverSessionID
        command.host = host
        command.port = port
        command.defaultModelID = defaultModelID
        command.servedModelIds = servedModelIDs ?? (defaultModelID.isEmpty ? [] : [defaultModelID])
        command.rateLimitPerMinute = rateLimitPerMinute
        command.timeoutSeconds = timeoutSeconds
        command.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
        return command
    }

    private func makeApplyServingDefaultsCommand(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        temperature: Double,
        topP: Double,
        maxTokens: UInt32,
        streamIntervalTokens: UInt32,
        maxConcurrentRequests: UInt32,
        concurrentProcessingEnabled: Bool = true,
        prefillBatchSize: UInt32 = 2,
        completionBatchSize: UInt32 = 2,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode = .baseline,
        draftModelID: String = "",
        numDraftTokens: UInt32 = 0
    ) -> Melix_Controlplane_V1_ApplyServingDefaults {
        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = serverSessionID
        command.temperature = temperature
        command.topP = topP
        command.maxTokens = maxTokens
        command.streamIntervalTokens = streamIntervalTokens
        command.maxConcurrentRequests = maxConcurrentRequests
        command.concurrentProcessingEnabled = concurrentProcessingEnabled
        command.prefillBatchSize = prefillBatchSize
        command.completionBatchSize = completionBatchSize
        command.accelerationMode = accelerationMode
        command.draftModelID = draftModelID
        command.numDraftTokens = numDraftTokens
        return command
    }

    private func makeApplyImageDefaultsCommand(
        generateModelID: String,
        editModelID: String,
        size: String,
        steps: UInt32,
        guidance: Float,
        strength: Float,
        negativePrompt: String = ""
    ) -> Melix_Controlplane_V1_ApplyImageDefaults {
        var command = Melix_Controlplane_V1_ApplyImageDefaults()
        command.generateModelID = generateModelID
        command.editModelID = editModelID
        command.size = size
        command.steps = steps
        command.guidance = guidance
        command.strength = strength
        command.negativePrompt = negativePrompt
        return command
    }

    private func makeListModelsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-list"
        request.commandType = "model.list"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.list = Melix_Controlplane_V1_ListModels()
        return request
    }

    private func makeLoadModelRequest(
        modelID: String,
        memoryBudgetBytes: UInt64 = 0
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-load-\(modelID)"
        request.commandType = "model.load"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.load = Melix_Controlplane_V1_LoadModel()
        request.model.load.modelID = modelID
        request.model.load.memoryBudgetBytes = memoryBudgetBytes
        return request
    }

    private func makeUnloadModelRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-unload-\(modelID)"
        request.commandType = "model.unload"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.unload = Melix_Controlplane_V1_UnloadModel()
        request.model.unload.modelID = modelID
        return request
    }

    private func makeImageGenerateRequest(
        requestID: String = "req-image-generate",
        modelID: String,
        prompt: String,
        size: String,
        n: UInt32,
        steps: UInt32 = 0,
        guidance: Float = 0,
        negativePrompt: String = ""
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = requestID
        request.commandType = "image.generate"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.generate = Melix_Controlplane_V1_GenerateImage()
        request.image.generate.modelID = modelID
        request.image.generate.prompt = prompt
        request.image.generate.size = size
        request.image.generate.steps = steps
        request.image.generate.guidance = guidance
        request.image.generate.negativePrompt = negativePrompt
        request.image.generate.n = n
        request.image.generate.responseFormat = "png"
        return request
    }

    private func makeImageEditRequest(
        requestID: String = "req-image-edit",
        modelID: String,
        prompt: String,
        imageURI: String,
        maskURI: String,
        strength: Float,
        size: String = "1024x1024",
        steps: UInt32 = 0,
        guidance: Float = 0,
        negativePrompt: String = ""
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = requestID
        request.commandType = "image.edit"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.edit = Melix_Controlplane_V1_EditImage()
        request.image.edit.modelID = modelID
        request.image.edit.prompt = prompt
        request.image.edit.imageUri = imageURI
        request.image.edit.maskUri = maskURI
        request.image.edit.strength = strength
        request.image.edit.size = size
        request.image.edit.steps = steps
        request.image.edit.guidance = guidance
        request.image.edit.negativePrompt = negativePrompt
        request.image.edit.n = 1
        request.image.edit.responseFormat = "png"
        return request
    }

    private func makeMetricsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-metrics"
        request.commandType = "ops.get_metrics"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.getMetrics = Melix_Controlplane_V1_GetMetricsSnapshot()
        return request
    }

    private func makeRunDoctorRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-doctor"
        request.commandType = "ops.run_doctor"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runDoctor = Melix_Controlplane_V1_RunDoctor()
        return request
    }

    private func makeSearchHubModelsRequest(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-search-hub-models"
        request.commandType = "ops.search_hub_models"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.searchHubModels = Melix_Controlplane_V1_SearchHubModels()
        request.ops.searchHubModels.query = query
        request.ops.searchHubModels.pageSize = pageSize
        request.ops.searchHubModels.cursor = cursor
        request.ops.searchHubModels.mlxOnly = mlxOnly
        return request
    }

    private func makeGetHubModelCardRequest(
        repoID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-get-hub-model-card"
        request.commandType = "ops.get_hub_model_card"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.getHubModelCard = Melix_Controlplane_V1_GetHubModelCard()
        request.ops.getHubModelCard.repoID = repoID
        return request
    }

    private func makeRunBenchRequest(
        modelID: String = "",
        hfRepoID: String = "",
        suites: [String] = ["smoke", "latency"],
        contextLengths: [UInt32] = [1024, 4096],
        generationLength: UInt32 = 128,
        batchSizes: [UInt32] = [2, 4],
        repeats: UInt32 = 3,
        cacheProfile: String = "partial_prefix",
        reasoningMode: String = "enabled",
        structuredOutputMode: String = "json_schema",
        parameters: [String: String] = [:]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-bench"
        request.commandType = "ops.run_bench"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runBench = Melix_Controlplane_V1_RunBench()
        request.ops.runBench.modelID = modelID
        request.ops.runBench.hfRepoID = hfRepoID
        request.ops.runBench.suites = suites
        request.ops.runBench.contextLengths = contextLengths
        request.ops.runBench.generationLength = generationLength
        request.ops.runBench.batchSizes = batchSizes
        request.ops.runBench.repeats = repeats
        request.ops.runBench.cacheProfile = cacheProfile
        request.ops.runBench.reasoningMode = reasoningMode
        request.ops.runBench.structuredOutputMode = structuredOutputMode
        request.ops.runBench.parameters = parameters
        return request
    }

    private func makeRunBenchMatrixRequest(
        modelID: String = "melix-dev-text",
        hfRepoID: String = "",
        suites: [String] = ["smoke"],
        contextLengths: [UInt32] = [1024, 4096],
        generationLengths: [UInt32] = [128, 256],
        batchSizes: [UInt32] = [2, 4],
        cacheProfiles: [String] = ["cold", "warm"],
        reasoningModes: [String] = ["enabled", "disabled"],
        structuredOutputModes: [String] = ["plain_text", "json_schema"],
        concurrencyLevels: [UInt32] = [1, 8],
        repeats: UInt32 = 3,
        requests: UInt32 = 24,
        durationSeconds: UInt32 = 0,
        allowLargeMatrix: Bool = false
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-bench-matrix"
        request.commandType = "ops.run_bench_matrix"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runBenchMatrix = Melix_Controlplane_V1_RunBenchMatrix()
        request.ops.runBenchMatrix.modelID = modelID
        request.ops.runBenchMatrix.hfRepoID = hfRepoID
        request.ops.runBenchMatrix.suiteIds = suites
        request.ops.runBenchMatrix.contextLengths = contextLengths
        request.ops.runBenchMatrix.generationLengths = generationLengths
        request.ops.runBenchMatrix.batchSizes = batchSizes
        request.ops.runBenchMatrix.cacheProfiles = cacheProfiles
        request.ops.runBenchMatrix.reasoningModes = reasoningModes
        request.ops.runBenchMatrix.structuredOutputModes = structuredOutputModes
        request.ops.runBenchMatrix.concurrencyLevels = concurrencyLevels
        request.ops.runBenchMatrix.repeats = repeats
        request.ops.runBenchMatrix.requests = requests
        request.ops.runBenchMatrix.durationSeconds = durationSeconds
        request.ops.runBenchMatrix.allowLargeMatrix = allowLargeMatrix
        return request
    }

    private func makeBenchmarkMatrixJobSummary(
        jobID: String,
        modelID: String
    ) -> Melix_Controlplane_V1_BenchmarkMatrixJobSummary {
        var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
        job.schemaVersion = "melix.benchmark_matrix_job.v1"
        job.jobID = jobID
        job.modelID = modelID
        job.taskKind = "text-generation"
        job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
        job.suiteIds = ["smoke"]
        job.benchmarkMode = "matrix"
        job.status = "completed"
        job.outputDir = "/tmp/melix/bench/matrix-runs/\(jobID)"
        job.createdAtUnixMs = 1712200000000
        job.updatedAtUnixMs = 1712200005000
        return job
    }

    private func makeBenchmarkMatrixResponse(
        jobID: String,
        modelID: String
    ) -> Melix_Worker_V1_RunBenchMatrixResponse {
        var response = Melix_Worker_V1_RunBenchMatrixResponse()
        response.job = Melix_Worker_V1_BenchmarkMatrixJobSummary()
        response.job.schemaVersion = "melix.benchmark_matrix_job.v1"
        response.job.jobID = jobID
        response.job.modelID = modelID
        response.job.taskKind = "text-generation"
        response.job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
        response.job.suiteIds = ["smoke"]
        response.job.benchmarkMode = "matrix"
        response.job.status = "completed"
        response.job.outputDir = "/tmp/melix/bench/matrix-runs/\(jobID)"
        response.job.createdAtUnixMs = 1712200000000
        response.job.updatedAtUnixMs = 1712200005000
        var row = Melix_Worker_V1_BenchmarkMatrixSummaryRow()
        row.jobID = jobID
        row.taskKind = "text-generation"
        row.sourceRepo = "HuggingFaceH4/ultrachat_200k"
        row.modelID = modelID
        row.suiteID = "smoke"
        row.contextLength = 1024
        row.generationLength = 128
        row.batchSize = 2
        row.cacheProfile = "cold"
        row.reasoningMode = "enabled"
        row.structuredOutputMode = "plain_text"
        row.concurrencyLevel = 1
        row.repeats = 3
        row.requests = 24
        row.ttftMeanMs = 24.45
        row.createdAtUnixMs = 1712200000000
        response.summaryRows = [row]
        return response
    }

    private func makeBenchmarkHubModelCardResponse(
        repoID: String,
        modelName: String,
        pipelineTag: String,
        mlxCompatible: Bool = true,
        tags: [String] = ["mlx"],
        siblingFiles: [String] = ["config.json", "tokenizer.json"]
    ) -> Melix_Worker_V1_GetHubModelCardResponse {
        var response = Melix_Worker_V1_GetHubModelCardResponse()
        response.ok = true
        response.card = Melix_Worker_V1_HubModelCard()
        response.card.repoID = repoID
        response.card.author = repoID.split(separator: "/").first.map(String.init) ?? "mlx-community"
        response.card.modelName = modelName
        response.card.pipelineTag = pipelineTag
        response.card.mlxCompatible = mlxCompatible
        response.card.tags = tags
        response.card.siblingFiles = siblingFiles
        return response
    }

    private func makeBenchmarkLifecycleEvents(
        jobID: String,
        reportPath: String
    ) -> [Melix_Worker_V1_RunBenchEvent] {
        [
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = jobID
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
                return event
            }(),
        ]
    }

    private func makeRunEvaluationRequest(
        modelID: String = "melix-dev-text",
        hfRepoID: String = "",
        suiteID: String = "qa_smoke",
        datasetID: String = "qa_smoke.dev.v1"
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-evaluation"
        request.commandType = "ops.run_evaluation"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runEvaluation = Melix_Controlplane_V1_RunEvaluation()
        request.ops.runEvaluation.modelID = modelID
        request.ops.runEvaluation.hfRepoID = hfRepoID
        request.ops.runEvaluation.suiteID = suiteID
        request.ops.runEvaluation.datasetID = datasetID
        request.ops.runEvaluation.sampleSize = 8
        request.ops.runEvaluation.fewShot = 4
        request.ops.runEvaluation.seed = 7
        request.ops.runEvaluation.scoringMode = "multiple_choice_accuracy"
        request.ops.runEvaluation.codeExecPolicy = "sandboxed"
        request.ops.runEvaluation.parameters = [
            "judge": "deterministic",
        ]
        return request
    }

    private func makeExportResultsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-export"
        request.commandType = "ops.export_results"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.exportResults = Melix_Controlplane_V1_ExportResults()
        request.ops.exportResults.outputDir = "/tmp/melix-export"
        return request
    }

    private func makeSubmitResultsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-submit"
        request.commandType = "ops.submit_results"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.submitResults = Melix_Controlplane_V1_SubmitResults()
        request.ops.submitResults.outputDir = "/tmp/melix-export"
        request.ops.submitResults.deviceMetadata = [
            "melix_version": "0.1.0",
        ]
        return request
    }

    private func makeCancelRequest(
        requestID targetRequestID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-cancel-\(targetRequestID)"
        request.commandType = "ops.cancel_request"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.cancelRequest = Melix_Controlplane_V1_CancelRequest()
        request.ops.cancelRequest.requestID = targetRequestID
        return request
    }

    private func makeCacheSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-cache-snapshot"
        request.commandType = "cache.get_snapshot"
        request.cache = Melix_Controlplane_V1_CacheCommand()
        request.cache.getSnapshot = Melix_Controlplane_V1_GetCacheSnapshot()
        return request
    }

    private func makeSessionStateRequest(sessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-state-\(sessionID)"
        request.commandType = "session.get_state"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.getState = Melix_Controlplane_V1_GetSessionState()
        request.session.getState.sessionID = sessionID
        return request
    }

    private func makeSessionCreateRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-create"
        request.commandType = "session.create"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.createSession = Melix_Controlplane_V1_CreateSession()
        return request
    }

    private func makeCreateBranchRequest(
        sessionID: String,
        parentBranchID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-branch-\(sessionID)"
        request.commandType = "session.create_branch"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.createBranch = Melix_Controlplane_V1_CreateBranch()
        request.session.createBranch.sessionID = sessionID
        request.session.createBranch.parentBranchID = parentBranchID
        return request
    }

    private func makeRegisterToolResultRequest(
        sessionID: String,
        branchID: String,
        toolCallID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-tool-\(toolCallID)"
        request.commandType = "session.register_tool_result"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.registerToolResult = Melix_Controlplane_V1_RegisterToolResult()
        request.session.registerToolResult.sessionID = sessionID
        request.session.registerToolResult.branchID = branchID
        request.session.registerToolResult.toolCallID = toolCallID
        return request
    }

    private func makeResumeAfterToolRequest(
        sessionID: String,
        branchID: String,
        snapshotID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-resume-\(snapshotID)"
        request.commandType = "session.resume_after_tool"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.resumeAfterTool = Melix_Controlplane_V1_ResumeAfterTool()
        request.session.resumeAfterTool.sessionID = sessionID
        request.session.resumeAfterTool.branchID = branchID
        request.session.resumeAfterTool.snapshotID = snapshotID
        return request
    }

    private func makeCloseSessionRequest(sessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-close-\(sessionID)"
        request.commandType = "session.close"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.closeSession = Melix_Controlplane_V1_CloseSession()
        request.session.closeSession.sessionID = sessionID
        return request
    }

    private func makePresetRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-preset-list"
        request.commandType = "preset.list"
        request.preset = Melix_Controlplane_V1_PresetCommand()
        request.preset.list = Melix_Controlplane_V1_ListPresets()
        return request
    }

    private func makeModelPinRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-pin"
        request.commandType = "model.pin"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.pin = Melix_Controlplane_V1_PinModel()
        request.model.pin.modelID = "melix-dev-text"
        return request
    }

    private func makeOpsTraceRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-tail-logs"
        request.commandType = "ops.tail_logs"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.tailLogs = Melix_Controlplane_V1_TailLogs()
        return request
    }

    private func makeSetModelPolicyRequest(
        modelID: String,
        values: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-set-policy-\(modelID)"
        request.commandType = "model.set_policy"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.setPolicy = Melix_Controlplane_V1_SetModelPolicy()
        request.model.setPolicy.modelID = modelID
        request.model.setPolicy.values = values
        return request
    }

    private func makeGetModelInfoRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-get-info-\(modelID)"
        request.commandType = "model.get_info"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.getInfo = Melix_Controlplane_V1_GetModelInfo()
        request.model.getInfo.modelID = modelID
        return request
    }

    private func makeRunModelOperationRequest(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String = "",
        weightQuant: String = "",
        kvQuant: String = "",
        ext: [String: String] = [:]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-run-operation-\(modelID)-\(operation)"
        request.commandType = "model.run_operation"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.runOperation = Melix_Controlplane_V1_RunModelOperation()
        request.model.runOperation.modelID = modelID
        request.model.runOperation.operation = operation
        request.model.runOperation.outputDir = outputDir
        request.model.runOperation.weightQuant = weightQuant
        request.model.runOperation.kvQuant = kvQuant
        request.model.runOperation.generateManifest = true
        request.model.runOperation.runSmokeTest = true
        request.model.runOperation.ext = ext
        if !quantProfileID.isEmpty {
            request.model.runOperation.quantProfile = Melix_Controlplane_V1_QuantizationProfile()
            request.model.runOperation.quantProfile.algorithm = "oq"
            request.model.runOperation.quantProfile.schemaVersion = "melix.quant_profile.v1"
            request.model.runOperation.quantProfile.quantProfileID = quantProfileID
            request.model.runOperation.quantProfile.weightQuant = quantProfileID
            request.model.runOperation.quantProfile.kvQuant = kvQuant
        }
        return request
    }

    private func makeRegistrySnapshotManifestJSON(
        models: [[String: Any]]? = nil,
        derivedModels: [[String: Any]] = []
    ) throws -> String {
        let payload: [String: Any] = [
            "operation": "registry_snapshot",
            "derived_models": derivedModels,
            "model_registry": [
                "scanned_at_unix_ms": 1_711_955_200_000,
                "roots": [
                    [
                        "root_id": "root-1",
                        "root_path": "/tmp/registry-root",
                        "accessible": true,
                        "error_code": "",
                        "error_message": "",
                        "discovered_model_ids": ["mlx-community/Qwen2.5-7B-Instruct/4bit"],
                    ],
                ],
                "models": models ?? [
                    [
                        "model_id": "mlx-community/Qwen2.5-7B-Instruct/4bit",
                        "model_path": "/tmp/registry-root/mlx-community/Qwen2.5-7B-Instruct/4bit",
                        "model_kind": "text",
                        "revision": "registry",
                        "tokenizer_hash": "tok-registry",
                        "quant_profile_id": "q4",
                        "parser_mode": "text",
                        "reasoning_mode": "off",
                        "max_context": 16384,
                        "ext": [
                            "melix.registry_root_id": "root-1",
                            "melix.registry_root_path": "/tmp/registry-root",
                            "melix.registry_relative_path": "mlx-community/Qwen2.5-7B-Instruct/4bit",
                            "melix.model_path": "/tmp/registry-root/mlx-community/Qwen2.5-7B-Instruct/4bit",
                        ],
                    ],
                ],
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }

    private func makeCacheSnapshot() -> Melix_Controlplane_V1_CacheSnapshot {
        var summary = Melix_Controlplane_V1_CacheSummary()
        summary.l1Bytes = 2048
        summary.l2Bytes = 8192
        summary.blockCount = 4
        summary.checkpointCount = 1
        summary.compressionRatio = 2.5
        summary.l2RestoreHitRate = 0.5

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA, 0xBB])
        cacheKey.scope = Melix_Controlplane_V1_CacheScopeKey()
        cacheKey.scope.modelID = "melix-dev-text"
        cacheKey.scope.revision = "main"
        cacheKey.scope.tokenizerHash = "tok-1"
        cacheKey.scope.quantProfileID = "q4"

        var prefix = Melix_Controlplane_V1_PrefixRef()
        prefix.prefixID = "prefix-1"
        prefix.cacheKey = cacheKey
        prefix.tokenLength = 64
        prefix.tier = "l1"
        prefix.pinned = true

        var block = Melix_Controlplane_V1_CacheBlockRef()
        block.blockID = "block-1"
        block.tokenLength = 64
        block.bytes = 2048

        var snapshotRef = Melix_Controlplane_V1_SnapshotRef()
        snapshotRef.snapshotID = "snap-1"
        snapshotRef.tokenBoundary = 64
        snapshotRef.requestID = "req-main"
        snapshotRef.sessionID = "session-1"
        snapshotRef.branchID = "branch-main"
        snapshotRef.checkpointID = "ckpt-main"

        var scope = Melix_Controlplane_V1_CacheScopeSummary()
        scope.scopeID = "scope-1"
        scope.scope = cacheKey.scope
        scope.l1Bytes = 2048
        scope.l2Bytes = 8192
        scope.blockCount = 4
        scope.prefixCount = 1
        scope.snapshotCount = 1
        scope.hotBlocks = [block]
        scope.recentSnapshots = [snapshotRef]

        summary.hotKeys = [cacheKey]
        summary.hotPrefixes = [prefix]
        summary.recentSnapshots = [snapshotRef]

        var snapshot = Melix_Controlplane_V1_CacheSnapshot()
        snapshot.summary = summary
        snapshot.scopes = [scope]
        snapshot.pinnedPrefixes = [prefix]
        snapshot.hotPrefixes = [prefix]
        snapshot.snapshots = [snapshotRef]
        return snapshot
    }

    private func makeSessionState() -> Melix_Controlplane_V1_SessionState {
        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA])
        cacheKey.scope = Melix_Controlplane_V1_CacheScopeKey()
        cacheKey.scope.modelID = "melix-dev-text"
        cacheKey.scope.revision = "main"

        var branchMain = Melix_Controlplane_V1_BranchState()
        branchMain.branchID = "branch-main"
        branchMain.parentBranchID = ""
        branchMain.headRequestID = "req-main"
        branchMain.headCheckpointID = "ckpt-main"
        branchMain.resumeSnapshotID = "snap-1"
        branchMain.lastToolCallID = "tool-1"
        branchMain.label = "main"
        branchMain.createdAtUnixMs = 1000
        branchMain.updatedAtUnixMs = 2000
        branchMain.headCacheKey = cacheKey

        var branchAlt = Melix_Controlplane_V1_BranchState()
        branchAlt.branchID = "branch-alt"
        branchAlt.parentBranchID = "branch-main"
        branchAlt.headRequestID = "req-alt"
        branchAlt.headCheckpointID = "ckpt-alt"
        branchAlt.resumeSnapshotID = "snap-2"
        branchAlt.lastToolCallID = "tool-2"
        branchAlt.label = "alternate"
        branchAlt.createdAtUnixMs = 3000
        branchAlt.updatedAtUnixMs = 4000
        branchAlt.headCacheKey = cacheKey

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-1"
        snapshot.tokenBoundary = 64
        snapshot.requestID = "req-main"
        snapshot.sessionID = "session-1"
        snapshot.branchID = "branch-main"
        snapshot.checkpointID = "ckpt-main"

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = "session-1"
        session.branches = [branchMain, branchAlt]
        session.activeBranchID = "branch-main"
        session.latestRequestID = "req-main"
        session.latestCheckpointID = "ckpt-main"
        session.latestSnapshotID = "snap-1"
        session.createdAtUnixMs = 1000
        session.updatedAtUnixMs = 4000
        session.latestToolCallID = "tool-2"
        session.availableSnapshots = [snapshot]
        return session
    }
}

private actor ScriptedImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private(set) var lastImageGenerateRequest: Melix_Worker_V1_ImageGenerateRequest?
    private(set) var lastImageEditRequest: Melix_Worker_V1_ImageEditRequest?
    private var imageGenerateResponse = Melix_Worker_V1_ImageGenerateResponse()
    private var imageEditResponse = Melix_Worker_V1_ImageEditResponse()
    private var imageGenerateError: Error?
    private var imageEditError: Error?

    func setImageGenerateResponse(_ response: Melix_Worker_V1_ImageGenerateResponse) {
        imageGenerateResponse = response
        imageGenerateError = nil
    }

    func setImageEditResponse(_ response: Melix_Worker_V1_ImageEditResponse) {
        imageEditResponse = response
        imageEditError = nil
    }

    func setImageGenerateError(_ error: Error) {
        imageGenerateError = error
    }

    func setImageEditError(_ error: Error) {
        imageEditError = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        lastImageGenerateRequest = request
        if let imageGenerateError {
            throw imageGenerateError
        }
        return imageGenerateResponse
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        lastImageEditRequest = request
        if let imageEditError {
            throw imageEditError
        }
        return imageEditResponse
    }
}

private enum ImageWorkerFailure: Error {
    case synthetic
}

private actor BlockingImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private var generateRequests: [String: Melix_Worker_V1_ImageGenerateRequest] = [:]
    private var generateContinuations: [String: CheckedContinuation<Melix_Worker_V1_ImageGenerateResponse, Error>] = [:]

    private(set) var startedRequestIDs: [String] = []
    private(set) var abortedRequestIDs: [String] = []

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        abortedRequestIDs.append(requestID)
        guard let request = generateRequests.removeValue(forKey: requestID),
              let continuation = generateContinuations.removeValue(forKey: requestID) else {
            return false
        }

        var response = Melix_Worker_V1_ImageGenerateResponse()
        response.job.requestID = requestID
        response.job.jobID = "\(requestID)::image-generate"
        response.job.modelHandle = request.modelHandle
        response.job.operation = "image_generate"
        response.job.state = .imageJobCanceled
        response.job.progress.stage = "canceled"
        response.job.error.code = "cancelled"
        response.job.error.message = "Image generation was canceled."
        response.error.code = "cancelled"
        response.error.message = "Image generation was canceled."
        continuation.resume(returning: response)
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        let requestID = request.id.requestID
        startedRequestIDs.append(requestID)
        generateRequests[requestID] = request
        return try await withCheckedThrowingContinuation { continuation in
            generateContinuations[requestID] = continuation
        }
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        Melix_Worker_V1_ImageEditResponse()
    }

    func finishGenerate(requestID: String) {
        guard let request = generateRequests.removeValue(forKey: requestID),
              let continuation = generateContinuations.removeValue(forKey: requestID) else {
            return
        }

        var response = Melix_Worker_V1_ImageGenerateResponse()
        response.job.requestID = requestID
        response.job.jobID = "\(requestID)::image-generate"
        response.job.modelHandle = request.modelHandle
        response.job.operation = "image_generate"
        response.job.state = .imageJobCompleted
        response.job.progress.stage = "completed"
        response.job.progress.pct = 1
        response.job.artifacts = [makeWorkerArtifact(jobID: "\(requestID)::image-generate")]
        continuation.resume(returning: response)
    }
}

private actor AbortFalseImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        _ = request
        return Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        _ = request
        return Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        _ = request
        return Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        _ = request
        return Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        _ = request
        return Melix_Worker_V1_ImageGenerateResponse()
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        _ = request
        return Melix_Worker_V1_ImageEditResponse()
    }
}

private actor ThrowingAbortImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        throw WorkerClientError.unavailable
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(request: Melix_Worker_V1_EmbedRequest) async throws -> Melix_Worker_V1_EmbedResponse {
        _ = request
        return Melix_Worker_V1_EmbedResponse()
    }

    func rerank(request: Melix_Worker_V1_RerankRequest) async throws -> Melix_Worker_V1_RerankResponse {
        _ = request
        return Melix_Worker_V1_RerankResponse()
    }

    func transcribe(request: Melix_Worker_V1_TranscribeRequest) async throws -> Melix_Worker_V1_TranscribeResponse {
        _ = request
        return Melix_Worker_V1_TranscribeResponse()
    }

    func speak(request: Melix_Worker_V1_SpeakRequest) async throws -> Melix_Worker_V1_SpeakResponse {
        _ = request
        return Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        _ = request
        return Melix_Worker_V1_ImageGenerateResponse()
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        _ = request
        return Melix_Worker_V1_ImageEditResponse()
    }
}

private actor StubImageJobAdmissionController: ImageJobAdmissionControlling {
    private let acquireError: Error?
    private let cancelDisposition: ImageJobCancelDisposition

    init(
        acquireError: Error? = nil,
        cancelDisposition: ImageJobCancelDisposition = .running
    ) {
        self.acquireError = acquireError
        self.cancelDisposition = cancelDisposition
    }

    func acquire(
        requestID: String,
        laneHint: String,
        workerID: String,
        priority: Int32
    ) async throws {
        _ = requestID
        _ = laneHint
        _ = workerID
        _ = priority
        if let acquireError {
            throw acquireError
        }
    }

    func finish(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        workerID: String?
    ) async {
        _ = requestID
        _ = phase
        _ = workerID
    }

    func cancel(requestID: String) async -> ImageJobCancelDisposition {
        _ = requestID
        return cancelDisposition
    }
}

private actor BlockingAbortTextWorkerClient: WorkerRoutingClient {
    private let abortError: Error?
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]

    private(set) var startedRequestIDs: [String] = []

    init(abortError: Error? = nil) {
        self.abortError = abortError
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        let requestID = request.execution.id.requestID
        startedRequestIDs.append(requestID)
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        if let abortError {
            throw abortError
        }
        guard let continuation = continuations.removeValue(forKey: requestID) else {
            return false
        }
        continuation.finish()
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.modelHandle = request.model.modelID
        return response
    }

    func emitToken(requestID: String, text: String) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.tokenDelta = Melix_Worker_V1_TokenDelta()
        event.tokenDelta.text = text
        continuation.yield(event)
    }

    func finishDecode(requestID: String, assistantText: String) {
        guard let continuation = continuations.removeValue(forKey: requestID) else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.completed = Melix_Worker_V1_Completed()
        event.completed.finishReason = "stop"
        event.completed.assistantText = assistantText
        continuation.yield(event)
        continuation.finish()
    }
}

private func makeWorkerArtifact(
    jobID: String,
    role: Melix_Worker_V1_ImageArtifactRole = .imageArtifactGenerated,
    artifactID: String = "artifact-0"
) -> Melix_Worker_V1_ImageArtifactMetadata {
    var artifact = Melix_Worker_V1_ImageArtifactMetadata()
    artifact.artifactID = "\(jobID)::\(artifactID)"
    artifact.jobID = jobID
    artifact.role = role
    artifact.mimeType = "image/png"
    artifact.format = "png"
    artifact.width = 512
    artifact.height = 512
    artifact.byteLength = 32
    artifact.storageUri = "/tmp/\(artifactID).png"
    artifact.sha256 = "sha256-\(artifactID)"
    artifact.variantIndex = 0
    return artifact
}

private func waitForControlPlaneCondition(
    _ description: String,
    timeout: Duration = .milliseconds(500),
    pollInterval: Duration = .milliseconds(10),
    condition: @escaping @Sendable () async -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }
    throw ControlPlaneConditionTimeoutError(description: description)
}

private struct ControlPlaneConditionTimeoutError: Error, CustomStringConvertible {
    let description: String
}

private actor ModelLifecycleWorkerClient: WorkerRoutingClient {
    private var loadResponse = Melix_Worker_V1_LoadModelResponse()
    private var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
    private var loadError: Error?
    private var unloadError: Error?
    private(set) var loadRequests: [Melix_Worker_V1_LoadModelRequest] = []
    private(set) var unloadRequests: [Melix_Worker_V1_UnloadModelRequest] = []
    private(set) var recordedOperations: [String] = []

    func setLoadResponse(_ response: Melix_Worker_V1_LoadModelResponse) {
        loadResponse = response
    }

    func setUnloadResponse(_ response: Melix_Worker_V1_UnloadModelResponse) {
        unloadResponse = response
    }

    func setLoadError(_ error: Error?) {
        loadError = error
    }

    func setUnloadError(_ error: Error?) {
        unloadError = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadRequests.append(request)
        recordedOperations.append("load:\(request.model.modelID)")
        if let loadError {
            throw loadError
        }
        return loadResponse
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadRequests.append(request)
        recordedOperations.append("unload:\(request.modelHandle)")
        if let unloadError {
            throw unloadError
        }
        return unloadResponse
    }
}

private actor ScriptedModelOperationsWorkerClient: WorkerRoutingClient, ModelOperationsWorkerClientProtocol {
    private(set) var lastInfoRequest: Melix_Worker_V1_GetModelInfoRequest?
    private(set) var lastConvertRequest: Melix_Worker_V1_ConvertModelRequest?
    private(set) var convertRequests: [Melix_Worker_V1_ConvertModelRequest] = []
    private(set) var lastDoctorRequest: Melix_Worker_V1_RunDoctorRequest?
    private(set) var lastHubSearchRequest: Melix_Worker_V1_SearchHubModelsRequest?
    private(set) var lastHubModelCardRequest: Melix_Worker_V1_GetHubModelCardRequest?
    private(set) var lastBenchRequest: Melix_Worker_V1_RunBenchRequest?
    private(set) var lastBenchMatrixRequest: Melix_Worker_V1_RunBenchMatrixRequest?
    private(set) var lastEvaluationRequest: Melix_Worker_V1_RunEvaluationRequest?
    private(set) var lastExportRequest: Melix_Worker_V1_ExportResultsRequest?
    private(set) var lastSubmitRequest: Melix_Worker_V1_SubmitResultsRequest?
    private var infoResponse = Melix_Worker_V1_GetModelInfoResponse()
    private var convertEvents: [Melix_Worker_V1_ConvertModelEvent] = []
    private var convertEventBatches: [[Melix_Worker_V1_ConvertModelEvent]] = []
    private var doctorResponse = Melix_Worker_V1_RunDoctorResponse()
    private var hubSearchResponse = Melix_Worker_V1_SearchHubModelsResponse()
    private var hubModelCardResponse = Melix_Worker_V1_GetHubModelCardResponse()
    private var benchEvents: [Melix_Worker_V1_RunBenchEvent] = []
    private var benchMatrixResponse = Melix_Worker_V1_RunBenchMatrixResponse()
    private var evaluationResponse = Melix_Worker_V1_RunEvaluationResponse()
    private var exportResponse = Melix_Worker_V1_ExportResultsResponse()
    private var submitResponse = Melix_Worker_V1_SubmitResultsResponse()
    private var infoError: Error?
    private var convertError: Error?
    private var doctorError: Error?
    private var hubSearchError: Error?
    private var hubModelCardError: Error?
    private var benchError: Error?
    private var benchMatrixError: Error?
    private var evaluationError: Error?

    func setInfoResponse(_ response: Melix_Worker_V1_GetModelInfoResponse) {
        infoResponse = response
    }

    func setConvertEvents(_ events: [Melix_Worker_V1_ConvertModelEvent]) {
        convertEvents = events
        convertEventBatches = []
    }

    func setConvertEventBatches(_ batches: [[Melix_Worker_V1_ConvertModelEvent]]) {
        convertEventBatches = batches
    }

    func setDoctorResponse(_ response: Melix_Worker_V1_RunDoctorResponse) {
        doctorResponse = response
    }

    func setHubSearchResponse(_ response: Melix_Worker_V1_SearchHubModelsResponse) {
        hubSearchResponse = response
    }

    func setHubModelCardResponse(_ response: Melix_Worker_V1_GetHubModelCardResponse) {
        hubModelCardResponse = response
    }

    func setBenchEvents(_ events: [Melix_Worker_V1_RunBenchEvent]) {
        benchEvents = events
    }

    func setBenchMatrixResponse(_ response: Melix_Worker_V1_RunBenchMatrixResponse) {
        benchMatrixResponse = response
    }

    func setEvaluationResponse(_ response: Melix_Worker_V1_RunEvaluationResponse) {
        evaluationResponse = response
    }

    func setInfoError(_ error: Error?) {
        infoError = error
    }

    func setConvertError(_ error: Error?) {
        convertError = error
    }

    func setDoctorError(_ error: Error?) {
        doctorError = error
    }

    func setHubSearchError(_ error: Error?) {
        hubSearchError = error
    }

    func setHubModelCardError(_ error: Error?) {
        hubModelCardError = error
    }

    func setBenchError(_ error: Error?) {
        benchError = error
    }

    func setBenchMatrixError(_ error: Error?) {
        benchMatrixError = error
    }

    func setEvaluationError(_ error: Error?) {
        evaluationError = error
    }

    func setExportResponse(_ response: Melix_Worker_V1_ExportResultsResponse) {
        exportResponse = response
    }

    func setSubmitResponse(_ response: Melix_Worker_V1_SubmitResultsResponse) {
        submitResponse = response
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        lastInfoRequest = request
        if let infoError {
            throw infoError
        }
        return infoResponse
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        lastConvertRequest = request
        convertRequests.append(request)
        if let convertError {
            throw convertError
        }
        let events: [Melix_Worker_V1_ConvertModelEvent]
        if convertEventBatches.isEmpty {
            events = convertEvents
        } else {
            events = convertEventBatches.removeFirst()
        }
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        lastDoctorRequest = request
        if let doctorError {
            throw doctorError
        }
        return doctorResponse
    }

    func searchHubModels(
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        lastHubSearchRequest = request
        if let hubSearchError {
            throw hubSearchError
        }
        return hubSearchResponse
    }

    func getHubModelCard(
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        lastHubModelCardRequest = request
        if let hubModelCardError {
            throw hubModelCardError
        }
        return hubModelCardResponse
    }

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        lastBenchRequest = request
        if let benchError {
            throw benchError
        }
        let events = benchEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func runBenchMatrix(
        request: Melix_Worker_V1_RunBenchMatrixRequest
    ) async throws -> Melix_Worker_V1_RunBenchMatrixResponse {
        lastBenchMatrixRequest = request
        if let benchMatrixError {
            throw benchMatrixError
        }
        return benchMatrixResponse
    }

    func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        lastEvaluationRequest = request
        if let evaluationError {
            throw evaluationError
        }
        return evaluationResponse
    }

    func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        lastExportRequest = request
        return exportResponse
    }

    func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        lastSubmitRequest = request
        return submitResponse
    }
}

private actor ScriptedStreamingExportResultsWorkerClient:
    WorkerRoutingClient,
    StreamingExportResultsWorkerClientProtocol
{
    private(set) var unaryRequests: [Melix_Worker_V1_ExportResultsRequest] = []
    private(set) var streamRequests: [Melix_Worker_V1_ExportResultsRequest] = []
    private var streamResponse = Melix_Worker_V1_ExportResultsResponse()
    private var streamError: Error?

    func setStreamResponse(_ response: Melix_Worker_V1_ExportResultsResponse) {
        streamResponse = response
        streamError = nil
    }

    func setStreamError(_ error: Error?) {
        streamError = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func searchHubModels(
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getHubModelCard(
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        unaryRequests.append(request)
        throw WorkerClientError.unavailable
    }

    func exportResultsStream(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        streamRequests.append(request)
        if let streamError {
            throw streamError
        }
        return streamResponse
    }

    func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }
}

private actor ScriptedChatWorkerClient: WorkerRoutingClient {
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?
    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?
    private(set) var loadModelRequests: [Melix_Worker_V1_LoadModelRequest] = []
    private(set) var unloadRequests: [Melix_Worker_V1_UnloadModelRequest] = []
    private var loadModelResponse: Melix_Worker_V1_LoadModelResponse?
    private var loadModelResponses: [Melix_Worker_V1_LoadModelResponse] = []

    init(events: [Melix_Worker_V1_ExecuteEvent]) {
        self.events = events
    }

    func setLoadModelResponse(_ response: Melix_Worker_V1_LoadModelResponse) {
        loadModelResponse = response
        loadModelResponses = []
    }

    func setLoadModelResponses(_ responses: [Melix_Worker_V1_LoadModelResponse]) {
        loadModelResponses = responses
        loadModelResponse = nil
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        lastGenerateRequest = request
        let events = self.events
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        lastLoadModelRequest = request
        loadModelRequests.append(request)
        if !loadModelResponses.isEmpty {
            return loadModelResponses.removeFirst()
        }
        if let loadModelResponse {
            return loadModelResponse
        }
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = request.model.modelID
        return response
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadRequests.append(request)
        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = true
        return response
    }
}

private actor ScriptedRemoteProviderChatClient: RemoteProviderChatClient {
    private let events: [RemoteProviderChatStreamEvent]
    private(set) var lastRequest: RemoteProviderChatRequest?

    init(events: [RemoteProviderChatStreamEvent]) {
        self.events = events
    }

    func complete(_ request: RemoteProviderChatRequest) async throws -> RemoteProviderChatCompletion {
        lastRequest = request
        var assistantText = ""
        var finishReason = "stop"
        for event in events {
            switch event {
            case .tokenDelta(let text):
                assistantText += text
            case .completed(let completedFinishReason, let completedAssistantText):
                finishReason = completedFinishReason
                assistantText = completedAssistantText
            case .usage:
                break
            }
        }
        return RemoteProviderChatCompletion(
            assistantText: assistantText,
            finishReason: finishReason,
            promptTokens: 0,
            completionTokens: 0
        )
    }

    func stream(
        _ request: RemoteProviderChatRequest
    ) async throws -> AsyncThrowingStream<RemoteProviderChatStreamEvent, Error> {
        lastRequest = request
        let events = self.events
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }
}

private func makeTextCatalogModel(
    id: String,
    state: Melix_Controlplane_V1_ModelState,
    ttlSeconds: UInt32 = 0,
    pinOnLoad: Bool = false
) -> Melix_Controlplane_V1_ModelSummary {
    var model = ModelCatalog.devTextModel()
    model.modelID = id
    model.state = state
    if ttlSeconds > 0 {
        model.settings.ttlSeconds = ttlSeconds
        model.settings.memoryPolicy = .memoryResidencyTtl
    }
    if pinOnLoad {
        model.settings.pinOnLoad = true
        model.settings.memoryPolicy = .memoryResidencyPinned
        model.pinned = true
    }
    return model
}

private func makeQueuedExecuteEvent(requestID: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.queued = Melix_Worker_V1_Queued()
    event.queued.lane = "text.decode.interactive"
    return event
}

private func makeTokenExecuteEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeReasoningExecuteEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.reasoningDelta = Melix_Worker_V1_ReasoningDelta()
    event.reasoningDelta.text = text
    return event
}

private func makeToolExecuteEvent(
    requestID: String,
    callID: String,
    toolName: String,
    arguments: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.toolCallDelta = Melix_Worker_V1_ToolCallDelta()
    event.toolCallDelta.callID = callID
    event.toolCallDelta.toolName = toolName
    event.toolCallDelta.argumentsJsonFragment = arguments
    return event
}

private func makeUsageExecuteEvent(
    requestID: String,
    promptTokens: UInt32,
    completionTokens: UInt32
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.usageDelta = Melix_Worker_V1_UsageDelta()
    event.usageDelta.promptTokens = promptTokens
    event.usageDelta.completionTokens = completionTokens
    return event
}

private func makeCompletedExecuteEvent(
    requestID: String,
    finishReason: String,
    assistant: String,
    reasoning: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistant
    event.completed.reasoningText = reasoning
    return event
}

private struct TestWorkerError: Error, CustomStringConvertible {
    let description: String
}
