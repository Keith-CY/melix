import CryptoKit
import Foundation

public struct PersistentAuthSessionMetadata: Equatable, Sendable {
    public let sessionID: String
    public let keyID: String
    public let rememberMe: Bool
    public let createdAtUnixMs: Int64
    public let expiresAtUnixMs: Int64
    public let revokedAtUnixMs: Int64
    public let lastRestoredAtUnixMs: Int64

    var state: String {
        if revokedAtUnixMs > 0 {
            return "revoked"
        }
        return "active"
    }
}

public struct PersistentAuthSessionIssue: Equatable, Sendable {
    public let token: String
    public let metadata: PersistentAuthSessionMetadata
}

public struct PersistentAuthSessionRestoreResult: Equatable, Sendable {
    public let restoredSessionCount: Int
    public let expiredSessionCount: Int
    public let malformedRecordCount: Int
}

public enum PersistentAuthSessionValidationFailure: Error, Equatable, Sendable {
    case missingSession
    case revokedSession(sessionID: String, keyID: String, rememberMe: Bool)
    case expiredSession(sessionID: String, keyID: String, rememberMe: Bool)
}

private struct PersistentAuthSessionRecord: Codable, Equatable, Sendable {
    let sessionID: String
    let keyID: String
    let rememberMe: Bool
    let tokenHash: String
    let createdAtUnixMs: Int64
    let expiresAtUnixMs: Int64
    var revokedAtUnixMs: Int64
    var lastRestoredAtUnixMs: Int64

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case keyID = "key_id"
        case rememberMe = "remember_me"
        case tokenHash = "token_hash"
        case createdAtUnixMs = "created_at_unix_ms"
        case expiresAtUnixMs = "expires_at_unix_ms"
        case revokedAtUnixMs = "revoked_at_unix_ms"
        case lastRestoredAtUnixMs = "last_restored_at_unix_ms"
    }

    var metadata: PersistentAuthSessionMetadata {
        PersistentAuthSessionMetadata(
            sessionID: sessionID,
            keyID: keyID,
            rememberMe: rememberMe,
            createdAtUnixMs: createdAtUnixMs,
            expiresAtUnixMs: expiresAtUnixMs,
            revokedAtUnixMs: revokedAtUnixMs,
            lastRestoredAtUnixMs: lastRestoredAtUnixMs
        )
    }
}

private struct PersistentAuthSessionDocument: Codable, Equatable, Sendable {
    var schemaVersion: Int
    var sessions: [PersistentAuthSessionRecord]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessions
    }
}

