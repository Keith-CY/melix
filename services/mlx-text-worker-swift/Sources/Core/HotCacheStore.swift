import CryptoKit
import Foundation
import MelixWorkerProtocol

struct HotCacheRegistration: Sendable {
    let prefix: Melix_Worker_V1_PrefixRef
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let cacheHit: Bool
}

struct HotCacheLogicalIdentity: Sendable {
    let scope: Melix_Worker_V1_CacheScope
    let cacheKey: Melix_Worker_V1_CacheKey
    let prefixID: String
}

struct CacheScopeIdentity: Hashable, Sendable {
    let components: [String]

    init(_ scope: Melix_Worker_V1_CacheScope) {
        self.components = cacheScopeIdentityComponents(scope)
    }
}

struct CacheLogicalPrefixKey: Hashable, Sendable {
    let scopeComponents: [String]
    let cacheScopeID: String
    let prefixHash: Data
    let fingerprintHash: Data

    init(scope: Melix_Worker_V1_CacheScope, cacheKey: Melix_Worker_V1_CacheKey) {
        self.scopeComponents = cacheScopeIdentityComponents(scope)
        self.cacheScopeID = cacheKey.scopeID
        self.prefixHash = cacheKey.prefixHash
        self.fingerprintHash = cacheKey.fingerprintHash
    }

    init(_ prefix: Melix_Worker_V1_PrefixRef) {
        self.init(scope: prefix.scope, cacheKey: prefix.cacheKey)
    }

    init(_ identity: HotCacheLogicalIdentity) {
        self.init(scope: identity.scope, cacheKey: identity.cacheKey)
    }

    var stableComponents: [String] {
        scopeComponents + [
            cacheScopeID,
            prefixHash.base64EncodedString(),
            fingerprintHash.base64EncodedString(),
        ]
    }

