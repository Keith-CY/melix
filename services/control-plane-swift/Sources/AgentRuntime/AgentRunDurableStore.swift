import CryptoKit
import Darwin
import Foundation
import MelixControlPlaneProtocol
import OSLog

public struct AgentApprovalDecisionJournalReceipt: Codable, Sendable, Equatable {
    public struct Binding: Codable, Sendable, Equatable {
        public let runID: String
        public let callID: String
        public let schemaDigest: String
        public let argumentDigest: String
        public let policyRevision: String
        public let bindingDigest: String

        public init(_ binding: AgentApprovalBinding) {
            runID = binding.runID
            callID = binding.callID
            schemaDigest = binding.schemaDigest
            argumentDigest = binding.argumentDigest
            policyRevision = binding.policyRevision
            bindingDigest = binding.bindingDigest
        }
    }

    public let schemaVersion: String
    public let decisionID: String
    public let actorID: String
    public let decidedAtUnixMs: Int64
    public let binding: Binding
    public let choice: String

    public init(
        decisionID: String,
        actorID: String,
        decidedAtUnixMs: Int64,
        binding: AgentApprovalBinding,
        choice: AgentApprovalChoice
    ) {
        schemaVersion = "melix.agent-approval-decision.v1"
        self.decisionID = decisionID
        self.actorID = actorID
        self.decidedAtUnixMs = decidedAtUnixMs
        self.binding = Binding(binding)
        switch choice {
        case .allowOnce:
            self.choice = "allow_once"
        case .alwaysAllow:
            self.choice = "always_allow"
        case .deny:
            self.choice = "deny"
        }
    }
}

public struct AgentRunDurableStoreLimits: Sendable, Equatable {
    public let maxSnapshots: Int
    public let maxApprovalDecisions: Int
    public let maxCancellations: Int
    public let maxEntryBytes: Int

    public init(
        maxSnapshots: Int = 500,
        maxApprovalDecisions: Int = 2_000,
        maxCancellations: Int = 500,
        maxEntryBytes: Int = 1_048_576
    ) {
        self.maxSnapshots = max(maxSnapshots, 1)
        self.maxApprovalDecisions = max(maxApprovalDecisions, 1)
        self.maxCancellations = max(maxCancellations, 1)
        self.maxEntryBytes = max(maxEntryBytes, 4_096)
    }
}

public struct AgentRunDurableSnapshotPage: Sendable, Equatable {
    public let snapshots: [Melix_Controlplane_V1_AgentRunSnapshot]
    public let isComplete: Bool

    public init(
        snapshots: [Melix_Controlplane_V1_AgentRunSnapshot],
        isComplete: Bool
    ) {
        self.snapshots = snapshots
        self.isComplete = isComplete
    }
}

public enum AgentRunDurableStoreError: Error, Sendable, Equatable {
    case entryTooLarge(kind: String, bytes: Int)
    case invalidEntry(kind: String)
    case conflictingImmutableEntry(kind: String)
    case retentionCapacityExhausted(kind: String)
    case ioFailure(operation: String, code: Int32)
}

struct AgentRunDurableStoreSystemCalls: Sendable {
    var open: @Sendable (URL, Int32, mode_t) -> Int32
    var fchmod: @Sendable (Int32, mode_t) -> Int32
    var write: @Sendable (Int32, Data, Int) -> Int
    var fsync: @Sendable (Int32) -> Int32
    var close: @Sendable (Int32) -> Int32
    var rename: @Sendable (URL, URL) -> Int32
    var unlink: @Sendable (URL) -> Int32

    static let live = Self(
        open: { url, flags, mode in
            url.path.withCString { Darwin.open($0, flags, mode) }
        },
        fchmod: { Darwin.fchmod($0, $1) },
        write: { descriptor, data, offset in
            data.withUnsafeBytes { bytes in
                Darwin.write(
                    descriptor,
                    bytes.baseAddress?.advanced(by: offset),
                    bytes.count - offset
                )
            }
        },
        fsync: { Darwin.fsync($0) },
        close: { Darwin.close($0) },
        rename: { source, target in
            source.path.withCString { sourcePath in
                target.path.withCString { targetPath in
                    Darwin.rename(sourcePath, targetPath)
                }
            }
        },
        unlink: { url in
            url.path.withCString { Darwin.unlink($0) }
        }
    )
}

