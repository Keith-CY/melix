import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("OpenAI Handler")
struct OpenAIHandlerTests {
    @Test("GET /v1/models accepts configured shared-access API keys and records metrics")
    func getModelsAcceptsConfiguredSharedAccessAPIKeysAndRecordsMetrics() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                    .init(keyID: "codex", label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            )
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["x-api-key": "sk-codex"],
                body: Data()
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"id\":\"melix-dev-text\""))
        #expect(await metricsStore.value(forKey: "shared_access.accepted_client_count") == 1)
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == 0)
    }

    @Test("GET /v1/models rejects unknown shared-access API keys with 401")
    func getModelsRejectsUnknownSharedAccessAPIKeys() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                ]
            )
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["x-api-key": "sk-unknown"],
                body: Data()
            )
        )
        let payload = try await jsonObject(from: response.body)

        #expect(response.statusCode == 401)
        #expect(payload.errorCode == "invalid_api_key")
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == 1)
        #expect(await metricsStore.value(forKey: "shared_access.rejected_request_count") == 1)
    }

    @Test("GET /v1/models rejects shared-access API keys while shared mode is disabled")
    func getModelsRejectsSharedAccessAPIKeysWhileSharedModeIsDisabled() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: false,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                ]
            )
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["x-api-key": "sk-desktop"],
                body: Data()
            )
        )
        let payload = try await jsonObject(from: response.body)

        #expect(response.statusCode == 403)
        #expect(payload.errorCode == "shared_access_disabled")
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == 1)
        #expect(await metricsStore.value(forKey: "shared_access.rejected_request_count") == 1)
    }

    @Test("GET /v1/models preserves unauthenticated local trust when shared access is configured but disabled")
    func getModelsPreservesUnauthenticatedLocalTrustWhenSharedAccessIsConfiguredButDisabled() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: false,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                ]
            )
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: [:],
                body: Data()
            )
        )

        #expect(response.statusCode == 200)
        #expect(await metricsStore.value(forKey: "shared_access.accepted_client_count") == 0)
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == 0)
    }

    @Test("GET /v1/models also accepts authorization bearer headers for shared API-key mode")
    func getModelsAlsoAcceptsAuthorizationBearerHeadersForSharedAPIKeyMode() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "codex", label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            )
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["Authorization": "Bearer sk-codex"],
                body: Data()
            )
        )

        #expect(response.statusCode == 200)
        #expect(await metricsStore.value(forKey: "shared_access.accepted_client_count") == 1)
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == 0)
    }

    @Test("GET /v1/models enforces bearer-token gateway access and rejects disallowed headers")
    func getModelsEnforcesBearerTokenGatewayAccessAndRejectsDisallowedHeaders() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .bearerToken,
                keys: [
                    .init(keyID: "primary-bearer", label: "Primary Bearer", tokenHint: "primary-bearer", token: "sk-bearer"),
                ]
            )
        )

        let authorizedResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["Authorization": "Bearer sk-bearer"],
                body: Data()
            )
        )
        let disallowedResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["x-api-key": "sk-bearer"],
                body: Data()
            )
        )
        let disallowedPayload = try await jsonObject(from: disallowedResponse.body)
        let invalidResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["Authorization": "Bearer sk-invalid"],
                body: Data()
            )
        )
        let invalidPayload = try await jsonObject(from: invalidResponse.body)

        #expect(authorizedResponse.statusCode == 200)
        #expect(disallowedResponse.statusCode == 403)
        #expect(disallowedPayload.errorCode == "auth_header_not_allowed")
        #expect(invalidResponse.statusCode == 401)
        #expect(invalidPayload.errorCode == "invalid_authorization")
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == 2)
    }

    @Test("GET /v1/models uses runtime gateway access policy store")
    func getModelsUsesRuntimeGatewayAccessPolicyStore() async throws {
        let metricsStore = MetricsStore()
        let store = GatewayAccessPolicyStore(
            GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(
                        keyID: "primary",
                        label: "Primary Key",
                        tokenHint: "primary",
                        token: "melix_sk_primary_secret"
                    ),
                ]
            )
        )
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicyStore: store
        )
        let service = ControlPlaneService(
            metricsStore: metricsStore,
            gatewayAccessPolicyStore: store
        )

        let unauthorized = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: [:],
                body: Data()
            )
        )
        let unauthorizedPayload = try await jsonObject(from: unauthorized.body)

        let applyResponse = try await service.execute(
            makeApplyGatewayAccessRequest(
                serverSessionID: "server-session-1",
                mode: .none,
                sharedAccessEnabled: false,
                primaryKey: nil
            )
        )

        let authorized = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: [:],
                body: Data()
            )
        )

        #expect(unauthorized.statusCode == 401)
        #expect(unauthorizedPayload.errorCode == "missing_api_key")
        #expect(applyResponse.ok)
        #expect(authorized.statusCode == 200)
    }

    @Test("shared API-key policy gates every operator-facing route except health")
    func sharedAPIKeyPolicyGatesEveryOperatorFacingRouteExceptHealth() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels()),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "operator", label: "Operator", tokenHint: "operator", token: "sk-operator"),
                ]
            )
        )
        let operatorRoutes: [(HTTPMethod, String, String, Bool)] = [
            (.get, "/v1/models", "missing_api_key", true),
            (.get, "/v1/cache/stats", "missing_api_key", true),
            (.post, "/v1/melix/auth/session", "missing_api_key", true),
            (.get, "/v1/melix/auth/session", "missing_session", false),
            (.delete, "/v1/melix/auth/session", "missing_session", false),
            (.post, "/v1/chat/completions", "missing_api_key", true),
            (.post, "/v1/completions", "missing_api_key", true),
            (.post, "/v1/responses", "missing_api_key", true),
            (.post, "/v1/messages", "missing_api_key", true),
            (.post, "/v1/embeddings", "missing_api_key", true),
            (.post, "/v1/rerank", "missing_api_key", true),
            (.post, "/v1/audio/transcriptions", "missing_api_key", true),
            (.post, "/v1/audio/speech", "missing_api_key", true),
            (.post, "/v1/images/generations", "missing_api_key", true),
            (.post, "/v1/images/edits", "missing_api_key", true),
            (.get, "/v1/unknown", "missing_api_key", true),
        ]

        for (method, path, expectedErrorCode, _) in operatorRoutes {
            let response = try await handler.handle(
                HTTPRequest(method: method, path: path, headers: [:], body: Data("{}".utf8))
            )
            let payload = try await jsonObject(from: response.body)
            #expect(response.statusCode == 401)
            #expect(payload.errorCode == expectedErrorCode)
        }

        let health = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )

        let gatewayPolicyFailures = operatorRoutes.filter(\.3).count
        #expect(health.statusCode == 200)
        #expect(await metricsStore.value(forKey: "gateway.auth_validation_failures") == Double(gatewayPolicyFailures))
        #expect(await metricsStore.value(forKey: "route_auth_policy") == 2)
    }

    @Test("gateway auth sessions can be created reused and revoked")
    func gatewayAuthSessionsCanBeCreatedReusedAndRevoked() async throws {
        let metricsStore = MetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-auth-session-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "codex", label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            ),
            persistentAuthSessionStore: PersistentAuthSessionStore(
                storeURL: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json"),
                metricsStore: metricsStore,
                retentionTTLSeconds: 3600,
                nowUnixMs: { 1_000 }
            )
        )

        let createResponse = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/melix/auth/session",
                headers: [
                    "content-type": "application/json",
                    "x-api-key": "sk-codex",
                ],
                body: try #require("{\"remember_me\":true}".data(using: .utf8))
            )
        )
        let createPayload = try await jsonPayload(from: createResponse.body)
        let sessionToken = try #require((createPayload["resume"] as? [String: Any])?["token"] as? String)

        let modelsResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        let inspectResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/melix/auth/session",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        let signOutResponse = try await handler.handle(
            HTTPRequest(
                method: .delete,
                path: "/v1/melix/auth/session",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        let rejectedResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        let rejectedPayload = try await jsonPayload(from: rejectedResponse.body)
        let error = try #require(rejectedPayload["error"] as? [String: Any])
        let sessionState = try #require(error["session_state"] as? [String: Any])

        #expect(createResponse.statusCode == 200)
        #expect(modelsResponse.statusCode == 200)
        #expect(inspectResponse.statusCode == 200)
        #expect(signOutResponse.statusCode == 200)
        #expect(rejectedResponse.statusCode == 401)
        #expect(error["code"] as? String == "revoked_session")
        #expect(sessionState["state"] as? String == "revoked")
        #expect(await metricsStore.value(forKey: "persistent_session.active_session_count") == 0)
    }

    @Test("gateway auth session responses sanitize rich output in encoded and manual json payloads")
    func gatewayAuthSessionResponsesSanitizeRichOutputAcrossResponsePaths() async throws {
        let metricsStore = MetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-auth-sanitize-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let maliciousKeyID = "<b>codex</b> [click](javascript:alert(1)) file:///tmp/melix"
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: maliciousKeyID, label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            ),
            persistentAuthSessionStore: PersistentAuthSessionStore(
                storeURL: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json"),
                metricsStore: metricsStore,
                retentionTTLSeconds: 3600,
                nowUnixMs: { 1_000 }
            )
        )

        let createResponse = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/melix/auth/session",
                headers: [
                    "content-type": "application/json",
                    "x-api-key": "sk-codex",
                ],
                body: try #require("{\"remember_me\":true}".data(using: .utf8))
            )
        )
        let createPayload = try await jsonPayload(from: createResponse.body)
        let createSession = try #require(createPayload["session"] as? [String: Any])
        let sessionToken = try #require((createPayload["resume"] as? [String: Any])?["token"] as? String)

        let signOutResponse = try await handler.handle(
            HTTPRequest(
                method: .delete,
                path: "/v1/melix/auth/session",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        #expect(signOutResponse.statusCode == 200)

        let rejectedResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        let rejectedPayload = try await jsonPayload(from: rejectedResponse.body)
        let rejectedError = try #require(rejectedPayload["error"] as? [String: Any])
        let rejectedSessionState = try #require(rejectedError["session_state"] as? [String: Any])
        try await Task.sleep(for: .milliseconds(20))

        #expect(createSession["key_id"] as? String == "codex click [unsafe link removed]")
        #expect(rejectedSessionState["key_id"] as? String == "codex click [unsafe link removed]")
        #expect(await metricsStore.value(forKey: "sanitized_output.enforcement_count") >= 2)
        #expect(await metricsStore.value(forKey: "sanitized_output.blocked_html_fragment_count") >= 2)
        #expect(await metricsStore.value(forKey: "sanitized_output.unsafe_uri_rejection_count") >= 2)
    }

    @Test("gateway auth session routes reject missing unsupported and unavailable session flows")
    func gatewayAuthSessionRoutesRejectMissingUnsupportedAndUnavailableSessionFlows() async throws {
        let metricsStore = MetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-auth-errors-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let sessionStore = PersistentAuthSessionStore(
            storeURL: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json"),
            metricsStore: metricsStore,
            retentionTTLSeconds: 3600,
            nowUnixMs: { 1_000 }
        )
        let sessionAwareHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "codex", label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            ),
            persistentAuthSessionStore: sessionStore
        )

        let missingCurrentSession = try await sessionAwareHandler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/melix/auth/session",
                headers: [:],
                body: Data()
            )
        )
        let missingCurrentPayload = try await jsonPayload(from: missingCurrentSession.body)
        let missingCurrentError = try #require(missingCurrentPayload["error"] as? [String: Any])

        let missingSessionOnModels = try await sessionAwareHandler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["x-melix-session": "melix_sess_missing"],
                body: Data()
            )
        )
        let missingSessionPayload = try await jsonPayload(from: missingSessionOnModels.body)
        let missingSessionError = try #require(missingSessionPayload["error"] as? [String: Any])
        let missingSessionState = try #require(missingSessionError["session_state"] as? [String: Any])

        let localTrustHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: .localTrust,
            persistentAuthSessionStore: sessionStore
        )
        let unsupportedCreateResponse = try await localTrustHandler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/melix/auth/session",
                headers: ["content-type": "application/json"],
                body: try #require("{\"remember_me\":true}".data(using: .utf8))
            )
        )
        let unsupportedCreatePayload = try await jsonPayload(from: unsupportedCreateResponse.body)
        let unsupportedCreateError = try #require(unsupportedCreatePayload["error"] as? [String: Any])

        let unavailableHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "codex", label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            )
        )
        let unavailableCreateResponse = try await unavailableHandler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/melix/auth/session",
                headers: [
                    "content-type": "application/json",
                    "x-api-key": "sk-codex",
                ],
                body: try #require("{\"remember_me\":true}".data(using: .utf8))
            )
        )
        let unavailableCreatePayload = try await jsonPayload(from: unavailableCreateResponse.body)
        let unavailableCreateError = try #require(unavailableCreatePayload["error"] as? [String: Any])

        #expect(missingCurrentSession.statusCode == 401)
        #expect(missingCurrentError["code"] as? String == "missing_session")
        #expect(missingSessionOnModels.statusCode == 401)
        #expect(missingSessionError["code"] as? String == "missing_session")
        #expect(missingSessionState["state"] as? String == "missing")
        #expect(unsupportedCreateResponse.statusCode == 403)
        #expect(unsupportedCreateError["code"] as? String == "auth_session_requires_configured_gateway_auth")
        #expect(unavailableCreateResponse.statusCode == 503)
        #expect(unavailableCreateError["code"] as? String == "auth_session_unavailable")
    }

    @Test("expired gateway auth sessions return structured session metadata")
    func expiredGatewayAuthSessionsReturnStructuredSessionMetadata() async throws {
        let metricsStore = MetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-gateway-auth-expired-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let clock = TestNowUnixMSSequence([1_000, 1_000, 5_000, 5_000, 5_000])
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayAccessPolicy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "codex", label: "Codex", tokenHint: "codex", token: "sk-codex"),
                ]
            ),
            persistentAuthSessionStore: PersistentAuthSessionStore(
                storeURL: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json"),
                metricsStore: metricsStore,
                retentionTTLSeconds: 1,
                nowUnixMs: { clock.next() }
            )
        )

        let createResponse = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/melix/auth/session",
                headers: [
                    "content-type": "application/json",
                    "x-api-key": "sk-codex",
                ],
                body: try #require("{\"remember_me\":true}".data(using: .utf8))
            )
        )
        let createPayload = try await jsonPayload(from: createResponse.body)
        let sessionToken = try #require((createPayload["resume"] as? [String: Any])?["token"] as? String)

        let expiredResponse = try await handler.handle(
            HTTPRequest(
                method: .get,
                path: "/v1/models",
                headers: ["X-Melix-Session": sessionToken],
                body: Data()
            )
        )
        let expiredPayload = try await jsonPayload(from: expiredResponse.body)
        let error = try #require(expiredPayload["error"] as? [String: Any])
        let sessionState = try #require(error["session_state"] as? [String: Any])

        #expect(expiredResponse.statusCode == 401)
        #expect(error["code"] as? String == "expired_session")
        #expect(sessionState["state"] as? String == "expired")
    }

    @Test("POST /v1/chat/completions translates into a worker generate request")
    func postChatCompletionsTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "req-fixed", seq: 1, text: "Hel"),
            makeTokenEvent(requestID: "req-fixed", seq: 2, text: "lo"),
            makeUsageEvent(requestID: "req-fixed", seq: 3, promptTokens: 1, completionTokens: 2),
            makeCompletedEvent(requestID: "req-fixed", seq: 4, finishReason: "stop", assistantText: "Hello"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-fixed" })
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: translator,
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "stream_options": { "include_usage": true },
              "messages": [
                { "role": "user", "content": "Hello" }
              ],
              "temperature": 0.2,
              "max_tokens": 16
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.execution.id.requestID == "req-fixed")
        #expect(request.execution.modelHandle == "melix-dev-text::local")
        #expect(request.execution.scheduling.lane == "text.decode.interactive")
        #expect(request.execution.scheduling.priority == 100)
        #expect(request.execution.scheduling.latencySensitive)
        #expect(request.messages.count == 1)
        #expect(request.messages[0].role == "user")
        #expect(request.messages[0].parts.count == 1)
        #expect(request.messages[0].parts[0].text == "Hello")
        #expect(request.sampling.temperature == 0.2)
        #expect(request.sampling.maxOutputTokens == 16)
        #expect(request.returnUsage)
        #expect(payload.contains("\"content\":\"Hel\""))
        #expect(payload.contains("\"content\":\"lo\""))
        #expect(payload.contains("\"finish_reason\":\"stop\""))
        #expect(payload.contains("\"prompt_tokens\":1"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/chat/completions routes by payload model within the active server roster")
    func postChatCompletionsRoutesByPayloadModelWithinActiveServerRoster() async throws {
        var primary = ModelCatalog.devTextModel()
        primary.modelID = "melix-primary"
        primary.state = .modelWarm
        var secondary = ModelCatalog.devTextModel()
        secondary.modelID = "melix-secondary"
        secondary.state = .modelWarm
        let catalog = ModelCatalog(seedModels: [primary, secondary])
        _ = await catalog.recordLoadSucceeded(id: "melix-secondary", dispatchHandle: "melix-secondary::swift")
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(
                requestID: "req-routed-secondary",
                seq: 1,
                finishReason: "stop",
                assistantText: "secondary"
            ),
        ])
        let gatewayConfigStore = GatewayConfigStore(
            storeURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("melix-test-gateway-config-\(UUID().uuidString).json"),
            defaults: [:]
        )
        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "127.0.0.1"
        command.port = 11_434
        command.defaultModelID = "melix-primary"
        command.servedModelIds = ["melix-primary", "melix-secondary"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60
        try await gatewayConfigStore.apply(command: command)
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-routed-secondary" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) }),
            gatewayConfigStore: gatewayConfigStore
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    """
                    {
                      "model": "melix-secondary",
                      "stream": true,
                      "messages": [
                        { "role": "user", "content": "route" }
                      ]
                    }
                    """.utf8
                )
            )
        )
        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(request.execution.modelHandle == "melix-secondary::swift")
        #expect(payload.contains("\"model\":\"melix-secondary\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/chat/completions does not block on idle unloads")
    func postChatCompletionsDoesNotBlockOnIdleUnloads() async throws {
        final class ClockBox: @unchecked Sendable {
            var now: Date

            init(now: Date) {
                self.now = now
            }
        }

        let clock = ClockBox(now: Date(timeIntervalSince1970: 100))
        var active = ModelCatalog.devTextModel()
        active.modelID = "melix-active"
        active.state = .modelWarm
        var idle = ModelCatalog.devTextModel()
        idle.modelID = "melix-idle"
        idle.state = .modelWarm
        let catalog = ModelCatalog(seedModels: [active, idle], nowUnixMs: {
            Int64(clock.now.timeIntervalSince1970 * 1000)
        })
        _ = await catalog.recordLoadSucceeded(id: "melix-active", dispatchHandle: "melix-active::swift")
        _ = await catalog.recordLoadSucceeded(id: "melix-idle", dispatchHandle: "melix-idle::swift")
        clock.now = Date(timeIntervalSince1970: 200)

        let unloadGate = ScriptedWorkerUnloadGate()
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(
                requestID: "req-idle-sweep",
                seq: 1,
                finishReason: "stop",
                assistantText: "active"
            ),
        ], unloadGate: unloadGate)
        let gatewayConfigStore = GatewayConfigStore(
            storeURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("melix-test-gateway-config-\(UUID().uuidString).json"),
            defaults: [:]
        )
        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "127.0.0.1"
        command.port = 11_434
        command.defaultModelID = "melix-active"
        command.servedModelIds = ["melix-active", "melix-idle"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60
        command.modelIdleTimeoutSeconds = 1
        try await gatewayConfigStore.apply(command: command)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: registry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-idle-sweep" }),
            sseWriter: SSEStreamWriter(now: { clock.now }),
            gatewayConfigStore: gatewayConfigStore,
            now: { clock.now }
        )

        let startedAt = ContinuousClock.now
        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    """
                    {
                      "model": "melix-active",
                      "stream": true,
                      "messages": [
                        { "role": "user", "content": "route" }
                      ]
                    }
                    """.utf8
                )
            )
        )
        let elapsed = startedAt.duration(to: .now)
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("data: [DONE]"))
        #expect(elapsed < .seconds(2))

        try await waitForOpenAIHandlerCondition("idle sweep starts after response") {
            await workerClient.unloadRequestCount == 1
        }
        #expect(await workerClient.unloadCompletedCount == 0)

        await unloadGate.release()
        try await waitForOpenAIHandlerCondition(
            "idle sweep unloads after response",
            timeout: .seconds(2)
        ) {
            await workerClient.unloadCompletedCount == 1
        }
    }

    @Test("POST /v1/chat/completions rejects payload models outside the active server roster")
    func postChatCompletionsRejectsPayloadModelsOutsideActiveServerRoster() async throws {
        var primary = ModelCatalog.devTextModel()
        primary.modelID = "melix-primary"
        primary.state = .modelWarm
        var secondary = ModelCatalog.devTextModel()
        secondary.modelID = "melix-secondary"
        secondary.state = .modelWarm
        let catalog = ModelCatalog(seedModels: [primary, secondary])
        let workerClient = ScriptedWorkerClient(events: [])
        let gatewayConfigStore = GatewayConfigStore(
            storeURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("melix-test-gateway-config-\(UUID().uuidString).json"),
            defaults: [:]
        )
        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "127.0.0.1"
        command.port = 11_434
        command.defaultModelID = "melix-primary"
        command.servedModelIds = ["melix-primary"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60
        try await gatewayConfigStore.apply(command: command)
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
            gatewayConfigStore: gatewayConfigStore
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    """
                    {
                      "model": "melix-secondary",
                      "stream": true,
                      "messages": [
                        { "role": "user", "content": "route" }
                      ]
                    }
                    """.utf8
                )
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 404)
        #expect(payload.contains("\"code\":\"model_not_served_by_server\""))
        #expect(await workerClient.lastGenerateRequest == nil)
    }

    @Test("POST /v1/chat/completions skips registry sync for catalog-resident warm models")
    func postChatCompletionsSkipsRegistrySyncForCatalogResidentWarmModels() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-warm-no-registry", seq: 1, finishReason: "stop", assistantText: "ready"),
        ])
        let modelOpsClient = ScriptedRegistryModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = #"{"model_registry":{"models":[],"roots":[]}}"#
                return event
            }(),
        ])
        let registry = WorkerRegistry(
            defaultTextClient: workerClient,
            modelOperationsClient: modelOpsClient,
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: registry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-warm-no-registry" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let generated = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(payload.contains("data: [DONE]"))
        #expect(generated.execution.modelHandle == "melix-dev-text::local")
        #expect(await modelOpsClient.lastConvertRequest == nil)
    }

    @Test("POST /v1/chat/completions forwards OpenAI tools and emits SDK-compatible tool deltas")
    func postChatCompletionsForwardsOpenAIToolsAndToolDeltas() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeToolCallEvent(
                requestID: "req-openai-tools",
                seq: 1,
                callID: "req-openai-tools-tool-1",
                toolName: "terminal",
                argumentsJSONFragment: "{\"command\":\"gh auth status\"}",
                fragmentIndex: 2
            ),
            makeCompletedEvent(
                requestID: "req-openai-tools",
                seq: 2,
                finishReason: "tool_calls",
                assistantText: ""
            ),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-openai-tools" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Check gh auth." }
              ],
              "tools": [
                {
                  "type": "function",
                  "function": {
                    "name": "terminal",
                    "description": "Run a shell command.",
                    "parameters": {
                      "type": "object",
                      "properties": {
                        "command": { "type": "string" }
                      },
                      "required": ["command"]
                    }
                  }
                }
              ],
              "tool_choice": "auto"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.execution.hasToolConfig)
        #expect(request.execution.toolConfig.tools.map(\.name) == ["terminal"])
        #expect(request.execution.toolConfig.parser == "xml")
        #expect(request.execution.toolConfig.toolChoice == "auto")
        #expect(request.execution.ext["melix.tool_parser.mode"] == "xml")
        #expect(request.execution.ext["melix.tool_config.source"] == "openai_chat_tools")
        #expect(payload.contains("event: message"))
        #expect(payload.contains("\"object\":\"chat.completion.chunk\""))
        #expect(payload.contains("\"tool_calls\""))
        #expect(payload.contains("\"index\":1"))
        #expect(payload.contains("\"name\":\"terminal\""))
        #expect(payload.contains("\"arguments\":\"{\\\"command\\\":\\\"gh auth status\\\"}\""))
        #expect(!payload.contains("event: tool_call"))
        #expect(metrics.values["http.openai_chat_tools_request_count"] == 1)
        #expect(metrics.values["http.openai_chat_tools_configured_count"] == 1)
    }

    @Test("POST /v1/chat/completions lazy-loads text-only VLM requests through the Python VLM route")
    func postChatCompletionsLazyLoadsTextOnlyVLMRequestsThroughPythonVLMRoute() async throws {
        var vlmModel = ModelCatalog.devVLMModel()
        vlmModel.settings.ext["melix.vlm.text_only_step_cooperative"] = "true"
        vlmModel.settings.ext["melix.vlm.text_only_batch_generator"] = "true"
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), vlmModel])
        let textClient = ScriptedWorkerClient(events: [])
        let vlmClient = ScriptedWorkerClient(
            events: [
                makeTokenEvent(requestID: "req-http-vlm-text", seq: 1, text: "vlm"),
                makeCompletedEvent(
                    requestID: "req-http-vlm-text",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: "vlm"
                ),
            ],
            loadModelHandle: "melix-dev-vlm::python"
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: textClient,
            pythonCompatibilityClient: vlmClient,
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: workerRegistry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: workerRegistry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-http-vlm-text" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-vlm",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Reply briefly." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let loadRequest = try #require(await vlmClient.lastLoadModelRequest)
        let generateRequest = try #require(await vlmClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"content\":\"vlm\""))
        #expect(payload.contains("data: [DONE]"))
        #expect(loadRequest.model.modelKind == "vlm")
        #expect(loadRequest.model.ext["melix.capability.route_kind"] == "python_vlm")
        #expect(generateRequest.execution.modelHandle == "melix-dev-vlm::python")
        #expect(generateRequest.execution.ext["melix.vlm.text_only_step_cooperative"] == "true")
        #expect(generateRequest.execution.ext["melix.vlm.text_only_batch_generator"] == "true")
        #expect(await textClient.lastGenerateRequest == nil)
    }

    @Test("POST /v1/chat/completions copies imported VLM batch-generator metadata by route metadata")
    func postChatCompletionsCopiesImportedVLMBatchGeneratorMetadataByRouteMetadata() async throws {
        var vlmModel = ModelCatalog.devVLMModel()
        vlmModel.modelID = "imported-gemma-vlm"
        vlmModel.routeClass = .workerRouteSwiftText
        vlmModel.settings.ext["melix.capability.route_kind"] = "python_vlm"
        vlmModel.settings.ext["melix.model_path"] = "/tmp/imported-gemma-vlm"
        vlmModel.settings.ext["melix.vlm.text_only_step_cooperative"] = "false"
        vlmModel.settings.ext["melix.vlm.text_only_batch_generator"] = "true"
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), vlmModel])
        let textClient = ScriptedWorkerClient(events: [])
        let vlmClient = ScriptedWorkerClient(
            events: [
                makeTokenEvent(requestID: "req-http-imported-vlm-text", seq: 1, text: "vlm"),
                makeCompletedEvent(
                    requestID: "req-http-imported-vlm-text",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: "vlm"
                ),
            ],
            loadModelHandle: "imported-gemma-vlm::python"
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: textClient,
            pythonCompatibilityClient: vlmClient,
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: workerRegistry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: workerRegistry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-http-imported-vlm-text" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "imported-gemma-vlm",
              "stream": true,
              "temperature": 0,
              "messages": [
                { "role": "user", "content": "Reply briefly." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let generateRequest = try #require(await vlmClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(generateRequest.execution.ext["melix.vlm.text_only_step_cooperative"] == nil)
        #expect(generateRequest.execution.ext["melix.vlm.text_only_batch_generator"] == "true")
        #expect(generateRequest.sampling.temperature == 0)
        #expect(generateRequest.sampling.topP == 1)
        #expect(generateRequest.sampling.topK == 0)
        #expect(await textClient.lastGenerateRequest == nil)
    }

    @Test("model sparse-prefill policy is applied to generated worker requests")
    func modelSparsePrefillPolicyIsAppliedToGeneratedWorkerRequests() async throws {
        var model = warmModel()
        model.settings.defaultAccelerationMode = .sparsePrefill
        model.settings.accelerationProfileID = "structured-user"
        model.settings.ext["melix.acceleration.supported_modes"] = "baseline,sparse_prefill"
        model.settings.ext["melix.acceleration.target_capability"] = "sparse_prefill"
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-sparse-prefill", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-sparse-prefill" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "system", "content": "Protect system instructions." },
                { "role": "user", "content": "{\\"kind\\":\\"structured\\"}\\n{\\"kind\\":\\"structured\\"}" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.acceleration.mode == .sparsePrefill)
        #expect(request.execution.acceleration.profileID == "structured-user")
        #expect(request.execution.acceleration.prefillHint == "structured-user")
        #expect(request.execution.ext["melix.capability.receipt_schema"] == "melix.model_capability_receipt.v1")
        #expect(request.execution.ext["melix.acceleration.requested_acceleration_mode"] == "sparse_prefill")
        #expect(request.execution.ext["melix.acceleration.resolved_acceleration_mode"] == "sparse_prefill")
        #expect(request.execution.ext["melix.acceleration.unsupported_reason"] == "none")
    }

    @Test("POST /v1/chat/completions returns typed unsupported acceleration errors")
    func postChatCompletionsReturnsTypedUnsupportedAccelerationErrors() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-unsupported-acceleration-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        var defaults = Melix_Controlplane_V1_ApplyServingDefaults()
        defaults.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        defaults.temperature = 0.7
        defaults.topP = 1.0
        defaults.maxTokens = 256
        defaults.streamIntervalTokens = 1
        defaults.maxConcurrentRequests = 4
        defaults.concurrentProcessingEnabled = true
        defaults.prefillBatchSize = 2
        defaults.completionBatchSize = 2
        defaults.accelerationMode = .speculativeDecode
        defaults.draftModelID = "other-draft"
        defaults.numDraftTokens = 4
        try await servingDefaultsStore.apply(command: defaults)

        var model = warmModel()
        model.settings.defaultAccelerationMode = .unspecified
        model.settings.ext["melix.acceleration.supported_modes"] = "baseline,speculative_decode"
        model.settings.ext["melix.acceleration.valid_draft_model_ids"] = "melix-dev-draft"
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-unsupported-acceleration", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-unsupported-acceleration" }),
            gatewayServingDefaultsStore: servingDefaultsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await jsonPayload(from: response.body)
        let error = try #require(payload["error"] as? [String: Any])

        #expect(response.statusCode == 400)
        #expect(error["code"] as? String == "unsupported_acceleration")
        #expect(error["unsupported_reason"] as? String == "draft_model_not_allowed")
        #expect(error["recovery_hint"] as? String == "Choose one of the target receipt's valid_draft_model_ids.")
        #expect(await workerClient.lastGenerateRequest == nil)
    }

    @Test("POST /v1/chat/completions omits usage frames unless stream options opt in")
    func postChatCompletionsOmitUsageFramesUnlessRequested() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeUsageEvent(requestID: "req-chat-usage", seq: 1, promptTokens: 2, completionTokens: 1),
            makeCompletedEvent(requestID: "req-chat-usage", seq: 2, finishReason: "stop", assistantText: "done"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-chat-usage" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "usage off by default" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.returnUsage == false)
        #expect(payload.contains("\"finish_reason\":\"stop\""))
        #expect(payload.contains("\"prompt_tokens\":2") == false)
    }

    @Test("POST /v1/chat/completions returns JSON when stream is false")
    func postChatCompletionsReturnsJSONWhenStreamIsFalse() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "req-json", seq: 1, text: "Hel"),
            makeTokenEvent(requestID: "req-json", seq: 2, text: "lo"),
            makeUsageEvent(requestID: "req-json", seq: 3, promptTokens: 1, completionTokens: 2),
            makeCompletedEvent(requestID: "req-json", seq: 4, finishReason: "stop", assistantText: "Hello"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            metricsStore: metricsStore
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-json" }),
            now: { Date(timeIntervalSince1970: 1_778_520_000) }
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ],
              "temperature": 0.2,
              "max_tokens": 16
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await jsonPayload(from: response.body)
        let choice = try #require((payload["choices"] as? [[String: Any]])?.first)
        let message = try #require(choice["message"] as? [String: Any])
        let usage = try #require(payload["usage"] as? [String: Any])
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(payload["id"] as? String == "req-json")
        #expect(payload["object"] as? String == "chat.completion")
        #expect(payload["created"] as? Int == 1_778_520_000)
        #expect(payload["model"] as? String == "melix-dev-text")
        #expect(message["role"] as? String == "assistant")
        #expect(message["content"] as? String == "Hello")
        #expect(choice["finish_reason"] as? String == "stop")
        #expect(usage["prompt_tokens"] as? Int == 1)
        #expect(usage["completion_tokens"] as? Int == 2)
        #expect(usage["total_tokens"] as? Int == 3)
        #expect(request.stream)
        #expect(request.returnUsage)
        #expect(request.execution.ext["melix.stream.include_usage"] == "true")
        #expect(metrics.values["http.chat_completions_non_stream_request_count", default: 0] == 1)
        #expect(metrics.values["http.chat_completions_non_stream_latency_ms", default: 0] > 0)
        #expect(metrics.values["http.chat_completions_non_stream_time_to_first_token_ms", default: 0] > 0)
        #expect(metrics.values["http.ttfd_ms", default: 0] == 0)
        #expect(metrics.values["http.chat_completions_non_stream_completion_tokens", default: 0] == 2)
    }

    @Test("POST /v1/chat/completions accumulates non-stream completion token metrics")
    func postChatCompletionsAccumulatesNonStreamCompletionTokenMetrics() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(events: [
            makeUsageEvent(requestID: "req-json-metrics", seq: 1, promptTokens: 1, completionTokens: 2),
            makeCompletedEvent(requestID: "req-json-metrics", seq: 2, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-json-metrics" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        _ = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: ["content-type": "application/json"], body: body)
        )
        _ = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: ["content-type": "application/json"], body: body)
        )

        let metrics = await metricsStore.snapshot()
        #expect(metrics.values["http.chat_completions_non_stream_request_count", default: 0] == 2)
        #expect(metrics.values["http.chat_completions_non_stream_completion_tokens", default: 0] == 4)
    }

    @Test("POST /v1/chat/completions uses latest cumulative non-stream usage")
    func postChatCompletionsUsesLatestCumulativeNonStreamUsage() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "req-json-usage", seq: 1, text: "Hello"),
            makeUsageEvent(requestID: "req-json-usage", seq: 2, promptTokens: 1, completionTokens: 1),
            makeUsageEvent(requestID: "req-json-usage", seq: 3, promptTokens: 3, completionTokens: 5),
            makeCompletedEvent(requestID: "req-json-usage", seq: 4, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-json-usage" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Usage" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await jsonPayload(from: response.body)
        let usage = try #require(payload["usage"] as? [String: Any])
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(usage["prompt_tokens"] as? Int == 3)
        #expect(usage["completion_tokens"] as? Int == 5)
        #expect(usage["total_tokens"] as? Int == 8)
        #expect(metrics.values["http.chat_completions_non_stream_completion_tokens", default: 0] == 5)
    }

    @Test("POST /v1/chat/completions stops non-stream aggregation on worker error")
    func postChatCompletionsStopsNonStreamAggregationOnWorkerError() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "req-json-error", seq: 1, text: "partial"),
            makeErrorEvent(requestID: "req-json-error", seq: 2, code: "invalid_argument", message: "bad request"),
            makeUsageEvent(requestID: "req-json-error", seq: 3, promptTokens: 10, completionTokens: 20),
            makeCompletedEvent(requestID: "req-json-error", seq: 4, finishReason: "stop", assistantText: "must not win"),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-json-error" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Bad request" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await jsonPayload(from: response.body)
        let error = try #require(payload["error"] as? [String: Any])
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 400)
        #expect(error["code"] as? String == "invalid_argument")
        #expect(error["message"] as? String == "bad request")
        #expect(metrics.values["http.chat_completions_non_stream_request_count", default: 0] == 0)
        #expect(metrics.values["http.chat_completions_non_stream_completion_tokens", default: 0] == 0)
    }

    @Test("POST /v1/chat/completions maps non-stream aggregation failures to worker unavailable")
    func postChatCompletionsMapsNonStreamAggregationFailuresToWorkerUnavailable() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(
            events: [
                makeTokenEvent(requestID: "req-json-throw", seq: 1, text: "partial"),
            ],
            streamFailure: OpenAIHandlerTestError(description: "stream exploded")
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-json-throw" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Fail" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await jsonPayload(from: response.body)
        let error = try #require(payload["error"] as? [String: Any])
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 503)
        #expect(error["code"] as? String == "worker_unavailable")
        #expect(metrics.values["http.chat_completions_non_stream_request_count", default: 0] == 0)
        #expect(metrics.values["http.chat_completions_non_stream_completion_tokens", default: 0] == 0)
    }

    @Test("POST /v1/chat/completions defaults to non-stream JSON when stream is omitted")
    func postChatCompletionsDefaultsToNonStreamJSONWhenStreamIsOmitted() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "req-json-default", seq: 1, text: "Default"),
            makeTokenEvent(requestID: "req-json-default", seq: 2, text: " JSON"),
            makeCompletedEvent(
                requestID: "req-json-default",
                seq: 3,
                finishReason: "stop",
                assistantText: ""
            ),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-json-default" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "messages": [
                { "role": "user", "content": "Default response" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await jsonPayload(from: response.body)
        let choice = try #require((payload["choices"] as? [[String: Any]])?.first)
        let message = try #require(choice["message"] as? [String: Any])

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(payload["object"] as? String == "chat.completion")
        #expect(message["content"] as? String == "Default JSON")
        #expect(payload["usage"] == nil)
        #expect(request.stream)
        #expect(request.returnUsage)
    }

    @Test("POST /v1/chat/completions lazily loads a discovered text model before streaming")
    func postChatCompletionsLazilyLoadsDiscoveredTextModel() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(
            events: [
                makeTokenEvent(requestID: "req-lazy", seq: 1, text: "Echo"),
                makeCompletedEvent(requestID: "req-lazy", seq: 2, finishReason: "stop", assistantText: "Echo"),
            ],
            loadModelHandle: "melix-dev-text::swift",
            loadModelEstimatedResidentBytes: 4_096,
            runtimeResidentBytes: 6_144,
            runtimeCacheResidentBytes: 2_048
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let coordinator = RequestCoordinator(
            workerRegistry: registry,
            abortRegistry: AbortRegistry(),
            metricsStore: metricsStore
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            workerRegistry: registry,
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-lazy" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "hello lazy load" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        let generateRequest = try #require(await workerClient.lastGenerateRequest)
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()
        let loadedModel = await catalog.model(id: "melix-dev-text")

        #expect(response.statusCode == 200)
        #expect(loadRequest.model.modelID == "melix-dev-text")
        #expect(loadRequest.pinOnLoad == false)
        #expect(generateRequest.execution.modelHandle == "melix-dev-text::swift")
        #expect(loadedModel?.state == .modelWarm)
        #expect(metrics.values["control_plane.text_first_load_ms", default: -1] >= 0)
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 4_096)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 8_192)
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/chat/completions falls back to estimated resident bytes when runtime stats are unavailable")
    func postChatCompletionsFallsBackToEstimatedResidentBytesWhenRuntimeStatsAreUnavailable() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(
            events: [
                makeCompletedEvent(requestID: "req-lazy-estimate", seq: 1, finishReason: "stop", assistantText: "done"),
            ],
            loadModelHandle: "melix-dev-text::swift",
            loadModelEstimatedResidentBytes: 12_288,
            runtimeStatsFailure: WorkerClientError.unavailable
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            workerRegistry: registry,
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-lazy-estimate" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "warm with estimated resident bytes" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 12_288)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 12_288)
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/responses merges model and request chat template kwargs and records metrics")
    func postResponsesMergesModelAndRequestChatTemplateKwargsAndRecordsMetrics() async throws {
        let model = warmModel()
        var configuredModel = model
        configuredModel.settings.ext["chat_template_kwargs"] = "{\"chat_template\":\"model-template\",\"tokenize\":true}"
        configuredModel.settings.ext["chat_template_forced_kwargs"] = "{\"chat_template\":\"forced-template\",\"add_generation_prompt\":true}"
        let catalog = ModelCatalog(seedModels: [configuredModel])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-template-http", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-template-http" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "Continue the answer.",
              "chat_template_kwargs": {
                "chat_template": "request-template",
                "continue_final_message": true
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        let metrics = await metricsStore.snapshot()
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(request.execution.ext["melix.chat_template_kwargs.source"] == "model+request+forced")
        #expect(
            request.execution.ext["melix.chat_template_kwargs.effective_json"]
                == "{\"add_generation_prompt\":true,\"chat_template\":\"forced-template\",\"continue_final_message\":true,\"tokenize\":true}"
        )
        #expect(request.execution.ext["melix.chat_template_kwargs.forced_keys"] == "add_generation_prompt,chat_template")
        #expect(metrics.values["http.chat_template_kwargs_request_count"] == 1)
        #expect(metrics.values["http.chat_template_kwargs_forced_request_count"] == 1)
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/chat/completions carries partial-mode assistant-prefill metadata")
    func postChatCompletionsCarriesPartialModeAssistantPrefillMetadata() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-prefill-http", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-prefill-http" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "messages": [
                { "role": "assistant", "name": "planner", "content": "Draft answer" }
              ],
              "chat_template_kwargs": {
                "continue_final_message": true,
                "add_generation_prompt": false
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.messages[0].name == "planner")
        #expect(request.execution.ext["melix.partial_mode"] == "continue_final_message")
        #expect(request.execution.ext["melix.assistant_prefill"] == "true")
        #expect(request.execution.ext["melix.assistant_prefill.message_index"] == "0")
        #expect(request.execution.ext["melix.assistant_prefill.name"] == "planner")
    }

    @Test("POST /v1/responses rejects malformed model chat template kwargs")
    func postResponsesRejectsMalformedModelChatTemplateKwargs() async throws {
        let model = warmModel()
        var configuredModel = model
        configuredModel.settings.ext["chat_template_kwargs"] = "[\"invalid-root\"]"
        let catalog = ModelCatalog(seedModels: [configuredModel])
        let workerClient = ScriptedWorkerClient(events: [])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-template-invalid-model" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "Continue the answer."
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("chat_template_kwargs must be a JSON object"))
    }

    @Test("POST /v1/chat/completions prefers explicit runtime memory accounting fields when available")
    func postChatCompletionsPrefersExplicitRuntimeMemoryAccountingFields() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let metricsStore = MetricsStore()
        let workerClient = ScriptedWorkerClient(
            events: [
                makeCompletedEvent(requestID: "req-lazy-explicit", seq: 1, finishReason: "stop", assistantText: "done"),
            ],
            loadModelHandle: "melix-dev-text::swift",
            loadModelEstimatedResidentBytes: 4_096,
            runtimeResidentBytes: 4_096,
            runtimeModelResidentBytes: 5_120,
            runtimeCacheResidentBytes: 1_024,
            runtimeKVCacheBytes: 256
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            workerRegistry: registry,
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-lazy-explicit" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "prefer explicit runtime accounting" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 4_096)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 6_400)
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/chat/completions returns 503 when lazy text loading cannot reach the worker")
    func postChatCompletionsReturns503WhenLazyTextLoadingCannotReachWorker() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let registry = WorkerRegistry(defaultTextClient: UnavailableWorkerClient(), modelCatalog: catalog)
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: registry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-lazy-unavailable" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "hello unavailable lazy load" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/chat/completions returns invalid argument for malformed multimodal payloads")
    func postChatCompletionsReturnsInvalidArgumentForMalformedMultimodalPayloads() async throws {
        let workerClient = ScriptedWorkerClient(events: [])
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-invalid-mm" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-vlm",
              "stream": true,
              "messages": [
                {
                  "role": "user",
                  "content": [
                    { "type": "text", "text": "Describe the image." },
                    { "type": "input_image", "input_image": {} }
                  ]
                }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("\"message\":\"input_image.url or input_image.data is required.\""))
        #expect(await workerClient.lastGenerateRequest == nil)
    }

    @Test("POST /v1/chat/completions records video frame metrics for VLM requests")
    func postChatCompletionsRecordsVideoFrameMetricsForVLMRequests() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let runtimeStats = {
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.lastProbeKind = "vlm"
            response.stats.lastPreprocessLatencyMs = 24
            response.stats.lastPreprocessPeakMemoryBytes = 32_768
            response.stats.lastFirstTokenLatencyMs = 11
            response.stats.lastVideoEffectiveFrameCount = 6
            response.stats.lastVideoRequestedFrameBudget = 6
            response.stats.lastVideoWindowMs = 4_000
            response.stats.lastTempMediaArtifactCount = 2
            response.stats.lastTempMediaArtifactBytes = 2_048
            response.stats.lastTempMediaCleanupLatencyMs = 4
            response.stats.lastTempMediaCleanupFailureCount = 1
            response.stats.generationStreamOwnerMode = "executor_owned"
            response.stats.workerThreadInitLatencyMs = 7
            response.stats.streamSyncFallbackCount = 0
            response.stats.lastModelLoadTrustPolicyResolutionMs = 0.75
            response.stats.modelLoadTrustBlockedCount = 1
            response.stats.lastMultimodalDecodeMode = "native_quantized"
            response.stats.lastMultimodalFallbackReason = ""
            response.stats.lastMultimodalDecodeSyncMode = "executor_stream"
            return response
        }()
        let vlmClient = ScriptedWorkerClient(
            events: [
                makeTokenEvent(requestID: "req-http-vlm-video", seq: 1, text: "video"),
                makeCompletedEvent(
                    requestID: "req-http-vlm-video",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: "video"
                ),
            ],
            loadModelHandle: "melix-dev-vlm::python",
            runtimeStatsResponseOverride: runtimeStats
        )
        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devVLMModel()])
        _ = await catalog.loadModel(id: "melix-dev-vlm", dispatchHandle: "melix-dev-vlm::python")
        let workerRegistry = WorkerRegistry(
            defaultTextClient: textClient,
            pythonCompatibilityClient: vlmClient,
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: workerRegistry,
                abortRegistry: AbortRegistry(),
                schedulerReadModel: schedulerReadModel,
                metricsStore: metricsStore
            ),
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-http-vlm-video" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-vlm",
              "stream": true,
              "messages": [
                {
                  "role": "user",
                  "content": [
                    { "type": "text", "text": "Summarize the clip." },
                    {
                      "type": "input_video",
                      "input_video": {
                        "data": "dmlkZW8gZml4dHVyZQ==",
                        "format": "mp4",
                        "filename": "clip.mp4",
                        "frame_budget": 6,
                        "start_ms": 1000,
                        "end_ms": 5000
                      }
                    }
                  ]
                }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await vlmClient.lastGenerateRequest)
        let metrics = await metricsStore.snapshot()
        let queueSummary = await schedulerReadModel.snapshot()
        let lane = try #require(
            queueSummary.lanes.first(where: { $0.laneID == "multimodal.vision.background" })
        )

        #expect(response.statusCode == 200)
        #expect(payload.contains("data: [DONE]"))
        #expect(request.execution.modelHandle == "melix-dev-vlm::python")
        #expect(request.messages[0].parts.count == 2)
        #expect(request.messages[0].parts[1].videoBytes == Data("video fixture".utf8))
        #expect(request.messages[0].parts[1].media.frameBudget == 6)
        #expect(request.messages[0].parts[1].media.startMs == 1_000)
        #expect(request.messages[0].parts[1].media.endMs == 5_000)
        #expect(lane.activeRequests == 0)
        #expect(metrics.values["vision.preprocess_latency_ms", default: -1] == 24)
        #expect(metrics.values["vision.preprocess_peak_memory_bytes", default: -1] == 32_768)
        #expect(metrics.values["vision.vlm_first_token_ms", default: -1] == 11)
        #expect(metrics.values["vision.video_first_token_ms", default: -1] == 11)
        #expect(metrics.values["vision.video_frame_count", default: -1] == 6)
        #expect(metrics.values["vision.video_frame_budget", default: -1] == 6)
        #expect(metrics.values["vision.video_window_ms", default: -1] == 4_000)
        #expect(metrics.values["vision.temp_media_artifact_count", default: -1] == 2)
        #expect(metrics.values["vision.temp_media_artifact_bytes", default: -1] == 2_048)
        #expect(metrics.values["vision.temp_media_cleanup_latency_ms", default: -1] == 4)
        #expect(metrics.values["vision.temp_media_cleanup_failure_count", default: -1] == 1)
        #expect(metrics.values["python_worker.generation_stream_owner_mode_code", default: -1] == 1)
        #expect(metrics.values["python_worker.worker_thread_init_latency_ms", default: -1] == 7)
        #expect(metrics.values["python_worker.stream_sync_fallback_count", default: -1] == 0)
        #expect(metrics.values["worker.model_load_trust_policy_resolution_ms", default: -1] == 0.75)
        #expect(metrics.values["worker.model_load_trust_blocked_count", default: -1] == 1)
        #expect(metrics.values["vision.multimodal_decode_mode_code", default: -1] == 3)
        #expect(metrics.values["vision.multimodal_fallback_reason_code", default: -1] == 0)
        #expect(metrics.values["vision.multimodal_decode_sync_mode_code", default: -1] == 1)
        #expect(metrics.values["vision.text_batch_generator.step_count", default: -1] == 0)
    }

    @Test("chat completions translator preserves recovery metadata on worker requests")
    func postChatCompletionsPreservesRecoveryMetadata() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-recovery", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-recovery" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "session_id": "session-recovery",
              "branch_id": "branch-main",
              "parent_request_id": "req-parent",
              "restore_snapshot_id": "snap-parent",
              "save_boundary_snapshot": true,
              "messages": [
                { "role": "user", "content": "Resume" }
              ]
            }
            """.data(using: .utf8)
        )

        _ = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        #expect(request.execution.id.sessionID == "session-recovery")
        #expect(request.execution.id.branchID == "branch-main")
        #expect(request.execution.id.parentRequestID == "req-parent")
        #expect(request.execution.cacheHints.restoreSnapshotID == "snap-parent")
        #expect(request.execution.cacheHints.saveBoundarySnapshot)
        #expect(request.execution.cacheHints.persistL2)
        #expect(request.execution.cacheHints.preferHotPrefix)
    }

    @Test("POST /v1/responses translates into the shared text request model")
    func postResponsesTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "resp-fixed", seq: 1, text: "Hello"),
            makeUsageEvent(requestID: "resp-fixed", seq: 2, promptTokens: 2, completionTokens: 1),
            makeCompletedEvent(requestID: "resp-fixed", seq: 3, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-fixed" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "instructions": "Be terse.",
              "input": "hello responses"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.messages.count == 2)
        #expect(request.messages[0].role == "system")
        #expect(request.messages[0].parts.first?.text == "Be terse.")
        #expect(request.messages[1].role == "user")
        #expect(request.messages[1].parts.first?.text == "hello responses")
        #expect(payload.contains("event: response.output_text.delta"))
        #expect(payload.contains("\"type\":\"response.output_text.delta\""))
        #expect(payload.contains("\"response_id\":\"resp-fixed\""))
        #expect(payload.contains("event: response.completed"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/completions translates prompt input into the shared text request model")
    func postCompletionsTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "cmp-fixed", seq: 1, text: "Hello"),
            makeUsageEvent(requestID: "cmp-fixed", seq: 2, promptTokens: 2, completionTokens: 1),
            makeCompletedEvent(requestID: "cmp-fixed", seq: 3, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "cmp-fixed" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "prompt": "hello completions"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.messages.count == 1)
        #expect(request.messages[0].role == "user")
        #expect(request.messages[0].parts.first?.text == "hello completions")
        #expect(payload.contains("\"object\":\"text_completion\""))
        #expect(payload.contains("\"text\":\"Hello\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/messages translates into the shared text request model")
    func postMessagesTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "msg-fixed", seq: 1, text: "Hello"),
            makeCompletedEvent(requestID: "msg-fixed", seq: 2, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "msg-fixed" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "system": "Be terse.",
              "messages": [
                { "role": "user", "content": "hello messages" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/messages",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.messages.count == 2)
        #expect(request.messages[0].role == "system")
        #expect(request.messages[0].parts.first?.text == "Be terse.")
        #expect(request.messages[1].role == "user")
        #expect(request.messages[1].parts.first?.text == "hello messages")
        #expect(payload.contains("event: message.delta"))
        #expect(payload.contains("\"type\":\"message.delta\""))
        #expect(payload.contains("\"content_block\":{\"type\":\"text\"}"))
        #expect(payload.contains("\"delta\":{\"text\":\"Hello\",\"type\":\"text_delta\"}"))
        #expect(payload.contains("\"message_id\":\"msg-fixed\""))
        #expect(payload.contains("event: message.completed"))
        #expect(payload.contains("\"content\":[{\"text\":\"Hello\",\"type\":\"text\"}]"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/messages accepts block fields thinking metadata and x-api-key headers")
    func postMessagesAcceptsBlocksThinkingMetadataAndAPIKeyHeaders() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeReasoningEvent(requestID: "msg-thinking", seq: 1, text: "trace"),
            makeTokenEvent(requestID: "msg-thinking", seq: 2, text: "done"),
            makeCompletedEvent(
                requestID: "msg-thinking",
                seq: 3,
                finishReason: "end_turn",
                assistantText: "done",
                reasoningText: "trace"
            ),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "msg-thinking" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "system": [
                { "type": "text", "text": "Be terse." }
              ],
              "stop_sequences": ["</final>"],
              "metadata": { "user_id": "operator-1" },
              "thinking": { "type": "enabled", "budget_tokens": 64 },
              "messages": [
                {
                  "role": "assistant",
                  "content": [
                    { "type": "thinking", "thinking": "trace" },
                    { "type": "text", "text": "draft" }
                  ]
                },
                {
                  "role": "user",
                  "content": [
                    { "type": "text", "text": "Continue." }
                  ]
                }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/messages",
                headers: [
                    "content-type": "application/json",
                    "x-api-key": "anthropic-local-key",
                ],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.messages.count == 3)
        #expect(request.messages[0].parts.map { $0.text } == ["Be terse."])
        #expect(request.messages[1].parts.map { $0.text } == ["trace", "draft"])
        #expect(request.execution.reasoning.enabled == true)
        #expect(request.execution.reasoning.separateStream == true)
        #expect(request.execution.ext["melix.messages.user_id"] == "operator-1")
        #expect(request.execution.ext["melix.messages.thinking.type"] == "enabled")
        #expect(request.execution.ext["melix.messages.thinking.budget_tokens"] == "64")
        #expect(request.execution.ext["melix.messages.x_api_key_present"] == "true")
        #expect(request.sampling.stop == ["</final>"])
        #expect(payload.contains("event: message.reasoning.delta"))
        #expect(payload.contains("\"content_block\":{\"type\":\"thinking\"}"))
        #expect(payload.contains("\"delta\":{\"thinking\":\"trace\",\"type\":\"thinking_delta\"}"))
        #expect(payload.contains("\"stop_reason\":\"end_turn\""))
        #expect(payload.contains("\"content\":[{\"thinking\":\"trace\",\"type\":\"thinking\"},{\"text\":\"done\",\"type\":\"text\"}]"))
    }

    @Test("POST /v1/responses forwards reasoning and tool delta events")
    func postResponsesForwardsReasoningAndToolDeltas() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeReasoningEvent(requestID: "resp-deltas", seq: 1, text: "think"),
            makeToolCallEvent(
                requestID: "resp-deltas",
                seq: 2,
                callID: "tool-1",
                toolName: "search",
                argumentsJSONFragment: "{\"q\":\"melix\"}"
            ),
            makeCompletedEvent(requestID: "resp-deltas", seq: 3, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-deltas" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "hello responses"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("event: response.reasoning.delta"))
        #expect(payload.contains("\"type\":\"response.reasoning.delta\""))
        #expect(payload.contains("\"delta\":\"think\""))
        #expect(payload.contains("event: response.tool_call.delta"))
        #expect(payload.contains("\"type\":\"response.tool_call.delta\""))
        #expect(payload.contains("\"tool_name\":\"search\""))
        #expect(payload.contains("event: response.completed"))
    }

    @Test("POST /v1/responses rejects invalid tool parser namespaces")
    func postResponsesRejectsInvalidToolParserNamespaces() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "hello responses",
              "tool_parser": {
                "mode": "qwen",
                "namespaces": ["bad namespace"]
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("Invalid tool parser namespace"))
    }

    @Test("POST /v1/responses applies model default tool parser to request metrics and stream frames")
    func postResponsesAppliesModelDefaultToolParserToRequestMetricsAndStreamFrames() async throws {
        var model = warmModel()
        model.settings.ext["tool_parser_mode"] = "qwen"
        model.settings.ext["tool_parser_namespaces"] = "tools.search"
        model.settings.ext["tool_parser_xml_fallback"] = "true"

        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = ScriptedWorkerClient(events: [
            makeToolCallEvent(
                requestID: "resp-model-parser",
                seq: 1,
                callID: "tool-1",
                toolName: "search",
                argumentsJSONFragment: "{\"q\":\"melix\"}"
            ),
            makeCompletedEvent(requestID: "resp-model-parser", seq: 2, finishReason: "stop", assistantText: "done"),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-model-parser" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "hello responses"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.execution.ext["melix.tool_parser.mode"] == "qwen")
        #expect(request.execution.ext["melix.tool_parser.source"] == "model")
        #expect(request.execution.ext["melix.tool_parser.namespaces"] == "tools.search")
        #expect(request.execution.ext["melix.tool_parser.fallback_mode"] == "xml")
        #expect(payload.contains("\"parser_mode\":\"qwen\""))
        #expect(payload.contains("\"parser_namespaces\":[\"tools.search\"]"))
        #expect(payload.contains("\"parser_fallback_mode\":\"xml\""))
        #expect(metrics.values["http.tool_parser_request_count"] == 1)
        #expect(metrics.values["http.tool_parser_qwen_request_count"] == 1)
    }

    @Test("POST /v1/responses auto injects MCP tool namespaces and source ids")
    func postResponsesAutoInjectsMCPToolNamespacesAndSourceIDs() async throws {
        let workerClient = ScriptedWorkerClient(events: [])
        let metricsStore = MetricsStore()
        let catalog = MCPToolCatalog(
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
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-mcp-auto" }),
            mcpToolCatalog: catalog
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "Call the configured tools."
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let request = try #require(await workerClient.lastGenerateRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.execution.ext["melix.tool_parser.mode"] == "json")
        #expect(request.execution.ext["melix.tool_parser.source"] == "mcp")
        #expect(request.execution.ext["melix.tool_parser.namespaces"] == "tools.fs.read,tools.fs.write")
        #expect(request.execution.ext["melix.mcp.source_ids"] == "filesystem")
        #expect(metrics.values["mcp.tool_injection_count"] == 1)
        #expect(metrics.values["mcp.configured_tool_count"] == 2)
    }

    @Test("responses requests default stream to true when omitted")
    func responsesRequestsDefaultStreamToTrue() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "resp-default", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-default" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "hello default stream"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.id.requestID == "resp-default")
        #expect(request.messages.count == 1)
        #expect(request.messages[0].parts.first?.text == "hello default stream")
    }

    @Test("POST /v1/chat/completions applies model OCR defaults for OCR models")
    func postChatCompletionsAppliesModelOCRDefaultsForOCRModels() async throws {
        let catalog = ModelCatalog(seedModels: [warmOCRModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-ocr-http", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-ocr-http" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-ocr",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Read this image." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.modelHandle == "melix-dev-ocr::local")
        #expect(request.sampling.stop == ["<ocr:end>"])
        #expect(request.execution.ext["melix.ocr.prompt_profile_id"] == "ocr-default-v1")
        #expect(request.execution.ext["melix.ocr.prompt_source"] == "request")
        #expect(request.execution.ext["melix.ocr.sampling_source"] == "model")
    }

    @Test("POST /v1/chat/completions applies gateway serving defaults when request and model omit sampling")
    func postChatCompletionsAppliesGatewayServingDefaults() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-serving-defaults-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let servingDefaultsStore = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        var defaults = Melix_Controlplane_V1_ApplyServingDefaults()
        defaults.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        defaults.temperature = 0.37
        defaults.topP = 0.91
        defaults.maxTokens = 448
        defaults.streamIntervalTokens = 4
        defaults.maxConcurrentRequests = 6
        defaults.concurrentProcessingEnabled = true
        defaults.prefillBatchSize = 3
        defaults.completionBatchSize = 2
        try await servingDefaultsStore.apply(command: defaults)

        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-http-serving-defaults", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-http-serving-defaults" }),
            gatewayServingDefaultsStore: servingDefaultsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.sampling.temperature == 0.37)
        #expect(request.sampling.topP == 0.91)
        #expect(request.sampling.maxOutputTokens == 448)
        #expect(request.execution.ext["melix.stream.interval_tokens"] == "4")
        #expect(request.execution.ext["melix.gateway.max_concurrent_requests"] == "6")
        #expect(request.execution.ext["melix.gateway.concurrent_processing"] == "true")
        #expect(request.execution.ext["melix.gateway.prefill_batch_size"] == "3")
        #expect(request.execution.ext["melix.gateway.completion_batch_size"] == "2")
    }

    @Test("responses requests preserve harmony metadata while keeping standard stream frames")
    func harmonyResponsesRequestsPreserveMetadataAndStreamFrames() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeReasoningEvent(requestID: "resp-harmony", seq: 1, text: "Need to continue."),
            makeTokenEvent(requestID: "resp-harmony", seq: 2, text: "Final answer."),
            makeCompletedEvent(requestID: "resp-harmony", seq: 3, finishReason: "stop", assistantText: "Final answer."),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-harmony" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": [
                { "role": "developer", "content": "Use tools carefully." },
                { "role": "assistant", "channel": "analysis", "content": "Need to call the weather tool." },
                {
                  "role": "assistant",
                  "channel": "commentary",
                  "recipient": "functions.get_weather",
                  "content_type": "json",
                  "content": "{\\"location\\":\\"Tokyo\\"}"
                },
                {
                  "role": "functions.get_weather",
                  "channel": "commentary",
                  "recipient": "assistant",
                  "content": "{\\"temperature\\":20}"
                },
                { "role": "user", "content": "Give me the final answer." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("event: response.reasoning.delta"))
        #expect(payload.contains("event: response.output_text.delta"))
        #expect(payload.contains("event: response.completed"))
        #expect(request.execution.ext["melix.harmony"] == "true")
        #expect(request.execution.ext["melix.harmony.message.1.channel"] == "analysis")
        #expect(request.execution.ext["melix.harmony.message.2.recipient"] == "functions.get_weather")
        #expect(request.execution.ext["melix.harmony.message.2.content_type"] == "json")
        #expect(request.execution.ext["melix.harmony.message.3.role"] == "functions.get_weather")
        #expect(metrics.values["http.harmony_shaped_count", default: 0] == 1)
    }

    @Test("chat completions reject invalid structured output contracts")
    func chatCompletionsRejectInvalidStructuredOutputContracts() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "response_format": {
                "type": "json_schema"
              },
              "messages": [
                { "role": "user", "content": "Return JSON." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("response_format json_schema requests must include json_schema."))
    }

    @Test("completions reject invalid structured output contracts")
    func completionsRejectInvalidStructuredOutputContracts() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "response_format": {
                "type": "json_schema"
              },
              "prompt": "Return JSON."
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("response_format json_schema requests must include json_schema."))
    }

    @Test("messages reject invalid structured output contracts")
    func messagesRejectInvalidStructuredOutputContracts() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "response_format": {
                "type": "json_schema"
              },
              "messages": [
                { "role": "user", "content": "Return JSON." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/messages", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("response_format json_schema requests must include json_schema."))
    }

    @Test("responses reject invalid structured output contracts")
    func responsesRejectInvalidStructuredOutputContracts() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "Return JSON.",
              "text": {
                "format": {
                  "type": "json_schema"
                }
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("response_format json_schema requests must include json_schema."))
    }

    @Test("responses structured output requests validate completed JSON before final framing")
    func responsesStructuredOutputRequestsValidateCompletedJSONBeforeFinalFraming() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(
                requestID: "resp-structured-fail",
                seq: 1,
                finishReason: "stop",
                assistantText: "{\"answer\":\"done\",\"extra\":true}"
            ),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-structured-fail" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "Return JSON.",
              "text": {
                "format": {
                  "type": "json_schema",
                  "json_schema": {
                    "name": "answer_contract",
                    "schema": {
                      "type": "object",
                      "properties": {
                        "answer": { "type": "string" }
                      },
                      "required": ["answer"]
                    },
                    "strict": true
                  }
                }
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.execution.ext["melix.structured_output.mode"] == "json_schema")
        #expect(request.execution.ext["melix.structured_output.schema_name"] == "answer_contract")
        #expect(request.execution.ext["melix.structured_output.strict"] == "true")
        #expect(request.execution.acceleration.prefillHint == "json-schema")
        #expect(metrics.values["http.structured_output_request_count", default: 0] == 1)
        #expect(metrics.values["http.structured_output_validation_failure_count", default: 0] == 1)
        #expect(payload.contains("event: error"))
        #expect(payload.contains("\"code\":\"schema_validation_failed\""))
        #expect(!payload.contains("event: response.completed"))
    }

    @Test("responses structured output requests record validation pass metrics before final framing")
    func responsesStructuredOutputRequestsRecordValidationPassMetricsBeforeFinalFraming() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(
                requestID: "resp-structured-pass",
                seq: 1,
                finishReason: "stop",
                assistantText: "{\"answer\":\"done\"}"
            ),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-structured-pass" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "Return JSON.",
              "text": {
                "format": {
                  "type": "json_schema",
                  "json_schema": {
                    "name": "answer_contract",
                    "schema": {
                      "type": "object",
                      "properties": {
                        "answer": { "type": "string" }
                      },
                      "required": ["answer"]
                    },
                    "strict": true
                  }
                }
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(metrics.values["http.structured_output_request_count", default: 0] == 1)
        #expect(metrics.values["http.structured_output_validation_pass_count", default: 0] == 1)
        #expect(metrics.values["http.structured_output_validation_failure_count", default: 0] == 0)
        #expect(!payload.contains("event: error"))
        #expect(payload.contains("event: response.completed"))
    }

    @Test("responses structured output requests skip validation for empty completed text")
    func responsesStructuredOutputRequestsSkipValidationForEmptyCompletedText() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(
                requestID: "resp-structured-empty",
                seq: 1,
                finishReason: "stop",
                assistantText: ""
            ),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-structured-empty" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "Return JSON.",
              "text": {
                "format": {
                  "type": "json_schema",
                  "json_schema": {
                    "name": "answer_contract",
                    "schema": {
                      "type": "object",
                      "properties": {
                        "answer": { "type": "string" }
                      },
                      "required": ["answer"]
                    },
                    "strict": true
                  }
                }
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(metrics.values["http.structured_output_request_count", default: 0] == 1)
        #expect(metrics.values["http.structured_output_validation_pass_count", default: 0] == 0)
        #expect(metrics.values["http.structured_output_validation_failure_count", default: 0] == 0)
        #expect(!payload.contains("event: error"))
        #expect(payload.contains("event: response.completed"))
    }

    @Test("non-stream responses requests return 400")
    func nonStreamResponsesRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "input": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("non-stream completions requests return 400")
    func nonStreamCompletionsRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "prompt": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("non-stream messages requests return 400")
    func nonStreamMessagesRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/messages", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("completions requests return 409 when the model is not ready")
    func completionsModelNotReadyReturns409() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: []),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "prompt": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("messages requests return 409 when the model is not ready")
    func messagesModelNotReadyReturns409() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: []),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/messages", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("responses requests return 409 when the model is not ready")
    func responsesModelNotReadyReturns409() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: []),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("responses requests sync registry snapshots before loading newly activated derived models")
    func responsesSyncRegistrySnapshotsBeforeLoadingNewlyActivatedDerivedModels() async throws {
        let derivedModelID = "melix-dev-text-lora-729f709c"
        let catalog = ModelCatalog(seedModels: [])
        let modelOpsClient = ScriptedRegistryModelOperationsWorkerClient()
        let workerClient = ScriptedWorkerClient(
            events: [
                makeCompletedEvent(
                    requestID: "req-derived-response",
                    seq: 1,
                    finishReason: "stop",
                    assistantText: "READY_DERIVED"
                ),
            ],
            loadModelHandle: "\(derivedModelID)::swift"
        )
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [],
            derivedModels: [
                [
                    "model_id": derivedModelID,
                    "model_path": "/tmp/melix-derived/\(derivedModelID)",
                    "source_model": "melix-dev-text",
                    "derived_model_alias": "melix-qwen35-acceptance",
                    "adapter_set_hash": "729f709c8b274b1c",
                    "status": "activated",
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
        let registry = WorkerRegistry(
            defaultTextClient: workerClient,
            pythonCompatibilityClient: workerClient,
            modelOperationsClient: modelOpsClient,
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: registry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-derived-response" })
        )
        let body = try #require(
            """
            {
              "model": "\(derivedModelID)",
              "stream": true,
              "input": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let registryRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.statusCode == 200)
        #expect(payload.contains("READY_DERIVED"))
        #expect(registryRequest.ext["operation"] == "registry_snapshot")
        #expect(registryRequest.ext["melix.registry_rescan"] == "true")
    }

    @Test("GET /v1/models returns model state from the catalog")
    func getModelsReturnsCatalogState() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/models", headers: [:], body: Data())
        )

        let body = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(body.contains("\"object\":\"list\""))
        #expect(body.contains("\"id\":\"melix-dev-text\""))
        #expect(body.contains("\"melix_state\":\"warm\""))
        #expect(body.contains("\"owned_by\":\"melix\""))
    }

    @Test("GET /v1/models hides internal operations and exposes user-facing metadata")
    func getModelsHidesInternalOperationsAndExposesUserFacingMetadata() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/models", headers: [:], body: Data())
        )
        let payload = try await jsonPayload(from: response.body)
        let rows = try #require(payload["data"] as? [[String: Any]])
        let ids = Set(rows.compactMap { $0["id"] as? String })
        let text = try #require(rows.first { ($0["id"] as? String) == "melix-dev-text" })
        let textMetadata = try #require(text["metadata"] as? [String: Any])
        let image = try #require(rows.first { ($0["id"] as? String) == "melix-dev-image" })
        let imageMetadata = try #require(image["metadata"] as? [String: Any])
        let imageTasks = Set(
            (imageMetadata["melix.capability.supported_tasks"] as? String ?? "")
                .split(separator: ",")
                .map(String.init)
        )

        #expect(response.statusCode == 200)
        #expect(ids.contains("melix-dev-text"))
        #expect(ids.contains("melix-dev-image"))
        #expect(ids.contains("melix-dev-model-ops") == false)
        #expect(textMetadata["melix.display_name"] as? String == "Melix Text")
        #expect(textMetadata["melix.kind"] as? String == "text")
        #expect(textMetadata["melix.capability.class"] as? String == "text")
        #expect(textMetadata["melix.capability.supported_tasks"] as? String == "generate")
        #expect(textMetadata["melix.capability.supported_modalities"] as? String == "text")
        #expect(textMetadata["melix.load_trust.requested_mode"] as? String == "default_safe")
        #expect(textMetadata["melix.load_trust.effective_mode"] as? String == "not_applicable")
        #expect(textMetadata["melix.load_trust.policy_source"] as? String == "not_applicable")
        #expect(textMetadata["melix.load_trust.receipt_present"] as? String == "false")
        #expect(textMetadata["melix.model_path"] == nil)
        #expect(imageMetadata["melix.display_name"] as? String == "Melix Image")
        #expect(imageMetadata["melix.capability.class"] as? String == "image_generation")
        #expect(imageTasks.contains("image_generate"))
    }

    @Test("GET /v1/models syncs registry models and exposes structured registry identity metadata")
    func getModelsSyncsRegistryModelsAndExposesStructuredRegistryIdentityMetadata() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let modelOpsClient = ScriptedRegistryModelOperationsWorkerClient()
        let manifestJSON = try makeRegistrySnapshotManifestJSON(
            models: [
                [
                    "model_id": "mlx-community/Qwen2.5-7B-Instruct/4bit",
                    "model_path": "/tmp/registry-root/huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit",
                    "model_kind": "text",
                    "quant_profile_id": "q4",
                    "max_context": 16384,
                    "ext": [
                        "melix.registry_root_id": "root-1",
                        "melix.registry_root_path": "/tmp/registry-root",
                        "melix.registry_relative_path": "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit",
                        "melix.registry_provider_id": "hf-mirror",
                        "melix.registry_organization_id": "mlx-community",
                        "melix.registry_model_name": "Qwen2.5-7B-Instruct",
                        "melix.registry_variant_id": "q4f16",
                        "melix.registry_descriptor_path": "/tmp/managed-root/huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit",
                        "melix.model_path": "/tmp/hf-cache/models--mlx-community--Qwen2.5-7B-Instruct/snapshots/abc123",
                        "melix.model_path_missing": "true",
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

        let registry = WorkerRegistry(
            defaultTextClient: NullWorkerClient(),
            modelOperationsClient: modelOpsClient,
            modelCatalog: catalog
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: registry
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/models", headers: [:], body: Data())
        )

        let request = try #require(await modelOpsClient.lastConvertRequest)
        let body = try await collectBody(response.body)
        let payload = try #require(
            JSONSerialization.jsonObject(with: Data(body.utf8)) as? [String: Any]
        )
        let rows = try #require(payload["data"] as? [[String: Any]])
        let discovered = try #require(
            rows.first(where: { ($0["id"] as? String) == "mlx-community/Qwen2.5-7B-Instruct/4bit" })
        )
        let metadata = try #require(discovered["metadata"] as? [String: Any])

        #expect(response.statusCode == 200)
        #expect(request.ext["operation"] == "registry_snapshot")
        #expect(request.ext["melix.registry_rescan"] == "true")
        #expect(request.generateManifest)
        #expect(discovered["melix_state"] as? String == "discovered")
        #expect(metadata["melix.registry_provider_id"] as? String == "hf-mirror")
        #expect(metadata["melix.registry_organization_id"] as? String == "mlx-community")
        #expect(metadata["melix.registry_model_name"] as? String == "Qwen2.5-7B-Instruct")
        #expect(metadata["melix.registry_variant_id"] as? String == "q4f16")
        #expect(metadata["melix.registry_descriptor_path"] as? String == "/tmp/managed-root/huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit")
        #expect(metadata["melix.registry_relative_path"] as? String == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit")
        #expect(metadata["melix.model_path"] as? String == "/tmp/hf-cache/models--mlx-community--Qwen2.5-7B-Instruct/snapshots/abc123")
        #expect(metadata["melix.model_path_missing"] as? String == "true")
    }

    @Test("registry model-ops stub covers unavailable control paths")
    func registryModelOpsStubCoversUnavailableControlPaths() async throws {
        let client = ScriptedRegistryModelOperationsWorkerClient()

        #expect(await client.canDispatchRequests())

        let generateStream = try await client.generate(request: Melix_Worker_V1_GenerateRequest())
        for try await _ in generateStream {}

        #expect(try await client.abort(requestID: "req-registry-stub") == false)

        let benchStream = try await client.runBench(request: Melix_Worker_V1_RunBenchRequest())
        for try await _ in benchStream {}

        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.getModelInfo(request: Melix_Worker_V1_GetModelInfoRequest())
        }
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.runDoctor(request: Melix_Worker_V1_RunDoctorRequest())
        }
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.runEvaluation(request: Melix_Worker_V1_RunEvaluationRequest())
        }
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.exportResults(request: Melix_Worker_V1_ExportResultsRequest())
        }
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.submitResults(request: Melix_Worker_V1_SubmitResultsRequest())
        }
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.loadModel(request: Melix_Worker_V1_LoadModelRequest())
        }
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await client.unloadModel(request: Melix_Worker_V1_UnloadModelRequest())
        }
    }

    @Test("GET /v1/models renders all public Melix model states")
    func getModelsRendersAllStates() async throws {
        var pinned = ModelCatalog.devTextModel()
        pinned.modelID = "melix-pinned"
        pinned.state = .modelPinned

        var unloaded = ModelCatalog.devTextModel()
        unloaded.modelID = "melix-unloaded"
        unloaded.state = .modelUnloaded

        var loading = ModelCatalog.devTextModel()
        loading.modelID = "melix-loading"
        loading.state = .modelLoading

        var discovered = ModelCatalog.devTextModel()
        discovered.modelID = "melix-discovered"
        discovered.state = .modelDiscovered

        var failed = ModelCatalog.devTextModel()
        failed.modelID = "melix-failed"
        failed.state = .modelFailed

        var evicting = ModelCatalog.devTextModel()
        evicting.modelID = "melix-evicting"
        evicting.state = .modelEvicting

        var unknown = ModelCatalog.devTextModel()
        unknown.modelID = "melix-unknown"
        unknown.state = .UNRECOGNIZED(99)

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [pinned, unloaded, loading, discovered, failed, evicting, unknown]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/models", headers: [:], body: Data())
        )
        let body = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(body.contains("\"id\":\"melix-pinned\""))
        #expect(body.contains("\"melix_state\":\"pinned\""))
        #expect(body.contains("\"id\":\"melix-unloaded\""))
        #expect(body.contains("\"melix_state\":\"unloaded\""))
        #expect(body.contains("\"id\":\"melix-loading\""))
        #expect(body.contains("\"melix_state\":\"loading\""))
        #expect(body.contains("\"id\":\"melix-discovered\""))
        #expect(body.contains("\"melix_state\":\"discovered\""))
        #expect(body.contains("\"id\":\"melix-failed\""))
        #expect(body.contains("\"melix_state\":\"failed\""))
        #expect(body.contains("\"id\":\"melix-evicting\""))
        #expect(body.contains("\"melix_state\":\"evicting\""))
        #expect(body.contains("\"id\":\"melix-unknown\""))
        #expect(body.contains("\"melix_state\":\"unknown\""))
    }

    @Test("wrong endpoint requests return actionable 400 diagnostics before worker dispatch")
    func wrongEndpointRequestsReturnActionableDiagnosticsBeforeWorkerDispatch() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let nonTextClient = ScriptedPhaseFiveWorkerClient()
        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: nonTextClient,
                embeddingClient: nonTextClient,
                rerankClient: nonTextClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore
        )
        let cases: [(HTTPMethod, String, String, String)] = [
            (
                .post,
                "/v1/chat/completions",
                #"{"model":"melix-dev-transcribe","stream":true,"messages":[{"role":"user","content":"hello"}]}"#,
                "/v1/audio/transcriptions"
            ),
            (.post, "/v1/embeddings", #"{"model":"melix-dev-speech","input":"hello"}"#, "/v1/audio/speech"),
            (
                .post,
                "/v1/rerank",
                #"{"model":"melix-dev-embed","query":"q","documents":["a"],"top_k":1}"#,
                "/v1/embeddings"
            ),
            (
                .post,
                "/v1/audio/transcriptions",
                #"{"model":"melix-dev-text","audio_base64":"aGVsbG8="}"#,
                "/v1/chat/completions"
            ),
            (.post, "/v1/audio/speech", #"{"model":"melix-dev-transcribe","input":"hello"}"#, "/v1/audio/transcriptions"),
            (.post, "/v1/images/generations", #"{"model":"melix-dev-rerank","prompt":"draw"}"#, "/v1/rerank"),
            (.post, "/v1/images/edits", #"{"model":"melix-dev-text","prompt":"edit"}"#, "/v1/chat/completions"),
        ]

        for (method, path, rawBody, expectedEndpoint) in cases {
            let response = try await handler.handle(
                HTTPRequest(
                    method: method,
                    path: path,
                    headers: [:],
                    body: Data(rawBody.utf8)
                )
            )
            let payload = try await jsonPayload(from: response.body)
            let error = try #require(payload["error"] as? [String: Any])

            #expect(response.statusCode == 400)
            #expect(error["code"] as? String == "wrong_endpoint_for_model")
            #expect(error["correct_endpoint"] as? String == expectedEndpoint)
            #expect((error["message"] as? String ?? "").contains(expectedEndpoint))
        }

        #expect(await textClient.lastGenerateRequest == nil)
        #expect(await nonTextClient.lastEmbedRequest == nil)
        #expect(await nonTextClient.lastRerankRequest == nil)
        #expect(await nonTextClient.lastTranscribeRequest == nil)
        #expect(await nonTextClient.lastSpeakRequest == nil)
        #expect(await nonTextClient.lastImageGenerateRequest == nil)
        #expect(await nonTextClient.lastImageEditRequest == nil)
        #expect(await metricsStore.value(forKey: "endpoint_type_validation_result") == 0)
        #expect(await metricsStore.value(forKey: "endpoint_type_validation_rejection_count") == Double(cases.count))
    }

    @Test("POST /v1/embeddings routes to the embedding worker and returns JSON")
    func postEmbeddingsRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setEmbedResponse({
            var response = Melix_Worker_V1_EmbedResponse()
            response.embeddings = [
                {
                    var embedding = Melix_Worker_V1_Embedding()
                    embedding.values = [0.1, 0.2]
                    return embedding
                }(),
                {
                    var embedding = Melix_Worker_V1_Embedding()
                    embedding.values = [0.3, 0.4]
                    return embedding
                }(),
            ]
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                embeddingClient: embeddingClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha", "beta"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await embeddingClient.lastEmbedRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(request.modelHandle == "melix-dev-embed::python")
        #expect(request.inputs == ["alpha", "beta"])
        #expect(payload.contains("\"object\":\"list\""))
        #expect(payload.contains("\"embedding\":[0.1,0.2]"))
        #expect(payload.contains("\"model\":\"melix-dev-embed\""))
        #expect(metrics.values["embeddings.request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["embeddings.items_per_second", default: 0] > 0)
    }

    @Test("POST /v1/rerank routes to the rerank worker and returns JSON")
    func postRerankRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let rerankClient = ScriptedPhaseFiveWorkerClient()
        await rerankClient.setRerankResponse({
            var response = Melix_Worker_V1_RerankResponse()
            response.items = [
                {
                    var item = Melix_Worker_V1_RerankItem()
                    item.index = 1
                    item.score = 0.91
                    return item
                }(),
                {
                    var item = Melix_Worker_V1_RerankItem()
                    item.index = 0
                    item.score = 0.73
                    return item
                }(),
            ]
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devRerankModel()])
        _ = await catalog.loadModel(id: "melix-dev-rerank", dispatchHandle: "melix-dev-rerank::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                rerankClient: rerankClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-rerank",
              "query": "swift worker",
              "documents": ["python bridge", "swift worker"],
              "top_k": 2
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await rerankClient.lastRerankRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.modelHandle == "melix-dev-rerank::python")
        #expect(request.query == "swift worker")
        #expect(request.documents == ["python bridge", "swift worker"])
        #expect(payload.contains("\"model\":\"melix-dev-rerank\""))
        #expect(payload.contains("\"index\":1"))
        #expect(payload.contains("\"score\":0.91"))
        #expect(metrics.values["rerank.request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["rerank.documents_per_second", default: 0] > 0)
    }

    @Test("POST /v1/audio/transcriptions routes to the transcription worker and returns JSON")
    func postAudioTranscriptionsRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.text = "hello audio"
            response.language = "en"
            response.durationSeconds = 0.25
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_base64": "aGVsbG8gYXVkaW8=",
              "format": "wav",
              "language": "en"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await audioClient.lastTranscribeRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(request.modelHandle == "melix-dev-transcribe::python")
        #expect(request.audioBytes == Data("hello audio".utf8))
        #expect(request.format == "wav")
        #expect(request.language == "en")
        #expect(payload.contains("\"model\":\"melix-dev-transcribe\""))
        #expect(payload.contains("\"text\":\"hello audio\""))
        #expect(payload.contains("\"language\":\"en\""))
        #expect(payload.contains("\"duration_seconds\":0.25"))
        #expect(metrics.values["audio.transcription_request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["audio.seconds_processed_per_second", default: 0] > 0)
    }

    @Test("POST /v1/audio/transcriptions lazy-loads managed mlx-audio models")
    func postAudioTranscriptionsLazyLoadsManagedMLXAudioModels() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.text = "lazy loaded whisper"
            response.language = "en"
            response.durationSeconds = 0.5
            return response
        }())

        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-lazy-transcribe-\(UUID().uuidString)", isDirectory: true)
        let managedModelPath = melixHomeDirectory
            .appendingPathComponent("managed/whisper", isDirectory: true)
            .path
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-stt"]
        )
        try assetManager.recordManagedModel(
            modelID: "melix-whisper-mlx",
            revision: "mlx-audio",
            sourceModelPath: "mlx-community/whisper-large-v3-turbo-asr-fp16",
            localModelPath: managedModelPath
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxWhisperModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )

        let body = try #require(
            """
            {
              "model": "melix-whisper-mlx",
              "audio_base64": "aGVsbG8gYXVkaW8=",
              "format": "wav"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let loadRequest = try #require(await audioClient.lastLoadModelRequest)
        let request = try #require(await audioClient.lastTranscribeRequest)

        #expect(response.statusCode == 200)
        #expect(loadRequest.model.modelID == "melix-whisper-mlx")
        #expect(loadRequest.model.modelPath == managedModelPath)
        #expect(loadRequest.model.revision == "mlx-audio")
        #expect(request.modelHandle == "melix-whisper-mlx::python")
        #expect(payload.contains("\"model\":\"melix-whisper-mlx\""))
        #expect(payload.contains("\"text\":\"lazy loaded whisper\""))
    }

    @Test("POST /v1/audio/transcriptions records background-lane and runtime probe metrics")
    func postAudioTranscriptionsRecordsIsolationAndProbeMetrics() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.text = "hello audio"
            response.language = "en"
            response.durationSeconds = 0.5
            return response
        }())
        await audioClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.activeMultimodalRequests = 1
            response.stats.lastProbeKind = "transcription"
            response.stats.lastPreprocessLatencyMs = 14
            response.stats.lastPreprocessPeakMemoryBytes = 4096
            response.stats.lastTranscriptionLatencyMs = 22
            response.stats.lastAudioDurationSeconds = 0.5
            response.stats.lastAudioChunkCount = 3
            return response
        }())

        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_base64": "aGVsbG8gYXVkaW8="
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let metrics = await metricsStore.snapshot()
        let queueSummary = await schedulerReadModel.snapshot()
        let lane = try #require(
            queueSummary.lanes.first(where: { $0.laneID == "multimodal.audio.transcription.background" })
        )

        #expect(response.statusCode == 200)
        #expect(lane.activeRequests == 0)
        #expect(lane.admissionRate == 1)
        #expect(metrics.values["scheduler.multimodal_queue_delay_ms", default: -1] >= 0)
        #expect(metrics.values["scheduler.multimodal_active_requests", default: -1] == 0)
        #expect(metrics.values["scheduler.text_protection_active", default: -1] == 0)
        #expect(metrics.values["audio.preprocess_latency_ms", default: -1] == 14)
        #expect(metrics.values["audio.preprocess_peak_memory_bytes", default: -1] == 4096)
        #expect(metrics.values["audio.transcription_latency_ms", default: -1] == 22)
        #expect(metrics.values["audio.audio_duration_seconds", default: -1] == 0.5)
        #expect(metrics.values["audio.audio_chunk_count", default: -1] == 3)
    }

    @Test("POST /v1/audio/transcriptions supports input_audio URIs and defaults the task")
    func postAudioTranscriptionsSupportsInputAudioURIsAndDefaultsTheTask() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.error.code = "invalid_argument"
            response.error.message = "bad audio uri"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "input_audio": {
                "url": "file:///tmp/audio.mp3",
                "format": "mp3",
                "mime_type": "audio/mpeg",
                "filename": "audio.mp3"
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await audioClient.lastTranscribeRequest)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(request.audioUri == "file:///tmp/audio.mp3")
        #expect(request.audio.sourceKind == .mediaSourceUri)
        #expect(request.audio.format == "mp3")
        #expect(request.audio.mimeType == "audio/mpeg")
        #expect(request.audio.filename == "audio.mp3")
        #expect(request.task == "transcribe")
        #expect(request.language.isEmpty)
    }

    @Test("POST /v1/audio/transcriptions validates input payloads and thrown failures")
    func postAudioTranscriptionsValidatesInputPayloadsAndThrownFailures() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let invalidBase64 = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_base64": "%%%INVALID%%%"
            }
            """.data(using: .utf8)
        )
        let invalidBase64Response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: invalidBase64)
        )
        let invalidBase64Payload = try await collectBody(invalidBase64Response.body)

        #expect(invalidBase64Response.statusCode == 400)
        #expect(invalidBase64Payload.contains("\"code\":\"invalid_argument\""))
        #expect(invalidBase64Payload.contains("audio_base64 must be valid base64"))

        let missingAudio = try #require(
            """
            {
              "model": "melix-dev-transcribe"
            }
            """.data(using: .utf8)
        )
        let missingAudioResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: missingAudio)
        )
        let missingAudioPayload = try await collectBody(missingAudioResponse.body)

        #expect(missingAudioResponse.statusCode == 400)
        #expect(missingAudioPayload.contains("\"code\":\"invalid_argument\""))
        #expect(missingAudioPayload.contains("input_audio or audio_base64\\/audio_url is required"))

        await audioClient.setThrownFailure(WorkerClientError.unavailable)
        let thrownFailure = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_url": "file:///tmp/audio.wav"
            }
            """.data(using: .utf8)
        )
        let thrownFailureResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: thrownFailure)
        )
        let thrownFailurePayload = try await collectBody(thrownFailureResponse.body)

        #expect(thrownFailureResponse.statusCode == 503)
        #expect(thrownFailurePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/transcriptions returns 503 for missing compatible routes and unavailable workers")
    func postAudioTranscriptionsReturns503ForMissingCompatibleRoutesAndUnavailableWorkers() async throws {
        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devTranscriptionModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_url": "file:///tmp/audio.wav"
            }
            """.data(using: .utf8)
        )

        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 503)
        #expect(unloadedPayload.contains("\"code\":\"worker_unavailable\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/transcriptions preflights missing audio runtime packs for real audio models")
    func postAudioTranscriptionsPreflightsMissingAudioRuntimePacksForRealAudioModels() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let assetManager = AudioAssetManager(
            melixHomeDirectory: FileManager.default.temporaryDirectory
                .appendingPathComponent("melix-http-audio-preflight-\(UUID().uuidString)", isDirectory: true)
        )
        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxWhisperModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )

        let body = try #require(
            """
            {
              "model": "melix-whisper-mlx",
              "audio_url": "file:///tmp/audio.wav"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"audio_runtime_pack_required\""))
        #expect(payload.contains("\"runtime_pack_id\":\"melix-audio-runtime-pack\""))
        #expect(await audioClient.lastTranscribeRequest == nil)
    }

    @Test("POST /v1/audio/speech routes to the speech worker and returns audio bytes")
    func postAudioSpeechRoutesAndReturnsAudioBytes() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("VOICE=alloy\nFORMAT=wav\nTEXT=hello speech".utf8)
            response.format = "wav"
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech",
              "voice": "alloy",
              "format": "wav",
              "instructions": "Use a calm voice."
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let request = try #require(await audioClient.lastSpeakRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "audio/wav")
        #expect(request.modelHandle == "melix-dev-speech::python")
        #expect(request.input == "hello speech")
        #expect(request.voice == "alloy")
        #expect(request.format == "wav")
        #expect(request.instructions == "Use a calm voice.")
        #expect(request.streamingEnabled == false)
        #expect(request.streamIntervalMs == 0)
        #expect(response.headers["x-melix-audio-resolved-locale"] == "und")
        #expect(response.headers["x-melix-audio-locale-source"] == "model_default")
        #expect(response.headers["x-melix-audio-locale-policy"] == "request>model_default>packaged_default")
        #expect(response.headers["x-melix-audio-model-default-locale"] == "und")
        #expect(response.headers["x-melix-audio-packaged-default-locale"] == "und")
        #expect(response.headers["x-melix-audio-supported-locales"] == "und")
        #expect(payload == Data("VOICE=alloy\nFORMAT=wav\nTEXT=hello speech".utf8))
        #expect(metrics.values["audio.speech_request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["audio.speech_output_bytes", default: 0] == 40)
    }

    @Test("POST /v1/audio/speech streams progressive WAV chunks and records streaming metrics")
    func postAudioSpeechStreamsProgressiveWAVAndRecordsStreamingMetrics() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let envelopeBytes = progressiveWAVHeader(sampleRate: 24_000)
        let pcmChunk = Data([0x00, 0x00, 0x01, 0x00])
        await audioClient.setSpeakStreamEvents([
            {
                var event = Melix_Worker_V1_SpeakStreamEvent()
                event.kind = .envelope
                event.audioBytes = envelopeBytes
                event.envelope.format = "wav"
                event.envelope.container = "wav"
                event.envelope.codec = "pcm_s16le"
                event.envelope.sampleRateHz = 24_000
                event.envelope.channelCount = 1
                event.envelope.bitsPerSample = 16
                event.envelope.streamIntervalMs = 30
                event.envelope.wavSizesUnknown = true
                return event
            }(),
            {
                var event = Melix_Worker_V1_SpeakStreamEvent()
                event.kind = .audioChunk
                event.audioBytes = pcmChunk
                return event
            }(),
            {
                var event = Melix_Worker_V1_SpeakStreamEvent()
                event.kind = .finish
                event.finish.speechStreamingEnabled = true
                event.finish.speechStreamingIntervalMs = 30
                event.finish.speechFirstAudioLatencyMs = 4.5
                event.finish.speechLatencyMs = 12
                event.finish.audioBytes = UInt64(envelopeBytes.count + pcmChunk.count)
                event.finish.audioChunkCount = 1
                return event
            }(),
        ])
        await audioClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.lastProbeKind = "speech"
            response.stats.lastSpeechLatencyMs = 12
            response.stats.lastAudioOutputBytes = UInt64(envelopeBytes.count + pcmChunk.count)
            response.stats.lastAudioChunkCount = 1
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello streamed speech",
              "voice": "alloy",
              "format": "wav",
              "stream": true,
              "stream_interval_ms": 30
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        if case .data = response.body {
            Issue.record("Expected streaming speech response body.")
        }
        let payload = try await collectBodyData(response.body)
        let request = try #require(await audioClient.lastSpeakRequest)
        let metrics = await metricsStore.snapshot()
        var expectedPayload = envelopeBytes
        expectedPayload.append(pcmChunk)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "audio/wav")
        #expect(response.headers["x-melix-audio-streaming"] == "true")
        #expect(response.headers["x-melix-audio-stream-interval-ms"] == "30")
        #expect(request.streamingEnabled == true)
        #expect(request.streamIntervalMs == 30)
        #expect(payload == expectedPayload)
        #expect(payload.starts(with: Data("RIFF".utf8)))
        #expect(metrics.values["audio.speech_streaming_enabled", default: -1] == 1)
        #expect(metrics.values["audio.speech_streaming_interval_ms", default: -1] == 30)
        #expect(metrics.values["audio.speech_first_audio_latency_ms", default: -1] == 4.5)
        #expect(metrics.values["audio.speech_stream_chunk_count", default: -1] == 1)
        #expect(metrics.values["audio.speech_output_bytes", default: -1] == Double(envelopeBytes.count + pcmChunk.count))
    }

    @Test("POST /v1/audio/speech propagates streaming worker error events")
    func postAudioSpeechStreamingPropagatesWorkerErrorEvents() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakStreamEvents([
            {
                var event = Melix_Worker_V1_SpeakStreamEvent()
                event.kind = .error
                event.error.code = "runtime_error"
                event.error.message = "stream failed"
                return event
            }(),
        ])
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "error stream",
              "stream": true
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )

        #expect(response.statusCode == 200)
        await #expect(throws: WorkerClientError.requestFailed(code: "runtime_error", message: "stream failed")) {
            _ = try await collectBodyData(response.body)
        }
    }

    @Test("POST /v1/audio/speech records fallback streaming metrics when finish is absent")
    func postAudioSpeechStreamingRecordsFallbackMetricsWhenFinishIsAbsent() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let envelopeBytes = progressiveWAVHeader(sampleRate: 24_000)
        let pcmChunk = Data([0x02, 0x00, 0x03, 0x00])
        await audioClient.setSpeakStreamEvents([
            {
                var event = Melix_Worker_V1_SpeakStreamEvent()
                event.kind = .envelope
                event.audioBytes = envelopeBytes
                return event
            }(),
            {
                var event = Melix_Worker_V1_SpeakStreamEvent()
                event.kind = .audioChunk
                event.audioBytes = pcmChunk
                return event
            }(),
        ])
        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "missing finish",
              "stream": true,
              "stream_interval_ms": 40
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let metrics = await metricsStore.snapshot()
        var expectedPayload = envelopeBytes
        expectedPayload.append(pcmChunk)

        #expect(payload == expectedPayload)
        #expect(metrics.values["audio.speech_streaming_enabled", default: -1] == 1)
        #expect(metrics.values["audio.speech_streaming_interval_ms", default: -1] == 40)
        #expect(metrics.values["audio.speech_stream_chunk_count", default: -1] == 1)
        #expect(metrics.values["audio.speech_output_bytes", default: -1] == Double(envelopeBytes.count + pcmChunk.count))
        #expect(metrics.values["audio.speech_first_audio_latency_ms", default: -1] > 0)
    }

    @Test("POST /v1/audio/speech propagates thrown streaming failures")
    func postAudioSpeechStreamingPropagatesThrownFailures() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakStreamFailure(WorkerClientError.unavailable)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "thrown stream",
              "stream": true
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )

        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await collectBodyData(response.body)
        }
    }

    @Test("POST /v1/audio/speech rejects out-of-range streaming cadence before dispatch")
    func postAudioSpeechRejectsOutOfRangeStreamingCadence() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "bad cadence",
              "stream": true,
              "stream_interval_ms": 0
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("stream_interval_ms"))
        #expect(await audioClient.lastSpeakRequest == nil)
    }

    @Test("POST /v1/audio/speech normalizes requested locales and exposes hydrated speech headers")
    func postAudioSpeechNormalizesRequestedLocalesAndExposesHydratedSpeechHeaders() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("qwen-voice".utf8)
            response.format = "wav"
            return response
        }())

        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-locale-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-tts"]
        )
        try assetManager.recordManagedModel(
            modelID: "melix-qwen3-tts-mlx",
            revision: "mlx-audio",
            sourceModelPath: "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit",
            localModelPath: melixHomeDirectory
                .appendingPathComponent("managed/qwen3-tts", isDirectory: true)
                .path
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.mlxQwen3TTSModel()])
        _ = await catalog.loadModel(id: "melix-qwen3-tts-mlx", dispatchHandle: "melix-qwen3-tts-mlx::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )

        let body = try #require(
            """
            {
              "model": "melix-qwen3-tts-mlx",
              "input": "hello speech",
              "format": "wav",
              "locale": "en_US"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let request = try #require(await audioClient.lastSpeakRequest)

        #expect(response.statusCode == 200)
        #expect(request.modelHandle == "melix-qwen3-tts-mlx::python")
        #expect(response.headers["x-melix-audio-requested-locale"] == "en-us")
        #expect(response.headers["x-melix-audio-resolved-locale"] == "en")
        #expect(response.headers["x-melix-audio-locale-source"] == "request")
        #expect(response.headers["x-melix-audio-locale-policy"] == "request>model_default>packaged_default")
        #expect(response.headers["x-melix-audio-model-default-locale"] == "zh")
        #expect(response.headers["x-melix-audio-packaged-default-locale"] == "zh")
        #expect(response.headers["x-melix-audio-supported-locales"] == "zh,en")
        #expect(response.headers["x-melix-audio-install-profile"] == "audio-tts")
        #expect(response.headers["x-melix-audio-runtime-pack-state"] == "installed")
        #expect(response.headers["x-melix-audio-runtime-pack-id"] == "melix-audio-runtime-pack")
        #expect(response.headers["x-melix-audio-model-state"] == "managed_local")
        #expect(payload == Data("qwen-voice".utf8))
    }

    @Test("POST /v1/audio/speech returns model_not_ready for unknown models and preserves requested locale normalization")
    func postAudioSpeechReturnsModelNotReadyForUnknownModels() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: []),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedPhaseFiveWorkerClient()
            )
        )

        let body = try #require(
            """
            {
              "model": "missing-speech-model",
              "input": "hello speech",
              "locale": "en_US"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("POST /v1/audio/speech falls back to packaged default locales and language metadata")
    func postAudioSpeechFallsBackToPackagedDefaultLocalesAndLanguageMetadata() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("packaged-default".utf8)
            response.format = "wav"
            return response
        }())

        var packagedDefaultModel = ModelCatalog.devSpeechModel()
        packagedDefaultModel.modelID = "melix-speech-packaged-default"
        packagedDefaultModel.settings.ext["melix.audio.voice_locales"] = ""
        packagedDefaultModel.settings.ext["melix.audio.languages"] = "en_US,en-us,zh"
        packagedDefaultModel.settings.ext["melix.audio.default_locale"] = ""
        packagedDefaultModel.settings.ext["melix.audio.packaged_default_locale"] = "zh"
        packagedDefaultModel.settings.ext["melix.audio.locale_policy"] = "request>model_default>packaged_default"

        let catalog = ModelCatalog(seedModels: [packagedDefaultModel])
        _ = await catalog.loadModel(
            id: "melix-speech-packaged-default",
            dispatchHandle: "melix-speech-packaged-default::python"
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-speech-packaged-default",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)

        #expect(response.statusCode == 200)
        #expect(response.headers["x-melix-audio-resolved-locale"] == "zh")
        #expect(response.headers["x-melix-audio-locale-source"] == "packaged_default")
        #expect(response.headers["x-melix-audio-packaged-default-locale"] == "zh")
        #expect(response.headers["x-melix-audio-supported-locales"] == "en-us,zh")
        #expect(payload == Data("packaged-default".utf8))
    }

    @Test("POST /v1/audio/speech omits locale headers when no locale metadata is advertised")
    func postAudioSpeechOmitsLocaleHeadersWhenNoLocaleMetadataIsAdvertised() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("no-locale-metadata".utf8)
            response.format = "wav"
            return response
        }())

        var noLocaleModel = ModelCatalog.devSpeechModel()
        noLocaleModel.modelID = "melix-speech-no-locale"
        noLocaleModel.settings.ext["melix.audio.voice_locales"] = ""
        noLocaleModel.settings.ext["melix.audio.languages"] = ""
        noLocaleModel.settings.ext["melix.audio.default_locale"] = ""
        noLocaleModel.settings.ext["melix.audio.packaged_default_locale"] = ""
        noLocaleModel.settings.ext["melix.audio.locale_policy"] = ""

        let catalog = ModelCatalog(seedModels: [noLocaleModel])
        _ = await catalog.loadModel(id: "melix-speech-no-locale", dispatchHandle: "melix-speech-no-locale::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-speech-no-locale",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)

        #expect(response.statusCode == 200)
        #expect(response.headers["x-melix-audio-requested-locale"] == nil)
        #expect(response.headers["x-melix-audio-resolved-locale"] == nil)
        #expect(response.headers["x-melix-audio-locale-source"] == nil)
        #expect(response.headers["x-melix-audio-model-default-locale"] == nil)
        #expect(response.headers["x-melix-audio-packaged-default-locale"] == nil)
        #expect(response.headers["x-melix-audio-supported-locales"] == nil)
        #expect(payload == Data("no-locale-metadata".utf8))
    }

    @Test("POST /v1/audio/speech records background-lane and runtime probe metrics")
    func postAudioSpeechRecordsIsolationAndProbeMetrics() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("runtime-bytes".utf8)
            response.format = "wav"
            return response
        }())
        await audioClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.activeMultimodalRequests = 1
            response.stats.lastProbeKind = "speech"
            response.stats.lastSpeechLatencyMs = 31
            response.stats.lastAudioOutputBytes = 13
            return response
        }())

        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let metrics = await metricsStore.snapshot()
        let queueSummary = await schedulerReadModel.snapshot()
        let lane = try #require(
            queueSummary.lanes.first(where: { $0.laneID == "multimodal.audio.speech.background" })
        )

        #expect(response.statusCode == 200)
        #expect(lane.activeRequests == 0)
        #expect(lane.admissionRate == 1)
        #expect(metrics.values["audio.speech_latency_ms", default: -1] == 31)
        #expect(metrics.values["audio.speech_output_bytes", default: -1] == 13)
        #expect(metrics.values["scheduler.multimodal_queue_delay_ms", default: -1] >= 0)
        #expect(metrics.values["scheduler.text_protection_active", default: -1] == 0)
    }

    @Test("POST /v1/audio/speech defaults optional fields and resolves mp3 content types")
    func postAudioSpeechDefaultsOptionalFieldsAndResolvesMp3ContentTypes() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("mp3-bytes".utf8)
            response.format = ""
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech",
              "format": "mp3"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let request = try #require(await audioClient.lastSpeakRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "audio/mpeg")
        #expect(request.voice.isEmpty)
        #expect(request.format == "mp3")
        #expect(request.instructions.isEmpty)
        #expect(payload == Data("mp3-bytes".utf8))
    }

    @Test("POST /v1/audio/speech lazy-loads managed mlx-audio models")
    func postAudioSpeechLazyLoadsManagedMLXAudioModels() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("lazy-loaded-kokoro".utf8)
            response.format = "wav"
            return response
        }())

        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-lazy-speech-\(UUID().uuidString)", isDirectory: true)
        let managedModelPath = melixHomeDirectory
            .appendingPathComponent("managed/kokoro", isDirectory: true)
            .path
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-tts"]
        )
        try assetManager.recordManagedModel(
            modelID: "melix-kokoro-mlx",
            revision: "mlx-audio",
            sourceModelPath: "mlx-community/Kokoro-82M-bf16",
            localModelPath: managedModelPath
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxKokoroModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )

        let body = try #require(
            """
            {
              "model": "melix-kokoro-mlx",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let loadRequest = try #require(await audioClient.lastLoadModelRequest)
        let request = try #require(await audioClient.lastSpeakRequest)

        #expect(response.statusCode == 200)
        #expect(loadRequest.model.modelID == "melix-kokoro-mlx")
        #expect(loadRequest.model.modelPath == managedModelPath)
        #expect(loadRequest.model.revision == "mlx-audio")
        #expect(request.modelHandle == "melix-kokoro-mlx::python")
        #expect(response.headers["x-melix-audio-model-state"] == "managed_local")
        #expect(payload == Data("lazy-loaded-kokoro".utf8))
    }

    @Test("POST /v1/audio/speech rejects formats unsupported by the selected model")
    func postAudioSpeechRejectsFormatsUnsupportedByTheSelectedModel() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        var kokoro = ModelCatalog.mlxKokoroModel()
        kokoro.state = .modelDiscovered
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), kokoro])
        _ = await catalog.loadModel(id: "melix-kokoro-mlx", dispatchHandle: "melix-kokoro-mlx::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-kokoro-mlx",
              "input": "hello speech",
              "format": "mp3"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("does not support format"))
        #expect(await audioClient.lastSpeakRequest == nil)
    }

    @Test("POST /v1/audio/speech rejects unsupported explicit locales")
    func postAudioSpeechRejectsUnsupportedExplicitLocales() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-unsupported-locale-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-tts"]
        )
        try assetManager.recordManagedModel(
            modelID: "melix-kokoro-mlx",
            revision: "mlx-audio",
            sourceModelPath: "mlx-community/Kokoro-82M-bf16",
            localModelPath: melixHomeDirectory
                .appendingPathComponent("managed/kokoro", isDirectory: true)
                .path
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxKokoroModel()])
        _ = await catalog.loadModel(id: "melix-kokoro-mlx", dispatchHandle: "melix-kokoro-mlx::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )

        let body = try #require(
            """
            {
              "model": "melix-kokoro-mlx",
              "input": "hello speech",
              "format": "wav",
              "locale": "fr-FR"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("does not advertise locale fr-fr"))
        #expect(payload.contains("Supported locales: en"))
        #expect(await audioClient.lastSpeakRequest == nil)
    }

    @Test("POST /v1/audio/speech maps worker errors and thrown failures to HTTP responses")
    func postAudioSpeechMapsWorkerErrorsAndThrownFailuresToHTTPResponses() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.error.code = "internal"
            response.error.message = "speech synthesis failed"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let errorResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let errorPayload = try await collectBody(errorResponse.body)

        #expect(errorResponse.statusCode == 500)
        #expect(errorPayload.contains("\"code\":\"internal\""))
        #expect(errorPayload.contains("\"message\":\"speech synthesis failed\""))

        await audioClient.setThrownFailure(WorkerClientError.unavailable)
        let unavailableResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/speech returns 503 for missing compatible routes and unavailable workers")
    func postAudioSpeechReturns503ForMissingCompatibleRoutesAndUnavailableWorkers() async throws {
        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devSpeechModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 503)
        #expect(unloadedPayload.contains("\"code\":\"worker_unavailable\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/speech preflights missing managed audio models after runtime install")
    func postAudioSpeechPreflightsMissingManagedAudioModelsAfterRuntimeInstall() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-model-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-stt", "audio-tts"]
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxKokoroModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )

        let body = try #require(
            """
            {
              "model": "melix-kokoro-mlx",
              "input": "hello speech",
              "format": "wav"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"audio_model_download_required\""))
        #expect(payload.contains("\"model_id\":\"melix-kokoro-mlx\""))
        #expect(await audioClient.lastSpeakRequest == nil)
    }

    @Test("POST /v1/audio/speech propagates missing processor asset diagnostics from first load")
    func postAudioSpeechPropagatesMissingProcessorAssetDiagnosticsFromFirstLoad() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        var loadFailure = Melix_Worker_V1_LoadModelResponse()
        loadFailure.ok = false
        loadFailure.error.code = "audio_processor_validation_failed"
        loadFailure.error.message = "Audio model melix-kokoro-mlx is missing required processor_config processor assets before load_model:processor_asset_preflight."
        loadFailure.error.details = [
            "missing_asset_class": "processor_config",
            "load_stage": "load_model:processor_asset_preflight",
            "audio_processor_validation_result": "0",
        ]
        await audioClient.setLoadModelResponse(loadFailure)

        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-processor-\(UUID().uuidString)", isDirectory: true)
        let managedModelPath = melixHomeDirectory
            .appendingPathComponent("managed/kokoro", isDirectory: true)
            .path
        let assetManager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        try assetManager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-tts"]
        )
        try assetManager.recordManagedModel(
            modelID: "melix-kokoro-mlx",
            revision: "mlx-audio",
            sourceModelPath: "mlx-community/Kokoro-82M-bf16",
            localModelPath: managedModelPath
        )

        let catalog = ModelCatalog(seedModels: [ModelCatalog.mlxKokoroModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            audioAssetManager: assetManager
        )
        let body = try #require(
            """
            {
              "model": "melix-kokoro-mlx",
              "input": "hello speech",
              "format": "wav"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await jsonPayload(from: response.body)
        let error = try #require(payload["error"] as? [String: Any])
        let details = try #require(error["details"] as? [String: Any])

        #expect(response.statusCode == 409)
        #expect(error["code"] as? String == "audio_processor_validation_failed")
        #expect(details["missing_asset_class"] as? String == "processor_config")
        #expect(details["load_stage"] as? String == "load_model:processor_asset_preflight")
        #expect(details["audio_processor_validation_result"] as? String == "0")
        #expect(await audioClient.lastLoadModelRequest != nil)
        #expect(await audioClient.lastSpeakRequest == nil)
    }

    @Test("POST /v1/images/generations routes to the image worker and returns JSON")
    func postImageGenerationsRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.images = [Data("generated-image".utf8)]
            response.job.requestID = "image-generate-1"
            response.job.jobID = "image-generate-1::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [makeWorkerArtifact(jobID: "image-generate-1::image-generate", role: .imageArtifactGenerated)]
            return response
        }())
        await imageClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.lastProbeKind = "image"
            response.stats.lastImageJobLatencyMs = 48
            response.stats.lastImageArtifactPublishMs = 2.5
            response.stats.lastImageOutputBytes = 15
            response.stats.lastImagePeakMemoryBytes = 65536
            return response
        }())

        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel,
            imageJobReadModel: imageJobReadModel
        )

        let body = try #require(
            """
            {
              "id": "image-generate-1",
              "model": "melix-dev-image",
              "prompt": "red fox in snow",
              "size": "256x256",
              "n": 1,
              "response_format": "png",
              "artifact_namespace": "tests"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await imageClient.lastImageGenerateRequest)
        let metrics = await metricsStore.snapshot()
        let job = try #require(await imageJobReadModel.job(requestID: "image-generate-1"))

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(request.modelHandle == "melix-dev-image::python")
        #expect(request.prompt == "red fox in snow")
        #expect(request.size == "256x256")
        #expect(request.responseFormat == "png")
        #expect(request.artifactNamespace == "tests")
        #expect(payload.contains("\"job_id\":\"image-generate-1::image-generate\""))
        #expect(payload.contains("\"operation\":\"image_generate\""))
        #expect(payload.contains("\"request_timeout_seconds\":1800"))
        #expect(payload.contains("\"recipe\":{"))
        #expect(payload.contains("\"prompt\":\"red fox in snow\""))
        #expect(payload.contains("\"artifact_namespace\":\"tests\""))
        #expect(payload.contains("\"b64_json\":\"Z2VuZXJhdGVkLWltYWdl\""))
        #expect(job.state == .imageJobCompleted)
        #expect(job.lane == "image.generate.background")
        #expect(job.artifacts.count == 1)
        #expect(metrics.values["images.request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["images.output_bytes", default: 0] == 15)
        #expect(metrics.values["images.job_latency_ms", default: -1] == 48)
        #expect(metrics.values["images.artifact_publish_ms", default: -1] == 2.5)
        #expect(metrics.values["images.peak_memory_bytes", default: -1] == 65536)
    }

    @Test("POST /v1/images/edits routes to the image worker and returns JSON")
    func postImageEditsRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.images = [Data("edited-image".utf8)]
            response.job.requestID = "image-edit-1"
            response.job.jobID = "image-edit-1::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [
                makeWorkerArtifact(jobID: "image-edit-1::image-edit", role: .imageArtifactEditSource, artifactID: "source"),
                makeWorkerArtifact(jobID: "image-edit-1::image-edit", role: .imageArtifactMask, artifactID: "mask"),
                makeWorkerArtifact(jobID: "image-edit-1::image-edit", role: .imageArtifactGenerated),
            ]
            return response
        }())
        await imageClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.lastProbeKind = "image"
            response.stats.lastImageJobLatencyMs = 62
            response.stats.lastImageArtifactPublishMs = 4
            response.stats.lastImageOutputBytes = 12
            response.stats.lastImagePeakMemoryBytes = 98304
            return response
        }())

        let imageJobReadModel = ImageJobReadModel()
        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            imageJobReadModel: imageJobReadModel
        )

        let body = try #require(
            """
            {
              "id": "image-edit-1",
              "model": "melix-dev-image",
              "prompt": "add glow",
              "image_base64": "U09VUkNF",
              "mask_base64": "TUFTSw==",
              "strength": 0.55,
              "size": "256x256",
              "response_format": "png",
              "n": 1
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await imageClient.lastImageEditRequest)
        let job = try #require(await imageJobReadModel.job(requestID: "image-edit-1"))
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.modelHandle == "melix-dev-image::python")
        #expect(request.prompt == "add glow")
        #expect(request.image == Data("SOURCE".utf8))
        #expect(request.mask == Data("MASK".utf8))
        #expect(request.strength == 0.55)
        #expect(payload.contains("\"job_id\":\"image-edit-1::image-edit\""))
        #expect(payload.contains("\"operation\":\"image_edit\""))
        #expect(payload.contains("\"b64_json\":\"ZWRpdGVkLWltYWdl\""))
        #expect(job.state == .imageJobCompleted)
        #expect(job.artifacts.count == 3)
        #expect(metrics.values["images.job_latency_ms", default: -1] == 62)
        #expect(metrics.values["images.artifact_publish_ms", default: -1] == 4)
        #expect(metrics.values["images.peak_memory_bytes", default: -1] == 98304)
    }

    @Test("POST /v1/images/edits resolves iterate requests from source_artifact_id")
    func postImageEditsResolveIterateRequestsFromSourceArtifactID() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.images = [Data("iterated-image".utf8)]
            response.job.requestID = "image-edit-iterate"
            response.job.jobID = "image-edit-iterate::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_iterate"
            response.job.state = .imageJobCompleted
            response.job.sourceArtifactID = "artifact-source"
            response.job.sourceJobID = "job-source"
            response.job.promptDelta = "make the colors warmer"
            response.job.editMode = .iterate
            var generated = makeWorkerArtifact(
                jobID: "image-edit-iterate::image-edit",
                role: .imageArtifactGenerated,
                artifactID: "output"
            )
            generated.parentArtifactID = "artifact-source"
            response.job.artifacts = [generated]
            return response
        }())

        let imageJobReadModel = ImageJobReadModel()
        var sourceArtifact = Melix_Controlplane_V1_ImageArtifactRef()
        sourceArtifact.artifactID = "artifact-source"
        sourceArtifact.jobID = "job-source"
        sourceArtifact.role = .imageArtifactGenerated
        sourceArtifact.mimeType = "image/png"
        sourceArtifact.format = "png"
        sourceArtifact.width = 256
        sourceArtifact.height = 256
        sourceArtifact.byteLength = 64
        sourceArtifact.storageUri = "file:///tmp/source-origin.png"
        sourceArtifact.variantIndex = 0
        await imageJobReadModel.recordQueued(
            requestID: "req-image-source",
            jobID: "job-source",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        await imageJobReadModel.recordCompleted(jobID: "job-source", artifacts: [sourceArtifact])

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let body = try #require(
            """
            {
              "id": "image-edit-iterate",
              "model": "melix-dev-image",
              "prompt": "",
              "source_artifact_id": "artifact-source",
              "prompt_delta": "make the colors warmer",
              "edit_mode": "iterate",
              "strength": 0.7,
              "size": "256x256",
              "response_format": "png",
              "n": 1
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await imageClient.lastImageEditRequest)
        let job = try #require(await imageJobReadModel.job(requestID: "image-edit-iterate"))

        #expect(response.statusCode == 200)
        #expect(request.image.isEmpty)
        #expect(request.imageUri == "file:///tmp/source-origin.png")
        #expect(request.sourceArtifactID == "artifact-source")
        #expect(request.prompt == "make the colors warmer")
        #expect(request.promptDelta == "make the colors warmer")
        #expect(request.editMode == .iterate)
        #expect(request.ext["melix.image.source_job_id"] == "job-source")
        #expect(payload.contains("\"operation\":\"image_iterate\""))
        #expect(payload.contains("\"source_artifact_id\":\"artifact-source\""))
        #expect(payload.contains("\"source_job_id\":\"job-source\""))
        #expect(payload.contains("\"prompt_delta\":\"make the colors warmer\""))
        #expect(payload.contains("\"edit_mode\":\"iterate\""))
        #expect(payload.contains("\"request_timeout_seconds\":1800"))
        #expect(payload.contains("\"source_image_uri\":\""))
        #expect(payload.contains("\"parent_artifact_id\":\"artifact-source\""))
        #expect(job.operation == "image_iterate")
        #expect(job.sourceArtifactID == "artifact-source")
        #expect(job.sourceJobID == "job-source")
        #expect(job.promptDelta == "make the colors warmer")
        #expect(job.editMode == .iterate)
    }

    @Test("POST /v1/images/edits includes variation lineage payload fields")
    func postImageEditsIncludeVariationLineagePayloadFields() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.images = [Data("variation-image".utf8)]
            response.job.requestID = "image-edit-variation"
            response.job.jobID = "image-edit-variation::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_variation"
            response.job.state = .imageJobCompleted
            response.job.sourceArtifactID = "artifact-source"
            response.job.sourceJobID = "job-source"
            response.job.editMode = .variation
            var generated = makeWorkerArtifact(
                jobID: "image-edit-variation::image-edit",
                role: .imageArtifactGenerated,
                artifactID: "variation-output"
            )
            generated.parentArtifactID = "artifact-source"
            response.job.artifacts = [generated]
            return response
        }())

        let imageJobReadModel = ImageJobReadModel()
        var sourceArtifact = Melix_Controlplane_V1_ImageArtifactRef()
        sourceArtifact.artifactID = "artifact-source"
        sourceArtifact.jobID = "job-source"
        sourceArtifact.role = .imageArtifactGenerated
        sourceArtifact.mimeType = "image/png"
        sourceArtifact.format = "png"
        sourceArtifact.width = 256
        sourceArtifact.height = 256
        sourceArtifact.byteLength = 64
        sourceArtifact.storageUri = "file:///tmp/source-origin.png"
        sourceArtifact.variantIndex = 0
        await imageJobReadModel.recordQueued(
            requestID: "req-image-source-variation",
            jobID: "job-source",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        await imageJobReadModel.recordCompleted(jobID: "job-source", artifacts: [sourceArtifact])

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let body = try #require(
            """
            {
              "id": "image-edit-variation",
              "model": "melix-dev-image",
              "prompt": "keep composition",
              "source_artifact_id": "artifact-source",
              "edit_mode": "variation",
              "strength": 0.7,
              "size": "256x256",
              "response_format": "png",
              "n": 1
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"operation\":\"image_variation\""))
        #expect(payload.contains("\"source_artifact_id\":\"artifact-source\""))
        #expect(payload.contains("\"edit_mode\":\"variation\""))
        #expect(payload.contains("\"parent_artifact_id\":\"artifact-source\""))
    }

    @Test("image endpoints validate payloads and return 409 and 503 when routing is unavailable")
    func imageEndpointsValidatePayloadsAndReturnUnavailableResponses() async throws {
        let invalidHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devImageModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )

        let invalidEditBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "broken",
              "image_base64": "%%%not-base64%%%"
            }
            """.data(using: .utf8)
        )
        let invalidEditResponse = try await invalidHandler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: invalidEditBody)
        )
        let invalidEditPayload = try await collectBody(invalidEditResponse.body)

        #expect(invalidEditResponse.statusCode == 400)
        #expect(invalidEditPayload.contains("\"code\":\"invalid_argument\""))

        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devImageModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )
        let generateBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "red fox"
            }
            """.data(using: .utf8)
        )
        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: generateBody)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: generateBody)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("image edit endpoints validate variation and iterate lineage inputs")
    func imageEditEndpointsValidateVariationAndIterateLineageInputs() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedPhaseFiveWorkerClient(),
                modelCatalog: catalog
            ),
            imageJobReadModel: ImageJobReadModel()
        )

        let missingSourceBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "keep composition",
              "edit_mode": "variation"
            }
            """.data(using: .utf8)
        )
        let missingSourceResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: missingSourceBody)
        )
        let missingSourcePayload = try await collectBody(missingSourceResponse.body)

        let invalidPromptDeltaBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "replace the sky",
              "image_base64": "U09VUkNF",
              "prompt_delta": "make it warmer"
            }
            """.data(using: .utf8)
        )
        let invalidPromptDeltaResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: invalidPromptDeltaBody)
        )
        let invalidPromptDeltaPayload = try await collectBody(invalidPromptDeltaResponse.body)

        let missingIterateDeltaBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "",
              "source_artifact_id": "artifact-source",
              "edit_mode": "iterate"
            }
            """.data(using: .utf8)
        )
        let missingIterateDeltaResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: missingIterateDeltaBody)
        )
        let missingIterateDeltaPayload = try await collectBody(missingIterateDeltaResponse.body)

        let mixedSourceInputsBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "",
              "source_artifact_id": "artifact-source",
              "image_url": "file:///tmp/source.png",
              "prompt_delta": "make it warmer",
              "edit_mode": "iterate"
            }
            """.data(using: .utf8)
        )
        let mixedSourceInputsResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: mixedSourceInputsBody)
        )
        let mixedSourceInputsPayload = try await collectBody(mixedSourceInputsResponse.body)

        #expect(missingSourceResponse.statusCode == 400)
        #expect(missingSourcePayload.contains("source_artifact_id is required"))
        #expect(invalidPromptDeltaResponse.statusCode == 400)
        #expect(invalidPromptDeltaPayload.contains("prompt_delta is only supported"))
        #expect(missingIterateDeltaResponse.statusCode == 400)
        #expect(missingIterateDeltaPayload.contains("prompt_delta is required"))
        #expect(mixedSourceInputsResponse.statusCode == 400)
        #expect(mixedSourceInputsPayload.contains("source_artifact_id cannot be combined"))
    }

    @Test("image generation returns resource_exhausted when the background queue is saturated")
    func postImageGenerationsReturnResourceExhaustedWhenQueueIsSaturated() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = BlockingPhaseSevenImageWorkerClient()
        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 0)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController
        )

        let activeBody = try #require(
            """
            {
              "id": "image-saturated-active",
              "model": "melix-dev-image",
              "prompt": "Hold the image worker"
            }
            """.data(using: .utf8)
        )
        let activeTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: activeBody)
            )
        }
        try await waitForOpenAIHandlerCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["image-saturated-active"]
        }

        let saturatedBody = try #require(
            """
            {
              "id": "image-saturated-rejected",
              "model": "melix-dev-image",
              "prompt": "This request should saturate"
            }
            """.data(using: .utf8)
        )
        let saturatedResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: saturatedBody)
        )
        let saturatedPayload = try await collectBody(saturatedResponse.body)
        let rejectedJob = try #require(await imageJobReadModel.job(requestID: "image-saturated-rejected"))

        await imageClient.finishGenerate(requestID: "image-saturated-active")
        _ = try await activeTask.value

        #expect(saturatedResponse.statusCode == 503)
        #expect(saturatedPayload.contains("\"code\":\"resource_exhausted\""))
        #expect(rejectedJob.state == .imageJobFailed)
        #expect(rejectedJob.error.code == "resource_exhausted")
    }

    @Test("image edit returns resource_exhausted when the background queue is saturated")
    func postImageEditsReturnResourceExhaustedWhenQueueIsSaturated() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = BlockingPhaseSevenImageWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 0)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController
        )

        let activeBody = try #require(
            """
            {
              "id": "image-edit-saturated-active",
              "model": "melix-dev-image",
              "prompt": "Hold the image worker"
            }
            """.data(using: .utf8)
        )
        let activeTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: activeBody)
            )
        }
        try await waitForOpenAIHandlerCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["image-edit-saturated-active"]
        }

        let saturatedEditBody = try #require(
            """
            {
              "id": "image-edit-saturated-rejected",
              "model": "melix-dev-image",
              "prompt": "This edit should saturate",
              "image_url": "file:///tmp/source.png"
            }
            """.data(using: .utf8)
        )
        let saturatedResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: saturatedEditBody)
        )
        let saturatedPayload = try await collectBody(saturatedResponse.body)
        let rejectedJob = try #require(await imageJobReadModel.job(requestID: "image-edit-saturated-rejected"))

        await imageClient.finishGenerate(requestID: "image-edit-saturated-active")
        _ = try await activeTask.value

        #expect(saturatedResponse.statusCode == 503)
        #expect(saturatedPayload.contains("\"code\":\"resource_exhausted\""))
        #expect(rejectedJob.state == .imageJobFailed)
        #expect(rejectedJob.error.code == "resource_exhausted")
    }

    @Test("image generation returns worker_unavailable when admission fails generically")
    func postImageGenerationsReturnWorkerUnavailableWhenAdmissionFailsGenerically() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(acquireError: WorkerClientError.unavailable)
        )

        let body = try #require(
            """
            {
              "id": "image-generate-admission-failed",
              "model": "melix-dev-image",
              "prompt": "blocked"
            }
            """.data(using: .utf8)
        )
        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let failedJob = try #require(await imageJobReadModel.job(requestID: "image-generate-admission-failed"))

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
        #expect(failedJob.state == .imageJobFailed)
        #expect(failedJob.error.code == "worker_unavailable")
    }

    @Test("image edit returns worker_unavailable when admission fails generically")
    func postImageEditsReturnWorkerUnavailableWhenAdmissionFailsGenerically() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(acquireError: WorkerClientError.unavailable)
        )

        let body = try #require(
            """
            {
              "id": "image-edit-admission-failed",
              "model": "melix-dev-image",
              "prompt": "blocked",
              "image_url": "file:///tmp/source.png"
            }
            """.data(using: .utf8)
        )
        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let failedJob = try #require(await imageJobReadModel.job(requestID: "image-edit-admission-failed"))

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
        #expect(failedJob.state == .imageJobFailed)
        #expect(failedJob.error.code == "worker_unavailable")
    }

    @Test("queued image generation returns cancelled when admission is aborted before execution")
    func postImageGenerationsReturnCancelledWhenQueuedAdmissionIsAborted() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = BlockingPhaseSevenImageWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController
        )

        let activeBody = try #require(
            """
            {
              "id": "image-cancel-active",
              "model": "melix-dev-image",
              "prompt": "Hold the image worker"
            }
            """.data(using: .utf8)
        )
        let activeTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: activeBody)
            )
        }
        try await waitForOpenAIHandlerCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["image-cancel-active"]
        }

        let queuedBody = try #require(
            """
            {
              "id": "image-cancel-queued",
              "model": "melix-dev-image",
              "prompt": "Queue this image job"
            }
            """.data(using: .utf8)
        )
        let queuedTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: queuedBody)
            )
        }
        try await waitForOpenAIHandlerCondition("expected queued image job to be visible") {
            await imageJobReadModel.job(requestID: "image-cancel-queued")?.state == .imageJobQueued
        }

        let disposition = await admissionController.cancel(requestID: "image-cancel-queued")
        let cancelledResponse = try await queuedTask.value
        let cancelledPayload = try await collectBody(cancelledResponse.body)
        let cancelledJob = try #require(await imageJobReadModel.job(requestID: "image-cancel-queued"))

        await imageClient.finishGenerate(requestID: "image-cancel-active")
        _ = try await activeTask.value

        #expect(disposition == .queued)
        #expect(cancelledResponse.statusCode == 409)
        #expect(cancelledPayload.contains("\"code\":\"cancelled\""))
        #expect(cancelledJob.state == .imageJobCanceled)
    }

    @Test("queued image edit returns cancelled when admission is aborted before execution")
    func postImageEditsReturnCancelledWhenQueuedAdmissionIsAborted() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = BlockingPhaseSevenImageWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController
        )

        let activeBody = try #require(
            """
            {
              "id": "image-edit-cancel-active",
              "model": "melix-dev-image",
              "prompt": "Hold the image worker"
            }
            """.data(using: .utf8)
        )
        let activeTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: activeBody)
            )
        }
        try await waitForOpenAIHandlerCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["image-edit-cancel-active"]
        }

        let queuedEditBody = try #require(
            """
            {
              "id": "image-edit-cancel-queued",
              "model": "melix-dev-image",
              "prompt": "Queue this image edit",
              "image_url": "file:///tmp/source.png"
            }
            """.data(using: .utf8)
        )
        let queuedTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: queuedEditBody)
            )
        }
        try await waitForOpenAIHandlerCondition("expected queued image edit to be visible") {
            await imageJobReadModel.job(requestID: "image-edit-cancel-queued")?.state == .imageJobQueued
        }

        let disposition = await admissionController.cancel(requestID: "image-edit-cancel-queued")
        let cancelledResponse = try await queuedTask.value
        let cancelledPayload = try await collectBody(cancelledResponse.body)
        let cancelledJob = try #require(await imageJobReadModel.job(requestID: "image-edit-cancel-queued"))

        await imageClient.finishGenerate(requestID: "image-edit-cancel-active")
        _ = try await activeTask.value

        #expect(disposition == .queued)
        #expect(cancelledResponse.statusCode == 409)
        #expect(cancelledPayload.contains("\"code\":\"cancelled\""))
        #expect(cancelledJob.state == .imageJobCanceled)
    }

    @Test("image endpoints map cancellation thrown failures and non-terminal states into operator-visible responses")
    func imageEndpointsMapCancellationThrownFailuresAndNonTerminalStates() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let generateBody = try #require(
            """
            {
              "id": "image-generate-cancelled",
              "model": "melix-dev-image",
              "prompt": "cancel this"
            }
            """.data(using: .utf8)
        )
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "image-generate-cancelled"
            response.job.jobID = "image-generate-cancelled::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCanceled
            response.error.code = "cancelled"
            response.error.message = "request cancelled"
            return response
        }())

        let cancelledResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: generateBody)
        )
        let cancelledPayload = try await collectBody(cancelledResponse.body)
        let cancelledJob = try #require(await imageJobReadModel.job(requestID: "image-generate-cancelled"))

        #expect(cancelledResponse.statusCode == 409)
        #expect(cancelledPayload.contains("\"code\":\"cancelled\""))
        #expect(cancelledJob.state == .imageJobCanceled)

        let runningBody = try #require(
            """
            {
              "id": "image-generate-running",
              "model": "melix-dev-image",
              "prompt": "still running"
            }
            """.data(using: .utf8)
        )
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.images = [Data("preview".utf8)]
            response.job.requestID = "image-generate-running"
            response.job.jobID = "image-generate-running::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobRunning
            response.job.artifacts = [
                makeWorkerArtifact(
                    jobID: "image-generate-running::image-generate",
                    role: .imageArtifactPreview
                )
            ]
            return response
        }())

        let runningResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: runningBody)
        )
        let runningPayload = try await collectBody(runningResponse.body)
        let runningJob = try #require(await imageJobReadModel.job(requestID: "image-generate-running"))

        #expect(runningResponse.statusCode == 200)
        #expect(runningPayload.contains("\"state\":\"failed\""))
        #expect(runningPayload.contains("\"role\":\"preview\""))
        #expect(runningJob.state == .imageJobFailed)
        #expect(runningJob.error.code == "runtime_error")

        await imageClient.setThrownFailure(WorkerClientError.unavailable)
        let thrownResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: generateBody)
        )
        let thrownPayload = try await collectBody(thrownResponse.body)

        #expect(thrownResponse.statusCode == 503)
        #expect(thrownPayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("image edit endpoints accept image URLs and validate missing or malformed image inputs")
    func imageEditEndpointsAcceptImageURLsAndValidateMissingOrMalformedInputs() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.images = [Data("input".utf8)]
            response.job.requestID = "image-edit-url"
            response.job.jobID = "image-edit-url::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobQueued
            response.job.artifacts = [
                makeWorkerArtifact(jobID: "image-edit-url::image-edit", role: .imageArtifactInput, artifactID: "input"),
                makeWorkerArtifact(jobID: "image-edit-url::image-edit", role: .unspecified, artifactID: "unknown"),
            ]
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let urlBody = try #require(
            """
            {
              "id": "image-edit-url",
              "model": "melix-dev-image",
              "prompt": "use a URL",
              "image_url": "file:///tmp/source.png"
            }
            """.data(using: .utf8)
        )
        let urlResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: urlBody)
        )
        let urlPayload = try await collectBody(urlResponse.body)
        let urlRequest = try #require(await imageClient.lastImageEditRequest)
        let urlJob = try #require(await imageJobReadModel.job(requestID: "image-edit-url"))

        #expect(urlResponse.statusCode == 200)
        #expect(urlRequest.image.isEmpty)
        #expect(urlRequest.imageUri == "file:///tmp/source.png")
        #expect(urlPayload.contains("\"state\":\"failed\""))
        #expect(urlPayload.contains("\"role\":\"unspecified\""))
        #expect(urlJob.state == .imageJobFailed)
        #expect(urlJob.error.code == "runtime_error")

        let missingImageBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "missing image"
            }
            """.data(using: .utf8)
        )
        let missingImageResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: missingImageBody)
        )
        let missingImagePayload = try await collectBody(missingImageResponse.body)

        #expect(missingImageResponse.statusCode == 400)
        #expect(missingImagePayload.contains("image_base64 or image_url is required."))

        let invalidMaskBody = try #require(
            """
            {
              "model": "melix-dev-image",
              "prompt": "bad mask",
              "image_base64": "U09VUkNF",
              "mask_base64": "%%%bad-mask%%%"
            }
            """.data(using: .utf8)
        )
        let invalidMaskResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: invalidMaskBody)
        )
        let invalidMaskPayload = try await collectBody(invalidMaskResponse.body)

        #expect(invalidMaskResponse.statusCode == 400)
        #expect(invalidMaskPayload.contains("mask_base64 must be valid base64."))
    }

    @Test("image edit responses map failed and completed states into payloads and job summaries")
    func imageEditResponsesMapFailedAndCompletedStatesIntoPayloadsAndJobSummaries() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let body = try #require(
            """
            {
              "id": "image-edit-failed",
              "model": "melix-dev-image",
              "prompt": "failed edit",
              "image_base64": "U09VUkNF"
            }
            """.data(using: .utf8)
        )

        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.images = [Data("failed".utf8)]
            response.job.requestID = "image-edit-failed"
            response.job.jobID = "image-edit-failed::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobFailed
            response.job.artifacts = [makeWorkerArtifact(jobID: "image-edit-failed::image-edit", role: .imageArtifactGenerated)]
            return response
        }())

        let failedResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let failedPayload = try await collectBody(failedResponse.body)
        let failedJob = try #require(await imageJobReadModel.job(requestID: "image-edit-failed"))

        #expect(failedResponse.statusCode == 200)
        #expect(failedPayload.contains("\"state\":\"failed\""))
        #expect(failedJob.state == .imageJobFailed)

        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.images = [Data("done".utf8)]
            response.job.requestID = "image-edit-failed"
            response.job.jobID = "image-edit-failed::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.artifacts = [makeWorkerArtifact(jobID: "image-edit-failed::image-edit", role: .imageArtifactGenerated)]
            return response
        }())

        let completedResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let completedPayload = try await collectBody(completedResponse.body)

        #expect(completedResponse.statusCode == 200)
        #expect(completedPayload.contains("\"state\":\"completed\""))
        #expect(completedPayload.contains("\"role\":\"generated\""))
    }

    @Test("image edit returns worker_unavailable when the worker throws after admission")
    func imageEditReturnsWorkerUnavailableWhenWorkerThrowsAfterAdmission() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setThrownFailure(WorkerClientError.unavailable)
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let body = try #require(
            """
            {
              "id": "image-edit-worker-threw",
              "model": "melix-dev-image",
              "prompt": "throw",
              "image_base64": "U09VUkNF"
            }
            """.data(using: .utf8)
        )
        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let failedJob = try #require(await imageJobReadModel.job(requestID: "image-edit-worker-threw"))

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
        #expect(failedJob.state == .imageJobFailed)
        #expect(failedJob.error.code == "worker_unavailable")
    }

    @Test("image generate returns deadline_exceeded when the worker exceeds the creative timeout")
    func imageGenerateReturnsDeadlineExceededWhenWorkerTimesOut() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setThrownFailure(
            WorkerClientError.requestFailed(code: "DEADLINE_EXCEEDED", message: "image generate timed out")
        )
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            environment: ["MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS": "600"]
        )

        let body = try #require(
            """
            {
              "id": "image-generate-timeout",
              "model": "melix-dev-image",
              "prompt": "timeout"
            }
            """.data(using: .utf8)
        )
        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let failedJob = try #require(await imageJobReadModel.job(requestID: "image-generate-timeout"))

        #expect(response.statusCode == 504)
        #expect(payload.contains("\"code\":\"deadline_exceeded\""))
        #expect(payload.contains("600-second creative workflow deadline"))
        #expect(failedJob.state == .imageJobFailed)
        #expect(failedJob.error.code == "deadline_exceeded")
        #expect(failedJob.progress.stage == "timed_out")
        #expect(failedJob.timeoutSeconds == 600)
        #expect(failedJob.recipe.prompt == "timeout")
    }

    @Test("image generate maps unknown deadline failures into deadline_exceeded")
    func imageGenerateMapsUnknownDeadlineFailure() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        await imageClient.setThrownFailure(
            WorkerClientError.requestFailed(code: "UNKNOWN", message: "deadline exceeded before response headers")
        )
        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel,
            environment: ["MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS": "600"]
        )

        let body = try #require(
            """
            {
              "id": "image-generate-unknown-timeout",
              "model": "melix-dev-image",
              "prompt": "timeout"
            }
            """.data(using: .utf8)
        )
        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let failedJob = try #require(await imageJobReadModel.job(requestID: "image-generate-unknown-timeout"))

        #expect(response.statusCode == 504)
        #expect(payload.contains("\"code\":\"deadline_exceeded\""))
        #expect(failedJob.state == .imageJobFailed)
        #expect(failedJob.error.code == "deadline_exceeded")
        #expect(failedJob.progress.stage == "timed_out")
    }

    @Test("image endpoints fall back to request mapped jobs when worker job identifiers drift")
    func imageEndpointsFallBackToRequestMappedJobsWhenWorkerJobIdentifiersDrift() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let imageClient = ScriptedPhaseFiveWorkerClient()
        var generateResponse = Melix_Worker_V1_ImageGenerateResponse()
        generateResponse.images = [Data("generate".utf8)]
        generateResponse.job.requestID = "image-generate-fallback"
        generateResponse.job.jobID = "worker-generate-fallback"
        generateResponse.job.modelHandle = "melix-dev-image::python"
        generateResponse.job.operation = "image_generate"
        generateResponse.job.state = .imageJobCompleted
        generateResponse.job.artifacts = [makeWorkerArtifact(jobID: "worker-generate-fallback", role: .imageArtifactGenerated)]
        await imageClient.setImageGenerateResponse(generateResponse)

        var editResponse = Melix_Worker_V1_ImageEditResponse()
        editResponse.images = [Data("edit".utf8)]
        editResponse.job.requestID = "image-edit-fallback"
        editResponse.job.jobID = "worker-edit-fallback"
        editResponse.job.modelHandle = "melix-dev-image::python"
        editResponse.job.operation = "image_edit"
        editResponse.job.state = .imageJobCompleted
        editResponse.job.artifacts = [makeWorkerArtifact(jobID: "worker-edit-fallback", role: .imageArtifactGenerated)]
        await imageClient.setImageEditResponse(editResponse)

        let imageJobReadModel = ImageJobReadModel()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: imageClient,
                modelCatalog: catalog
            ),
            imageJobReadModel: imageJobReadModel
        )

        let generateBody = try #require(
            """
            {
              "id": "image-generate-fallback",
              "model": "melix-dev-image",
              "prompt": "fallback generate"
            }
            """.data(using: .utf8)
        )
        let generateHTTPResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: generateBody)
        )
        let generatePayload = try await collectBody(generateHTTPResponse.body)

        let editBody = try #require(
            """
            {
              "id": "image-edit-fallback",
              "model": "melix-dev-image",
              "prompt": "fallback edit",
              "image_url": "file:///tmp/source.png"
            }
            """.data(using: .utf8)
        )
        let editHTTPResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/images/edits", headers: [:], body: editBody)
        )
        let editPayload = try await collectBody(editHTTPResponse.body)

        #expect(generateHTTPResponse.statusCode == 200)
        #expect(generatePayload.contains("\"job_id\":\"image-generate-fallback::image-generate\""))
        #expect(editHTTPResponse.statusCode == 200)
        #expect(editPayload.contains("\"job_id\":\"image-edit-fallback::image-edit\""))
    }

    @Test("image generation maps resource exhausted cancelled empty default and generic worker failures")
    func imageGenerationMapsResourceExhaustedCancelledEmptyDefaultAndGenericWorkerFailures() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        _ = await catalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")

        let cases: [(String, Error, Int, String, String)] = [
            ("image-generate-resource", WorkerClientError.requestFailed(code: "RESOURCE_EXHAUSTED", message: "queue full"), 503, "resource_exhausted", "queue full"),
            ("image-generate-cancelled", WorkerClientError.requestFailed(code: "cancelled", message: "operator stop"), 409, "cancelled", "operator stop"),
            ("image-generate-empty-code", WorkerClientError.requestFailed(code: "", message: ""), 503, "worker_unavailable", "worker_unavailable"),
            ("image-generate-invalid-argument", WorkerClientError.requestFailed(code: "invalid_argument", message: "bad image request"), 400, "invalid_argument", "bad image request"),
            ("image-generate-generic", NSError(domain: "OpenAIHandlerTests", code: 17, userInfo: [NSLocalizedDescriptionKey: "generic failure"]), 503, "worker_unavailable", "worker_unavailable"),
        ]

        for (requestID, failure, expectedStatusCode, expectedCode, expectedFragment) in cases {
            let imageClient = ScriptedPhaseFiveWorkerClient()
            await imageClient.setThrownFailure(failure)
            let imageJobReadModel = ImageJobReadModel()
            let handler = OpenAIHandler(
                modelCatalog: catalog,
                requestCoordinator: RequestCoordinator(
                    workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                    abortRegistry: AbortRegistry()
                ),
                workerRegistry: WorkerRegistry(
                    defaultTextClient: textClient,
                    pythonCompatibilityClient: imageClient,
                    modelCatalog: catalog
                ),
                imageJobReadModel: imageJobReadModel
            )

            let body = try #require(
                """
                {
                  "id": "\(requestID)",
                  "model": "melix-dev-image",
                  "prompt": "map this worker failure"
                }
                """.data(using: .utf8)
            )
            let response = try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/images/generations", headers: [:], body: body)
            )
            let payload = try await collectBody(response.body)

            #expect(response.statusCode == expectedStatusCode)
            #expect(payload.contains("\"\(expectedCode)\""))
            #expect(payload.contains(expectedFragment))
        }
    }

    @Test("GET /health reports route readiness and model counts")
    func getHealthReportsRouteReadinessAndModelCounts() async throws {
        let healthyClient = ScriptedWorkerClient(events: [])
        let unhealthyClient = UnavailableWorkerClient()
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel(), warmEmbeddingModel(), warmRerankModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: healthyClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: healthyClient,
                pythonCompatibilityClient: healthyClient,
                embeddingClient: healthyClient,
                rerankClient: unhealthyClient,
                modelOperationsClient: healthyClient
            ),
            metricsStore: metricsStore
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"status\":\"degraded\""))
        #expect(payload.contains("\"swift_text\":true"))
        #expect(payload.contains("\"python_embedding\":true"))
        #expect(payload.contains("\"python_rerank\":false"))
        #expect(payload.contains("\"python_transcription\":true"))
        #expect(payload.contains("\"python_speech\":true"))
        #expect(payload.contains("\"python_image\":true"))
        #expect(payload.contains("\"models_ready\":3"))
        #expect(payload.contains("\"models_total\":3"))
        #expect(metrics.values["operator.health_latency_ms", default: -1] >= 0)
    }

    @Test("GET /health reports ok when all routes are ready and pinned models count as ready")
    func getHealthReportsOkWhenAllRoutesAreReadyAndPinnedModelsCountAsReady() async throws {
        let healthyTextClient = ScriptedWorkerClient(events: [])
        let healthyPythonClient = ScriptedPhaseFiveWorkerClient()

        var pinned = warmModel()
        pinned.modelID = "melix-pinned-text"
        pinned.state = .modelPinned

        var discovered = warmEmbeddingModel()
        discovered.modelID = "melix-discovered-embed"
        discovered.state = .modelDiscovered

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel(), pinned, discovered]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: healthyTextClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: healthyTextClient,
                pythonCompatibilityClient: healthyPythonClient,
                embeddingClient: healthyPythonClient,
                rerankClient: healthyPythonClient,
                modelOperationsClient: healthyPythonClient
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"status\":\"ok\""))
        #expect(payload.contains("\"models_ready\":2"))
        #expect(payload.contains("\"models_total\":3"))
    }

    @Test("GET /health reports missing route clients as false when a registry is present")
    func getHealthReportsMissingRouteClientsAsFalseWhenARegistryIsPresent() async throws {
        let healthyTextClient = ScriptedWorkerClient(events: [])
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: healthyTextClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(defaultTextClient: healthyTextClient)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"swift_text\":true"))
        #expect(payload.contains("\"python_embedding\":false"))
        #expect(payload.contains("\"python_model_operations\":false"))
    }

    @Test("GET /health degrades cleanly when no worker registry is wired")
    func getHealthDegradesCleanlyWithoutAWorkerRegistry() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"status\":\"degraded\""))
        #expect(payload.contains("\"swift_text\":false"))
        #expect(payload.contains("\"python_embedding\":false"))
        #expect(payload.contains("\"python_rerank\":false"))
        #expect(payload.contains("\"python_model_operations\":false"))
        #expect(payload.contains("\"python_transcription\":false"))
        #expect(payload.contains("\"python_speech\":false"))
    }

    @Test("GET discovery endpoints expose machine readable local runtime contracts")
    func getDiscoveryEndpointsExposeMachineReadableLocalRuntimeContracts() async throws {
        let metricsStore = MetricsStore()
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-discovery-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try Data(
            """
            [project]
            version-control = "ignored"
            version = "7.8.9"
            """.utf8
        ).write(to: root.appendingPathComponent("pyproject.toml"))
        defer { try? FileManager.default.removeItem(at: root) }

        var qwen = warmModel()
        qwen.modelID = "mlx-community/Qwen3.5-9B-MLX-4bit"
        qwen.kind = "text"
        qwen.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3.5-9B-MLX-4bit"
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [qwen, warmEmbeddingModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore,
            gatewayRuntimeBinding: GatewayRuntimeBinding(host: "127.0.0.1", port: 12_434),
            environment: [
                "MELIX_HOME": "/tmp/melix-discovery-home",
                "MELIX_HTTP_PORT": "12434",
                "MELIX_REPO_ROOT": root.path,
            ]
        )

        let wellKnownResponse = try await handler.handle(
            HTTPRequest(method: .get, path: "/.well-known/melix.json", headers: [:], body: Data())
        )
        let wellKnown = try await jsonPayload(from: wellKnownResponse.body)
        let links = try #require(wellKnown["links"] as? [String: Any])
        let features = try #require(wellKnown["features"] as? [String])
        #expect(wellKnownResponse.statusCode == 200)
        #expect(wellKnown["schema_version"] as? String == "melix.discovery.info.v1")
        #expect(wellKnown["version"] as? String == "7.8.9")
        #expect(links["capabilities"] as? String == "/api/capabilities")
        #expect(features.contains("runtime_settings"))

        let capabilitiesResponse = try await handler.handle(
            HTTPRequest(method: .get, path: "/api/capabilities", headers: [:], body: Data())
        )
        let capabilities = try await jsonPayload(from: capabilitiesResponse.body)
        let models = try #require(capabilities["models"] as? [[String: Any]])
        let qwenModel = try #require(models.first { $0["model_id"] as? String == "mlx-community/Qwen3.5-9B-MLX-4bit" })
        let capabilityReceipt = try #require(qwenModel["capability_receipt"] as? [String: Any])
        let accelerationReceipt = try #require(capabilityReceipt["acceleration"] as? [String: Any])
        #expect(capabilitiesResponse.statusCode == 200)
        #expect(capabilities["schema_version"] as? String == "melix.discovery.capabilities.v1")
        #expect((capabilities["supported_tasks"] as? [String])?.contains("text-generation") == true)
        #expect(models.contains { $0["model_id"] as? String == "mlx-community/Qwen3.5-9B-MLX-4bit" })
        #expect(capabilityReceipt["schema_version"] as? String == "melix.model_capability_receipt.v1")
        #expect(accelerationReceipt["requested_acceleration_mode"] as? String == "baseline")
        #expect((accelerationReceipt["supported_modes"] as? [String]) == ["baseline"])

        let instructionsResponse = try await handler.handle(
            HTTPRequest(method: .get, path: "/api/instructions", headers: [:], body: Data())
        )
        let instructions = try await jsonPayload(from: instructionsResponse.body)
        #expect(instructionsResponse.statusCode == 200)
        #expect(instructions["schema_version"] as? String == "melix.discovery.instructions.v1")
        #expect((instructions["areas"] as? [[String: Any]])?.contains { $0["id"] as? String == "settings" } == true)

        let metadataResponse = try await handler.handle(
            HTTPRequest(method: .get, path: "/api/config-metadata", headers: [:], body: Data())
        )
        let metadata = try await jsonPayload(from: metadataResponse.body)
        #expect(metadataResponse.statusCode == 200)
        #expect(metadata["schema_version"] as? String == "melix.discovery.config_metadata.v1")
        #expect((metadata["settings"] as? [[String: Any]])?.contains { $0["key"] as? String == "max_concurrent_jobs" } == true)
        #expect(await metricsStore.value(forKey: "operator.discovery_well_known_latency_ms") >= 0)
        #expect(await metricsStore.value(forKey: "operator.discovery_capabilities_latency_ms") >= 0)
        #expect(await metricsStore.value(forKey: "operator.discovery_instructions_latency_ms") >= 0)
        #expect(await metricsStore.value(forKey: "operator.discovery_config_metadata_latency_ms") >= 0)
    }

    @Test("runtime discovery contracts expose stable aliases links metadata and onboarding endpoints")
    func runtimeDiscoveryContractsExposeStableAliasesLinksMetadataAndOnboardingEndpoints() throws {
        let layout = MelixPathLayout(environment: ["MELIX_HOME": "/tmp/melix-contract-home"])
        let metadata = MelixRuntimeDiscoveryContracts.runtimeSettingsMetadata(layout: layout)
        let links = MelixRuntimeDiscoveryContracts.discoveryLinks(baseURL: "/v1/melix/")
        let instructions = MelixRuntimeDiscoveryContracts.instructionsPayload()
        let schema = MelixRuntimeDiscoveryContracts.schemaPayload(repoRootPath: "/tmp/melix-repo")
        let configMetadata = MelixRuntimeDiscoveryContracts.configMetadataPayload(layout: layout)
        let onboarding = APIOnboardingSnapshotSource().summary()

        #expect(metadata.count == MelixRuntimeDiscoveryContracts.runtimeSettingDefinitions.count)
        #expect(metadata.contains { $0["key"] as? String == "auto_cleanup_policy" && $0["default"] as? String == "manual" })
        #expect(metadata.contains { ($0["default"] as? String)?.contains("/tmp/melix-contract-home/models/default-managed") == true })
        #expect(links["well_known"] == "/v1/melix/.well-known/melix.json")
        #expect(links["config_metadata"] == "/v1/melix/api/config-metadata")
        #expect((instructions["areas"] as? [[String: Any]])?.contains { $0["id"] as? String == "updates" } == true)
        #expect((schema["schemas"] as? [[String: Any]])?.contains { $0["id"] as? String == "plans" } == true)
        #expect(configMetadata["schema_version"] as? String == "melix.discovery.config_metadata.v1")

        let blankAlias = MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: "  ")
        #expect(blankAlias["status"] as? String == "not_requested")
        for query in ["/tmp/model", "~/model", "./model", "../model", "file:///tmp/model"] {
            let alias = MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: query)
            #expect(alias["status"] as? String == "local_path_passthrough")
            #expect((alias["suggestions"] as? [[String: Any]])?.isEmpty == true)
        }
        let fullModelID = MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: "owner/model")
        #expect(fullModelID["status"] as? String == "valid_full_model_id")
        let noMatch = MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: "owner/model with space")
        #expect(noMatch["status"] as? String == "no_match")
        let qwen8Bit = MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: "qwen35_9b_mlx_8bit")
        #expect((qwen8Bit["suggestions"] as? [[String: Any]])?.contains { $0["model_id"] as? String == "mlx-community/Qwen3.5-9B-MLX-8bit" } == true)
        let qwen26B = MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: "qwen35_26b_mlx_4bit")
        #expect((qwen26B["suggestions"] as? [[String: Any]])?.contains { $0["model_id"] as? String == "mlx-community/Qwen3.5-26B-MLX-4bit" } == true)

        let localService = try #require(onboarding.surfaces.first { $0.surfaceID == "local_service" })
        #expect(localService.endpointIds.contains("well_known"))
        #expect(localService.endpointIds.contains("capabilities"))
        #expect(localService.endpointIds.contains("instructions"))
        #expect(localService.endpointIds.contains("config_metadata"))
        let endpointIDs = Set(onboarding.endpoints.map(\.endpointID))
        #expect(endpointIDs.isSuperset(of: ["well_known", "capabilities", "instructions", "config_metadata"]))
    }

    @Test("GET capabilities discovery renders all model residency states")
    func getCapabilitiesDiscoveryRendersAllModelResidencyStates() async throws {
        let stateCases: [(String, Melix_Controlplane_V1_ModelState, String)] = [
            ("melix-warm", .modelWarm, "warm"),
            ("melix-pinned", .modelPinned, "pinned"),
            ("melix-unloaded", .modelUnloaded, "unloaded"),
            ("melix-loading", .modelLoading, "loading"),
            ("melix-discovered", .modelDiscovered, "discovered"),
            ("melix-failed", .modelFailed, "failed"),
            ("melix-evicting", .modelEvicting, "evicting"),
            ("melix-unknown", .UNRECOGNIZED(99), "unknown"),
        ]
        let models = stateCases.map { modelID, state, _ in
            var model = ModelCatalog.devTextModel()
            model.modelID = modelID
            model.state = state
            return model
        }
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: models),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/api/capabilities", headers: [:], body: Data())
        )
        let payload = try await jsonPayload(from: response.body)
        let discoveredModels = try #require(payload["models"] as? [[String: Any]])
        let firstReceipt = try #require(discoveredModels.first?["capability_receipt"] as? [String: Any])

        #expect(response.statusCode == 200)
        #expect(firstReceipt["schema_version"] as? String == "melix.model_capability_receipt.v1")
        for (modelID, _, discoveryState) in stateCases {
            #expect(discoveredModels.contains { model in
                model["model_id"] as? String == modelID && model["state"] as? String == discoveryState
            })
        }
    }

    @Test("POST /v1/embeddings returns 503 when the embedding worker throws")
    func postEmbeddingsReturns503WhenTheEmbeddingWorkerThrows() async throws {
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setThrownFailure(WorkerClientError.unavailable)

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: embeddingClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/rerank returns 409 and 503 when routing prerequisites are missing")
    func postRerankReturns409And503WhenRoutingPrerequisitesAreMissing() async throws {
        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devRerankModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                rerankClient: ScriptedPhaseFiveWorkerClient()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-rerank",
              "query": "swift worker",
              "documents": ["swift worker"],
              "top_k": 1
            }
            """.data(using: .utf8)
        )

        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devRerankModel()])
        _ = await catalog.loadModel(id: "melix-dev-rerank", dispatchHandle: "melix-dev-rerank::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                rerankClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("GET /v1/cache/stats renders the control-plane cache summary")
    func getCacheStatsRendersControlPlaneCacheSummary() async throws {
        var snapshot = CacheMetadataStore.emptySnapshot()
        snapshot.summary.l1Bytes = 2048
        snapshot.summary.l2Bytes = 4096
        snapshot.summary.l1HitRate = 0.5
        snapshot.summary.l2RestoreHitRate = 0.75
        snapshot.summary.compressionRatio = 0.25
        snapshot.summary.quantizedBytes = 1024
        snapshot.summary.activeMode = .rotating

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            cacheMetadataStore: CacheMetadataStore(snapshot: snapshot)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/cache/stats", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"l1_bytes\":2048"))
        #expect(payload.contains("\"l2_bytes\":4096"))
        #expect(payload.contains("\"l1_hit_rate\":0.5"))
        #expect(payload.contains("\"l2_restore_hit_rate\":0.75"))
        #expect(payload.contains("\"compression_ratio\":0.25"))
        #expect(payload.contains("\"quantized_bytes\":1024"))
        #expect(payload.contains("\"active_cache_mode\":\"rotating\""))
    }

    @Test("GET /v1/cache/stats returns empty zeros and metrics without a cache store")
    func getCacheStatsReturnsEmptyZerosAndMetricsWithoutACacheStore() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/cache/stats", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"l1_bytes\":0"))
        #expect(payload.contains("\"l2_bytes\":0"))
        #expect(payload.contains("\"compression_ratio\":0"))
        #expect(payload.contains("\"active_cache_mode\":\"tiered\""))
        #expect(metrics.values["operator.cache_stats_latency_ms", default: -1] >= 0)
    }

    @Test("POST /v1/embeddings accepts a single string input and estimates usage")
    func postEmbeddingsAcceptsASingleStringInputAndEstimatesUsage() async throws {
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setEmbedResponse({
            var response = Melix_Worker_V1_EmbedResponse()
            response.embeddings = [
                {
                    var embedding = Melix_Worker_V1_Embedding()
                    embedding.values = [0.9, 0.1]
                    return embedding
                }(),
            ]
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: embeddingClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": "alpha beta"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await embeddingClient.lastEmbedRequest)

        #expect(response.statusCode == 200)
        #expect(request.inputs == ["alpha beta"])
        #expect(payload.contains("\"prompt_tokens\":2"))
        #expect(payload.contains("\"total_tokens\":2"))
    }

    @Test("POST /v1/embeddings returns 409 when the embedding model is not loaded")
    func postEmbeddingsReturns409WhenTheEmbeddingModelIsNotLoaded() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: ScriptedPhaseFiveWorkerClient()
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("POST /v1/embeddings returns 503 when no compatible embedding worker is available")
    func postEmbeddingsReturns503WhenNoCompatibleEmbeddingWorkerIsAvailable() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: ScriptedWorkerClient(events: [])
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/embeddings maps worker error payloads to HTTP responses")
    func postEmbeddingsMapsWorkerErrorPayloadsToHTTPResponses() async throws {
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setEmbedResponse({
            var response = Melix_Worker_V1_EmbedResponse()
            response.error.code = "invalid_argument"
            response.error.message = "bad embedding input"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: embeddingClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("\"message\":\"bad embedding input\""))
    }

    @Test("POST /v1/rerank maps worker errors and thrown failures to HTTP responses")
    func postRerankMapsWorkerErrorsAndThrownFailuresToHTTPResponses() async throws {
        let rerankClient = ScriptedPhaseFiveWorkerClient()
        await rerankClient.setRerankResponse({
            var response = Melix_Worker_V1_RerankResponse()
            response.error.code = "not_found"
            response.error.message = "rerank model missing"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devRerankModel()])
        _ = await catalog.loadModel(id: "melix-dev-rerank", dispatchHandle: "melix-dev-rerank::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                rerankClient: rerankClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-rerank",
              "query": "swift worker",
              "documents": ["swift worker"],
              "top_k": 1
            }
            """.data(using: .utf8)
        )

        let errorResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let errorPayload = try await collectBody(errorResponse.body)

        #expect(errorResponse.statusCode == 404)
        #expect(errorPayload.contains("\"code\":\"not_found\""))

        await rerankClient.setThrownFailure(WorkerClientError.unavailable)
        let unavailableResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("unknown routes return 404 json")
    func unknownRoutesReturn404() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/unknown", headers: [:], body: Data())
        )
        let body = try await collectBody(response.body)

        #expect(response.statusCode == 404)
        #expect(body.contains("\"code\":\"not_found\""))
    }

    @Test("non-stream chat requests return JSON")
    func nonStreamRequestsReturnJSON() async throws {
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-non-stream-json", seq: 1, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "req-non-stream-json" })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await jsonPayload(from: response.body)
        let choice = try #require((payload["choices"] as? [[String: Any]])?.first)
        let message = try #require(choice["message"] as? [String: Any])

        #expect(response.statusCode == 200)
        #expect(payload["object"] as? String == "chat.completion")
        #expect(message["content"] as? String == "Hello")
    }

    @Test("chat requests return 409 when the model is not ready")
    func modelNotReadyReturns409() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: []),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("chat requests return 409 when the managed Hugging Face cache is missing")
    func missingManagedHuggingFaceCacheReturns409() async throws {
        var model = warmModel()
        model.settings.ext["melix.model_path_missing"] = "true"
        model.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        model.settings.ext["melix.registry_descriptor_path"] = "/tmp/melix-managed/huggingface/mlx-community/Qwen3/main"
        let workerClient = ScriptedWorkerClient(events: [])
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [model]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_runtime_missing\""))
        #expect(payload.contains("Hugging Face cache files are missing. Re-download this model to restore it."))
        #expect(await workerClient.lastLoadModelRequest == nil)
        #expect(await workerClient.lastGenerateRequest == nil)
    }

    @Test("chat requests return 503 when the worker is unavailable")
    func workerUnavailableReturns503() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: UnavailableWorkerClient()),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("second chat request waits in queue until the active request is cancelled")
    func secondRequestQueuesUntilTheActiveRequestIsCancelled() async throws {
        let workerClient = BlockingOpenAIWorkerClient()
        let requestIDs = RequestIDSequence(["req-1", "req-2"])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: {
                requestIDs.next()
            })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let first = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let secondTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
            )
        }

        try await Task.sleep(for: .milliseconds(50))
        #expect(await workerClient.generatedRequestIDs == ["req-1"])

        #expect(try await coordinator.cancel(requestID: "req-1"))

        let second = try await secondTask.value
        #expect(await workerClient.generatedRequestIDs == ["req-1", "req-2"])
        #expect(try await coordinator.cancel(requestID: "req-2"))

        #expect(first.statusCode == 200)
        #expect(second.statusCode == 200)
    }

    @Test("duplicate request identifiers return 409 conflict")
    func duplicateRequestIdentifiersReturn409() async throws {
        let workerClient = BlockingOpenAIWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-duplicate" })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let first = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let second = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let secondPayload = try await collectBody(second.body)

        #expect(first.statusCode == 200)
        #expect(second.statusCode == 409)
        #expect(secondPayload.contains("\"code\":\"request_already_active\""))
        #expect(secondPayload.contains("A text generation request is already active."))
        #expect(try await coordinator.cancel(requestID: "req-duplicate"))
    }

    @Test("chat completions can resume a disconnected request via resume_request_id")
    func chatCompletionsCanResumeADisconnectedRequestViaResumeRequestID() async throws {
        let workerClient = BlockingOpenAIWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            lifecyclePolicy: ConnectionLifecyclePolicy(
                keepaliveInterval: 0.01,
                disconnectGracePeriod: 0.1
            )
        )
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-http-resume" }),
            sseWriter: SSEStreamWriter(
                now: { Date(timeIntervalSince1970: 123) },
                lifecyclePolicy: ConnectionLifecyclePolicy(
                    keepaliveInterval: 0.01,
                    disconnectGracePeriod: 0.1
                )
            )
        )

        let firstBody = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let first = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: firstBody)
        )
        let firstChunk = try await collectFirstStreamChunk(first.body)

        let secondBody = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "resume_request_id": "req-http-resume",
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let second = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: secondBody)
        )
        await workerClient.emitToken(requestID: "req-http-resume", text: "resumed")
        await workerClient.finish(requestID: "req-http-resume", assistantText: "resumed")
        let secondPayload = try await collectBody(second.body)

        #expect(first.statusCode == 200)
        #expect(firstChunk.contains(": keepalive"))
        #expect(second.statusCode == 200)
        #expect(secondPayload.contains("\"content\":\"resumed\""))
        #expect(secondPayload.contains("data: [DONE]"))
        #expect(await workerClient.generatedRequestIDs == ["req-http-resume"])
    }

    @Test("handler applies workflow-aware shaping and records shaping metrics")
    func handlerAppliesWorkflowAwareShapingAndRecordsMetrics() async throws {
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "msg-workflow", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "msg-workflow" })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "preset_id": "deep_reasoning",
              "workflow": "tool_followup",
              "workflow_run_id": "wf-handler",
              "workflow_node_id": "node-handler",
              "session_id": "session-handler",
              "messages": [
                { "role": "assistant", "content": "<think>hidden prior turn</think><|tool_call>call:github_auth:github_auth_check()<tool_call|>Visible prior answer." },
                { "role": "user", "content": "Continue the tool result." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/messages", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let generated = await workerClient.lastGenerateRequest
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("event: message.completed"))
        #expect(generated?.execution.id.workflowRunID == "wf-handler")
        #expect(generated?.execution.id.workflowNodeID == "node-handler")
        #expect(generated?.execution.scheduling.lane == "text.prefill.hot")
        #expect(generated?.execution.scheduling.admissionPolicy == "workflow.tool_followup")
        #expect(generated?.execution.cacheHints.cachePolicy == "session-hot")
        #expect(generated?.messages.first?.parts.first?.text == "Visible prior answer.")
        #expect(generated?.execution.ext["melix.preset_id"] == "deep_reasoning")
        #expect(generated?.execution.ext["melix.workflow"] == "tool_followup")
        #expect(generated?.execution.ext["melix.reasoning.history_strip_count"] == "1")
        #expect(generated?.execution.ext["melix.tool_call_history_strip_count"] == "1")
        #expect(metrics.values["http.preset_shaped_count", default: 0] == 1)
        #expect(metrics.values["http.workflow_shaped_count", default: 0] == 1)
        #expect(metrics.values["http.reasoning_history_strip_count", default: 0] == 1)
        #expect(metrics.values["http.tool_call_history_strip_count", default: 0] == 1)
        #expect(metrics.values["http.shaping_ms", default: -1] >= 0)
    }

    private func warmModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devTextModel()
        model.state = .modelWarm
        return model
    }

    private func warmEmbeddingModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devEmbeddingModel()
        model.state = .modelWarm
        return model
    }

    private func warmOCRModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devOCRModel()
        model.state = .modelWarm
        return model
    }

    private func warmRerankModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devRerankModel()
        model.state = .modelWarm
        return model
    }

    private func warmImageModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devImageModel()
        model.state = .modelWarm
        return model
    }
}