public actor PersistentAuthSessionStore {
    public static let sessionHeaderName = "x-melix-session"

    private var sessionRecords: [String: PersistentAuthSessionRecord] = [:]
    private let storeURL: URL
    private let metricsStore: MetricsStore
    private let retentionTTLSeconds: Int
    private let fileManager: FileManager
    private let nowUnixMs: @Sendable () -> Int64

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        metricsStore: MetricsStore,
        fileManager: FileManager = .default,
        nowUnixMs: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.storeURL = Self.resolveStoreURL(environment: environment)
        self.metricsStore = metricsStore
        self.retentionTTLSeconds = Self.resolveRetentionTTLSeconds(environment: environment)
        self.fileManager = fileManager
        self.nowUnixMs = nowUnixMs
    }

    public init(
        storeURL: URL,
        metricsStore: MetricsStore,
        retentionTTLSeconds: Int,
        fileManager: FileManager = .default,
        nowUnixMs: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.storeURL = storeURL
        self.metricsStore = metricsStore
        self.retentionTTLSeconds = max(1, retentionTTLSeconds)
        self.fileManager = fileManager
        self.nowUnixMs = nowUnixMs
    }

    public func restorePersistedSessions() async throws -> PersistentAuthSessionRestoreResult {
        let loaded = try loadPersistedRecords()
        let now = nowUnixMs()
        var restoredSessionCount = 0
        var expiredSessionCount = 0
        var nextRecords: [String: PersistentAuthSessionRecord] = [:]

        for var record in loaded.records {
            if record.expiresAtUnixMs <= now {
                expiredSessionCount += 1
                continue
            }
            if record.revokedAtUnixMs == 0 {
                record.lastRestoredAtUnixMs = now
                restoredSessionCount += 1
            }
            nextRecords[record.tokenHash] = record
        }

        sessionRecords = nextRecords
        try writePersistedRecords()
        await updateMetrics(
            expiredSessionCount: expiredSessionCount,
            malformedRecordCount: loaded.malformedRecordCount,
            restoredSessionCount: restoredSessionCount
        )
        return PersistentAuthSessionRestoreResult(
            restoredSessionCount: restoredSessionCount,
            expiredSessionCount: expiredSessionCount,
            malformedRecordCount: loaded.malformedRecordCount
        )
    }

    public func issueSession(
        keyID: String,
        rememberMe: Bool
    ) async throws -> PersistentAuthSessionIssue {
        let createdAtUnixMs = nowUnixMs()
        let token = "melix_sess_\(UUID().uuidString.replacingOccurrences(of: "-", with: ""))"
        let record = PersistentAuthSessionRecord(
            sessionID: "auth-session-\(UUID().uuidString)",
            keyID: keyID,
            rememberMe: rememberMe,
            tokenHash: Self.hash(token),
            createdAtUnixMs: createdAtUnixMs,
            expiresAtUnixMs: createdAtUnixMs + Int64(retentionTTLSeconds * 1_000),
            revokedAtUnixMs: 0,
            lastRestoredAtUnixMs: 0
        )
        sessionRecords[record.tokenHash] = record
        if rememberMe {
            try writePersistedRecords()
        }
        await updateMetrics()
        return PersistentAuthSessionIssue(token: token, metadata: record.metadata)
    }

    public func validateSessionToken(
        _ token: String,
        policy: GatewayAccessPolicy
    ) async -> Result<PersistentAuthSessionMetadata, PersistentAuthSessionValidationFailure> {
        let tokenHash = Self.hash(token)
        guard let record = sessionRecords[tokenHash] else {
            return .failure(.missingSession)
        }

        let now = nowUnixMs()
        if record.expiresAtUnixMs <= now {
            await updateMetrics(expiredSessionCount: 1)
            return .failure(.expiredSession(
                sessionID: record.sessionID,
                keyID: record.keyID,
                rememberMe: record.rememberMe
            ))
        }
        if record.revokedAtUnixMs > 0 {
            return .failure(.revokedSession(
                sessionID: record.sessionID,
                keyID: record.keyID,
                rememberMe: record.rememberMe
            ))
        }
        if policy.supportsPersistentSessions == false || policy.containsKey(id: record.keyID) == false {
            var revoked = record
            revoked.revokedAtUnixMs = now
            sessionRecords[tokenHash] = revoked
            if revoked.rememberMe {
                try? writePersistedRecords()
            }
            await updateMetrics()
            return .failure(.revokedSession(
                sessionID: revoked.sessionID,
                keyID: revoked.keyID,
                rememberMe: revoked.rememberMe
            ))
        }
        return .success(record.metadata)
    }

    public func revokeSessionToken(
        _ token: String
    ) async throws -> Result<PersistentAuthSessionMetadata, PersistentAuthSessionValidationFailure> {
        let tokenHash = Self.hash(token)
        guard var record = sessionRecords[tokenHash] else {
            return .failure(.missingSession)
        }

        let startedAt = Date()
        guard record.revokedAtUnixMs == 0 else {
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "persistent_session.sign_out_latency_ms"
            )
            await updateMetrics()
            return .failure(.revokedSession(
                sessionID: record.sessionID,
                keyID: record.keyID,
                rememberMe: record.rememberMe
            ))
        }

        record.revokedAtUnixMs = nowUnixMs()
        sessionRecords[tokenHash] = record
        if record.rememberMe {
            try writePersistedRecords()
        }
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "persistent_session.sign_out_latency_ms"
        )
        await updateMetrics()
        return .success(record.metadata)
    }

    public func reconcile(with policy: GatewayAccessPolicy) async throws {
        let now = nowUnixMs()
        var changed = false
        for (tokenHash, record) in sessionRecords {
            guard record.revokedAtUnixMs == 0 else {
                continue
            }
            if policy.supportsPersistentSessions == false || policy.containsKey(id: record.keyID) == false {
                var revoked = record
                revoked.revokedAtUnixMs = now
                sessionRecords[tokenHash] = revoked
                changed = true
            }
        }
        if changed {
            try writePersistedRecords()
        }
        await updateMetrics()
    }

    private func updateMetrics(
        expiredSessionCount: Int? = nil,
        malformedRecordCount: Int = 0,
        restoredSessionCount: Int? = nil
    ) async {
        let activeSessions = sessionRecords.values.filter { record in
            record.revokedAtUnixMs == 0 && record.expiresAtUnixMs > nowUnixMs()
        }
        let rememberedSessions = activeSessions.filter(\.rememberMe)
        await metricsStore.set(Double(activeSessions.count), forKey: "persistent_session.active_session_count")
        await metricsStore.set(Double(rememberedSessions.count), forKey: "persistent_session.remembered_session_count")
        await metricsStore.set(Double(retentionTTLSeconds), forKey: "persistent_session.retention_ttl_seconds")
        if let expiredSessionCount {
            await metricsStore.set(Double(expiredSessionCount), forKey: "persistent_session.expired_session_count")
        } else {
            let expiredCount = sessionRecords.values.filter { $0.expiresAtUnixMs <= nowUnixMs() }.count
            await metricsStore.set(Double(expiredCount), forKey: "persistent_session.expired_session_count")
        }
        let denominator = max(
            Double((restoredSessionCount ?? activeSessions.count) + expiredSessionCount.orZero + malformedRecordCount),
            1
        )
        let numerator = Double(restoredSessionCount ?? activeSessions.count)
        await metricsStore.set((numerator / denominator) * 100, forKey: "persistent_session.restore_success_rate")
    }

    private func loadPersistedRecords() throws -> (records: [PersistentAuthSessionRecord], malformedRecordCount: Int) {
        guard fileManager.fileExists(atPath: storeURL.path) else {
            return ([], 0)
        }

        let data = try Data(contentsOf: storeURL)
        guard let rootObject = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rawSessions = rootObject["sessions"] as? [Any]
        else {
            return ([], 1)
        }

        var malformedRecordCount = 0
        var records: [PersistentAuthSessionRecord] = []
        for rawRecord in rawSessions {
            guard JSONSerialization.isValidJSONObject(rawRecord) else {
                malformedRecordCount += 1
                continue
            }
            do {
                let recordData = try JSONSerialization.data(withJSONObject: rawRecord, options: [.sortedKeys])
                let record = try Self.decoder.decode(PersistentAuthSessionRecord.self, from: recordData)
                records.append(record)
            } catch {
                malformedRecordCount += 1
            }
        }
        return (records, malformedRecordCount)
    }

    private func writePersistedRecords() throws {
        let records = sessionRecords.values
            .filter(\.rememberMe)
            .sorted { lhs, rhs in lhs.sessionID < rhs.sessionID }
        let document = PersistentAuthSessionDocument(schemaVersion: 1, sessions: records)
        let data = try Self.encoder.encode(document)
        try Self.writeAtomically(data, to: storeURL, fileManager: fileManager)
    }

    private static func resolveStoreURL(environment: [String: String]) -> URL {
        MelixPathLayout(environment: environment).persistentAuthSessionsURL
    }

    private static func resolveRetentionTTLSeconds(environment: [String: String]) -> Int {
        let raw = environment["MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        return max(Int(raw ?? "") ?? 2_592_000, 1)
    }

    private static func writeAtomically(_ data: Data, to fileURL: URL, fileManager: FileManager) throws {
        try fileManager.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let temporaryURL = fileURL
            .deletingLastPathComponent()
            .appendingPathComponent(".\(fileURL.lastPathComponent).\(UUID().uuidString).tmp")
        defer {
            try? fileManager.removeItem(at: temporaryURL)
        }
        try data.write(to: temporaryURL, options: [])
        if fileManager.fileExists(atPath: fileURL.path) {
            _ = try fileManager.replaceItemAt(fileURL, withItemAt: temporaryURL)
        } else {
            try fileManager.moveItem(at: temporaryURL, to: fileURL)
        }
    }

    private static func hash(_ token: String) -> String {
        SHA256.hash(data: Data(token.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }()

    private static let decoder = JSONDecoder()
}

private extension Optional where Wrapped == Int {
    var orZero: Int {
        self ?? 0
    }
}
