import Foundation
import MelixWorkerProtocol

struct DiskCacheScopeSummary: Sendable {
    let scope: Melix_Worker_V1_CacheScope
    let l2Bytes: UInt64
    let snapshotCount: UInt64
}

struct DiskCacheSummary: Sendable {
    let l2Bytes: UInt64
    let quantizedBytes: UInt64
    let unquantizedBytes: UInt64
    let snapshotCount: UInt64
    let l2HitRate: Double
    let l2RestoreHitRate: Double
    let writeBackQueueDepth: UInt64
    let restoreQueueDepth: UInt64
    let writeBackCount: UInt64
    let namespaceMismatchCount: UInt64
    let snapshots: [Melix_Worker_V1_SnapshotRef]
    let scopes: [DiskCacheScopeSummary]
}

struct DiskCacheTierMetrics: Sendable {
    let l2HitRate: Double
    let l2RestoreHitRate: Double
    let writeBackQueueDepth: UInt64
    let restoreQueueDepth: UInt64
    let writeBackCount: UInt64
}

struct RestoredBoundarySnapshot: Sendable {
    let snapshot: Melix_Worker_V1_SnapshotRef
    let model: Melix_Worker_V1_ModelSpec
    let messages: [Melix_Worker_V1_ChatMessage]
    let resumeHint: String
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let promptTokens: Int
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
}

struct DiskCacheOwnershipSnapshot: Sendable {
    let prefixCount: Int
    let pageCount: Int
    let blockCount: Int
    let snapshotCount: Int
}

private struct PersistedPrefixEnvelope: Codable {
    let runtimeCacheFingerprint: String?
    let prefixID: String
    let prefixData: Data
    let blockTableID: String
    let blockTableData: Data
    let quantizedBytes: UInt64
    let unquantizedBytes: UInt64
}

private struct PersistedSnapshotEnvelope: Codable {
    let runtimeCacheFingerprint: String?
    let snapshotID: String
    let snapshotData: Data
    let modelData: Data
    let messagesData: [Data]
    let resumeHint: String
    let accelerationData: Data
    let promptTokens: Int
    let blockTableID: String
    let blockTableData: Data
}

private struct StoredL2PrefixRecord: Sendable {
    let prefix: Melix_Worker_V1_PrefixRef
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let quantizedBytes: UInt64
    let unquantizedBytes: UInt64
}

private struct StoredBoundarySnapshotRecord: Sendable {
    let snapshot: Melix_Worker_V1_SnapshotRef
    let model: Melix_Worker_V1_ModelSpec
    let messages: [Melix_Worker_V1_ChatMessage]
    let resumeHint: String
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let promptTokens: Int
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
}