private func makeRegistrySnapshotManifestJSON(
    models: [[String: Any]],
    derivedModels: [[String: Any]] = []
) throws -> String {
    let payload: [String: Any] = [
        "operation": "registry_snapshot",
        "model_registry": [
            "scanned_at_unix_ms": 1_711_955_200_000,
            "roots": [
                [
                    "root_id": "root-1",
                    "root_path": "/tmp/registry-root",
                    "accessible": true,
                    "error_code": "",
                    "error_message": "",
                    "discovered_model_ids": models.compactMap { $0["model_id"] as? String },
                ],
            ],
            "models": models,
        ],
        "derived_models": derivedModels,
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return String(decoding: data, as: UTF8.self)
}

private actor ScriptedWorkerUnloadGate {
    private var released = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        guard released == false else {
            return
        }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func release() {
        released = true
        let pendingWaiters = waiters
        waiters.removeAll()
        for waiter in pendingWaiters {
            waiter.resume()
        }
    }
}

private actor ScriptedWorkerClient: WorkerRoutingClient, RuntimeIntrospectingWorkerClientProtocol {
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private let streamFailure: Error?
    private let loadModelHandle: String
    private let loadModelEstimatedResidentBytes: UInt64
    private let runtimeResidentBytes: UInt64
    private let runtimeModelResidentBytes: UInt64
    private let runtimeCacheResidentBytes: UInt64
    private let runtimeKVCacheBytes: UInt64
    private let runtimeStatsFailure: Error?
    private let runtimeStatsResponseOverride: Melix_Worker_V1_GetRuntimeStatsResponse?
    private let unloadDelayNanoseconds: UInt64
    private let unloadGate: ScriptedWorkerUnloadGate?
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?
    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?
    private(set) var unloadRequestCount = 0
    private(set) var unloadCompletedCount = 0

    init(
        events: [Melix_Worker_V1_ExecuteEvent],
        streamFailure: Error? = nil,
        loadModelHandle: String = "melix-dev-text::swift",
        loadModelEstimatedResidentBytes: UInt64 = 0,
        runtimeResidentBytes: UInt64 = 0,
        runtimeModelResidentBytes: UInt64 = 0,
        runtimeCacheResidentBytes: UInt64 = 0,
        runtimeKVCacheBytes: UInt64 = 0,
        runtimeStatsFailure: Error? = nil,
        runtimeStatsResponseOverride: Melix_Worker_V1_GetRuntimeStatsResponse? = nil,
        unloadDelayNanoseconds: UInt64 = 0,
        unloadGate: ScriptedWorkerUnloadGate? = nil
    ) {
        self.events = events
        self.streamFailure = streamFailure
        self.loadModelHandle = loadModelHandle
        self.loadModelEstimatedResidentBytes = loadModelEstimatedResidentBytes
        self.runtimeResidentBytes = runtimeResidentBytes
        self.runtimeModelResidentBytes = runtimeModelResidentBytes
        self.runtimeCacheResidentBytes = runtimeCacheResidentBytes
        self.runtimeKVCacheBytes = runtimeKVCacheBytes
        self.runtimeStatsFailure = runtimeStatsFailure
        self.runtimeStatsResponseOverride = runtimeStatsResponseOverride
        self.unloadDelayNanoseconds = unloadDelayNanoseconds
        self.unloadGate = unloadGate
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        lastGenerateRequest = request
        let events = self.events
        let streamFailure = self.streamFailure
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish(throwing: streamFailure)
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        lastLoadModelRequest = request
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = loadModelHandle
        response.estimatedResidentBytes = loadModelEstimatedResidentBytes
        return response
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        _ = request
        unloadRequestCount += 1
        if unloadDelayNanoseconds > 0 {
            try await Task.sleep(nanoseconds: unloadDelayNanoseconds)
        }
        await unloadGate?.wait()
        unloadCompletedCount += 1
        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = true
        return response
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        if let runtimeStatsFailure {
            throw runtimeStatsFailure
        }
        if let runtimeStatsResponseOverride {
            return runtimeStatsResponseOverride
        }
        var response = Melix_Worker_V1_GetRuntimeStatsResponse()
        response.stats.residentBytes = runtimeResidentBytes
        response.stats.modelResidentBytes = runtimeModelResidentBytes
        response.stats.cacheResidentBytes = runtimeCacheResidentBytes
        response.stats.kvCacheBytes = runtimeKVCacheBytes
        return response
    }
}

private actor ScriptedPhaseFiveWorkerClient:
    WorkerRoutingClient,
    NonTextInferenceWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol
{
    private(set) var lastEmbedRequest: Melix_Worker_V1_EmbedRequest?
    private(set) var lastRerankRequest: Melix_Worker_V1_RerankRequest?
    private(set) var lastTranscribeRequest: Melix_Worker_V1_TranscribeRequest?
    private(set) var lastSpeakRequest: Melix_Worker_V1_SpeakRequest?
    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?
    private(set) var lastImageGenerateRequest: Melix_Worker_V1_ImageGenerateRequest?
    private(set) var lastImageEditRequest: Melix_Worker_V1_ImageEditRequest?
    private var embedResponse = Melix_Worker_V1_EmbedResponse()
    private var rerankResponse = Melix_Worker_V1_RerankResponse()
    private var transcribeResponse = Melix_Worker_V1_TranscribeResponse()
    private var speakResponse = Melix_Worker_V1_SpeakResponse()
    private var speakStreamEvents: [Melix_Worker_V1_SpeakStreamEvent] = []
    private var speakStreamFailure: Error?
    private var imageGenerateResponse = Melix_Worker_V1_ImageGenerateResponse()
    private var imageEditResponse = Melix_Worker_V1_ImageEditResponse()
    private var runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
    private var loadModelResponseOverride: Melix_Worker_V1_LoadModelResponse?
    private var thrownFailure: Error?

    func setEmbedResponse(_ response: Melix_Worker_V1_EmbedResponse) {
        embedResponse = response
    }

    func setRerankResponse(_ response: Melix_Worker_V1_RerankResponse) {
        rerankResponse = response
    }

    func setTranscribeResponse(_ response: Melix_Worker_V1_TranscribeResponse) {
        transcribeResponse = response
    }

    func setSpeakResponse(_ response: Melix_Worker_V1_SpeakResponse) {
        speakResponse = response
    }

    func setSpeakStreamEvents(_ events: [Melix_Worker_V1_SpeakStreamEvent]) {
        speakStreamEvents = events
    }

    func setSpeakStreamFailure(_ failure: Error?) {
        speakStreamFailure = failure
    }

    func setImageGenerateResponse(_ response: Melix_Worker_V1_ImageGenerateResponse) {
        imageGenerateResponse = response
    }

    func setImageEditResponse(_ response: Melix_Worker_V1_ImageEditResponse) {
        imageEditResponse = response
    }

    func setRuntimeStatsResponse(_ response: Melix_Worker_V1_GetRuntimeStatsResponse) {
        runtimeStatsResponse = response
    }

    func setLoadModelResponse(_ response: Melix_Worker_V1_LoadModelResponse) {
        loadModelResponseOverride = response
    }

    func setThrownFailure(_ failure: Error?) {
        thrownFailure = failure
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
        lastLoadModelRequest = request
        if let loadModelResponseOverride {
            return loadModelResponseOverride
        }
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastEmbedRequest = request
        return embedResponse
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastRerankRequest = request
        return rerankResponse
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastTranscribeRequest = request
        return transcribeResponse
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastSpeakRequest = request
        return speakResponse
    }

    func speakStream(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_SpeakStreamEvent, Error> {
        if let thrownFailure {
            throw thrownFailure
        }
        lastSpeakRequest = request
        let events = speakStreamEvents
        let failure = speakStreamFailure
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            if let failure {
                continuation.finish(throwing: failure)
            } else {
                continuation.finish()
            }
        }
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastImageGenerateRequest = request
        return imageGenerateResponse
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastImageEditRequest = request
        return imageEditResponse
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        return runtimeStatsResponse
    }
}

private actor BlockingPhaseSevenImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private var generateRequests: [String: Melix_Worker_V1_ImageGenerateRequest] = [:]
    private var generateContinuations: [String: CheckedContinuation<Melix_Worker_V1_ImageGenerateResponse, Error>] = [:]

    private(set) var startedRequestIDs: [String] = []

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
        _ = request
        return Melix_Worker_V1_ImageEditResponse()
    }

    func finishGenerate(requestID: String) {
        guard let request = generateRequests.removeValue(forKey: requestID),
              let continuation = generateContinuations.removeValue(forKey: requestID) else {
            return
        }

        var response = Melix_Worker_V1_ImageGenerateResponse()
        response.images = [Data("done".utf8)]
        response.job.requestID = requestID
        response.job.jobID = "\(requestID)::image-generate"
        response.job.modelHandle = request.modelHandle
        response.job.operation = "image_generate"
        response.job.state = .imageJobCompleted
        response.job.progress.stage = "completed"
        response.job.progress.pct = 1
        response.job.artifacts = [
            makeWorkerArtifact(
                jobID: "\(requestID)::image-generate",
                role: .imageArtifactGenerated
            )
        ]
        continuation.resume(returning: response)
    }
}

