import CryptoKit
import Foundation
import MLX
import MLXFast
import MLXLMCommon

struct RuntimeKVBlockDescriptor: Sendable, Equatable {
    let blockID: String
    let tokenStart: Int
    let tokenEnd: Int
    let bytes: UInt64
}

struct RuntimePagedCacheEvidence: Sendable {
    let admitted: Bool
    let cacheHitMode: String
    let fallbackReason: String
    let recoveredPrefixTokens: Int
    let blocks: [RuntimeKVBlockDescriptor]
    let lookupMicros: Int
    let restoreMicros: Int
    let streamOwnerMatch: Bool
    let copyOnWriteBlockCount: Int
    let computedPrefixTokens: Int
    let modelPrefillMicros: Int
    let modelPrefillChunkTokens: Int
    let modelPrefillCallTokenCounts: [Int]
    let blockTableBytes: UInt64

    static func fallback(
        _ reason: String,
        computedPrefixTokens: Int = 0,
        modelPrefillMicros: Int = 0
    ) -> RuntimePagedCacheEvidence {
        RuntimePagedCacheEvidence(
            admitted: false,
            cacheHitMode: "none",
            fallbackReason: reason,
            recoveredPrefixTokens: 0,
            blocks: [],
            lookupMicros: 0,
            restoreMicros: 0,
            streamOwnerMatch: false,
            copyOnWriteBlockCount: 0,
            computedPrefixTokens: computedPrefixTokens,
            modelPrefillMicros: modelPrefillMicros,
            modelPrefillChunkTokens: 0,
            modelPrefillCallTokenCounts: [],
            blockTableBytes: 0
        )
    }
}

struct RuntimePagedKVPoolStats: Sendable, Equatable {
    let residentBytes: UInt64
    let logicalBytes: UInt64
    let peakResidentBytes: UInt64
    let blockCount: Int
    let sharedBlockCount: Int
    let entryCount: Int
    let lookupCount: UInt64
    let hitCount: UInt64
    let restoredTokenCount: UInt64
    let copyOnWriteBlockCount: UInt64

    static let empty = RuntimePagedKVPoolStats(
        residentBytes: 0,
        logicalBytes: 0,
        peakResidentBytes: 0,
        blockCount: 0,
        sharedBlockCount: 0,
        entryCount: 0,
        lookupCount: 0,
        hitCount: 0,
        restoredTokenCount: 0,
        copyOnWriteBlockCount: 0
    )
}

struct PagedKVLayerPayload: @unchecked Sendable {
    let keys: MLXArray
    let values: MLXArray

    var tokenCount: Int {
        keys.dim(2)
    }

    var bytes: UInt64 {
        pagedKVArrayBytes(keys) + pagedKVArrayBytes(values)
    }
}

final class PagedKVBlock: @unchecked Sendable {
    let blockID: String
    let tokenStart: Int
    let tokenEnd: Int
    let layers: [PagedKVLayerPayload]
    let bytes: UInt64

    private let lock = NSLock()
    private var activeLeaseCount = 0

    init(
        blockID: String,
        tokenStart: Int,
        tokenEnd: Int,
        layers: [PagedKVLayerPayload]
    ) {
        self.blockID = blockID
        self.tokenStart = tokenStart
        self.tokenEnd = tokenEnd
        self.layers = layers
        self.bytes = layers.reduce(UInt64(0)) { $0 + $1.bytes }
    }

    func retainLease() {
        lock.withLock {
            activeLeaseCount += 1
        }
    }

    func releaseLease() {
        lock.withLock {
            precondition(activeLeaseCount > 0, "Paged KV block lease count underflow.")
            activeLeaseCount -= 1
        }
    }

    func leaseCount() -> Int {
        lock.withLock { activeLeaseCount }
    }
}

