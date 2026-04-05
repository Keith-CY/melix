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

    @Test("model sparse-prefill policy is applied to generated worker requests")
    func modelSparsePrefillPolicyIsAppliedToGeneratedWorkerRequests() async throws {
        var model = warmModel()
        model.settings.defaultAccelerationMode = .sparsePrefill
        model.settings.accelerationProfileID = "structured-user"
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
                        "melix.model_path": "/tmp/registry-root/huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit",
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
        #expect(request.generateManifest)
        #expect(discovered["melix_state"] as? String == "discovered")
        #expect(metadata["melix.registry_provider_id"] as? String == "hf-mirror")
        #expect(metadata["melix.registry_organization_id"] as? String == "mlx-community")
        #expect(metadata["melix.registry_model_name"] as? String == "Qwen2.5-7B-Instruct")
        #expect(metadata["melix.registry_variant_id"] as? String == "q4f16")
        #expect(metadata["melix.registry_relative_path"] as? String == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit")
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

    @Test("POST /v1/audio/transcriptions returns 409 and 503 for unavailable routes")
    func postAudioTranscriptionsReturns409And503ForUnavailableRoutes() async throws {
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

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

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
            appSupportDirectory: FileManager.default.temporaryDirectory
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
        #expect(payload == Data("VOICE=alloy\nFORMAT=wav\nTEXT=hello speech".utf8))
        #expect(metrics.values["audio.speech_request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["audio.speech_output_bytes", default: 0] == 40)
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

    @Test("POST /v1/audio/speech returns 409 and 503 for unavailable routes")
    func postAudioSpeechReturns409And503ForUnavailableRoutes() async throws {
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

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

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
        let appSupportDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-http-audio-model-\(UUID().uuidString)", isDirectory: true)
        let assetManager = AudioAssetManager(appSupportDirectory: appSupportDirectory)
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
        #expect(job.operation == "image_iterate")
        #expect(job.sourceArtifactID == "artifact-source")
        #expect(job.sourceJobID == "job-source")
        #expect(job.promptDelta == "make the colors warmer")
        #expect(job.editMode == .iterate)
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
        #expect(runningPayload.contains("\"state\":\"running\""))
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
        #expect(urlPayload.contains("\"state\":\"queued\""))
        #expect(urlPayload.contains("\"role\":\"input\""))
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

    @Test("non-stream chat requests return 400")
    func nonStreamRequestsReturn400() async throws {
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
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
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
        #expect(generated?.execution.ext["melix.preset_id"] == "deep_reasoning")
        #expect(generated?.execution.ext["melix.workflow"] == "tool_followup")
        #expect(metrics.values["http.preset_shaped_count", default: 0] == 1)
        #expect(metrics.values["http.workflow_shaped_count", default: 0] == 1)
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
    models: [[String: Any]]
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
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return String(decoding: data, as: UTF8.self)
}

private actor ScriptedWorkerClient: WorkerRoutingClient, RuntimeIntrospectingWorkerClientProtocol {
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private let loadModelHandle: String
    private let loadModelEstimatedResidentBytes: UInt64
    private let runtimeResidentBytes: UInt64
    private let runtimeModelResidentBytes: UInt64
    private let runtimeCacheResidentBytes: UInt64
    private let runtimeKVCacheBytes: UInt64
    private let runtimeStatsFailure: Error?
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?
    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?

    init(
        events: [Melix_Worker_V1_ExecuteEvent],
        loadModelHandle: String = "melix-dev-text::swift",
        loadModelEstimatedResidentBytes: UInt64 = 0,
        runtimeResidentBytes: UInt64 = 0,
        runtimeModelResidentBytes: UInt64 = 0,
        runtimeCacheResidentBytes: UInt64 = 0,
        runtimeKVCacheBytes: UInt64 = 0,
        runtimeStatsFailure: Error? = nil
    ) {
        self.events = events
        self.loadModelHandle = loadModelHandle
        self.loadModelEstimatedResidentBytes = loadModelEstimatedResidentBytes
        self.runtimeResidentBytes = runtimeResidentBytes
        self.runtimeModelResidentBytes = runtimeModelResidentBytes
        self.runtimeCacheResidentBytes = runtimeCacheResidentBytes
        self.runtimeKVCacheBytes = runtimeKVCacheBytes
        self.runtimeStatsFailure = runtimeStatsFailure
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

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        if let runtimeStatsFailure {
            throw runtimeStatsFailure
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
    private(set) var lastImageGenerateRequest: Melix_Worker_V1_ImageGenerateRequest?
    private(set) var lastImageEditRequest: Melix_Worker_V1_ImageEditRequest?
    private var embedResponse = Melix_Worker_V1_EmbedResponse()
    private var rerankResponse = Melix_Worker_V1_RerankResponse()
    private var transcribeResponse = Melix_Worker_V1_TranscribeResponse()
    private var speakResponse = Melix_Worker_V1_SpeakResponse()
    private var imageGenerateResponse = Melix_Worker_V1_ImageGenerateResponse()
    private var imageEditResponse = Melix_Worker_V1_ImageEditResponse()
    private var runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
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

    func setImageGenerateResponse(_ response: Melix_Worker_V1_ImageGenerateResponse) {
        imageGenerateResponse = response
    }

    func setImageEditResponse(_ response: Melix_Worker_V1_ImageEditResponse) {
        imageEditResponse = response
    }

    func setRuntimeStatsResponse(_ response: Melix_Worker_V1_GetRuntimeStatsResponse) {
        runtimeStatsResponse = response
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