private actor StubImageJobAdmissionController: ImageJobAdmissionControlling {
    private let acquireError: Error?

    init(acquireError: Error? = nil) {
        self.acquireError = acquireError
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
        return .notFound
    }
}

private func makeWorkerArtifact(
    jobID: String,
    role: Melix_Worker_V1_ImageArtifactRole,
    artifactID: String = "artifact-0"
) -> Melix_Worker_V1_ImageArtifactMetadata {
    var artifact = Melix_Worker_V1_ImageArtifactMetadata()
    artifact.artifactID = "\(jobID)::\(artifactID)"
    artifact.jobID = jobID
    artifact.role = role
    artifact.mimeType = "image/png"
    artifact.format = "png"
    artifact.width = 256
    artifact.height = 256
    artifact.byteLength = 15
    artifact.storageUri = "/tmp/\(artifactID).png"
    artifact.sha256 = "sha256-\(artifactID)"
    artifact.variantIndex = 0
    return artifact
}

private func waitForOpenAIHandlerCondition(
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

    throw OpenAIHandlerTestError(description: description)
}

private struct OpenAIHandlerTestError: Error, CustomStringConvertible {
    let description: String
}

private actor ScriptedRegistryModelOperationsWorkerClient:
    WorkerRoutingClient,
    ModelOperationsWorkerClientProtocol
{
    private var convertEvents: [Melix_Worker_V1_ConvertModelEvent] = []
    private(set) var lastConvertRequest: Melix_Worker_V1_ConvertModelRequest?

    func setConvertEvents(_ events: [Melix_Worker_V1_ConvertModelEvent]) {
        convertEvents = events
    }

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

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        lastConvertRequest = request
        let events = convertEvents
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
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
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
        _ = request
        throw WorkerClientError.unavailable
    }

    func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        _ = request
        throw WorkerClientError.unavailable
    }
}