fileprivate final class PagedKVCacheLease: @unchecked Sendable {
    let blocks: [PagedKVBlock]
    private let lock = NSLock()
    private var copiedBlockIdentities: Set<ObjectIdentifier> = []
    private let onCopyOnWrite: @Sendable () -> Void
    private let onRelease: @Sendable () -> Void

    init(
        blocks: [PagedKVBlock],
        onCopyOnWrite: @escaping @Sendable () -> Void = {},
        onRelease: @escaping @Sendable () -> Void = {}
    ) {
        self.blocks = blocks
        self.onCopyOnWrite = onCopyOnWrite
        self.onRelease = onRelease
        for block in blocks {
            block.retainLease()
        }
    }

    func recordCopyOnWrite(of block: PagedKVBlock) {
        let recorded = lock.withLock {
            copiedBlockIdentities.insert(ObjectIdentifier(block)).inserted
        }
        if recorded {
            onCopyOnWrite()
        }
    }

    deinit {
        for block in blocks {
            block.releaseLease()
        }
        onRelease()
    }
}

final class PagedKVCache: KVCache, @unchecked Sendable {
    private var lease: PagedKVCacheLease?
    private var sharedBlocks: [PagedKVBlock]
    private var privatePayloads: [PagedKVLayerPayload]
    private let layerIndex: Int
    private let blockSize: Int

    private(set) var offset: Int
    var maxSize: Int? { nil }
    var isTrimmable: Bool { true }

    init(blockSize: Int, layerIndex: Int) {
        self.blockSize = max(1, blockSize)
        self.layerIndex = layerIndex
        self.sharedBlocks = []
        self.privatePayloads = []
        self.offset = 0
    }

    private init(
        blockSize: Int,
        layerIndex: Int,
        lease: PagedKVCacheLease
    ) {
        self.blockSize = max(1, blockSize)
        self.layerIndex = layerIndex
        self.lease = lease
        self.sharedBlocks = lease.blocks
        self.privatePayloads = []
        self.offset = lease.blocks.reduce(0) { $0 + ($1.tokenEnd - $1.tokenStart) }
    }

    fileprivate static func makeCaches(
        blocks: [PagedKVBlock],
        blockSize: Int,
        layerCount: Int,
        lease suppliedLease: PagedKVCacheLease? = nil
    ) -> [KVCache] {
        let lease = suppliedLease ?? PagedKVCacheLease(blocks: blocks)
        return (0 ..< layerCount).map { layerIndex in
            PagedKVCache(blockSize: blockSize, layerIndex: layerIndex, lease: lease)
        }
    }

    func innerState() -> [MLXArray] {
        allPayloads().flatMap { [$0.keys, $0.values] }
    }

    func update(keys: MLXArray, values: MLXArray) -> (MLXArray, MLXArray) {
        precondition(keys.dim(2) == values.dim(2), "Paged KV keys and values must have equal token counts.")
        var cursor = 0
        let incomingCount = keys.dim(2)

        if let last = privatePayloads.last, last.tokenCount < blockSize, incomingCount > 0 {
            let accepted = min(blockSize - last.tokenCount, incomingCount)
            let appended = PagedKVLayerPayload(
                keys: concatenated(
                    [last.keys, keys[.ellipsis, cursor ..< cursor + accepted, 0...]],
                    axis: 2
                ).contiguous(),
                values: concatenated(
                    [last.values, values[.ellipsis, cursor ..< cursor + accepted, 0...]],
                    axis: 2
                ).contiguous()
            )
            eval(appended.keys, appended.values)
            privatePayloads[privatePayloads.count - 1] = appended
            cursor += accepted
        }

        while cursor < incomingCount {
            let end = min(incomingCount, cursor + blockSize)
            let payload = PagedKVLayerPayload(
                keys: keys[.ellipsis, cursor ..< end, 0...].contiguous(),
                values: values[.ellipsis, cursor ..< end, 0...].contiguous()
            )
            eval(payload.keys, payload.values)
            privatePayloads.append(payload)
            cursor = end
        }

        offset += incomingCount
        return materializedState()
    }

    var state: [MLXArray] {
        get {
            guard offset > 0 else { return [] }
            let materialized = materializedState()
            return [materialized.0, materialized.1]
        }
        set {
            precondition(newValue.count == 2, "PagedKVCache state requires keys and values.")
            lease = nil
            sharedBlocks = []
            privatePayloads = []
            offset = 0
            _ = update(keys: newValue[0], values: newValue[1])
        }
    }