/// Bounded, product-owned journal for operator-facing Agent truth.
///
/// Snapshot files are atomically replaceable projections. Approval decisions
/// and cancellation receipts are immutable receipts: the first durable value
/// for an identifier wins, and a conflicting replay is rejected.
public actor AgentRunDurableStore {
    private static let logger = Logger(
        subsystem: "Melix.ControlPlane",
        category: "AgentRunDurableStore"
    )
    private let rootURL: URL
    private let limits: AgentRunDurableStoreLimits
    private let systemCalls: AgentRunDurableStoreSystemCalls
    private var pendingSnapshotMaintenance: [String: String] = [:]
    private var pendingImmutableMaintenance: [String: String] = [:]

    public init(
        rootURL: URL,
        limits: AgentRunDurableStoreLimits = AgentRunDurableStoreLimits()
    ) {
        self.rootURL = rootURL
        self.limits = limits
        systemCalls = .live
    }

    init(
        rootURL: URL,
        limits: AgentRunDurableStoreLimits = AgentRunDurableStoreLimits(),
        systemCalls: AgentRunDurableStoreSystemCalls
    ) {
        self.rootURL = rootURL
        self.limits = limits
        self.systemCalls = systemCalls
    }

    public func persistSnapshot(
        _ snapshot: Melix_Controlplane_V1_AgentRunSnapshot
    ) throws {
        let data = try snapshot.serializedData()
        try validateSize(data, kind: "snapshot")
        let directory = rootURL.appendingPathComponent("runs", isDirectory: true)
        try Self.prepareDirectory(directory)
        let destination = directory.appendingPathComponent(
            Self.fileKey(snapshot.runID) + ".pb"
        )
        try prepareSnapshotWrite(
            at: destination,
            in: directory
        )
        let directoryKey = directory.standardizedFileURL.path
        do {
            try atomicReplace(data, at: destination)
        } catch {
            if FileManager.default.fileExists(atPath: destination.path) {
                pendingSnapshotMaintenance[directoryKey] = destination.path
            }
            throw error
        }
        do {
            try enforceSnapshotRetention(
                in: directory,
                maxCount: limits.maxSnapshots,
                retaining: destination
            )
            pendingSnapshotMaintenance.removeValue(forKey: directoryKey)
        } catch {
            pendingSnapshotMaintenance[directoryKey] = destination.path
            throw error
        }
    }

    public func persistApprovalDecision(
        _ receipt: AgentApprovalDecisionJournalReceipt
    ) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(receipt)
        try validateSize(data, kind: "approval")
        let directory = rootURL.appendingPathComponent("approvals", isDirectory: true)
        try Self.prepareDirectory(directory)
        let destination = directory.appendingPathComponent(
            Self.fileKey(receipt.decisionID) + ".json"
        )
        guard try prepareImmutableWrite(
            data,
            at: destination,
            in: directory,
            maxCount: limits.maxApprovalDecisions,
            kind: "approval"
        ) else {
            return
        }
        try writeImmutable(
            data,
            at: destination,
            kind: "approval"
        )
        finishImmutableWrite(
            in: directory,
            maxCount: limits.maxApprovalDecisions,
            retaining: destination,
            kind: "approval"
        )
    }

    public func persistCancellation(
        _ receipt: Melix_Controlplane_V1_AgentRunCancellationReceipt
    ) throws {
        let data = try receipt.serializedData()
        try validateSize(data, kind: "cancellation")
        let directory = rootURL.appendingPathComponent("cancellations", isDirectory: true)
        try Self.prepareDirectory(directory)
        let destination = directory.appendingPathComponent(
            Self.fileKey(receipt.runID) + ".pb"
        )
        guard try prepareImmutableWrite(
            data,
            at: destination,
            in: directory,
            maxCount: limits.maxCancellations,
            kind: "cancellation"
        ) else {
            return
        }
        try writeImmutable(
            data,
            at: destination,
            kind: "cancellation"
        )
        finishImmutableWrite(
            in: directory,
            maxCount: limits.maxCancellations,
            retaining: destination,
            kind: "cancellation"
        )
    }

    public func snapshot(
        runID: String
    ) throws -> Melix_Controlplane_V1_AgentRunSnapshot? {
        let fileURL = rootURL
            .appendingPathComponent("runs", isDirectory: true)
            .appendingPathComponent(Self.fileKey(runID) + ".pb")
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return nil
        }
        let data = try readBounded(fileURL, kind: "snapshot")
        let snapshot = try Melix_Controlplane_V1_AgentRunSnapshot(
            serializedBytes: data
        )
        guard snapshot.runID == runID else {
            throw AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        }
        return snapshot
    }

    public func snapshots(
        sessionID: String = "",
        limit: Int = 100
    ) throws -> [Melix_Controlplane_V1_AgentRunSnapshot] {
        let boundedLimit = min(max(limit, 1), limits.maxSnapshots)
        let directory = rootURL.appendingPathComponent("runs", isDirectory: true)
        let files = try Self.newestFiles(in: directory)
        var snapshots: [Melix_Controlplane_V1_AgentRunSnapshot] = []
        for fileURL in files {
            guard snapshots.count < boundedLimit else { break }
            guard let data = try? readBounded(fileURL, kind: "snapshot"),
                  let snapshot = try? Melix_Controlplane_V1_AgentRunSnapshot(
                    serializedBytes: data
                  ),
                  !snapshot.runID.isEmpty,
                  sessionID.isEmpty || snapshot.sessionID == sessionID
            else {
                continue
            }
            snapshots.append(snapshot)
        }
        return snapshots.sorted { lhs, rhs in
            if lhs.updatedAtUnixMs == rhs.updatedAtUnixMs {
                return lhs.runID > rhs.runID
            }
            return lhs.updatedAtUnixMs > rhs.updatedAtUnixMs
        }
    }

    /// Returns a safety inventory that is complete only when every durable
    /// snapshot could be decoded and classified. Unknown states are treated as
    /// nonterminal so callers cannot mistake a future state for safe history.
    public func nonterminalSnapshotPage(
        sessionID: String = "",
        limit: Int = 500
    ) throws -> AgentRunDurableSnapshotPage {
        let boundedLimit = min(max(limit, 1), limits.maxSnapshots)
        let directory = rootURL.appendingPathComponent("runs", isDirectory: true)
        var matches: [Melix_Controlplane_V1_AgentRunSnapshot] = []
        for fileURL in try Self.strictNewestFiles(
            in: directory,
            kind: "snapshot"
        ) {
            let snapshot = try validatedSnapshot(at: fileURL)
            guard !Self.isTerminalSnapshot(snapshot),
                  sessionID.isEmpty || snapshot.sessionID == sessionID
            else {
                continue
            }
            matches.append(snapshot)
        }
        matches.sort { lhs, rhs in
            if lhs.updatedAtUnixMs == rhs.updatedAtUnixMs {
                return lhs.runID > rhs.runID
            }
            return lhs.updatedAtUnixMs > rhs.updatedAtUnixMs
        }
        return AgentRunDurableSnapshotPage(
            snapshots: Array(matches.prefix(boundedLimit)),
            isComplete: matches.count <= boundedLimit
        )
    }

    public func cancellation(
        runID: String
    ) throws -> Melix_Controlplane_V1_AgentRunCancellationReceipt? {
        let fileURL = rootURL
            .appendingPathComponent("cancellations", isDirectory: true)
            .appendingPathComponent(Self.fileKey(runID) + ".pb")
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return nil
        }
        let data = try readBounded(fileURL, kind: "cancellation")
        let receipt = try Melix_Controlplane_V1_AgentRunCancellationReceipt(
            serializedBytes: data
        )
        guard receipt.runID == runID else {
            throw AgentRunDurableStoreError.invalidEntry(kind: "cancellation")
        }
        return receipt
    }

    public func approvalDecisions(
        runID: String,
        limit: Int = 100
    ) throws -> [AgentApprovalDecisionJournalReceipt] {
        let boundedLimit = min(max(limit, 1), limits.maxApprovalDecisions)
        let directory = rootURL.appendingPathComponent("approvals", isDirectory: true)
        let decoder = JSONDecoder()
        var receipts: [AgentApprovalDecisionJournalReceipt] = []
        for fileURL in try Self.newestFiles(in: directory) {
            guard receipts.count < boundedLimit else { break }
            guard let data = try? readBounded(fileURL, kind: "approval"),
                  let receipt = try? decoder.decode(
                    AgentApprovalDecisionJournalReceipt.self,
                    from: data
                  ),
                  receipt.schemaVersion == "melix.agent-approval-decision.v1",
                  receipt.binding.runID == runID
            else {
                continue
            }
            receipts.append(receipt)
        }
        return receipts.sorted { lhs, rhs in
            if lhs.decidedAtUnixMs == rhs.decidedAtUnixMs {
                return lhs.decisionID > rhs.decisionID
            }
            return lhs.decidedAtUnixMs > rhs.decidedAtUnixMs
        }
    }

    private func validateSize(_ data: Data, kind: String) throws {
        guard data.count <= limits.maxEntryBytes else {
            throw AgentRunDurableStoreError.entryTooLarge(
                kind: kind,
                bytes: data.count
            )
        }
    }

    private func readBounded(_ fileURL: URL, kind: String) throws -> Data {
        let descriptor = fileURL.path.withCString {
            Darwin.open($0, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
        }
        guard descriptor >= 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "open-read-entry",
                code: errno
            )
        }
        defer { _ = Darwin.close(descriptor) }
        var status = stat()
        guard Darwin.fstat(descriptor, &status) == 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "stat-read-entry",
                code: errno
            )
        }
        guard (status.st_mode & S_IFMT) == S_IFREG else {
            throw AgentRunDurableStoreError.invalidEntry(kind: kind)
        }
        guard status.st_size >= 0,
              status.st_size <= limits.maxEntryBytes else {
            throw AgentRunDurableStoreError.entryTooLarge(
                kind: kind,
                bytes: Int(max(status.st_size, 0))
            )
        }
        var data = Data(count: Int(status.st_size))
        var offset = 0
        while offset < data.count {
            let count = data.withUnsafeMutableBytes { bytes in
                Darwin.read(
                    descriptor,
                    bytes.baseAddress?.advanced(by: offset),
                    bytes.count - offset
                )
            }
            if count < 0, errno == EINTR { continue }
            guard count > 0 else {
                throw AgentRunDurableStoreError.invalidEntry(kind: kind)
            }
            offset += count
        }
        var trailingByte: UInt8 = 0
        let trailingCount = Darwin.read(descriptor, &trailingByte, 1)
        guard trailingCount == 0 else {
            throw AgentRunDurableStoreError.invalidEntry(kind: kind)
        }
        try validateSize(data, kind: kind)
        return data
    }

    private static func fileKey(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { byte in
            String(format: "%02x", byte)
        }.joined()
    }

    private static func newestFiles(in directory: URL) throws -> [URL] {
        guard FileManager.default.fileExists(atPath: directory.path) else {
            return []
        }
        let keys: Set<URLResourceKey> = [
            .isRegularFileKey,
            .contentModificationDateKey,
        ]
        return try FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: Array(keys),
            options: [.skipsHiddenFiles]
        )
        .filter { url in
            (try? url.resourceValues(forKeys: keys).isRegularFile) == true
        }
        .sorted { lhs, rhs in
            let left = try? lhs.resourceValues(forKeys: keys).contentModificationDate
            let right = try? rhs.resourceValues(forKeys: keys).contentModificationDate
            if left == right {
                return lhs.lastPathComponent > rhs.lastPathComponent
            }
            return (left ?? .distantPast) > (right ?? .distantPast)
        }
    }

    /// Safety inventories must classify every directory entry. A symlink,
    /// FIFO, device, or unreadable entry is corruption rather than an absent
    /// run; silently filtering it could turn an incomplete inventory into a
    /// false-safe empty result.
    private static func strictNewestFiles(
        in directory: URL,
        kind: String
    ) throws -> [URL] {
        guard FileManager.default.fileExists(atPath: directory.path) else {
            return []
        }
        let urls = try FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: []
        )
        var classified: [(url: URL, modifiedAt: Date)] = []
        classified.reserveCapacity(urls.count)
        for url in urls {
            var status = stat()
            let result = url.path.withCString { Darwin.lstat($0, &status) }
            guard result == 0,
                  (status.st_mode & S_IFMT) == S_IFREG else {
                throw AgentRunDurableStoreError.invalidEntry(kind: kind)
            }
            if kind == "snapshot",
               Self.isAtomicSnapshotStagingFile(url.lastPathComponent) {
                do {
                    try FileManager.default.removeItem(at: url)
                    let directoryDescriptor = directory.path.withCString {
                        Darwin.open($0, O_RDONLY | O_DIRECTORY | O_CLOEXEC)
                    }
                    guard directoryDescriptor >= 0 else {
                        throw AgentRunDurableStoreError.ioFailure(
                            operation: "open-directory",
                            code: errno
                        )
                    }
                    defer { _ = Darwin.close(directoryDescriptor) }
                    guard Darwin.fsync(directoryDescriptor) == 0 else {
                        throw AgentRunDurableStoreError.ioFailure(
                            operation: "sync-directory",
                            code: errno
                        )
                    }
                    continue
                } catch let error as AgentRunDurableStoreError {
                    throw error
                } catch let error as NSError {
                    throw AgentRunDurableStoreError.ioFailure(
                        operation: "remove-staging-entry",
                        code: Int32(error.code)
                    )
                }
            }
            guard Self.isCanonicalJournalFile(
                url.lastPathComponent,
                kind: kind
            ) else {
                throw AgentRunDurableStoreError.invalidEntry(kind: kind)
            }
            let modifiedAt = try url.resourceValues(
                forKeys: [.contentModificationDateKey]
            ).contentModificationDate ?? .distantPast
            classified.append((url, modifiedAt))
        }
        return classified.sorted { lhs, rhs in
            if lhs.modifiedAt == rhs.modifiedAt {
                return lhs.url.lastPathComponent > rhs.url.lastPathComponent
            }
            return lhs.modifiedAt > rhs.modifiedAt
        }.map(\.url)
    }

    private static func isAtomicSnapshotStagingFile(_ name: String) -> Bool {
        guard name.first == ".",
              let separator = name.range(of: ".pb.tmp-") else {
            return false
        }
        let digest = name[name.index(after: name.startIndex)..<separator.lowerBound]
        let uuid = name[separator.upperBound...]
        return digest.count == 64
            && digest.allSatisfy {
                ("0"..."9").contains($0) || ("a"..."f").contains($0)
            }
            && UUID(uuidString: String(uuid)) != nil
    }

    private static func isCanonicalJournalFile(
        _ name: String,
        kind: String
    ) -> Bool {
        let suffix: String
        switch kind {
        case "snapshot", "cancellation":
            suffix = ".pb"
        case "approval":
            suffix = ".json"
        default:
            return false
        }
        guard name.hasSuffix(suffix) else { return false }
        let digest = name.dropLast(suffix.count)
        return digest.count == 64
            && digest.allSatisfy {
                ("0"..."9").contains($0) || ("a"..."f").contains($0)
            }
    }

    private func prepareSnapshotWrite(
        at destination: URL,
        in directory: URL
    ) throws {
        let directoryKey = directory.standardizedFileURL.path
        if let pendingPath = pendingSnapshotMaintenance[directoryKey] {
            try syncDirectory(directory)
            try enforceSnapshotRetention(
                in: directory,
                maxCount: limits.maxSnapshots,
                retaining: URL(fileURLWithPath: pendingPath)
            )
            pendingSnapshotMaintenance.removeValue(forKey: directoryKey)
        }

        var files = try Self.strictNewestFiles(
            in: directory,
            kind: "snapshot"
        )
        if files.count > limits.maxSnapshots {
            try enforceSnapshotRetention(
                in: directory,
                maxCount: limits.maxSnapshots,
                retaining: destination
            )
            files = try Self.strictNewestFiles(
                in: directory,
                kind: "snapshot"
            )
        }

        let snapshots = try files.map { fileURL in
            try validatedSnapshot(at: fileURL)
        }
        let destinationPath = destination.standardizedFileURL.path
        if files.contains(where: {
            $0.standardizedFileURL.path == destinationPath
        }) {
            return
        }
        guard files.count < limits.maxSnapshots
                || snapshots.contains(where: Self.isTerminalSnapshot)
        else {
            throw AgentRunDurableStoreError.retentionCapacityExhausted(
                kind: "snapshot"
            )
        }
    }

    func hasPendingSnapshotRetentionMaintenance() -> Bool {
        pendingSnapshotMaintenance.isEmpty == false
    }

    private func enforceSnapshotRetention(
        in directory: URL,
        maxCount: Int,
        retaining protectedURL: URL
    ) throws {
        let files = try Self.strictNewestFiles(
            in: directory,
            kind: "snapshot"
        )
        guard files.count > maxCount else { return }
        let protectedPath = protectedURL.standardizedFileURL.path
        var terminalCandidates: [URL] = []
        for fileURL in files.reversed() where
            fileURL.standardizedFileURL.path != protectedPath
        {
            if Self.isTerminalSnapshot(try validatedSnapshot(at: fileURL)) {
                terminalCandidates.append(fileURL)
            }
        }
        let removalCount = files.count - maxCount
        guard terminalCandidates.count >= removalCount else {
            throw AgentRunDurableStoreError.retentionCapacityExhausted(
                kind: "snapshot"
            )
        }
        for fileURL in terminalCandidates.prefix(removalCount) {
            do {
                try FileManager.default.removeItem(at: fileURL)
            } catch let error as NSError {
                throw AgentRunDurableStoreError.ioFailure(
                    operation: "retention-delete",
                    code: Int32(error.code)
                )
            }
        }
        try syncDirectory(directory)
    }

    private func enforceRetention(
        in directory: URL,
        maxCount: Int,
        retaining protectedURL: URL,
        kind: String
    ) throws {
        var files = try Self.strictNewestFiles(
            in: directory,
            kind: kind
        )
        let protectedPath = protectedURL.standardizedFileURL.path
        if let protectedIndex = files.firstIndex(where: {
            $0.standardizedFileURL.path == protectedPath
        }), protectedIndex != 0 {
            let protected = files.remove(at: protectedIndex)
            files.insert(protected, at: 0)
        }
        guard files.count > maxCount else { return }
        for fileURL in files.dropFirst(maxCount) {
            do {
                try FileManager.default.removeItem(at: fileURL)
            } catch let error as NSError {
                throw AgentRunDurableStoreError.ioFailure(
                    operation: "retention-delete",
                    code: Int32(error.code)
                )
            }
        }
        try syncDirectory(directory)
    }

    private func validatedSnapshot(
        at fileURL: URL
    ) throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        let data = try readBounded(fileURL, kind: "snapshot")
        let snapshot: Melix_Controlplane_V1_AgentRunSnapshot
        do {
            snapshot = try Melix_Controlplane_V1_AgentRunSnapshot(
                serializedBytes: data
            )
        } catch {
            throw AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        }
        guard !snapshot.runID.isEmpty,
              fileURL.lastPathComponent
                == Self.fileKey(snapshot.runID) + ".pb"
        else {
            throw AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        }
        return snapshot
    }

    private static func isTerminalSnapshot(
        _ snapshot: Melix_Controlplane_V1_AgentRunSnapshot
    ) -> Bool {
        snapshot.state == "completed"
            || snapshot.state == "failed"
            || snapshot.state == "cancelled"
    }

    private static func prepareDirectory(_ directory: URL) throws {
        do {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: NSNumber(value: 0o700)]
            )
            try FileManager.default.setAttributes(
                [.posixPermissions: NSNumber(value: 0o700)],
                ofItemAtPath: directory.path
            )
        } catch let error as NSError {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "prepare-directory",
                code: Int32(error.code)
            )
        }
    }

    private func atomicReplace(_ data: Data, at destination: URL) throws {
        let temporary = destination.deletingLastPathComponent().appendingPathComponent(
            ".\(destination.lastPathComponent).tmp-\(UUID().uuidString)"
        )
        do {
            try writeNewFile(data, at: temporary)
            let result = systemCalls.rename(temporary, destination)
            guard result == 0 else {
                throw AgentRunDurableStoreError.ioFailure(
                    operation: "rename-entry",
                    code: errno
                )
            }
            try syncDirectory(destination.deletingLastPathComponent())
        } catch {
            try? FileManager.default.removeItem(at: temporary)
            throw error
        }
    }

    private func writeImmutable(
        _ data: Data,
        at destination: URL,
        kind: String
    ) throws {
        do {
            try writeNewFile(data, at: destination)
            try syncDirectory(destination.deletingLastPathComponent())
        } catch let error as AgentRunDurableStoreError {
            if case .ioFailure(let operation, let code) = error,
               operation == "open-entry",
               code == EEXIST {
                guard immutableEntryMatches(data, at: destination) else {
                    throw AgentRunDurableStoreError.conflictingImmutableEntry(
                        kind: kind
                    )
                }
                try syncDirectory(destination.deletingLastPathComponent())
                return
            }
            throw error
        }
    }

    func pendingImmutableMaintenanceKinds() -> [String] {
        Array(Set(pendingImmutableMaintenance.values)).sorted()
    }

    private func prepareImmutableWrite(
        _ data: Data,
        at destination: URL,
        in directory: URL,
        maxCount: Int,
        kind: String
    ) throws -> Bool {
        let directoryKey = directory.standardizedFileURL.path
        if FileManager.default.fileExists(atPath: destination.path) {
            guard immutableEntryMatches(data, at: destination) else {
                throw AgentRunDurableStoreError.conflictingImmutableEntry(
                    kind: kind
                )
            }
            // Confirm the exact committed identity before deleting any older
            // receipt. This preserves the previous durable truth across
            // repeated directory-fsync failures after a first-create attempt.
            try syncDirectory(directory)
            finishImmutableWrite(
                in: directory,
                maxCount: maxCount,
                retaining: destination,
                kind: kind
            )
            return false
        }
        if pendingImmutableMaintenance[directoryKey] != nil {
            try syncDirectory(directory)
            try enforceRetention(
                in: directory,
                maxCount: maxCount,
                retaining: destination,
                kind: kind
            )
            pendingImmutableMaintenance.removeValue(forKey: directoryKey)
        }
        // Resolve any pre-existing overflow before admitting one bounded
        // staging/commit slot. A committed write may temporarily leave at
        // most maxCount + 1 files if post-commit cleanup itself fails; no
        // further new identity is admitted until that maintenance recovers.
        try enforceRetention(
            in: directory,
            maxCount: maxCount,
            retaining: destination,
            kind: kind
        )
        return true
    }

    private func finishImmutableWrite(
        in directory: URL,
        maxCount: Int,
        retaining destination: URL,
        kind: String
    ) {
        let directoryKey = directory.standardizedFileURL.path
        do {
            try enforceRetention(
                in: directory,
                maxCount: maxCount,
                retaining: destination,
                kind: kind
            )
            pendingImmutableMaintenance.removeValue(forKey: directoryKey)
        } catch {
            pendingImmutableMaintenance[directoryKey] = kind
            Self.logger.error(
                "Committed \(kind, privacy: .public) receipt has pending bounded-retention maintenance: \(String(describing: error), privacy: .public)"
            )
        }
    }

    private func immutableEntryMatches(
        _ data: Data,
        at destination: URL
    ) -> Bool {
        guard let existing = try? readBounded(
            destination,
            kind: "immutable"
        ),
        existing == data else {
            return false
        }
        return true
    }

    private func writeNewFile(_ data: Data, at destination: URL) throws {
        let descriptor = systemCalls.open(
            destination,
            O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC,
            mode_t(S_IRUSR | S_IWUSR)
        )
        guard descriptor >= 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "open-entry",
                code: errno
            )
        }
        var descriptorOpen = true
        var completed = false
        defer {
            if descriptorOpen { _ = systemCalls.close(descriptor) }
            if !completed {
                _ = systemCalls.unlink(destination)
            }
        }
        guard systemCalls.fchmod(descriptor, mode_t(S_IRUSR | S_IWUSR)) == 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "chmod-entry",
                code: errno
            )
        }
        var offset = 0
        while offset < data.count {
            let result = systemCalls.write(descriptor, data, offset)
            if result < 0, errno == EINTR { continue }
            guard result > 0 else {
                throw AgentRunDurableStoreError.ioFailure(
                    operation: "write-entry",
                    code: result < 0 ? errno : EIO
                )
            }
            offset += result
        }
        guard systemCalls.fsync(descriptor) == 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "sync-entry",
                code: errno
            )
        }
        guard systemCalls.close(descriptor) == 0 else {
            descriptorOpen = false
            throw AgentRunDurableStoreError.ioFailure(
                operation: "close-entry",
                code: errno
            )
        }
        descriptorOpen = false
        completed = true
    }

    private func syncDirectory(_ directory: URL) throws {
        let descriptor = systemCalls.open(
            directory,
            O_RDONLY | O_CLOEXEC,
            0
        )
        guard descriptor >= 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "open-directory",
                code: errno
            )
        }
        defer { _ = systemCalls.close(descriptor) }
        guard systemCalls.fsync(descriptor) == 0 else {
            throw AgentRunDurableStoreError.ioFailure(
                operation: "sync-directory",
                code: errno
            )
        }
    }
}