actor DiskCacheStore {
    private let fileManager: FileManager
    private let rootURL: URL
    private let prefixesURL: URL
    private let snapshotsURL: URL
    private let runtimeCacheFingerprint: String

    private var prefixesByID: [String: StoredL2PrefixRecord]
    private var prefixIDByKey: [String: String]
    private var snapshotsByID: [String: StoredBoundarySnapshotRecord]
    private var prefixRestoreLookups: UInt64
    private var prefixRestoreHits: UInt64
    private var snapshotRestoreLookups: UInt64
    private var snapshotRestoreHits: UInt64
    private var pendingWriteBackOperations: UInt64
    private var pendingRestoreOperations: UInt64
    private var completedWriteBackCount: UInt64
    private var namespaceMismatchCount: UInt64

    init(
        rootPath: String,
        runtimeCacheFingerprint: String = "dev",
        fileManager: FileManager = .default
    ) {
        self.fileManager = fileManager
        self.rootURL = URL(fileURLWithPath: rootPath, isDirectory: true)
        self.prefixesURL = rootURL.appendingPathComponent("prefixes", isDirectory: true)
        self.snapshotsURL = rootURL.appendingPathComponent("snapshots", isDirectory: true)
        self.runtimeCacheFingerprint = runtimeCacheFingerprint

        let loaded = Self.loadState(
            fileManager: fileManager,
            prefixesURL: prefixesURL,
            snapshotsURL: snapshotsURL,
            runtimeCacheFingerprint: runtimeCacheFingerprint
        )
        self.prefixesByID = loaded.prefixes
        self.prefixIDByKey = Dictionary(
            uniqueKeysWithValues: loaded.prefixes.values.map { record in
                (diskCacheKeyIdentifier(record.prefix.cacheKey), record.prefix.prefixID)
            }
        )
        self.snapshotsByID = loaded.snapshots
        self.prefixRestoreLookups = 0
        self.prefixRestoreHits = 0
        self.snapshotRestoreLookups = 0
        self.snapshotRestoreHits = 0
        self.pendingWriteBackOperations = 0
        self.pendingRestoreOperations = 0
        self.completedWriteBackCount = 0
        self.namespaceMismatchCount = loaded.namespaceMismatchCount

        Self.ensureDirectory(fileManager: fileManager, url: prefixesURL)
        Self.ensureDirectory(fileManager: fileManager, url: snapshotsURL)
    }

    func persistPrefix(
        prefix: Melix_Worker_V1_PrefixRef,
        blockTableID: String,
        blockTable: Melix_Worker_V1_BlockTable,
        quantizedBytes: UInt64
    ) {
        var persistedPrefix = prefix
        persistedPrefix.tier = "l2"
        let normalizedTable = normalizedBlockTable(blockTable)
        let record = StoredL2PrefixRecord(
            prefix: persistedPrefix,
            blockTableID: blockTableID,
            blockTable: normalizedTable,
            quantizedBytes: quantizedBytes,
            unquantizedBytes: normalizedTable.blocks.reduce(UInt64(0)) { $0 + $1.bytes }
        )
        prefixesByID[persistedPrefix.prefixID] = record
        prefixIDByKey[diskCacheKeyIdentifier(persistedPrefix.cacheKey)] = persistedPrefix.prefixID

        pendingWriteBackOperations += 1
        writePrefixRecord(record)
        pendingWriteBackOperations -= 1
        completedWriteBackCount += 1
    }

    func saveSnapshot(
        snapshot: Melix_Worker_V1_SnapshotRef,
        model: Melix_Worker_V1_ModelSpec,
        messages: [Melix_Worker_V1_ChatMessage],
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        promptTokens: Int,
        blockTableID: String,
        blockTable: Melix_Worker_V1_BlockTable,
        prefix: Melix_Worker_V1_PrefixRef?
    ) {
        let normalizedTable = normalizedBlockTable(blockTable)
        if let prefix {
            let quantizedBytes = storageBoundaryQuantizedBytes(
                for: normalizedTable,
                activeKVQuantizationRatio: activeKVQuantizationRatio(from: acceleration)
            )
            persistPrefix(
                prefix: prefix,
                blockTableID: blockTableID,
                blockTable: normalizedTable,
                quantizedBytes: quantizedBytes
            )
        }

        let record = StoredBoundarySnapshotRecord(
            snapshot: snapshot,
            model: model,
            messages: messages,
            resumeHint: resumeHint,
            acceleration: acceleration,
            promptTokens: promptTokens,
            blockTableID: blockTableID,
            blockTable: normalizedTable
        )
        snapshotsByID[snapshot.snapshotID] = record
        writeSnapshotRecord(record)
    }

    func ownershipSnapshot() -> DiskCacheOwnershipSnapshot {
        let tables = prefixesByID.values.map(\.blockTable)
        let pageCount = Set(tables.flatMap(\.pages).map(\.pageID)).count
        let blockCount = Set(tables.flatMap(\.blocks).map(\.blockID)).count
        return DiskCacheOwnershipSnapshot(
            prefixCount: prefixesByID.count,
            pageCount: pageCount,
            blockCount: blockCount,
            snapshotCount: snapshotsByID.count
        )
    }

    func restoreSnapshot(snapshotID: String) -> RestoredBoundarySnapshot? {
        pendingRestoreOperations += 1
        snapshotRestoreLookups += 1
        defer { pendingRestoreOperations -= 1 }
        guard let record = snapshotsByID[snapshotID] else {
            return nil
        }

        snapshotRestoreHits += 1
        return RestoredBoundarySnapshot(
            snapshot: record.snapshot,
            model: record.model,
            messages: record.messages,
            resumeHint: record.resumeHint,
            acceleration: record.acceleration,
            promptTokens: record.promptTokens,
            blockTableID: record.blockTableID,
            blockTable: record.blockTable
        )
    }

    func restorePrefix(cacheKey: Melix_Worker_V1_CacheKey) -> (
        prefix: Melix_Worker_V1_PrefixRef,
        blockTableID: String,
        blockTable: Melix_Worker_V1_BlockTable,
        quantizedBytes: UInt64
    )? {
        pendingRestoreOperations += 1
        prefixRestoreLookups += 1
        defer { pendingRestoreOperations -= 1 }

        guard let prefixID = prefixIDByKey[diskCacheKeyIdentifier(cacheKey)],
              let record = prefixesByID[prefixID] else {
            return nil
        }

        prefixRestoreHits += 1
        return (
            prefix: record.prefix,
            blockTableID: record.blockTableID,
            blockTable: record.blockTable,
            quantizedBytes: record.quantizedBytes
        )
    }

    func tierMetrics() -> DiskCacheTierMetrics {
        let prefixHitRate = prefixRestoreLookups > 0
            ? Double(prefixRestoreHits) / Double(prefixRestoreLookups)
            : 0
        let snapshotHitRate = snapshotRestoreLookups > 0
            ? Double(snapshotRestoreHits) / Double(snapshotRestoreLookups)
            : 0

        return DiskCacheTierMetrics(
            l2HitRate: prefixHitRate,
            l2RestoreHitRate: snapshotHitRate,
            writeBackQueueDepth: pendingWriteBackOperations,
            restoreQueueDepth: pendingRestoreOperations,
            writeBackCount: completedWriteBackCount
        )
    }

    func summary() -> DiskCacheSummary {
        let prefixRecords = prefixesByID.values
        let l2Bytes = prefixRecords.reduce(UInt64(0)) { $0 + $1.quantizedBytes }
        let quantizedBytes = l2Bytes
        let unquantizedBytes = prefixRecords.reduce(UInt64(0)) { $0 + $1.unquantizedBytes }

        let groupedPrefixes = Dictionary(grouping: prefixRecords) { $0.prefix.scope.scopeID }
        let groupedSnapshots = Dictionary(grouping: snapshotsByID.values) { $0.blockTable.scopeID }

        let scopeIDs = Set(groupedPrefixes.keys).union(groupedSnapshots.keys).sorted()
        let scopeSummaries = scopeIDs.compactMap { scopeID -> DiskCacheScopeSummary? in
            let prefixGroup = groupedPrefixes[scopeID] ?? []
            let snapshotGroup = groupedSnapshots[scopeID] ?? []
            guard let firstPrefix = prefixGroup.first ?? snapshotGroup.first.flatMap({ snapshot in
                prefixesByID.values.first(where: { $0.blockTable.scopeID == snapshot.blockTable.scopeID })
            }) else {
                return nil
            }

            return DiskCacheScopeSummary(
                scope: firstPrefix.prefix.scope,
                l2Bytes: prefixGroup.reduce(UInt64(0)) { $0 + $1.quantizedBytes },
                snapshotCount: UInt64(snapshotGroup.count)
            )
        }

        let tierMetrics = tierMetrics()
        return DiskCacheSummary(
            l2Bytes: l2Bytes,
            quantizedBytes: quantizedBytes,
            unquantizedBytes: unquantizedBytes,
            snapshotCount: UInt64(snapshotsByID.count),
            l2HitRate: tierMetrics.l2HitRate,
            l2RestoreHitRate: tierMetrics.l2RestoreHitRate,
            writeBackQueueDepth: tierMetrics.writeBackQueueDepth,
            restoreQueueDepth: tierMetrics.restoreQueueDepth,
            writeBackCount: tierMetrics.writeBackCount,
            namespaceMismatchCount: namespaceMismatchCount,
            snapshots: snapshotsByID.values.map(\.snapshot).sorted { $0.snapshotID < $1.snapshotID },
            scopes: scopeSummaries
        )
    }

    func purge(
        scope: Melix_Worker_V1_CacheScope,
        cacheKey: Melix_Worker_V1_CacheKey,
        includePinned: Bool
    ) -> UInt64 {
        let matchingPrefixIDs = prefixesByID.values.compactMap { record -> String? in
            guard diskMatches(scope: scope, prefix: record.prefix),
                  diskMatches(cacheKey: cacheKey, prefix: record.prefix) else {
                return nil
            }
            if !includePinned && record.prefix.pinned {
                return nil
            }
            return record.prefix.prefixID
        }

        var purgedBlocks: UInt64 = 0
        for prefixID in matchingPrefixIDs {
            guard let removed = prefixesByID.removeValue(forKey: prefixID) else {
                continue
            }
            prefixIDByKey.removeValue(forKey: diskCacheKeyIdentifier(removed.prefix.cacheKey))
            purgedBlocks += UInt64(removed.blockTable.blocks.count)
            try? fileManager.removeItem(at: prefixFileURL(prefixID: prefixID))
        }

        let matchingSnapshotIDs = snapshotsByID.values.compactMap { snapshot -> String? in
            guard snapshotMatches(scope: scope, snapshot: snapshot) else {
                return nil
            }
            if !cacheKey.scopeID.isEmpty && snapshot.blockTable.cacheKey.scopeID != cacheKey.scopeID {
                return nil
            }
            if !(cacheKey.prefixHash.isEmpty && cacheKey.fingerprintHash.isEmpty) &&
                diskCacheKeyIdentifier(snapshot.blockTable.cacheKey) != diskCacheKeyIdentifier(cacheKey) {
                return nil
            }
            return snapshot.snapshot.snapshotID
        }

        for snapshotID in matchingSnapshotIDs {
            snapshotsByID.removeValue(forKey: snapshotID)
            try? fileManager.removeItem(at: snapshotFileURL(snapshotID: snapshotID))
        }

        return purgedBlocks
    }

    func purgeModel(modelID: String) {
        let prefixIDs = prefixesByID.values
            .filter { $0.prefix.scope.modelID == modelID }
            .map { $0.prefix.prefixID }
        for prefixID in prefixIDs {
            if let removed = prefixesByID.removeValue(forKey: prefixID) {
                prefixIDByKey.removeValue(forKey: diskCacheKeyIdentifier(removed.prefix.cacheKey))
            }
            try? fileManager.removeItem(at: prefixFileURL(prefixID: prefixID))
        }

        let snapshotIDs = snapshotsByID.values
            .filter { $0.model.modelID == modelID }
            .map { $0.snapshot.snapshotID }
        for snapshotID in snapshotIDs {
            snapshotsByID.removeValue(forKey: snapshotID)
            try? fileManager.removeItem(at: snapshotFileURL(snapshotID: snapshotID))
        }
    }

    func purgeScope(_ scope: Melix_Worker_V1_CacheScope) {
        let prefixIDs = prefixesByID.values
            .filter { diskMatches(scope: scope, prefix: $0.prefix) }
            .map { $0.prefix.prefixID }
        for prefixID in prefixIDs {
            if let removed = prefixesByID.removeValue(forKey: prefixID) {
                prefixIDByKey.removeValue(forKey: diskCacheKeyIdentifier(removed.prefix.cacheKey))
            }
            try? fileManager.removeItem(at: prefixFileURL(prefixID: prefixID))
        }

        let snapshotIDs = snapshotsByID.values
            .filter { snapshotMatches(scope: scope, snapshot: $0) }
            .map { $0.snapshot.snapshotID }
        for snapshotID in snapshotIDs {
            snapshotsByID.removeValue(forKey: snapshotID)
            try? fileManager.removeItem(at: snapshotFileURL(snapshotID: snapshotID))
        }
    }

    private func writePrefixRecord(_ record: StoredL2PrefixRecord) {
        guard let envelope = try? PersistedPrefixEnvelope(
            runtimeCacheFingerprint: runtimeCacheFingerprint,
            prefixID: record.prefix.prefixID,
            prefixData: record.prefix.serializedData(),
            blockTableID: record.blockTableID,
            blockTableData: record.blockTable.serializedData(),
            quantizedBytes: record.quantizedBytes,
            unquantizedBytes: record.unquantizedBytes
        ) else {
            return
        }

        guard let data = try? JSONEncoder().encode(envelope) else {
            return
        }
        try? data.write(to: prefixFileURL(prefixID: record.prefix.prefixID), options: [.atomic])
    }

    private func writeSnapshotRecord(_ record: StoredBoundarySnapshotRecord) {
        guard let envelope = try? PersistedSnapshotEnvelope(
            runtimeCacheFingerprint: runtimeCacheFingerprint,
            snapshotID: record.snapshot.snapshotID,
            snapshotData: record.snapshot.serializedData(),
            modelData: record.model.serializedData(),
            messagesData: try record.messages.map { try $0.serializedData() },
            resumeHint: record.resumeHint,
            accelerationData: record.acceleration.serializedData(),
            promptTokens: record.promptTokens,
            blockTableID: record.blockTableID,
            blockTableData: record.blockTable.serializedData()
        ) else {
            return
        }

        guard let data = try? JSONEncoder().encode(envelope) else {
            return
        }
        try? data.write(to: snapshotFileURL(snapshotID: record.snapshot.snapshotID), options: [.atomic])
    }

    private func prefixFileURL(prefixID: String) -> URL {
        prefixesURL.appendingPathComponent("\(safeFileComponent(prefixID)).json", isDirectory: false)
    }

    private func snapshotFileURL(snapshotID: String) -> URL {
        snapshotsURL.appendingPathComponent("\(safeFileComponent(snapshotID)).json", isDirectory: false)
    }

    private static func loadState(
        fileManager: FileManager,
        prefixesURL: URL,
        snapshotsURL: URL,
        runtimeCacheFingerprint: String
    ) -> (
        prefixes: [String: StoredL2PrefixRecord],
        snapshots: [String: StoredBoundarySnapshotRecord],
        namespaceMismatchCount: UInt64
    ) {
        ensureDirectory(fileManager: fileManager, url: prefixesURL)
        ensureDirectory(fileManager: fileManager, url: snapshotsURL)

        var prefixes: [String: StoredL2PrefixRecord] = [:]
        var snapshots: [String: StoredBoundarySnapshotRecord] = [:]
        var namespaceMismatchCount: UInt64 = 0

        if let contents = try? fileManager.contentsOfDirectory(at: prefixesURL, includingPropertiesForKeys: nil) {
            for fileURL in contents where fileURL.pathExtension == "json" {
                guard let data = try? Data(contentsOf: fileURL),
                      let envelope = try? JSONDecoder().decode(PersistedPrefixEnvelope.self, from: data) else {
                    continue
                }
                guard envelope.runtimeCacheFingerprint == runtimeCacheFingerprint else {
                    namespaceMismatchCount += 1
                    try? fileManager.removeItem(at: fileURL)
                    continue
                }
                guard let prefix = try? Melix_Worker_V1_PrefixRef(serializedBytes: envelope.prefixData),
                      let blockTable = try? Melix_Worker_V1_BlockTable(serializedBytes: envelope.blockTableData) else {
                    continue
                }
                prefixes[envelope.prefixID] = StoredL2PrefixRecord(
                    prefix: prefix,
                    blockTableID: envelope.blockTableID,
                    blockTable: normalizedBlockTable(blockTable),
                    quantizedBytes: envelope.quantizedBytes,
                    unquantizedBytes: envelope.unquantizedBytes
                )
            }
        }

        if let contents = try? fileManager.contentsOfDirectory(at: snapshotsURL, includingPropertiesForKeys: nil) {
            for fileURL in contents where fileURL.pathExtension == "json" {
                guard let data = try? Data(contentsOf: fileURL),
                      let envelope = try? JSONDecoder().decode(PersistedSnapshotEnvelope.self, from: data) else {
                    continue
                }
                guard envelope.runtimeCacheFingerprint == runtimeCacheFingerprint else {
                    namespaceMismatchCount += 1
                    try? fileManager.removeItem(at: fileURL)
                    continue
                }
                guard let snapshot = try? Melix_Worker_V1_SnapshotRef(serializedBytes: envelope.snapshotData),
                      let model = try? Melix_Worker_V1_ModelSpec(serializedBytes: envelope.modelData),
                      let acceleration = try? Melix_Worker_V1_AccelerationPolicy(serializedBytes: envelope.accelerationData),
                      let blockTable = try? Melix_Worker_V1_BlockTable(serializedBytes: envelope.blockTableData) else {
                    continue
                }

                let messages = envelope.messagesData.compactMap { try? Melix_Worker_V1_ChatMessage(serializedBytes: $0) }
                snapshots[envelope.snapshotID] = StoredBoundarySnapshotRecord(
                    snapshot: snapshot,
                    model: model,
                    messages: messages,
                    resumeHint: envelope.resumeHint,
                    acceleration: acceleration,
                    promptTokens: envelope.promptTokens,
                    blockTableID: envelope.blockTableID,
                    blockTable: normalizedBlockTable(blockTable)
                )
            }
        }

        return (prefixes, snapshots, namespaceMismatchCount)
    }

    private static func ensureDirectory(
        fileManager: FileManager,
        url: URL
    ) {
        try? fileManager.createDirectory(at: url, withIntermediateDirectories: true)
    }
}