    var metaState: [String] {
        get { ["melix-paged-v1", String(blockSize), String(offset)] }
        set {
            precondition(
                newValue.count == 3 && newValue[0] == "melix-paged-v1",
                "PagedKVCache metadata is incompatible."
            )
        }
    }

    @discardableResult
    func trim(_ n: Int) -> Int {
        var remaining = min(max(0, n), offset)
        let trimmed = remaining

        while remaining > 0, let last = privatePayloads.last {
            if remaining >= last.tokenCount {
                remaining -= last.tokenCount
                privatePayloads.removeLast()
            } else {
                let kept = last.tokenCount - remaining
                let replacement = PagedKVLayerPayload(
                    keys: last.keys[.ellipsis, ..<kept, 0...].contiguous(),
                    values: last.values[.ellipsis, ..<kept, 0...].contiguous()
                )
                eval(replacement.keys, replacement.values)
                privatePayloads[privatePayloads.count - 1] = replacement
                remaining = 0
            }
        }

        while remaining > 0, let last = sharedBlocks.last {
            let tokenCount = last.tokenEnd - last.tokenStart
            if remaining >= tokenCount {
                remaining -= tokenCount
                sharedBlocks.removeLast()
            } else {
                let kept = tokenCount - remaining
                let layer = last.layers[layerIndex]
                let replacement = PagedKVLayerPayload(
                    keys: layer.keys[.ellipsis, ..<kept, 0...].contiguous(),
                    values: layer.values[.ellipsis, ..<kept, 0...].contiguous()
                )
                eval(replacement.keys, replacement.values)
                lease?.recordCopyOnWrite(of: last)
                sharedBlocks.removeLast()
                privatePayloads.insert(replacement, at: 0)
                remaining = 0
            }
        }
        offset -= trimmed
        return trimmed
    }

    func makeMask(
        n: Int,
        windowSize: Int?,
        returnArray: Bool
    ) -> MLXFast.ScaledDotProductAttentionMaskMode {
        if n == 1 {
            return .none
        }
        if returnArray || (windowSize != nil && n > windowSize!) {
            return .array(createCausalMask(n: n, offset: offset, windowSize: windowSize))
        }
        return .causal
    }

    fileprivate func payloadsForSnapshot() -> [PagedKVLayerPayload] {
        allPayloads()
    }

    fileprivate func sharedBlock(at index: Int) -> PagedKVBlock? {
        sharedBlocks.indices.contains(index) ? sharedBlocks[index] : nil
    }

    var decodeBatchSignature: String {
        let payloadSignature = allPayloads().map { payload in
            [
                "k=\(payload.keys.dtype):\(payload.keys.shape)",
                "v=\(payload.values.dtype):\(payload.values.shape)",
            ].joined(separator: ",")
        }.joined(separator: "|")
        return [
            "PagedKVCache",
            "layer=\(layerIndex)",
            "block=\(blockSize)",
            "offset=\(offset)",
            payloadSignature,
        ].joined(separator: ":")
    }

    private func allPayloads() -> [PagedKVLayerPayload] {
        sharedBlocks.map { $0.layers[layerIndex] } + privatePayloads
    }

    private func materializedState() -> (MLXArray, MLXArray) {
        let payloads = allPayloads()
        precondition(!payloads.isEmpty, "PagedKVCache cannot materialize empty state.")
        if payloads.count == 1 {
            return (payloads[0].keys, payloads[0].values)
        }
        return (
            concatenated(payloads.map(\.keys), axis: 2),
            concatenated(payloads.map(\.values), axis: 2)
        )
    }
}

final class PagedKVPrefixSnapshot: @unchecked Sendable {
    let entryID: String
    let compatibilitySignature: String
    let blockSize: Int
    let tokenBlockDigests: [String]
    let blocks: [PagedKVBlock]
    let layerCount: Int
    let generation: UInt64
    var lastAccessOrdinal: UInt64

    var tokenCount: Int {
        blocks.reduce(0) { $0 + ($1.tokenEnd - $1.tokenStart) }
    }

