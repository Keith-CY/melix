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