private func safeFileComponent(_ raw: String) -> String {
    raw.replacingOccurrences(of: "/", with: "_")
}

func storageBoundaryQuantizedBytes(
    for table: Melix_Worker_V1_BlockTable,
    activeKVQuantizationRatio: Int
) -> UInt64 {
    let ratio = activeKVQuantizationRatio > 0 ? activeKVQuantizationRatio : 50
    let total = table.blocks.reduce(UInt64(0)) { $0 + $1.bytes }
    return UInt64((Double(total) * Double(max(1, min(100, ratio)))) / 100.0)
}

func activeKVQuantizationRatio(
    from acceleration: Melix_Worker_V1_AccelerationPolicy
) -> Int {
    if acceleration.mode == .activeKvQuantized {
        return ActiveKVQuantizationProfiles.quantizationRatioPercent(
            for: acceleration.activeKvQuantProfile
        )
    }
    return 0
}

private func diskMatches(
    scope: Melix_Worker_V1_CacheScope,
    prefix: Melix_Worker_V1_PrefixRef
) -> Bool {
    if scope.scopeID.isEmpty && scope.modelID.isEmpty {
        return true
    }
    if !scope.scopeID.isEmpty {
        return prefix.scope.scopeID == scope.scopeID
    }
    return prefix.scope.modelID == scope.modelID
}