    init(
        entryID: String,
        compatibilitySignature: String,
        blockSize: Int,
        tokenBlockDigests: [String],
        blocks: [PagedKVBlock],
        layerCount: Int,
        generation: UInt64,
        lastAccessOrdinal: UInt64
    ) {
        self.entryID = entryID
        self.compatibilitySignature = compatibilitySignature
        self.blockSize = blockSize
        self.tokenBlockDigests = tokenBlockDigests
        self.blocks = blocks
        self.layerCount = layerCount
        self.generation = generation
        self.lastAccessOrdinal = lastAccessOrdinal
    }

    var descriptors: [RuntimeKVBlockDescriptor] {
        blocks.map { block in
            RuntimeKVBlockDescriptor(
                blockID: block.blockID,
                tokenStart: block.tokenStart,
                tokenEnd: block.tokenEnd,
                bytes: block.bytes
            )
        }
    }
}

struct PagedKVLookupResult: @unchecked Sendable {
    let snapshot: PagedKVPrefixSnapshot?
    let lookupMicros: Int
    fileprivate let sourceSnapshot: PagedKVPrefixSnapshot?
    fileprivate let lease: PagedKVCacheLease?

    func makeCaches() -> [KVCache]? {
        guard let snapshot, let lease else { return nil }
        return PagedKVCache.makeCaches(
            blocks: snapshot.blocks,
            blockSize: snapshot.blockSize,
            layerCount: snapshot.layerCount,
            lease: lease
        )
    }
}

struct PagedKVStoreResult: @unchecked Sendable {
    let snapshot: PagedKVPrefixSnapshot?
    let fallbackReason: String
    let copyOnWriteBlockCount: Int

    private let leaseTransfer: PagedKVCacheLeaseTransfer?

    fileprivate init(
        snapshot: PagedKVPrefixSnapshot?,
        fallbackReason: String,
        copyOnWriteBlockCount: Int,
        lease: PagedKVCacheLease? = nil
    ) {
        self.snapshot = snapshot
        self.fallbackReason = fallbackReason
        self.copyOnWriteBlockCount = copyOnWriteBlockCount
        self.leaseTransfer = lease.map(PagedKVCacheLeaseTransfer.init)
    }

    func makeCaches() -> [KVCache]? {
        guard let snapshot, let lease = leaseTransfer?.take() else { return nil }
        return PagedKVCache.makeCaches(
            blocks: snapshot.blocks,
            blockSize: snapshot.blockSize,
            layerCount: snapshot.layerCount,
            lease: lease
        )
    }
}

fileprivate final class PagedKVCacheLeaseTransfer: @unchecked Sendable {
    private let lock = NSLock()
    private var lease: PagedKVCacheLease?

    init(_ lease: PagedKVCacheLease) {
        self.lease = lease
    }

    func take() -> PagedKVCacheLease? {
        lock.withLock {
            defer { lease = nil }
            return lease
        }
    }
}

final class PagedKVBlockPool: @unchecked Sendable {
    static let defaultBudgetBytes: UInt64 = 4 * 1_024 * 1_024 * 1_024

    private let lock = NSLock()
    private var entriesByID: [String: PagedKVPrefixSnapshot] = [:]
    private var blocksByIdentity: [ObjectIdentifier: PagedKVBlock] = [:]
    private var nextGeneration: UInt64 = 1
    private var nextAccessOrdinal: UInt64 = 1
    private var lookupCount: UInt64 = 0
    private var hitCount: UInt64 = 0
    private var restoredTokenCount: UInt64 = 0
    private var copyOnWriteBlockCount: UInt64 = 0
    private var peakResidentBytes: UInt64 = 0