private actor UnavailableWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        false
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        throw WorkerClientError.unavailable
    }
}

private actor BlockingOpenAIWorkerClient: WorkerRoutingClient {
    private(set) var generatedRequestIDs: [String] = []
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generatedRequestIDs.append(request.execution.id.requestID)
        let requestID = request.execution.id.requestID
        return AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        continuations.removeValue(forKey: requestID)?.finish()
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
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

    func finish(requestID: String, assistantText: String) {
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

private final class RequestIDSequence: @unchecked Sendable {
    private var remaining: [String]
    private let lock = NSLock()

    init(_ remaining: [String]) {
        self.remaining = remaining
    }

    func next() -> String {
        lock.lock()
        defer { lock.unlock() }
        return remaining.removeFirst()
    }
}

private func progressiveWAVHeader(sampleRate: UInt32) -> Data {
    var data = Data()
    data.append(Data("RIFF".utf8))
    data.append(littleEndianUInt32Data(UInt32.max))
    data.append(Data("WAVEfmt ".utf8))
    data.append(littleEndianUInt32Data(16))
    data.append(littleEndianUInt16Data(1))
    data.append(littleEndianUInt16Data(1))
    data.append(littleEndianUInt32Data(sampleRate))
    data.append(littleEndianUInt32Data(sampleRate * 2))
    data.append(littleEndianUInt16Data(2))
    data.append(littleEndianUInt16Data(16))
    data.append(Data("data".utf8))
    data.append(littleEndianUInt32Data(UInt32.max))
    return data
}

private func littleEndianUInt16Data(_ value: UInt16) -> Data {
    var littleEndianValue = value.littleEndian
    return Data(bytes: &littleEndianValue, count: MemoryLayout<UInt16>.size)
}

private func littleEndianUInt32Data(_ value: UInt32) -> Data {
    var littleEndianValue = value.littleEndian
    return Data(bytes: &littleEndianValue, count: MemoryLayout<UInt32>.size)
}

private func collectBody(_ body: HTTPBody) async throws -> String {
    switch body {
    case .data(let data):
        return try #require(String(data: data, encoding: .utf8))
    case .stream(let stream):
        var data = Data()
        for try await chunk in stream {
            data.append(chunk)
        }
        return try #require(String(data: data, encoding: .utf8))
    }
}

private func collectBodyData(_ body: HTTPBody) async throws -> Data {
    switch body {
    case .data(let data):
        return data
    case .stream(let stream):
        var data = Data()
        for try await chunk in stream {
            data.append(chunk)
        }
        return data
    }
}

private func collectFirstStreamChunk(_ body: HTTPBody) async throws -> String {
    switch body {
    case .data(let data):
        return try #require(String(data: data, encoding: .utf8))
    case .stream(let stream):
        var iterator = stream.makeAsyncIterator()
        let chunk = try #require(await iterator.next())
        return try #require(String(data: chunk, encoding: .utf8))
    }
}

private func jsonObject(from body: HTTPBody) async throws -> (errorCode: String, errorMessage: String) {
    let data = try await collectBodyData(body)
    let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let error = try #require(object["error"] as? [String: Any])
    let code = try #require(error["code"] as? String)
    let message = try #require(error["message"] as? String)
    return (code, message)
}

private func jsonPayload(from body: HTTPBody) async throws -> [String: Any] {
    let data = try await collectBodyData(body)
    return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
}

private final class TestNowUnixMSSequence: @unchecked Sendable {
    private var values: [Int64]
    private let lock = NSLock()

    init(_ values: [Int64]) {
        self.values = values
    }

    func next() -> Int64 {
        lock.lock()
        defer { lock.unlock() }
        if values.isEmpty {
            return 0
        }
        return values.removeFirst()
    }
}