private func snapshotMatches(
    scope: Melix_Worker_V1_CacheScope,
    snapshot: StoredBoundarySnapshotRecord
) -> Bool {
    if scope.scopeID.isEmpty && scope.modelID.isEmpty {
        return true
    }
    if !scope.scopeID.isEmpty {
        let snapshotScopeID = snapshot.blockTable.scopeID.isEmpty
            ? snapshot.blockTable.cacheKey.scopeID
            : snapshot.blockTable.scopeID
        return snapshotScopeID == scope.scopeID
    }
    return snapshot.model.modelID == scope.modelID
}

private func diskMatches(
    cacheKey: Melix_Worker_V1_CacheKey,
    prefix: Melix_Worker_V1_PrefixRef
) -> Bool {
    guard !(cacheKey.prefixHash.isEmpty && cacheKey.fingerprintHash.isEmpty && cacheKey.scopeID.isEmpty) else {
        return true
    }
    return diskCacheKeyIdentifier(cacheKey) == diskCacheKeyIdentifier(prefix.cacheKey)
}

private func diskCacheKeyIdentifier(_ key: Melix_Worker_V1_CacheKey) -> String {
    "\(key.scopeID)::\(Data(key.prefixHash).base64EncodedString())::\(Data(key.fingerprintHash).base64EncodedString())"
}