    func lookup(
        compatibilitySignature: String,
        tokenIDs: [Int],
        storedTokenBoundary: Int,
        blockSize: Int
    ) -> PagedKVLookupResult {
        let startedAt = Date.timeIntervalSinceReferenceDate
        let digests = pagedKVTokenBlockDigests(
            tokenIDs: tokenIDs,
            storedTokenBoundary: storedTokenBoundary,
            blockSize: blockSize
        )
        let match = lock.withLock {
            () -> (PagedKVPrefixSnapshot, PagedKVPrefixSnapshot, PagedKVCacheLease)? in
            lookupCount += 1
            var sourceSnapshot: PagedKVPrefixSnapshot?
            var matchedBlockCount = 0
            for candidate in entriesByID.values where
                candidate.compatibilitySignature == compatibilitySignature
                    && candidate.blockSize == blockSize
            {
                let commonBlockCount = zip(candidate.tokenBlockDigests, digests)
                    .prefix(while: { $0.0 == $0.1 })
                    .count
                if commonBlockCount > matchedBlockCount
                    || (commonBlockCount == matchedBlockCount
                        && commonBlockCount > 0
                        && candidate.lastAccessOrdinal > (sourceSnapshot?.lastAccessOrdinal ?? 0))
                {
                    sourceSnapshot = candidate
                    matchedBlockCount = commonBlockCount
                }
            }
            guard let sourceSnapshot, matchedBlockCount > 0 else {
                return nil
            }
            sourceSnapshot.lastAccessOrdinal = nextAccessOrdinal
            nextAccessOrdinal += 1
            let matchedDigests = Array(sourceSnapshot.tokenBlockDigests.prefix(matchedBlockCount))
            let matchedBlocks = Array(sourceSnapshot.blocks.prefix(matchedBlockCount))
            let matchedSnapshot = PagedKVPrefixSnapshot(
                entryID: sourceSnapshot.entryID,
                compatibilitySignature: sourceSnapshot.compatibilitySignature,
                blockSize: sourceSnapshot.blockSize,
                tokenBlockDigests: matchedDigests,
                blocks: matchedBlocks,
                layerCount: sourceSnapshot.layerCount,
                generation: sourceSnapshot.generation,
                lastAccessOrdinal: sourceSnapshot.lastAccessOrdinal
            )
            let lease = PagedKVCacheLease(
                blocks: matchedBlocks,
                onCopyOnWrite: { [weak self] in
                    self?.recordCopyOnWrite()
                },
                onRelease: { [weak self] in
                    self?.releaseUnreferencedBlocks()
                }
            )
            return (matchedSnapshot, sourceSnapshot, lease)
        }
        return PagedKVLookupResult(
            snapshot: match?.0,
            lookupMicros: pagedKVElapsedMicros(since: startedAt),
            sourceSnapshot: match?.1,
            lease: match?.2
        )
    }

