import CryptoKit
import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Persistent Auth Session Store")
struct PersistentAuthSessionStoreTests {
    @Test("environment-backed store resolves MELIX_HOME HOME and fallback paths while honoring retention TTL")
    func environmentBackedStoreResolvesConfiguredPathsAndTTL() async throws {
        let melixHomeRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-env-home-\(UUID().uuidString)")
        let homeRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: melixHomeRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: homeRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: melixHomeRoot)
            try? FileManager.default.removeItem(at: homeRoot)
        }

        let melixHomeMetrics = MetricsStore()
        let melixHomeStore = PersistentAuthSessionStore(
            environment: [
                "MELIX_HOME": melixHomeRoot.path,
                "MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS": "120",
            ],
            metricsStore: melixHomeMetrics,
            nowUnixMs: { 1_000 }
        )
        _ = try await melixHomeStore.restorePersistedSessions()
        _ = try await melixHomeStore.issueSession(keyID: "desktop-agent", rememberMe: true)

        let melixHomePersistedURL = melixHomeRoot
            .appendingPathComponent("state", isDirectory: true)
            .appendingPathComponent("persistent-auth-sessions.json", isDirectory: false)
        #expect(FileManager.default.fileExists(atPath: melixHomePersistedURL.path))
        #expect(await melixHomeMetrics.value(forKey: "persistent_session.retention_ttl_seconds") == 120)

        let homeMetrics = MetricsStore()
        let homeStore = PersistentAuthSessionStore(
            environment: [
                "HOME": homeRoot.path,
                "MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS": "0",
            ],
            metricsStore: homeMetrics,
            nowUnixMs: { 2_000 }
        )
        _ = try await homeStore.restorePersistedSessions()
        _ = try await homeStore.issueSession(keyID: "desktop-agent", rememberMe: true)

        let homePersistedURL = homeRoot
            .appendingPathComponent(".melix", isDirectory: true)
            .appendingPathComponent("state", isDirectory: true)
            .appendingPathComponent("persistent-auth-sessions.json", isDirectory: false)
        #expect(FileManager.default.fileExists(atPath: homePersistedURL.path))
        #expect(await homeMetrics.value(forKey: "persistent_session.retention_ttl_seconds") == 1)

        let fallbackMetrics = MetricsStore()
        let fallbackStore = PersistentAuthSessionStore(
            environment: [:],
            metricsStore: fallbackMetrics,
            nowUnixMs: { 3_000 }
        )
        let restoreResult = try await fallbackStore.restorePersistedSessions()
        #expect(restoreResult == PersistentAuthSessionRestoreResult(restoredSessionCount: 0, expiredSessionCount: 0, malformedRecordCount: 0))
        #expect(await fallbackMetrics.value(forKey: "persistent_session.retention_ttl_seconds") == 2_592_000)
    }

    @Test("store validation revokes sessions when gateway policy stops supporting them")
    func storeValidationRevokesSessionsWhenGatewayPolicyStopsSupportingThem() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-policy-\(UUID().uuidString)")
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
        let unsupportedPolicy = GatewayAccessPolicy(
            mode: .bearerToken,
            keys: []
        )
        let validation = await store.validateSessionToken(issued.token, policy: unsupportedPolicy)

        #expect(validation == .failure(.revokedSession(
            sessionID: issued.metadata.sessionID,
            keyID: "desktop-agent",
            rememberMe: true
        )))
        #expect(unsupportedPolicy.supportsPersistentSessions == false)
        #expect(unsupportedPolicy.containsKey(id: "desktop-agent") == false)

        let persistedObject = try persistedSessionDocument(
            at: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json")
        )
        let sessions = try #require(persistedObject["sessions"] as? [[String: Any]])
        let session = try #require(sessions.first)
        #expect((session["revoked_at_unix_ms"] as? Int64 ?? Int64(session["revoked_at_unix_ms"] as? Int ?? 0)) == 10_000)

        try await store.reconcile(with: unsupportedPolicy)
        #expect(await metricsStore.value(forKey: "persistent_session.active_session_count") == 0)
        #expect(await metricsStore.value(forKey: "persistent_session.remembered_session_count") == 0)
    }

    @Test("store records companion read-only session scope")
    func storeRecordsCompanionReadOnlySessionScope() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-scope-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let metricsStore = MetricsStore()
        let store = PersistentAuthSessionStore(
            storeURL: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json"),
            metricsStore: metricsStore,
            retentionTTLSeconds: 3600,
            nowUnixMs: { 10_000 }
        )

        let issued = try await store.issueSession(
            keyID: "desktop-agent",
            rememberMe: true,
            scope: .companionReadOnly
        )
        let validation = await store.validateSessionToken(
            issued.token,
            policy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                ]
            )
        )

        #expect(issued.metadata.scope == .companionReadOnly)
        #expect(validation == .success(issued.metadata))

        let persistedObject = try persistedSessionDocument(
            at: temporaryRoot.appendingPathComponent("persistent-auth-sessions.json")
        )
        let sessions = try #require(persistedObject["sessions"] as? [[String: Any]])
        let session = try #require(sessions.first)
        #expect(session["scope"] as? String == "companion_read_only")
    }

    @Test("store restores legacy sessions without scope as operator control")
    func storeRestoresLegacySessionsWithoutScopeAsOperatorControl() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-legacy-scope-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let token = "melix_sess_legacy"
        let tokenHash = SHA256.hash(data: Data(token.utf8)).map { String(format: "%02x", $0) }.joined()
        let storeURL = temporaryRoot.appendingPathComponent("persistent-auth-sessions.json")
        try #require("""
        {
          "schema_version": 1,
          "sessions": [
            {
              "session_id": "auth-session-legacy",
              "key_id": "desktop-agent",
              "remember_me": true,
              "token_hash": "\(tokenHash)",
              "created_at_unix_ms": 1000,
              "expires_at_unix_ms": 20000,
              "revoked_at_unix_ms": 0,
              "last_restored_at_unix_ms": 0
            }
          ]
        }
        """.data(using: .utf8)).write(to: storeURL)

        let metricsStore = MetricsStore()
        let store = PersistentAuthSessionStore(
            storeURL: storeURL,
            metricsStore: metricsStore,
            retentionTTLSeconds: 3600,
            nowUnixMs: { 10_000 }
        )
        let restoreResult = try await store.restorePersistedSessions()
        let validation = await store.validateSessionToken(
            token,
            policy: GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                keys: [
                    .init(keyID: "desktop-agent", label: "Desktop Agent", tokenHint: "desktop-agent", token: "sk-desktop"),
                ]
            )
        )

        #expect(restoreResult.restoredSessionCount == 1)
        #expect(restoreResult.malformedRecordCount == 0)
        guard case .success(let metadata) = validation else {
            Issue.record("Expected legacy session validation to succeed.")
            return
        }
        #expect(metadata.scope == .operatorControl)
        #expect(metadata.lastRestoredAtUnixMs == 10_000)
    }

    @Test("store consumes session revocation atomically")
    func storeConsumesSessionRevocationAtomically() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-revoke-\(UUID().uuidString)")
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

        async let first = store.revokeSessionToken(issued.token)
        async let second = store.revokeSessionToken(issued.token)
        let results = try await [first, second]
        let successCount = results.filter { result in
            if case .success = result {
                return true
            }
            return false
        }.count
        let revokedCount = results.filter { result in
            result == .failure(.revokedSession(
                sessionID: issued.metadata.sessionID,
                keyID: "desktop-agent",
                rememberMe: true
            ))
        }.count

        #expect(successCount == 1)
        #expect(revokedCount == 1)
        #expect(await metricsStore.value(forKey: "persistent_session.active_session_count") == 0)
    }

    @Test("store restore reports malformed roots and decode failures and revoke misses")
    func storeRestoreReportsMalformedRootsAndDecodeFailuresAndRevokeMisses() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-persistent-session-malformed-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("persistent-auth-sessions.json")
        let metricsStore = MetricsStore()
        let store = PersistentAuthSessionStore(
            storeURL: storeURL,
            metricsStore: metricsStore,
            retentionTTLSeconds: 3600,
            nowUnixMs: { 20_000 }
        )

        let missingRestore = try await store.restorePersistedSessions()
        #expect(missingRestore == PersistentAuthSessionRestoreResult(restoredSessionCount: 0, expiredSessionCount: 0, malformedRecordCount: 0))
        #expect(try await store.revokeSessionToken("missing-token") == .failure(.missingSession))

        try #require("""
        {
          "schema_version": 1
        }
        """.data(using: .utf8)).write(to: storeURL)

        let malformedRootRestore = try await store.restorePersistedSessions()
        #expect(malformedRootRestore.malformedRecordCount == 1)

        try #require("""
        {
          "schema_version": 1,
          "sessions": [
            {
              "session_id": "decode-failure"
            }
          ]
        }
        """.data(using: .utf8)).write(to: storeURL)

        let decodeFailureRestore = try await store.restorePersistedSessions()
        #expect(decodeFailureRestore.malformedRecordCount == 1)
    }
}

private func persistedSessionDocument(at url: URL) throws -> [String: Any] {
    let data = try Data(contentsOf: url)
    return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
}
