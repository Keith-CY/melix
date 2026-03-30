import CryptoKit
import Foundation
import MelixWorkerProtocol

struct HotCacheRegistration: Sendable {
    let prefix: Melix_Worker_V1_PrefixRef
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let cacheHit: Bool
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

private struct StoredHotPrefix: Sendable {
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
    var prefixIDs: Set<String>
    var blockTableIDs: Set<String>
    var referenceCount: UInt64
}

private struct StoredHotBlockOwnership: Sendable {
    let block: Melix_Worker_V1_BlockRef
    let scopeID: String
    var prefixIDs: Set<String>
    var pageIDs: Set<String>
    var referenceCount: UInt64
}

actor HotCacheStore {
    private let diskStore: DiskCacheStore
    private let initialCacheBlocks: UInt32
    private var prefixesByID: [String: StoredHotPrefix] = [:]
    private var prefixIDByKey: [String: String] = [:]
    private var pagesByID: [String: StoredHotPageOwnership] = [:]
    private var blocksByID: [String: StoredHotBlockOwnership] = [:]
    private var totalLookups: UInt64 = 0
    private var totalHits: UInt64 = 0
    private var totalReusedBlocks: UInt64 = 0
    private var totalCopyOnWriteForks: UInt64 = 0

    init(
        diskStore: DiskCacheStore = DiskCacheStore(rootPath: ".runtime/swift-text-worker-cache"),
        initialCacheBlocks: UInt32 = 0
    ) {
        self.diskStore = diskStore
        self.initialCacheBlocks = initialCacheBlocks
    }

    func registerPrefill(
        execution: Melix_Worker_V1_ExecutionMetadata,
        model: Melix_Worker_V1_ModelSpec,
        messages: [Melix_Worker_V1_ChatMessage],
        promptTokens: Int,
        decodeHandle: String,
        activeKVQuantizationRatio: Int
    ) async throws -> HotCacheRegistration {
        let resolvedScope = resolveScope(execution.scope, fallback: model)
        let renderedPrompt = try renderPrompt(from: messages)
        let resolvedKey = resolveCacheKey(
            execution.cacheKey,
            scope: resolvedScope,
            prompt: renderedPrompt
        )
        let keyID = cacheKeyIdentifier(resolvedKey)
        totalLookups += 1

        if let existingID = prefixIDByKey[keyID], var existing = prefixesByID[existingID] {
            totalHits += 1
            totalReusedBlocks += UInt64(existing.blockIDs.count)
            existing.accessCount += 1
            if shouldPinPrefix(existing.prefix.prefixID, hints: execution.cacheHints) {
                existing.prefix.pinned = true
            }
            prefixesByID[existingID] = existing
            return HotCacheRegistration(
                prefix: existing.prefix,
                blockTableID: existing.blockTableID,
                blockTable: existing.blockTable,
                cacheHit: true
            )
        }

        let prefixID = makePrefixID(for: resolvedKey)
        let blockTableID = "bt-\(decodeHandle)"
        let blockTable = normalizedBlockTable(makeBlockTable(
            cacheKey: resolvedKey,
            scopeID: resolvedScope.scopeID,
            decodeHandle: decodeHandle,
            promptTokens: promptTokens,
            preferredBlockSize: execution.cacheHints.preferredBlockSize,
            initialCacheBlocks: initialCacheBlocks
        ))

        var prefix = Melix_Worker_V1_PrefixRef()
        prefix.prefixID = prefixID
        prefix.cacheKey = resolvedKey
        prefix.scope = resolvedScope
        prefix.tokenLength = UInt32(max(0, promptTokens))
        prefix.pinned = shouldPinPrefix(prefixID, hints: execution.cacheHints)
        prefix.tier = "l1"

        let stored = StoredHotPrefix(
            prefix: prefix,
            blockTableID: blockTableID,
            blockTable: blockTable,
            pageIDs: blockTable.pages.map(\.pageID),
            blockIDs: blockTable.blocks.map(\.blockID),
            quantizedBytes: quantizedBytes(
                for: blockTable,
                activeKVQuantizationRatio: activeKVQuantizationRatio
            ),
            accessCount: 1
        )

        prefixesByID[prefixID] = stored
        prefixIDByKey[keyID] = prefixID
        registerOwnership(for: stored)
        if execution.cacheHints.allowL2 || execution.cacheHints.persistL2 {
            let l2QuantizedBytes = storageBoundaryQuantizedBytes(
                for: blockTable,
                activeKVQuantizationRatio: activeKVQuantizationRatio
            )
            await diskStore.persistPrefix(
                prefix: prefix,
                blockTableID: blockTableID,
                blockTable: blockTable,
                quantizedBytes: l2QuantizedBytes
            )
        }
        return HotCacheRegistration(
            prefix: prefix,
            blockTableID: blockTableID,
            blockTable: blockTable,
            cacheHit: false
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
        return HotCacheOwnershipSnapshot(
            prefixCount: prefixesByID.count,
            pageCount: pagesByID.count,
            blockCount: blocksByID.count,
            pageIDsByPrefixID: Dictionary(
                uniqueKeysWithValues: prefixesByID.map { key, value in
                    (key, value.pageIDs.sorted())
                }
            ),
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

    func lookupPrefix(for cacheKey: Melix_Worker_V1_CacheKey) -> Melix_Worker_V1_PrefixRef? {
        if let prefixID = prefixIDByKey[cacheKeyIdentifier(cacheKey)] {
            return prefixesByID[prefixID]?.prefix
        }
        return nil
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

    private func buildSnapshot() async -> Melix_Worker_V1_CacheSnapshot {
        var snapshot = Melix_Worker_V1_CacheSnapshot()
        let diskSummary = await diskStore.summary()
        snapshot.stats = buildStats(diskSummary: diskSummary)

        let entries = prefixesByID.values.sorted { $0.prefix.prefixID < $1.prefix.prefixID }
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
        let allEntries = prefixesByID.values.map(\.prefix)
        let matchingIDs = allEntries.compactMap { prefix -> String? in
            guard matches(scope: scope, prefix: prefix), matches(cacheKey: cacheKey, prefix: prefix) else {
                return nil
            }
            if !includePinned && prefix.pinned {
                return nil
            }
            return prefix.prefixID
        }

        var purgedBlocks: UInt64 = 0
        for prefixID in matchingIDs {
            guard let removed = prefixesByID.removeValue(forKey: prefixID) else {
                continue
            }
            prefixIDByKey.removeValue(forKey: cacheKeyIdentifier(removed.prefix.cacheKey))
            purgedBlocks += unregisterOwnership(for: removed)
        }
        let l2PurgedBlocks = await diskStore.purge(
            scope: scope,
            cacheKey: cacheKey,
            includePinned: includePinned
        )
        return purgedBlocks + l2PurgedBlocks
    }

    func purgeModel(modelID: String) async {
        for prefixID in prefixesByID.values
            .filter({ $0.prefix.scope.modelID == modelID })
            .map(\.prefix.prefixID) {
            guard let removed = prefixesByID.removeValue(forKey: prefixID) else {
                continue
            }
            prefixIDByKey.removeValue(forKey: cacheKeyIdentifier(removed.prefix.cacheKey))
            _ = unregisterOwnership(for: removed)
        }
        await diskStore.purgeModel(modelID: modelID)
    }

    func purgeScope(_ scope: Melix_Worker_V1_CacheScope) async {
        for prefixID in prefixesByID.values
            .filter({ matches(scope: scope, prefix: $0.prefix) })
            .map(\.prefix.prefixID) {
            guard let removed = prefixesByID.removeValue(forKey: prefixID) else {
                continue
            }
            prefixIDByKey.removeValue(forKey: cacheKeyIdentifier(removed.prefix.cacheKey))
            _ = unregisterOwnership(for: removed)
        }
        await diskStore.purgeScope(scope)
    }

    private func updatePinState(
        for request: Melix_Worker_V1_PrefixRef,
        pinned: Bool
    ) -> Bool {
        if !request.prefixID.isEmpty, var stored = prefixesByID[request.prefixID] {
            stored.prefix.pinned = pinned
            prefixesByID[request.prefixID] = stored
            return true
        }

        guard let prefixID = prefixIDByKey[cacheKeyIdentifier(request.cacheKey)],
              var stored = prefixesByID[prefixID] else {
            return false
        }
        stored.prefix.pinned = pinned
        prefixesByID[prefixID] = stored
        return true
    }

    private func buildStats(
        diskSummary: DiskCacheSummary
    ) -> Melix_Worker_V1_CacheStats {
        let entries = prefixesByID.values
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
        stats.dedupRatio = entries.isEmpty ? 0 : Double(totalLookups) / Double(entries.count)
        stats.quantizedBytes = quantizedBytes
        stats.compressionRatio = quantizedBytes > 0 ? Double(totalUnquantizedBytes) / Double(quantizedBytes) : 0
        stats.l2RestoreHitRate = diskSummary.l2RestoreHitRate
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
            entry.prefix.scope.scopeID
        }

        let diskScopes = Dictionary(uniqueKeysWithValues: diskSummary.scopes.map { ($0.scope.scopeID, $0) })
        let scopeIDs = Set(groups.keys).union(diskScopes.keys).sorted()

        return scopeIDs.compactMap { scopeID in
            let group = groups[scopeID] ?? []
            let diskScope = diskScopes[scopeID]
            guard let first = group.first ?? diskScope.map({ scope in
                var synthetic = StoredHotPrefix(
                    prefix: Melix_Worker_V1_PrefixRef(),
                    blockTableID: "",
                    blockTable: Melix_Worker_V1_BlockTable(),
                    pageIDs: [],
                    blockIDs: [],
                    quantizedBytes: 0,
                    accessCount: 0
                )
                synthetic.prefix.scope = scope.scope
                return synthetic
            }) else {
                return nil
            }

            var summary = Melix_Worker_V1_CacheScopeSummary()
            summary.scopeID = scopeID
            summary.scope = first.prefix.scope
            let scopeBlocks = blocksByID.values
                .filter { $0.scopeID == scopeID }
                .map(\.block)
                .sorted { $0.blockID < $1.blockID }
            summary.l1Bytes = scopeBlocks.reduce(UInt64(0)) { $0 + $1.bytes }
            summary.l2Bytes = diskScope?.l2Bytes ?? 0
            summary.blockCount = UInt64(scopeBlocks.count)
            summary.prefixCount = UInt64(group.count)
            summary.snapshotCount = diskScope?.snapshotCount ?? 0
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
                prefixIDs: [],
                blockTableIDs: [],
                referenceCount: 0
            )
            ownership.page = page
            ownership.prefixIDs.insert(stored.prefix.prefixID)
            ownership.blockTableIDs.insert(stored.blockTableID)
            ownership.referenceCount = UInt64(ownership.prefixIDs.count)
            pagesByID[page.pageID] = ownership
        }

        for block in stored.blockTable.blocks {
            var ownership = blocksByID[block.blockID] ?? StoredHotBlockOwnership(
                block: block,
                scopeID: scopeID,
                prefixIDs: [],
                pageIDs: [],
                referenceCount: 0
            )
            ownership.prefixIDs.insert(stored.prefix.prefixID)
            if let pageID = pageIDByBlockID[block.blockID] {
                ownership.pageIDs.insert(pageID)
            }
            ownership.referenceCount = UInt64(ownership.prefixIDs.count)
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
            ownership.prefixIDs.remove(stored.prefix.prefixID)
            ownership.blockTableIDs.remove(stored.blockTableID)
            if ownership.prefixIDs.isEmpty {
                pagesByID.removeValue(forKey: pageID)
            } else {
                ownership.referenceCount = UInt64(ownership.prefixIDs.count)
                pagesByID[pageID] = ownership
            }
        }

        for blockID in stored.blockIDs {
            guard var ownership = blocksByID[blockID] else {
                continue
            }
            ownership.prefixIDs.remove(stored.prefix.prefixID)
            if ownership.prefixIDs.isEmpty {
                blocksByID.removeValue(forKey: blockID)
                removedBlocks += 1
            } else {
                ownership.referenceCount = UInt64(ownership.prefixIDs.count)
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
        scope.scopeID = makeScopeID(scope)
    }
    return scope
}

private func resolveCacheKey(
    _ requested: Melix_Worker_V1_CacheKey,
    scope: Melix_Worker_V1_CacheScope,
    prompt: String
) -> Melix_Worker_V1_CacheKey {
    var key = requested
    if key.prefixHash.isEmpty {
        key.prefixHash = Data(SHA256.hash(data: Data("\(scope.scopeID)\n\(prompt)".utf8)))
    }
    if key.fingerprintHash.isEmpty {
        key.fingerprintHash = Data(SHA256.hash(data: Data(prompt.utf8)))
    }
    if key.scopeID.isEmpty {
        key.scopeID = scope.scopeID
    }
    return key
}

private func renderPrompt(
    from messages: [Melix_Worker_V1_ChatMessage]
) throws -> String {
    try messages
        .map(flattenTextContent(from:))
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
        .joined(separator: "\n")
}

private func makeBlockTable(
    cacheKey: Melix_Worker_V1_CacheKey,
    scopeID: String,
    decodeHandle: String,
    promptTokens: Int,
    preferredBlockSize: UInt32,
    initialCacheBlocks: UInt32
) -> Melix_Worker_V1_BlockTable {
    let tokenCount = max(promptTokens, 1)
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
        block.bytes = UInt64(end - start) * 1024
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

private func makeScopeID(_ scope: Melix_Worker_V1_CacheScope) -> String {
    [
        scope.modelID,
        scope.revision,
        scope.tokenizerHash,
        scope.quantProfileID,
        scope.promptTemplateHash,
        scope.parserMode,
        scope.reasoningMode,
        scope.multimodalAdapterHash,
    ].joined(separator: "::")
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

private func makePrefixID(for key: Melix_Worker_V1_CacheKey) -> String {
    "pfx-\(shortHex(key.prefixHash))"
}

private func cacheKeyIdentifier(_ key: Melix_Worker_V1_CacheKey) -> String {
    "\(key.scopeID)::\(Data(key.prefixHash).base64EncodedString())::\(Data(key.fingerprintHash).base64EncodedString())"
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

private func matches(
    cacheKey: Melix_Worker_V1_CacheKey,
    prefix: Melix_Worker_V1_PrefixRef
) -> Bool {
    guard !(cacheKey.prefixHash.isEmpty && cacheKey.fingerprintHash.isEmpty && cacheKey.scopeID.isEmpty) else {
        return true
    }
    return cacheKeyIdentifier(cacheKey) == cacheKeyIdentifier(prefix.cacheKey)
}