    func store(
        compatibilitySignature: String,
        tokenIDs: [Int],
        storedTokenBoundary: Int,
        blockSize: Int,
        caches: [KVCache],
        reusedLookup: PagedKVLookupResult?,
        budgetBytes: UInt64
    ) -> PagedKVStoreResult {
        let pagedCaches = caches.compactMap { $0 as? PagedKVCache }
        guard pagedCaches.count == caches.count, !pagedCaches.isEmpty else {
            return PagedKVStoreResult(
                snapshot: nil,
                fallbackReason: "cache_layout_unsupported",
                copyOnWriteBlockCount: 0
            )
        }
        let digests = pagedKVTokenBlockDigests(
            tokenIDs: tokenIDs,
            storedTokenBoundary: storedTokenBoundary,
            blockSize: blockSize
        )
        let entryID = "pkv-\(pagedKVHash([compatibilitySignature] + digests))"
        let expectedBlockCount = storedTokenBoundary / blockSize
        let payloadsByLayer = pagedCaches.map { $0.payloadsForSnapshot() }

        return lock.withLock {
            let reusedSnapshot: PagedKVPrefixSnapshot?
            if let reusedLookup {
                guard let matched = reusedLookup.snapshot,
                      let source = reusedLookup.sourceSnapshot,
                      let lease = reusedLookup.lease,
                      source.compatibilitySignature == compatibilitySignature,
                      source.blockSize == blockSize,
                      source.layerCount == caches.count,
                      matched.entryID == source.entryID,
                      matched.compatibilitySignature == source.compatibilitySignature,
                      matched.blockSize == source.blockSize,
                      matched.layerCount == source.layerCount,
                      matched.generation == source.generation,
                      !matched.blocks.isEmpty,
                      matched.blocks.count == matched.tokenBlockDigests.count,
                      matched.blocks.count <= source.blocks.count,
                      matched.tokenBlockDigests
                        == Array(source.tokenBlockDigests.prefix(matched.blocks.count)),
                      matched.tokenBlockDigests
                        == Array(digests.prefix(matched.blocks.count)),
                      let current = entriesByID[source.entryID],
                      current === source,
                      current.generation == source.generation,
                      lease.blocks.count == matched.blocks.count,
                      zip(lease.blocks, source.blocks.prefix(matched.blocks.count))
                        .allSatisfy({ $0.0 === $0.1 }),
                      zip(matched.blocks, source.blocks.prefix(matched.blocks.count))
                        .allSatisfy({ $0.0 === $0.1 }),
                      matched.blocks.allSatisfy({
                          blocksByIdentity[ObjectIdentifier($0)] === $0
                      }) else {
                    return PagedKVStoreResult(
                        snapshot: nil,
                        fallbackReason: "cache_snapshot_validation_failed",
                        copyOnWriteBlockCount: 0
                    )
                }
                reusedSnapshot = matched
            } else {
                reusedSnapshot = nil
            }

            guard expectedBlockCount > 0,
                  payloadsByLayer.allSatisfy({ $0.count == expectedBlockCount }),
                  payloadsByLayer.allSatisfy({ $0.allSatisfy { $0.tokenCount == blockSize } }) else {
                return PagedKVStoreResult(
                    snapshot: nil,
                    fallbackReason: "cache_block_shape_mismatch",
                    copyOnWriteBlockCount: 0
                )
            }

            var blocks: [PagedKVBlock] = []
            blocks.reserveCapacity(expectedBlockCount)
            for blockIndex in 0 ..< expectedBlockCount {
                if let reusedSnapshot,
                   reusedSnapshot.blocks.indices.contains(blockIndex),
                   reusedSnapshot.tokenBlockDigests[blockIndex] == digests[blockIndex] {
                    blocks.append(reusedSnapshot.blocks[blockIndex])
                    continue
                }

                let start = blockIndex * blockSize
                blocks.append(PagedKVBlock(
                    blockID: "pkvb-\(UUID().uuidString.lowercased())",
                    tokenStart: start,
                    tokenEnd: start + blockSize,
                    layers: payloadsByLayer.map { $0[blockIndex] }
                ))
            }

            let snapshot = PagedKVPrefixSnapshot(
                entryID: entryID,
                compatibilitySignature: compatibilitySignature,
                blockSize: blockSize,
                tokenBlockDigests: digests,
                blocks: blocks,
                layerCount: caches.count,
                generation: nextGeneration,
                lastAccessOrdinal: nextAccessOrdinal
            )
            let limit = budgetBytes
            var proposedEntries = entriesByID
            proposedEntries[entryID] = snapshot
            var residentBlocks = retainedBlocks(for: proposedEntries)
            var residentBytes = residentBlocks.values.reduce(UInt64(0)) { $0 + $1.bytes }
            while residentBytes > limit {
                guard let victim = proposedEntries.values
                    .filter({ $0.entryID != entryID })
                    .min(by: { $0.lastAccessOrdinal < $1.lastAccessOrdinal }) else {
                    break
                }
                proposedEntries.removeValue(forKey: victim.entryID)
                residentBlocks = retainedBlocks(for: proposedEntries)
                residentBytes = residentBlocks.values.reduce(UInt64(0)) { $0 + $1.bytes }
            }
            guard residentBytes <= limit else {
                return PagedKVStoreResult(
                    snapshot: nil,
                    fallbackReason: "cache_memory_budget_exceeded",
                    copyOnWriteBlockCount: 0
                )
            }

            entriesByID = proposedEntries
            blocksByIdentity = residentBlocks
            nextGeneration += 1
            nextAccessOrdinal += 1
            if let reusedSnapshot {
                hitCount += 1
                restoredTokenCount += UInt64(reusedSnapshot.tokenCount)
            }
            peakResidentBytes = max(peakResidentBytes, residentBytes)
            let lease = PagedKVCacheLease(
                blocks: snapshot.blocks,
                onCopyOnWrite: { [weak self] in
                    self?.recordCopyOnWrite()
                },
                onRelease: { [weak self] in
                    self?.releaseUnreferencedBlocks()
                }
            )
            return PagedKVStoreResult(
                snapshot: snapshot,
                fallbackReason: "",
                copyOnWriteBlockCount: 0,
                lease: lease
            )
        }
    }