    var storageIdentifier: String {
        let encoded = stableComponents
            .map { "\($0.utf8.count):\($0)" }
            .joined(separator: "|")
        return SHA256.hash(data: Data(encoded.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }
}

func resolveHotCacheLogicalIdentity(
    execution: Melix_Worker_V1_ExecutionMetadata,
    model: Melix_Worker_V1_ModelSpec,
    messages: [Melix_Worker_V1_ChatMessage]
) throws -> HotCacheLogicalIdentity {
    let scope = resolveScope(execution.scope, fallback: model)
    let messageIdentity = cacheMessageIdentityData(from: messages)
    let cacheKey = resolveCacheKey(
        execution.cacheKey,
        scope: scope,
        messageIdentity: messageIdentity
    )
    return HotCacheLogicalIdentity(
        scope: scope,
        cacheKey: cacheKey,
        prefixID: makePrefixID(for: cacheKey)
    )
}

struct HotCacheOwnershipSnapshot: Sendable {
    let prefixCount: Int
    let pageCount: Int
    let blockCount: Int
    let pageIDsByPrefixID: [String: [String]]
    let blockIDsByPageID: [String: [String]]
    let pageRefCountByPageID: [String: UInt64]
    let blockRefCountByBlockID: [String: UInt64]
    let sharedPageCount: Int
    let sharedBlockCount: Int
    let copyOnWriteForkCount: UInt64
}

struct SavedBoundarySnapshot: Sendable {
    let snapshot: Melix_Worker_V1_SnapshotRef
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let copyOnWriteForked: Bool
}

struct HotCacheTierMetrics: Sendable {
    let l2HitRate: Double
    let l2RestoreHitRate: Double
    let l2WriteBackQueueDepth: UInt64
    let l2RestoreQueueDepth: UInt64
    let l2WriteBackCount: UInt64
}

/// Aggregate hit-taxonomy counters exposed for observability (milestone #40 phase 1).
///
/// Partial hits are recorded by `WorkerRuntimeRegistry` when a walked-back boundary
/// snapshot yields an aligned shorter prefix. Reconstruction failures are recorded
/// when a `restoreSnapshotID` was requested but no aligned restore plan could be built.
struct HotCacheHitTaxonomy: Sendable {
    let exactHitCount: UInt64
    let partialHitCount: UInt64
    let fallbackCount: UInt64
    let reconstructionFailureCount: UInt64
}

struct HotCachePurgeResult: Sendable {
    let metadataBlockCount: UInt64
    let diskBlockCount: UInt64

    var totalBlockCount: UInt64 {
        metadataBlockCount + diskBlockCount
    }
}

private struct StoredHotPrefix: Sendable {
    let logicalKey: CacheLogicalPrefixKey
    var prefix: Melix_Worker_V1_PrefixRef
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let pageIDs: [String]
    let blockIDs: [String]
    let quantizedBytes: UInt64
    var accessCount: UInt64
}

private struct StoredHotPageOwnership: Sendable {
    var page: Melix_Worker_V1_PageRef
    let scopeID: String
    var logicalPrefixKeys: Set<CacheLogicalPrefixKey>
    var blockTableIDs: Set<String>
    var referenceCount: UInt64
}

private struct StoredHotBlockOwnership: Sendable {
    let block: Melix_Worker_V1_BlockRef
    let scopeID: String
    var logicalPrefixKeys: Set<CacheLogicalPrefixKey>
    var pageIDs: Set<String>
    var referenceCount: UInt64
}

actor HotCacheStore {
    private let diskStore: DiskCacheStore
    private let cacheRootPath: String
    private let runtimeCacheFingerprint: String
    private let initialCacheBlocks: UInt32
    private var activeMode: Melix_Worker_V1_CacheMode
    private var prefixesByLogicalKey: [CacheLogicalPrefixKey: StoredHotPrefix] = [:]
    private var pagesByID: [String: StoredHotPageOwnership] = [:]
    private var blocksByID: [String: StoredHotBlockOwnership] = [:]
    private var totalLookups: UInt64 = 0
    private var totalHits: UInt64 = 0
    private var totalReusedBlocks: UInt64 = 0
    private var totalCopyOnWriteForks: UInt64 = 0
    private var totalExactHits: UInt64 = 0
    private var totalPartialHits: UInt64 = 0
    private var totalFallbacks: UInt64 = 0
    private var totalReconstructionFailures: UInt64 = 0

    init(
        diskStore: DiskCacheStore = DiskCacheStore(rootPath: ".runtime/swift-text-worker-cache"),
        cacheRootPath: String = ".runtime/swift-text-worker-cache",
        runtimeCacheFingerprint: String = "dev",
        initialCacheBlocks: UInt32 = 0
    ) {
        self.diskStore = diskStore
        self.cacheRootPath = cacheRootPath
        self.runtimeCacheFingerprint = runtimeCacheFingerprint
        self.initialCacheBlocks = initialCacheBlocks
        self.activeMode = .tiered
    }

    func setActiveMode(_ mode: Melix_Worker_V1_CacheMode) {
        activeMode = mode == .unspecified ? .tiered : mode
    }

    func registerPrefill(
        execution: Melix_Worker_V1_ExecutionMetadata,
        model: Melix_Worker_V1_ModelSpec,
        messages: [Melix_Worker_V1_ChatMessage],
        promptTokens: Int,
        decodeHandle: String,
        activeKVQuantizationRatio: Int,
        pagedCacheEvidence: RuntimePagedCacheEvidence? = nil,
        shouldAbort: @escaping @Sendable () -> Bool = { false }
    ) async throws -> HotCacheRegistration {
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let identity = try resolveHotCacheLogicalIdentity(
            execution: execution,
            model: model,
            messages: messages
        )
        let resolvedScope = identity.scope
        let resolvedKey = identity.cacheKey
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let logicalKey = CacheLogicalPrefixKey(identity)
        totalLookups += 1
        let runtimeBlocks = pagedCacheEvidence?.admitted == true
            ? pagedCacheEvidence?.blocks ?? []
            : []

        if var existing = prefixesByLogicalKey[logicalKey],
           pagedCacheEvidence?.admitted == true,
           pagedCacheEvidence?.cacheHitMode == "exact",
           existing.blockIDs == runtimeBlocks.map(\.blockID) {
            try throwIfTextRuntimeCancellationRequested(shouldAbort)
            recordRuntimeCacheEvidence(pagedCacheEvidence)
            existing.accessCount += 1
            if shouldPinPrefix(existing.prefix.prefixID, hints: execution.cacheHints) {
                existing.prefix.pinned = true
            }
            prefixesByLogicalKey[logicalKey] = existing
            return HotCacheRegistration(
                prefix: existing.prefix,
                blockTableID: existing.blockTableID,
                blockTable: existing.blockTable,
                cacheHit: true
            )
        }

        if let existing = prefixesByLogicalKey[logicalKey],
           pagedCacheEvidence?.admitted != true {
            recordRuntimeCacheEvidence(pagedCacheEvidence)
            let metadataTable = normalizedBlockTable(makeBlockTable(
                cacheKey: resolvedKey,
                scopeID: resolvedScope.scopeID,
                decodeHandle: decodeHandle,
                promptTokens: promptTokens,
                preferredBlockSize: execution.cacheHints.preferredBlockSize,
                initialCacheBlocks: initialCacheBlocks,
                runtimeBlocks: []
            ))
            return HotCacheRegistration(
                prefix: existing.prefix,
                blockTableID: "bt-\(decodeHandle)",
                blockTable: metadataTable,
                cacheHit: false
            )
        }

        recordRuntimeCacheEvidence(pagedCacheEvidence)
        let existing = prefixesByLogicalKey[logicalKey]
        let prefixID = existing?.prefix.prefixID ?? identity.prefixID
        let blockTableID = "bt-\(decodeHandle)"
        let blockTable = normalizedBlockTable(makeBlockTable(
            cacheKey: resolvedKey,
            scopeID: resolvedScope.scopeID,
            decodeHandle: decodeHandle,
            promptTokens: promptTokens,
            preferredBlockSize: execution.cacheHints.preferredBlockSize,
            initialCacheBlocks: initialCacheBlocks,
            runtimeBlocks: runtimeBlocks
        ))
        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        var prefix = Melix_Worker_V1_PrefixRef()
        prefix.prefixID = prefixID
        prefix.cacheKey = resolvedKey
        prefix.scope = resolvedScope
        prefix.tokenLength = UInt32(max(0, promptTokens))
        prefix.pinned = existing?.prefix.pinned == true
            || shouldPinPrefix(prefixID, hints: execution.cacheHints)
        prefix.tier = runtimeBlocks.isEmpty ? "metadata-only" : "l1"

        let stored = StoredHotPrefix(
            logicalKey: logicalKey,
            prefix: prefix,
            blockTableID: blockTableID,
            blockTable: blockTable,
            pageIDs: blockTable.pages.map(\.pageID),
            blockIDs: blockTable.blocks.map(\.blockID),
            quantizedBytes: quantizedBytes(
                for: blockTable,
                activeKVQuantizationRatio: activeKVQuantizationRatio
            ),
            accessCount: (existing?.accessCount ?? 0) + 1
        )

        if let existing {
            _ = unregisterOwnership(for: existing)
        }
        prefixesByLogicalKey[logicalKey] = stored
        registerOwnership(for: stored)
        if execution.cacheHints.allowL2 || execution.cacheHints.persistL2 {
            let l2QuantizedBytes = storageBoundaryQuantizedBytes(
                for: blockTable,
                activeKVQuantizationRatio: activeKVQuantizationRatio
            )
            try throwIfTextRuntimeCancellationRequested(shouldAbort)
            await diskStore.persistPrefix(
                prefix: prefix,
                blockTableID: blockTableID,
                blockTable: blockTable,
                quantizedBytes: l2QuantizedBytes
            )
            try throwIfTextRuntimeCancellationRequested(shouldAbort)
        }
        return HotCacheRegistration(
            prefix: prefix,
            blockTableID: blockTableID,
            blockTable: blockTable,
            cacheHit: (pagedCacheEvidence?.recoveredPrefixTokens ?? 0) > 0
        )
    }

    private func recordRuntimeCacheEvidence(_ evidence: RuntimePagedCacheEvidence?) {
        guard let evidence else {
            totalFallbacks += 1
            return
        }
        guard evidence.admitted else {
            totalFallbacks += 1
            return
        }
        guard evidence.recoveredPrefixTokens > 0 else { return }
        totalHits += 1
        totalReusedBlocks += UInt64(
            evidence.blocks.lazy.filter { $0.tokenEnd <= evidence.recoveredPrefixTokens }.count
        )
        if evidence.cacheHitMode == "exact" {
            totalExactHits += 1
        } else {
            totalPartialHits += 1
        }
    }

    func recordExactHit() {
        totalExactHits += 1
    }

    func recordPartialHit() {
        totalPartialHits += 1
    }

    func recordReconstructionFailure() {
        totalReconstructionFailures += 1
    }

    func hitTaxonomy() -> HotCacheHitTaxonomy {
        HotCacheHitTaxonomy(
            exactHitCount: totalExactHits,
            partialHitCount: totalPartialHits,
            fallbackCount: totalFallbacks,
            reconstructionFailureCount: totalReconstructionFailures
        )
    }

    func ownershipSnapshot() async -> HotCacheOwnershipSnapshot {
        let pageRefCountByPageID = Dictionary(
            uniqueKeysWithValues: pagesByID.map { key, value in
                (key, value.referenceCount)
            }
        )
        let blockRefCountByBlockID = Dictionary(
            uniqueKeysWithValues: blocksByID.map { key, value in
                (key, value.referenceCount)
            }
        )
        let pageIDsByPrefixID = Dictionary(
            grouping: prefixesByLogicalKey.values,
            by: { $0.prefix.prefixID }
        ).mapValues { entries in
            Array(Set(entries.flatMap(\.pageIDs))).sorted()
        }
        return HotCacheOwnershipSnapshot(
            prefixCount: prefixesByLogicalKey.count,
            pageCount: pagesByID.count,
            blockCount: blocksByID.count,
            pageIDsByPrefixID: pageIDsByPrefixID,
            blockIDsByPageID: Dictionary(
                uniqueKeysWithValues: pagesByID.map { key, value in
                    (key, value.page.blockIds.sorted())
                }
            ),
            pageRefCountByPageID: pageRefCountByPageID,
            blockRefCountByBlockID: blockRefCountByBlockID,
            sharedPageCount: pageRefCountByPageID.values.filter { $0 > 1 }.count,
            sharedBlockCount: blockRefCountByBlockID.values.filter { $0 > 1 }.count,
            copyOnWriteForkCount: totalCopyOnWriteForks
        )
    }

    func stats() async -> Melix_Worker_V1_CacheStats {
        await buildStats()
    }

    func snapshot() async -> Melix_Worker_V1_CacheSnapshot {
        await buildSnapshot()
    }

    func lookupPrefix(for identity: HotCacheLogicalIdentity) -> Melix_Worker_V1_PrefixRef? {
        prefixesByLogicalKey[CacheLogicalPrefixKey(identity)]?.prefix
    }

    func saveBoundarySnapshot(
        requestID: String,
        tokenBoundary: UInt32,
        model: Melix_Worker_V1_ModelSpec,
        prefill: StoredPrefillContext
    ) async -> SavedBoundarySnapshot {
        var snapshot = Melix_Worker_V1_SnapshotRef()
        snapshot.snapshotID = "snap-\(UUID().uuidString.lowercased())"
        snapshot.requestID = requestID
        snapshot.tokenBoundary = tokenBoundary
        snapshot.checkpointID = "\(prefill.decodeHandle)::tok::\(tokenBoundary)"

        if let prefix = prefill.prefix {
            snapshot.sessionID = prefix.scope.scopeID
        }
        snapshot.branchID = prefill.modelHandle

        let preparedSnapshot = prepareSnapshotPersistence(
            snapshotID: snapshot.snapshotID,
            blockTableID: prefill.blockTableID,
            blockTable: prefill.blockTable
        )

        await diskStore.saveSnapshot(
            snapshot: snapshot,
            model: model,
            execution: prefill.execution,
            messages: prefill.messages,
            resumeHint: prefill.resumeHint,
            acceleration: prefill.acceleration,
            promptTokens: prefill.promptTokens,
            blockTableID: preparedSnapshot.blockTableID,
            blockTable: preparedSnapshot.blockTable,
            prefix: prefill.prefix
        )
        return SavedBoundarySnapshot(
            snapshot: snapshot,
            blockTableID: preparedSnapshot.blockTableID,
            blockTable: preparedSnapshot.blockTable,
            copyOnWriteForked: preparedSnapshot.copyOnWriteForked
        )
    }

    func restoreBoundarySnapshot(snapshotID: String) async -> RestoredBoundarySnapshot? {
        await diskStore.restoreSnapshot(snapshotID: snapshotID)
    }

    func tierMetrics() async -> HotCacheTierMetrics {
        let metrics = await diskStore.tierMetrics()
        return HotCacheTierMetrics(
            l2HitRate: metrics.l2HitRate,
            l2RestoreHitRate: metrics.l2RestoreHitRate,
            l2WriteBackQueueDepth: metrics.writeBackQueueDepth,
            l2RestoreQueueDepth: metrics.restoreQueueDepth,
            l2WriteBackCount: metrics.writeBackCount
        )
    }

    private func buildSnapshot() async -> Melix_Worker_V1_CacheSnapshot {
        var snapshot = Melix_Worker_V1_CacheSnapshot()
        let diskSummary = await diskStore.summary()
        snapshot.stats = buildStats(diskSummary: diskSummary)

        let entries = prefixesByLogicalKey.values.sorted { lhs, rhs in
            if lhs.prefix.prefixID != rhs.prefix.prefixID {
                return lhs.prefix.prefixID < rhs.prefix.prefixID
            }
            return lhs.logicalKey.stableComponents.lexicographicallyPrecedes(rhs.logicalKey.stableComponents)
        }
        snapshot.hotPrefixes = entries.map(\.prefix)
        snapshot.pinnedPrefixes = entries.filter(\.prefix.pinned).map(\.prefix)
        snapshot.snapshots = diskSummary.snapshots
        snapshot.scopes = buildScopeSummaries(from: entries, diskSummary: diskSummary)
        return snapshot
    }

    func pinPrefix(_ prefix: Melix_Worker_V1_PrefixRef) -> Bool {
        updatePinState(for: prefix, pinned: true)
    }

    func unpinPrefix(_ prefix: Melix_Worker_V1_PrefixRef) -> Bool {
        updatePinState(for: prefix, pinned: false)
    }

    func purgeCache(
        scope: Melix_Worker_V1_CacheScope,
        cacheKey: Melix_Worker_V1_CacheKey,
        includePinned: Bool
    ) async -> UInt64 {
        (await purgeCacheDetailed(
            scope: scope,
            cacheKey: cacheKey,
            includePinned: includePinned
        )).totalBlockCount
    }

    func purgeCacheDetailed(
        scope: Melix_Worker_V1_CacheScope,
        cacheKey: Melix_Worker_V1_CacheKey,
        includePinned: Bool
    ) async -> HotCachePurgeResult {
        let targetsOneLogicalPrefix = !cacheKey.scopeID.isEmpty
            || !cacheKey.prefixHash.isEmpty
            || !cacheKey.fingerprintHash.isEmpty
        let requestedLogicalKey = CacheLogicalPrefixKey(scope: scope, cacheKey: cacheKey)
        let matchingKeys = prefixesByLogicalKey.compactMap { logicalKey, stored -> CacheLogicalPrefixKey? in
            let matchesRequest = targetsOneLogicalPrefix
                ? logicalKey == requestedLogicalKey
                : matches(scope: scope, prefix: stored.prefix)
            guard matchesRequest else { return nil }
            if !includePinned && stored.prefix.pinned {
                return nil
            }
            return logicalKey
        }

        var purgedBlocks: UInt64 = 0
        for logicalKey in matchingKeys {
            guard let removed = prefixesByLogicalKey.removeValue(forKey: logicalKey) else {
                continue
            }
            purgedBlocks += unregisterOwnership(for: removed)
        }
        let l2PurgedBlocks = await diskStore.purge(
            scope: scope,
            cacheKey: cacheKey,
            includePinned: includePinned
        )
        return HotCachePurgeResult(
            metadataBlockCount: purgedBlocks,
            diskBlockCount: l2PurgedBlocks
        )
    }

    func purgeModel(modelID: String) async {
        for logicalKey in prefixesByLogicalKey.values
            .filter({ $0.prefix.scope.modelID == modelID })
            .map(\.logicalKey) {
            guard let removed = prefixesByLogicalKey.removeValue(forKey: logicalKey) else {
                continue
            }
            _ = unregisterOwnership(for: removed)
        }
        await diskStore.purgeModel(modelID: modelID)
    }

    func purgeScope(_ scope: Melix_Worker_V1_CacheScope) async {
        for logicalKey in prefixesByLogicalKey.values
            .filter({ matches(scope: scope, prefix: $0.prefix) })
            .map(\.logicalKey) {
            guard let removed = prefixesByLogicalKey.removeValue(forKey: logicalKey) else {
                continue
            }
            _ = unregisterOwnership(for: removed)
        }
        await diskStore.purgeScope(scope)
    }

    private func updatePinState(
        for request: Melix_Worker_V1_PrefixRef,
        pinned: Bool
    ) -> Bool {
        let hasLogicalIdentity = !request.scope.scopeID.isEmpty
            || !request.scope.modelID.isEmpty
            || !request.cacheKey.scopeID.isEmpty
            || !request.cacheKey.prefixHash.isEmpty
            || !request.cacheKey.fingerprintHash.isEmpty
        guard hasLogicalIdentity else { return false }
        let logicalKey = CacheLogicalPrefixKey(request)
        guard var stored = prefixesByLogicalKey[logicalKey],
              request.prefixID.isEmpty || request.prefixID == stored.prefix.prefixID else {
            return false
        }
        stored.prefix.pinned = pinned
        prefixesByLogicalKey[logicalKey] = stored
        return true
    }

    private func buildStats(
        diskSummary: DiskCacheSummary
    ) -> Melix_Worker_V1_CacheStats {
        let entries = prefixesByLogicalKey.values
        let l1Bytes = blocksByID.values.reduce(UInt64(0)) { $0 + $1.block.bytes }
        let l1QuantizedBytes = entries.reduce(UInt64(0)) { $0 + $1.quantizedBytes }
        let quantizedBytes = l1QuantizedBytes + diskSummary.quantizedBytes
        let totalUnquantizedBytes = l1Bytes + diskSummary.unquantizedBytes

        var stats = Melix_Worker_V1_CacheStats()
        stats.l1Bytes = l1Bytes
        stats.l2Bytes = diskSummary.l2Bytes
        stats.blockCount = UInt64(blocksByID.count)
        stats.pinnedPrefixCount = UInt64(entries.filter(\.prefix.pinned).count)
        stats.snapshotCount = diskSummary.snapshotCount
        stats.l1HitRate = totalLookups > 0 ? Double(totalHits) / Double(totalLookups) : 0
        stats.l2HitRate = diskSummary.l2HitRate
        let logicalL1Bytes = entries.reduce(UInt64(0)) { total, entry in
            total + entry.blockTable.blocks.reduce(UInt64(0)) { $0 + $1.bytes }
        }
        stats.dedupRatio = l1Bytes > 0 ? Double(logicalL1Bytes) / Double(l1Bytes) : 0
        stats.quantizedBytes = quantizedBytes
        stats.compressionRatio = quantizedBytes > 0 ? Double(totalUnquantizedBytes) / Double(quantizedBytes) : 0
        stats.l2RestoreHitRate = diskSummary.l2RestoreHitRate
        stats.activeMode = activeMode
        stats.cacheRoot = cacheRootPath
        stats.initialCacheBlocks = initialCacheBlocks
        stats.supportedModes = CacheModePolicy.supportedModes
        stats.experimentalModes = CacheModePolicy.experimentalModes
        stats.supportsPrefixCache = true
        stats.supportsPagedCache = false
        stats.supportsDiskCache = false
        stats.supportsBoundarySnapshots = false
        stats.runtimeCacheFingerprint = runtimeCacheFingerprint
        stats.cacheNamespaceMismatchCount = diskSummary.namespaceMismatchCount
        return stats
    }

    private func buildStats() async -> Melix_Worker_V1_CacheStats {
        let diskSummary = await diskStore.summary()
        return buildStats(diskSummary: diskSummary)
    }

    private func buildScopeSummaries(
        from entries: [StoredHotPrefix],
        diskSummary: DiskCacheSummary
    ) -> [Melix_Worker_V1_CacheScopeSummary] {
        let groups = Dictionary(grouping: entries) { entry in
            CacheScopeIdentity(entry.prefix.scope)
        }
        let diskScopes = Dictionary(grouping: diskSummary.scopes) {
            CacheScopeIdentity($0.scope)
        }
        let scopeIdentities = Set(groups.keys).union(diskScopes.keys).sorted {
            $0.components.lexicographicallyPrecedes($1.components)
        }

        return scopeIdentities.compactMap { scopeIdentity in
            let group = groups[scopeIdentity] ?? []
            let diskGroup = diskScopes[scopeIdentity] ?? []
            guard let scope = group.first?.prefix.scope ?? diskGroup.first?.scope else {
                return nil
            }

            var summary = Melix_Worker_V1_CacheScopeSummary()
            summary.scopeID = scope.scopeID
            summary.scope = scope
            let scopeBlocks = blocksByID.values
                .filter { ownership in
                    ownership.logicalPrefixKeys.contains {
                        $0.scopeComponents == scopeIdentity.components
                    }
                }
                .map(\.block)
                .sorted { $0.blockID < $1.blockID }
            summary.l1Bytes = scopeBlocks.reduce(UInt64(0)) { $0 + $1.bytes }
            summary.l2Bytes = diskGroup.reduce(UInt64(0)) { $0 + $1.l2Bytes }
            summary.blockCount = UInt64(scopeBlocks.count)
            summary.prefixCount = UInt64(group.count)
            summary.snapshotCount = diskGroup.reduce(UInt64(0)) { $0 + $1.snapshotCount }
            summary.hotBlocks = scopeBlocks
            return summary
        }
    }

    private func registerOwnership(for stored: StoredHotPrefix) {
        let scopeID = stored.blockTable.scopeID.isEmpty ? stored.prefix.scope.scopeID : stored.blockTable.scopeID
        let pageIDByBlockID = Dictionary(
            uniqueKeysWithValues: stored.blockTable.pages.flatMap { page in
                page.blockIds.map { ($0, page.pageID) }
            }
        )

        for page in stored.blockTable.pages {
            var ownership = pagesByID[page.pageID] ?? StoredHotPageOwnership(
                page: page,
                scopeID: scopeID,
                logicalPrefixKeys: [],
                blockTableIDs: [],
                referenceCount: 0
            )
            ownership.page = page
            ownership.logicalPrefixKeys.insert(stored.logicalKey)
            ownership.blockTableIDs.insert(stored.blockTableID)
            ownership.referenceCount = UInt64(ownership.logicalPrefixKeys.count)
            pagesByID[page.pageID] = ownership
        }

        for block in stored.blockTable.blocks {
            var ownership = blocksByID[block.blockID] ?? StoredHotBlockOwnership(
                block: block,
                scopeID: scopeID,
                logicalPrefixKeys: [],
                pageIDs: [],
                referenceCount: 0
            )
            ownership.logicalPrefixKeys.insert(stored.logicalKey)
            if let pageID = pageIDByBlockID[block.blockID] {
                ownership.pageIDs.insert(pageID)
            }
            ownership.referenceCount = UInt64(ownership.logicalPrefixKeys.count)
            blocksByID[block.blockID] = ownership
        }
    }

    @discardableResult
    private func unregisterOwnership(for stored: StoredHotPrefix) -> UInt64 {
        var removedBlocks: UInt64 = 0

        for pageID in stored.pageIDs {
            guard var ownership = pagesByID[pageID] else {
                continue
            }
            ownership.logicalPrefixKeys.remove(stored.logicalKey)
            ownership.blockTableIDs.remove(stored.blockTableID)
            if ownership.logicalPrefixKeys.isEmpty {
                pagesByID.removeValue(forKey: pageID)
            } else {
                ownership.referenceCount = UInt64(ownership.logicalPrefixKeys.count)
                pagesByID[pageID] = ownership
            }
        }

        for blockID in stored.blockIDs {
            guard var ownership = blocksByID[blockID] else {
                continue
            }
            ownership.logicalPrefixKeys.remove(stored.logicalKey)
            if ownership.logicalPrefixKeys.isEmpty {
                blocksByID.removeValue(forKey: blockID)
                removedBlocks += 1
            } else {
                ownership.referenceCount = UInt64(ownership.logicalPrefixKeys.count)
                blocksByID[blockID] = ownership
            }
        }

        return removedBlocks
    }

    private func prepareSnapshotPersistence(
        snapshotID: String,
        blockTableID: String,
        blockTable: Melix_Worker_V1_BlockTable
    ) -> (blockTableID: String, blockTable: Melix_Worker_V1_BlockTable, copyOnWriteForked: Bool) {
        let normalizedTable = normalizedBlockTable(blockTable)
        guard shouldForkForSnapshotPersistence(normalizedTable) else {
            return (blockTableID, normalizedTable, false)
        }

        let forkTag = "cow-\(snapshotID)"
        let cloned = copyOnWriteForkedBlockTable(normalizedTable, forkTag: forkTag)
        totalCopyOnWriteForks += 1
        return ("\(blockTableID)::\(forkTag)", cloned, true)
    }

    private func shouldForkForSnapshotPersistence(
        _ blockTable: Melix_Worker_V1_BlockTable
    ) -> Bool {
        for page in blockTable.pages {
            if let ownership = pagesByID[page.pageID], ownership.referenceCount > 1 {
                return true
            }
        }

        for block in blockTable.blocks {
            if let ownership = blocksByID[block.blockID], ownership.referenceCount > 1 {
                return true
            }
        }

        return false
    }

    private func copyOnWriteForkedBlockTable(
        _ blockTable: Melix_Worker_V1_BlockTable,
        forkTag: String
    ) -> Melix_Worker_V1_BlockTable {
        let blockIDMap = Dictionary(
            uniqueKeysWithValues: blockTable.blocks.map { block in
                (block.blockID, "\(block.blockID)::\(forkTag)")
            }
        )

        var cloned = blockTable
        cloned.blocks = blockTable.blocks.map { block in
            var clonedBlock = block
            clonedBlock.blockID = blockIDMap[block.blockID] ?? "\(block.blockID)::\(forkTag)"
            return clonedBlock
        }
        cloned.pages = blockTable.pages.map { page in
            var clonedPage = page
            clonedPage.pageID = "\(page.pageID)::\(forkTag)"
            clonedPage.blockIds = page.blockIds.map { blockID in
                blockIDMap[blockID] ?? "\(blockID)::\(forkTag)"
            }
            return clonedPage
        }
        return cloned
    }
}

private func resolveScope(
    _ requested: Melix_Worker_V1_CacheScope,
    fallback model: Melix_Worker_V1_ModelSpec
) -> Melix_Worker_V1_CacheScope {
    var scope = requested
    if scope.modelID.isEmpty {
        scope.modelID = model.modelID
    }
    if scope.revision.isEmpty {
        scope.revision = model.revision
    }
    if scope.tokenizerHash.isEmpty {
        scope.tokenizerHash = model.tokenizerHash
    }
    if scope.quantProfileID.isEmpty {
        scope.quantProfileID = model.quantProfileID
    }
    if scope.parserMode.isEmpty {
        scope.parserMode = model.parserMode
    }
    if scope.reasoningMode.isEmpty {
        scope.reasoningMode = model.reasoningMode
    }
    if scope.multimodalAdapterHash.isEmpty {
        scope.multimodalAdapterHash = cacheAdapterSetHash(from: model)
    }
    if scope.scopeID.isEmpty {
        scope.scopeID = makeCacheScopeID(scope)
    }
    return scope
}

private func resolveCacheKey(
    _ requested: Melix_Worker_V1_CacheKey,
    scope: Melix_Worker_V1_CacheScope,
    messageIdentity: Data
) -> Melix_Worker_V1_CacheKey {
    var key = requested
    if key.prefixHash.isEmpty {
        let scopeIdentity = cacheIdentityData(
            cacheScopeIdentityComponents(scope).map { Data($0.utf8) }
        )
        key.prefixHash = Data(SHA256.hash(data: cacheIdentityData([
            Data("melix-cache-prefix-v2".utf8),
            scopeIdentity,
            messageIdentity,
        ])))
    }
    if key.fingerprintHash.isEmpty {
        key.fingerprintHash = Data(SHA256.hash(data: messageIdentity))
    }
    if key.scopeID.isEmpty {
        key.scopeID = scope.scopeID
    }
    return key
}

private func cacheMessageIdentityData(
    from messages: [Melix_Worker_V1_ChatMessage]
) -> Data {
    var fields = [
        Data("melix-cache-messages-v2".utf8),
        Data(String(messages.count).utf8),
    ]
    fields.append(contentsOf: messages.map { message in
        cacheIdentityData([
            Data(message.role.utf8),
            Data(message.name.utf8),
            Data(String(message.parts.count).utf8),
            cacheIdentityData(message.parts.map(cacheMessagePartIdentityData)),
        ])
    })
    return cacheIdentityData(fields)
}

private func cacheMessagePartIdentityData(
    _ part: Melix_Worker_V1_MessagePart
) -> Data {
    let kind: String
    let value: Data
    switch part.part {
    case .text(let text):
        kind = "text"
        value = Data(text.utf8)
    case .imageUri(let uri):
        kind = "image-uri"
        value = Data(uri.utf8)
    case .imageBytes(let bytes):
        kind = "image-bytes-sha256"
        value = Data(SHA256.hash(data: bytes))
    case .audioUri(let uri):
        kind = "audio-uri"
        value = Data(uri.utf8)
    case .audioBytes(let bytes):
        kind = "audio-bytes-sha256"
        value = Data(SHA256.hash(data: bytes))
    case .videoUri(let uri):
        kind = "video-uri"
        value = Data(uri.utf8)
    case .videoBytes(let bytes):
        kind = "video-bytes-sha256"
        value = Data(SHA256.hash(data: bytes))
    case nil:
        kind = "none"
        value = Data()
    }

    let metadata = part.media
    let preprocessingHints = metadata.preprocessingHints
        .sorted { $0.key < $1.key }
        .flatMap { [Data($0.key.utf8), Data($0.value.utf8)] }
    return cacheIdentityData([
        Data(kind.utf8),
        value,
        Data(String(metadata.mediaType.rawValue).utf8),
        Data(String(metadata.sourceKind.rawValue).utf8),
        Data(metadata.mimeType.utf8),
        Data(metadata.format.utf8),
        Data(metadata.filename.utf8),
        Data(String(metadata.byteLength).utf8),
        Data(String(metadata.durationMs).utf8),
        Data(String(metadata.width).utf8),
        Data(String(metadata.height).utf8),
        cacheIdentityData(preprocessingHints),
        Data(String(metadata.frameBudget).utf8),
        Data(String(metadata.startMs).utf8),
        Data(String(metadata.endMs).utf8),
    ])
}

private func cacheIdentityData(_ fields: [Data]) -> Data {
    var result = Data()
    for field in fields {
        var length = UInt64(field.count).bigEndian
        withUnsafeBytes(of: &length) { result.append(contentsOf: $0) }
        result.append(field)
    }
    return result
}

private func makeBlockTable(
    cacheKey: Melix_Worker_V1_CacheKey,
    scopeID: String,
    decodeHandle: String,
    promptTokens: Int,
    preferredBlockSize: UInt32,
    initialCacheBlocks: UInt32,
    runtimeBlocks: [RuntimeKVBlockDescriptor] = []
) -> Melix_Worker_V1_BlockTable {
    let tokenCount = max(promptTokens, 1)
    if !runtimeBlocks.isEmpty {
        let blocks = runtimeBlocks.map { descriptor in
            var block = Melix_Worker_V1_BlockRef()
            block.blockID = descriptor.blockID
            block.tokenStart = Int32(clamping: descriptor.tokenStart)
            block.tokenEnd = Int32(clamping: descriptor.tokenEnd)
            block.bytes = descriptor.bytes
            return block
        }
        var table = Melix_Worker_V1_BlockTable()
        table.blocks = blocks
        table.cacheKey = cacheKey
        table.scopeID = scopeID
        table.pages = makePageRefs(from: blocks)
        table.totalTokenCount = UInt32(clamping: runtimeBlocks.map(\.tokenEnd).max() ?? 0)
        return table
    }

    let blockSize: Int
    if preferredBlockSize > 0 {
        blockSize = max(Int(preferredBlockSize), 16)
    } else if initialCacheBlocks > 0 {
        let targetBlocks = max(Int(initialCacheBlocks), 1)
        let suggestedBlockSize = Int(ceil(Double(tokenCount) / Double(targetBlocks)))
        blockSize = max(suggestedBlockSize, 16)
    } else {
        blockSize = 16
    }

    var blocks: [Melix_Worker_V1_BlockRef] = []
    if initialCacheBlocks > 0 {
        blocks.reserveCapacity(Int(initialCacheBlocks))
    }
    var start = 0
    var index = 0
    while start < tokenCount {
        let end = min(tokenCount, start + blockSize)
        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "\(decodeHandle)::blk::\(index)"
        block.tokenStart = Int32(start)
        block.tokenEnd = Int32(end)
        block.bytes = 0
        blocks.append(block)
        start = end
        index += 1
    }

    var table = Melix_Worker_V1_BlockTable()
    table.blocks = blocks
    table.cacheKey = cacheKey
    table.scopeID = scopeID
    table.pages = makePageRefs(from: blocks)
    table.totalTokenCount = UInt32(tokenCount)
    return table
}

private func quantizedBytes(
    for table: Melix_Worker_V1_BlockTable,
    activeKVQuantizationRatio: Int
) -> UInt64 {
    let ratio = max(0, min(100, activeKVQuantizationRatio))
    guard ratio > 0 else {
        return 0
    }

    let total = table.blocks.reduce(UInt64(0)) { $0 + $1.bytes }
    return UInt64((Double(total) * Double(ratio)) / 100.0)
}

private func shouldPinPrefix(
    _ prefixID: String,
    hints: Melix_Worker_V1_CacheHints
) -> Bool {
    hints.pinPrefixIds.contains(prefixID)
}

func makeCacheScopeID(_ scope: Melix_Worker_V1_CacheScope) -> String {
    let encoded = cacheScopeSemanticComponents(scope)
        .map { "\($0.utf8.count):\($0)" }
        .joined(separator: "|")
    return "scope-\(SHA256.hash(data: Data(encoded.utf8)).map { String(format: "%02x", $0) }.joined())"
}

func cacheScopeIdentityComponents(_ scope: Melix_Worker_V1_CacheScope) -> [String] {
    [scope.scopeID] + cacheScopeSemanticComponents(scope)
}

private func cacheScopeSemanticComponents(_ scope: Melix_Worker_V1_CacheScope) -> [String] {
    [
        scope.modelID,
        scope.revision,
        scope.tokenizerHash,
        scope.quantProfileID,
        scope.promptTemplateHash,
        scope.parserMode,
        scope.reasoningMode,
        scope.multimodalAdapterHash,
        scope.reasoningEffort,
        scope.toolParserMode,
        scope.structuredOutputMode,
        scope.chatTemplateKwargsHash,
        String(scope.reasoningContinuityPresent),
    ]
}

private func cacheAdapterSetHash(from model: Melix_Worker_V1_ModelSpec) -> String {
    if let explicit = model.ext["melix.adapter_set_hash"], !explicit.isEmpty {
        return explicit
    }
    if let legacy = model.ext["adapter_set_hash"], !legacy.isEmpty {
        return legacy
    }
    return ""
}

func makePrefixID(for key: Melix_Worker_V1_CacheKey) -> String {
    "pfx-\(shortHex(key.prefixHash))"
}

private func shortHex(_ data: Data) -> String {
    data.prefix(8).map { String(format: "%02x", $0) }.joined()
}

private func matches(
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