    func stats() -> RuntimePagedKVPoolStats {
        lock.withLock {
            pruneReleasedBlocks()
            let snapshots = Array(entriesByID.values)
            let blocks = Array(blocksByIdentity.values)
            let storedLogicalBytes = snapshots.flatMap(\.blocks).reduce(UInt64(0)) { $0 + $1.bytes }
            let activeLogicalBytes = blocks.reduce(UInt64(0)) { total, block in
                total + (block.bytes * UInt64(block.leaseCount()))
            }
            let logicalBytes = storedLogicalBytes + activeLogicalBytes
            let sharedBlockCount = blocks.filter { block in
                let entryReferences = snapshots.reduce(0) { count, snapshot in
                    count + snapshot.blocks.filter { $0 === block }.count
                }
                return entryReferences + block.leaseCount() > 1
            }.count
            return RuntimePagedKVPoolStats(
                residentBytes: blocks.reduce(UInt64(0)) { $0 + $1.bytes },
                logicalBytes: logicalBytes,
                peakResidentBytes: peakResidentBytes,
                blockCount: blocks.count,
                sharedBlockCount: sharedBlockCount,
                entryCount: snapshots.count,
                lookupCount: lookupCount,
                hitCount: hitCount,
                restoredTokenCount: restoredTokenCount,
                copyOnWriteBlockCount: copyOnWriteBlockCount
            )
        }
    }

    func removeAll(compatibilitySignaturePrefix: String? = nil) {
        lock.withLock {
            guard let compatibilitySignaturePrefix else {
                entriesByID.removeAll()
                pruneReleasedBlocks()
                return
            }
            entriesByID = entriesByID.filter {
                !$0.value.compatibilitySignature.hasPrefix(compatibilitySignaturePrefix)
            }
            pruneReleasedBlocks()
        }
    }

    private func retainedBlocks(
        for entries: [String: PagedKVPrefixSnapshot]
    ) -> [ObjectIdentifier: PagedKVBlock] {
        var retained = blocksByIdentity.filter { _, block in
            block.leaseCount() > 0
        }
        for block in entries.values.flatMap(\.blocks) {
            retained[ObjectIdentifier(block)] = block
        }
        return retained
    }

    private func pruneReleasedBlocks() {
        let referenced = Set(
            entriesByID.values
                .flatMap(\.blocks)
                .map(ObjectIdentifier.init)
        )
        blocksByIdentity = blocksByIdentity.filter { identity, block in
            referenced.contains(identity) || block.leaseCount() > 0
        }
    }

    private func recordCopyOnWrite() {
        lock.withLock {
            copyOnWriteBlockCount += 1
        }
    }

    private func releaseUnreferencedBlocks() {
        lock.withLock {
            pruneReleasedBlocks()
        }
    }

}

func pagedKVCacheLayoutIsSupported(_ caches: [KVCache]) -> Bool {
    !caches.isEmpty && caches.allSatisfy { cache in
        type(of: cache) == KVCacheSimple.self
    }
}

func pagedKVArrayBytes(_ array: MLXArray) -> UInt64 {
    UInt64(max(array.size, 0)) * UInt64(max(array.dtype.size, 1))
}

private func pagedKVTokenBlockDigests(
    tokenIDs: [Int],
    storedTokenBoundary: Int,
    blockSize: Int
) -> [String] {
    guard storedTokenBoundary > 0, blockSize > 0 else { return [] }
    return stride(from: 0, to: storedTokenBoundary, by: blockSize).map { start in
        let end = min(storedTokenBoundary, start + blockSize)
        var data = Data(capacity: (end - start) * MemoryLayout<Int64>.size)
        for tokenID in tokenIDs[start ..< end] {
            var value = Int64(tokenID).littleEndian
            withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
        }
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}

private func pagedKVHash(_ components: [String]) -> String {
    SHA256.hash(data: Data(components.joined(separator: "\n").utf8))
        .prefix(16)
        .map { String(format: "%02x", $0) }
        .joined()
}

private func pagedKVElapsedMicros(since startedAt: TimeInterval) -> Int {
    max(0, Int(((Date.timeIntervalSinceReferenceDate - startedAt) * 1_000_000).rounded()))
}
