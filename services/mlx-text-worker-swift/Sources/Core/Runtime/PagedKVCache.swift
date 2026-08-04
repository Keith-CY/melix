import CryptoKit
import Foundation
import MelixWorkerProtocol
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
    let privateResidentBytes: UInt64
    let activePrivateOwnerCount: Int
    let blockCount: Int
    let sharedBlockCount: Int
    let entryCount: Int
    let pinnedPrefixCount: Int
    let lookupCount: UInt64
    let hitCount: UInt64
    let restoredTokenCount: UInt64
    let copyOnWriteBlockCount: UInt64

    static let empty = RuntimePagedKVPoolStats(
        residentBytes: 0,
        logicalBytes: 0,
        peakResidentBytes: 0,
        privateResidentBytes: 0,
        activePrivateOwnerCount: 0,
        blockCount: 0,
        sharedBlockCount: 0,
        entryCount: 0,
        pinnedPrefixCount: 0,
        lookupCount: 0,
        hitCount: 0,
        restoredTokenCount: 0,
        copyOnWriteBlockCount: 0
    )
}

struct RuntimePagedKVPoolEntryProjection: Sendable {
    let prefix: Melix_Worker_V1_PrefixRef
    let blocks: [RuntimeKVBlockDescriptor]
}

struct RuntimePagedKVPoolProjection: Sendable {
    let entries: [RuntimePagedKVPoolEntryProjection]

    static let empty = RuntimePagedKVPoolProjection(entries: [])
}

struct RuntimePagedKVPoolSnapshot: Sendable {
    let stats: RuntimePagedKVPoolStats
    let projection: RuntimePagedKVPoolProjection

    static let empty = RuntimePagedKVPoolSnapshot(stats: .empty, projection: .empty)
}

private final class PagedKVPrivateAllocationOwner: @unchecked Sendable {
    let ownerID = UUID().uuidString.lowercased()

    private enum State: Equatable {
        case active
        case transferring
        case transferred
    }

    private let lock = NSLock()
    private let onBytesChanged: @Sendable (String, UInt64) -> Void
    private var bytesByLayer: [Int: UInt64] = [:]
    private var state = State.active

    init(onBytesChanged: @escaping @Sendable (String, UInt64) -> Void) {
        self.onBytesChanged = onBytesChanged
    }

    func setBytes(_ bytes: UInt64, forLayer layerIndex: Int) {
        lock.withLock {
            guard state == .active else { return }
            if bytes == 0 {
                bytesByLayer.removeValue(forKey: layerIndex)
            } else {
                bytesByLayer[layerIndex] = bytes
            }
            onBytesChanged(ownerID, bytesByLayer.values.reduce(UInt64(0), +))
        }
    }

    func withPoolTransfer<Result>(
        _ body: (String, UInt64) -> (result: Result, committed: Bool)
    ) -> Result? {
        lock.withLock {
            guard state == .active else { return nil }
            state = .transferring
            let outcome = body(ownerID, bytesByLayer.values.reduce(UInt64(0), +))
            if outcome.committed {
                bytesByLayer.removeAll()
                state = .transferred
            } else {
                state = .active
            }
            return outcome.result
        }
    }

    deinit {
        let shouldRemove = lock.withLock { () -> Bool in
            guard state == .active else { return false }
            state = .transferred
            return true
        }
        if shouldRemove {
            onBytesChanged(ownerID, 0)
        }
    }
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

private final class PagedKVCacheLease: @unchecked Sendable {
    let streamOwner: MLX.Stream
    let privateAllocationOwner: PagedKVPrivateAllocationOwner?
    private let lock = NSLock()
    private var activeBlocks: [PagedKVBlock]
    private var layerReferencesByBlock: [ObjectIdentifier: Int]
    private var copiedBlockIdentities: Set<ObjectIdentifier> = []
    private let onCopyOnWrite: @Sendable () -> Void
    private let onRelease: @Sendable () -> Void

    init(
        blocks: [PagedKVBlock],
        layerCount: Int,
        streamOwner: MLX.Stream,
        privateAllocationOwner: PagedKVPrivateAllocationOwner? = nil,
        onCopyOnWrite: @escaping @Sendable () -> Void = {},
        onRelease: @escaping @Sendable () -> Void = {}
    ) {
        self.activeBlocks = blocks
        self.streamOwner = streamOwner
        self.layerReferencesByBlock = Dictionary(
            uniqueKeysWithValues: blocks.map { (ObjectIdentifier($0), max(1, layerCount)) }
        )
        self.privateAllocationOwner = privateAllocationOwner
        self.onCopyOnWrite = onCopyOnWrite
        self.onRelease = onRelease
        for block in blocks {
            block.retainLease()
        }
    }

    var blocks: [PagedKVBlock] {
        lock.withLock { activeBlocks }
    }

    func recordCopyOnWrite(of block: PagedKVBlock) {
        let recorded = lock.withLock {
            copiedBlockIdentities.insert(ObjectIdentifier(block)).inserted
        }
        if recorded {
            onCopyOnWrite()
        }
    }

    func releaseLayerReference(to block: PagedKVBlock) {
        let released = lock.withLock { () -> PagedKVBlock? in
            let identity = ObjectIdentifier(block)
            guard let count = layerReferencesByBlock[identity], count > 0 else { return nil }
            if count > 1 {
                layerReferencesByBlock[identity] = count - 1
                return nil
            }
            layerReferencesByBlock.removeValue(forKey: identity)
            guard let index = activeBlocks.firstIndex(where: { $0 === block }) else { return nil }
            return activeBlocks.remove(at: index)
        }
        if let released {
            released.releaseLease()
            onRelease()
        }
    }

    deinit {
        let blocks = lock.withLock {
            let blocks = activeBlocks
            activeBlocks.removeAll()
            layerReferencesByBlock.removeAll()
            return blocks
        }
        for block in blocks {
            block.releaseLease()
        }
        onRelease()
    }
}

final class PagedKVCache: KVCache, @unchecked Sendable {
    private var lease: PagedKVCacheLease?
    private let privateAllocationOwner: PagedKVPrivateAllocationOwner?
    private var sharedBlocks: [PagedKVBlock]
    private var privatePayloads: [PagedKVLayerPayload]
    private let layerIndex: Int
    private let blockSize: Int
    private let streamOwner: MLX.Stream

    private(set) var offset: Int
    var maxSize: Int? { nil }
    var isTrimmable: Bool { true }

    init(blockSize: Int, layerIndex: Int) {
        self.blockSize = max(1, blockSize)
        self.layerIndex = layerIndex
        self.privateAllocationOwner = nil
        self.sharedBlocks = []
        self.privatePayloads = []
        self.offset = 0
        self.streamOwner = StreamOrDevice.default.stream
    }

    private init(
        blockSize: Int,
        layerIndex: Int,
        lease: PagedKVCacheLease
    ) {
        self.blockSize = max(1, blockSize)
        self.layerIndex = layerIndex
        self.lease = lease
        self.privateAllocationOwner = lease.privateAllocationOwner
        self.sharedBlocks = lease.blocks
        self.privatePayloads = []
        self.offset = lease.blocks.reduce(0) { $0 + ($1.tokenEnd - $1.tokenStart) }
        self.streamOwner = lease.streamOwner
    }

    fileprivate static func makeCaches(
        blocks: [PagedKVBlock],
        blockSize: Int,
        layerCount: Int,
        streamOwner: MLX.Stream = StreamOrDevice.default.stream,
        lease: PagedKVCacheLease
    ) -> [KVCache] {
        return (0..<layerCount).map { layerIndex in
            PagedKVCache(blockSize: blockSize, layerIndex: layerIndex, lease: lease)
        }
    }

    func innerState() -> [MLXArray] {
        allPayloads().flatMap { [$0.keys, $0.values] }
    }

    func update(keys: MLXArray, values: MLXArray) -> (MLXArray, MLXArray) {
        precondition(
            keys.dim(2) == values.dim(2), "Paged KV keys and values must have equal token counts.")
        var cursor = 0
        let incomingCount = keys.dim(2)

        if let last = privatePayloads.last, last.tokenCount < blockSize, incomingCount > 0 {
            let accepted = min(blockSize - last.tokenCount, incomingCount)
            let appended = PagedKVLayerPayload(
                keys: concatenated(
                    [last.keys, keys[.ellipsis, cursor..<cursor + accepted, 0...]],
                    axis: 2
                ).contiguous(),
                values: concatenated(
                    [last.values, values[.ellipsis, cursor..<cursor + accepted, 0...]],
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
                keys: keys[.ellipsis, cursor..<end, 0...].contiguous(),
                values: values[.ellipsis, cursor..<end, 0...].contiguous()
            )
            eval(payload.keys, payload.values)
            privatePayloads.append(payload)
            cursor = end
        }

        offset += incomingCount
        publishPrivateBytes()
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
            for block in sharedBlocks {
                lease?.releaseLayerReference(to: block)
            }
            lease = nil
            sharedBlocks = []
            privatePayloads = []
            offset = 0
            publishPrivateBytes()
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
                lease?.releaseLayerReference(to: last)
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
                lease?.releaseLayerReference(to: last)
                sharedBlocks.removeLast()
                privatePayloads.insert(replacement, at: 0)
                remaining = 0
            }
        }
        offset -= trimmed
        publishPrivateBytes()
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

    fileprivate var allocationOwner: PagedKVPrivateAllocationOwner? {
        privateAllocationOwner
    }

    fileprivate var ownerStream: MLX.Stream {
        streamOwner
    }

    var streamOwnerMatchesCurrent: Bool {
        streamOwner === StreamOrDevice.default.stream
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

    private func publishPrivateBytes() {
        privateAllocationOwner?.setBytes(
            privatePayloads.reduce(UInt64(0)) { $0 + $1.bytes },
            forLayer: layerIndex
        )
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

    deinit {
        for block in sharedBlocks {
            lease?.releaseLayerReference(to: block)
        }
        privateAllocationOwner?.setBytes(0, forLayer: layerIndex)
    }
}

final class PagedKVPrefixSnapshot: @unchecked Sendable {
    let entryID: String
    let compatibilitySignature: String
    let blockSize: Int
    let tokenBlockDigests: [String]
    let blocks: [PagedKVBlock]
    let layerCount: Int
    let streamOwner: MLX.Stream
    let generation: UInt64
    var logicalPrefix: Melix_Worker_V1_PrefixRef?
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
        streamOwner: MLX.Stream,
        generation: UInt64,
        logicalPrefix: Melix_Worker_V1_PrefixRef?,
        lastAccessOrdinal: UInt64
    ) {
        self.entryID = entryID
        self.compatibilitySignature = compatibilitySignature
        self.blockSize = blockSize
        self.tokenBlockDigests = tokenBlockDigests
        self.blocks = blocks
        self.layerCount = layerCount
        self.streamOwner = streamOwner
        self.generation = generation
        self.logicalPrefix = logicalPrefix
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
    private let leaseTransfer: PagedKVCacheLeaseTransfer?

    fileprivate init(
        snapshot: PagedKVPrefixSnapshot?,
        lookupMicros: Int,
        sourceSnapshot: PagedKVPrefixSnapshot?,
        lease: PagedKVCacheLease?
    ) {
        self.snapshot = snapshot
        self.lookupMicros = lookupMicros
        self.sourceSnapshot = sourceSnapshot
        self.leaseTransfer = lease.map(PagedKVCacheLeaseTransfer.init)
    }

    fileprivate var lease: PagedKVCacheLease? {
        leaseTransfer?.borrowedLease()
    }

    func makeCaches() -> [KVCache]? {
        guard let snapshot, let lease = leaseTransfer?.take() else { return nil }
        return PagedKVCache.makeCaches(
            blocks: snapshot.blocks,
            blockSize: snapshot.blockSize,
            layerCount: snapshot.layerCount,
            streamOwner: snapshot.streamOwner,
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
            streamOwner: snapshot.streamOwner,
            lease: lease
        )
    }
}

private final class PagedKVCacheLeaseTransfer: @unchecked Sendable {
    private let lock = NSLock()
    private var lease: PagedKVCacheLease?
    private weak var transferredLease: PagedKVCacheLease?

    init(_ lease: PagedKVCacheLease) {
        self.lease = lease
    }

    func take() -> PagedKVCacheLease? {
        lock.withLock {
            guard let lease else { return nil }
            self.lease = nil
            transferredLease = lease
            return lease
        }
    }

    func borrowedLease() -> PagedKVCacheLease? {
        lock.withLock { lease ?? transferredLease }
    }
}

private struct PagedKVLogicalProjectionAccumulator {
    var prefix: Melix_Worker_V1_PrefixRef
    var blocksByID: [String: RuntimeKVBlockDescriptor]
}

final class PagedKVBlockPool: @unchecked Sendable {
    static let defaultBudgetBytes: UInt64 = 4 * 1_024 * 1_024 * 1_024

    private let lock = NSLock()
    private let testHookLock = NSLock()
    private var entriesByID: [String: PagedKVPrefixSnapshot] = [:]
    private var pinnedLogicalPrefixes: Set<CacheLogicalPrefixKey> = []
    private var blocksByIdentity: [ObjectIdentifier: PagedKVBlock] = [:]
    private var privateBytesByOwnerID: [String: UInt64] = [:]
    private var nextGeneration: UInt64 = 1
    private var nextAccessOrdinal: UInt64 = 1
    private var lookupCount: UInt64 = 0
    private var hitCount: UInt64 = 0
    private var restoredTokenCount: UInt64 = 0
    private var copyOnWriteBlockCount: UInt64 = 0
    private var peakResidentBytes: UInt64 = 0
    private var storeCommitBoundaryHookForTesting: (@Sendable () -> Void)?
    private var snapshotBoundaryHookForTesting: (@Sendable () -> Void)?

    func setStoreCommitBoundaryHookForTesting(_ hook: (@Sendable () -> Void)?) {
        testHookLock.withLock {
            storeCommitBoundaryHookForTesting = hook
        }
    }

    func setSnapshotBoundaryHookForTesting(_ hook: (@Sendable () -> Void)?) {
        testHookLock.withLock {
            snapshotBoundaryHookForTesting = hook
        }
    }

    func makeCaches(
        blockSize: Int,
        layerCount: Int,
        streamOwner: MLX.Stream = StreamOrDevice.default.stream
    ) -> [KVCache] {
        guard layerCount > 0 else { return [] }
        let lease = PagedKVCacheLease(
            blocks: [],
            layerCount: layerCount,
            streamOwner: streamOwner,
            privateAllocationOwner: makePrivateAllocationOwner()
        )
        return PagedKVCache.makeCaches(
            blocks: [],
            blockSize: blockSize,
            layerCount: layerCount,
            streamOwner: streamOwner,
            lease: lease
        )
    }

    func lookup(
        compatibilitySignature: String,
        tokenIDs: [Int],
        storedTokenBoundary: Int,
        blockSize: Int,
        streamOwner: MLX.Stream = StreamOrDevice.default.stream
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
            for candidate in entriesByID.values
            where
                candidate.compatibilitySignature == compatibilitySignature
                && candidate.blockSize == blockSize
                && candidate.streamOwner === streamOwner
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
                streamOwner: sourceSnapshot.streamOwner,
                generation: sourceSnapshot.generation,
                logicalPrefix: sourceSnapshot.logicalPrefix,
                lastAccessOrdinal: sourceSnapshot.lastAccessOrdinal
            )
            let lease = PagedKVCacheLease(
                blocks: matchedBlocks,
                layerCount: sourceSnapshot.layerCount,
                streamOwner: sourceSnapshot.streamOwner,
                privateAllocationOwner: makePrivateAllocationOwner(),
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
        budgetBytes: UInt64,
        logicalPrefix: Melix_Worker_V1_PrefixRef? = nil
    ) -> PagedKVStoreResult {
        let pagedCaches = caches.compactMap { $0 as? PagedKVCache }
        guard pagedCaches.count == caches.count, !pagedCaches.isEmpty else {
            return PagedKVStoreResult(
                snapshot: nil,
                fallbackReason: "cache_layout_unsupported",
                copyOnWriteBlockCount: 0
            )
        }
        guard let streamOwner = pagedCaches.first?.ownerStream,
            streamOwner === StreamOrDevice.default.stream,
            pagedCaches.allSatisfy({ $0.ownerStream === streamOwner })
        else {
            return PagedKVStoreResult(
                snapshot: nil,
                fallbackReason: "cache_stream_owner_mismatch",
                copyOnWriteBlockCount: 0
            )
        }
        let digests = pagedKVTokenBlockDigests(
            tokenIDs: tokenIDs,
            storedTokenBoundary: storedTokenBoundary,
            blockSize: blockSize
        )
        let logicalEntryIDComponents = logicalPrefix.map {
            ["logical-prefix-v1"] + CacheLogicalPrefixKey($0).stableComponents
        } ?? ["logical-prefix-none"]
        let entryIDHash = pagedKVHash(
            [compatibilitySignature] + digests + logicalEntryIDComponents
        )
        let entryID = "pkv-\(entryIDHash)"
        let expectedBlockCount = storedTokenBoundary / blockSize
        let payloadsByLayer = pagedCaches.map { $0.payloadsForSnapshot() }
        let privateAllocationOwner = pagedCaches.first?.allocationOwner
        let transfersOnePrivateOwner =
            privateAllocationOwner != nil
            && pagedCaches.allSatisfy { $0.allocationOwner === privateAllocationOwner }
        let transferringOwner = transfersOnePrivateOwner ? privateAllocationOwner : nil
        let performStore: (String?, UInt64) -> PagedKVStoreResult = {
            [self] submittingOwnerID, submittingOwnerBytes in
            let commitBoundaryHook = self.testHookLock.withLock {
                self.storeCommitBoundaryHookForTesting
            }
            commitBoundaryHook?()
            return self.lock.withLock {
                let reusedSnapshot: PagedKVPrefixSnapshot?
                if let reusedLookup {
                    guard let matched = reusedLookup.snapshot,
                        let source = reusedLookup.sourceSnapshot,
                        let lease = reusedLookup.lease,
                        source.compatibilitySignature == compatibilitySignature,
                        source.blockSize == blockSize,
                        source.layerCount == caches.count,
                        source.streamOwner === streamOwner,
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
                        lease.streamOwner === streamOwner,
                        zip(lease.blocks, source.blocks.prefix(matched.blocks.count))
                            .allSatisfy({ $0.0 === $0.1 }),
                        zip(matched.blocks, source.blocks.prefix(matched.blocks.count))
                            .allSatisfy({ $0.0 === $0.1 }),
                        matched.blocks.allSatisfy({
                            blocksByIdentity[ObjectIdentifier($0)] === $0
                        })
                    else {
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
                    payloadsByLayer.allSatisfy({ $0.allSatisfy { $0.tokenCount == blockSize } })
                else {
                    return PagedKVStoreResult(
                        snapshot: nil,
                        fallbackReason: "cache_block_shape_mismatch",
                        copyOnWriteBlockCount: 0
                    )
                }

                var blocks: [PagedKVBlock] = []
                blocks.reserveCapacity(expectedBlockCount)
                for blockIndex in 0..<expectedBlockCount {
                    if let reusedSnapshot,
                        reusedSnapshot.blocks.indices.contains(blockIndex),
                        reusedSnapshot.tokenBlockDigests[blockIndex] == digests[blockIndex]
                    {
                        blocks.append(reusedSnapshot.blocks[blockIndex])
                        continue
                    }

                    let start = blockIndex * blockSize
                    blocks.append(
                        PagedKVBlock(
                            blockID: "pkvb-\(UUID().uuidString.lowercased())",
                            tokenStart: start,
                            tokenEnd: start + blockSize,
                            layers: payloadsByLayer.map { $0[blockIndex] }
                        ))
                }

                var committedLogicalPrefix = logicalPrefix ?? entriesByID[entryID]?.logicalPrefix
                let logicalPrefixKey = committedLogicalPrefix.map(CacheLogicalPrefixKey.init)
                let logicalPrefixWasPinned = logicalPrefixKey.map { key in
                    pinnedLogicalPrefixes.contains(key)
                        || entriesByID.values.contains { candidate in
                            candidate.logicalPrefix.map(CacheLogicalPrefixKey.init) == key
                                && candidate.logicalPrefix?.pinned == true
                        }
                } ?? false
                if committedLogicalPrefix?.pinned == true || logicalPrefixWasPinned {
                    committedLogicalPrefix?.pinned = true
                }
                let snapshot = PagedKVPrefixSnapshot(
                    entryID: entryID,
                    compatibilitySignature: compatibilitySignature,
                    blockSize: blockSize,
                    tokenBlockDigests: digests,
                    blocks: blocks,
                    layerCount: caches.count,
                    streamOwner: streamOwner,
                    generation: nextGeneration,
                    logicalPrefix: committedLogicalPrefix,
                    lastAccessOrdinal: nextAccessOrdinal
                )
                let limit = budgetBytes
                let activePrivateBytes =
                    privateBytesByOwnerID.values.reduce(UInt64(0), +)
                    - submittingOwnerBytes
                var proposedEntries = entriesByID
                proposedEntries[entryID] = snapshot
                var residentBlocks = retainedBlocks(for: proposedEntries)
                var residentBytes =
                    residentBlocks.values.reduce(UInt64(0)) { $0 + $1.bytes }
                    + activePrivateBytes
                while residentBytes > limit {
                    guard
                        let victim = proposedEntries.values
                            .filter({ candidate in
                                candidate.entryID != entryID
                                    && !isPinned(candidate)
                                    && candidate.blocks.allSatisfy { $0.leaseCount() == 0 }
                            })
                            .min(by: { $0.lastAccessOrdinal < $1.lastAccessOrdinal })
                    else {
                        break
                    }
                    proposedEntries.removeValue(forKey: victim.entryID)
                    residentBlocks = retainedBlocks(for: proposedEntries)
                    residentBytes =
                        residentBlocks.values.reduce(UInt64(0)) { $0 + $1.bytes }
                        + activePrivateBytes
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
                if committedLogicalPrefix?.pinned == true, let logicalPrefixKey {
                    pinnedLogicalPrefixes.insert(logicalPrefixKey)
                }
                if let submittingOwnerID {
                    privateBytesByOwnerID.removeValue(forKey: submittingOwnerID)
                }
                nextGeneration += 1
                nextAccessOrdinal += 1
                if let reusedSnapshot {
                    hitCount += 1
                    restoredTokenCount += UInt64(reusedSnapshot.tokenCount)
                }
                peakResidentBytes = max(peakResidentBytes, residentBytes)
                let lease = PagedKVCacheLease(
                    blocks: snapshot.blocks,
                    layerCount: caches.count,
                    streamOwner: snapshot.streamOwner,
                    privateAllocationOwner: makePrivateAllocationOwner(),
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
        guard let transferringOwner else {
            return performStore(nil, 0)
        }
        return transferringOwner.withPoolTransfer { ownerID, ownerBytes in
            let result = performStore(ownerID, ownerBytes)
            return (result, result.snapshot != nil)
        }
            ?? PagedKVStoreResult(
                snapshot: nil,
                fallbackReason: "cache_private_owner_transfer_unavailable",
                copyOnWriteBlockCount: 0
            )
    }

    func snapshot() -> RuntimePagedKVPoolSnapshot {
        lock.withLock {
            pruneReleasedBlocks()
            let boundaryHook = testHookLock.withLock { snapshotBoundaryHookForTesting }
            boundaryHook?()
            let snapshots = Array(entriesByID.values)
            let blocks = Array(blocksByIdentity.values)
            let privateResidentBytes = privateBytesByOwnerID.values.reduce(UInt64(0), +)
            let storedLogicalBytes = snapshots.flatMap(\.blocks).reduce(UInt64(0)) { $0 + $1.bytes }
            let activeLogicalBytes = blocks.reduce(UInt64(0)) { total, block in
                total + (block.bytes * UInt64(block.leaseCount()))
            }
            let logicalBytes = storedLogicalBytes + activeLogicalBytes + privateResidentBytes
            let sharedBlockCount = blocks.filter { block in
                let entryReferences = snapshots.reduce(0) { count, snapshot in
                    count + snapshot.blocks.filter { $0 === block }.count
                }
                return entryReferences + block.leaseCount() > 1
            }.count
            let pinnedLogicalPrefixCount = snapshots.reduce(
                into: Set<CacheLogicalPrefixKey>()
            ) { keys, snapshot in
                guard let prefix = snapshot.logicalPrefix,
                      isPinned(snapshot) else { return }
                keys.insert(CacheLogicalPrefixKey(prefix))
            }.count
            let stats = RuntimePagedKVPoolStats(
                residentBytes: blocks.reduce(UInt64(0)) { $0 + $1.bytes } + privateResidentBytes,
                logicalBytes: logicalBytes,
                peakResidentBytes: peakResidentBytes,
                privateResidentBytes: privateResidentBytes,
                activePrivateOwnerCount: privateBytesByOwnerID.count,
                blockCount: blocks.count,
                sharedBlockCount: sharedBlockCount,
                entryCount: snapshots.count,
                pinnedPrefixCount: pinnedLogicalPrefixCount,
                lookupCount: lookupCount,
                hitCount: hitCount,
                restoredTokenCount: restoredTokenCount,
                copyOnWriteBlockCount: copyOnWriteBlockCount
            )
            var logicalEntries: [CacheLogicalPrefixKey: PagedKVLogicalProjectionAccumulator] = [:]
            for entry in snapshots {
                guard var prefix = entry.logicalPrefix else { continue }
                let key = CacheLogicalPrefixKey(prefix)
                prefix.pinned = isPinned(entry)
                var accumulator = logicalEntries[key]
                    ?? PagedKVLogicalProjectionAccumulator(prefix: prefix, blocksByID: [:])
                accumulator.prefix.pinned = accumulator.prefix.pinned || prefix.pinned
                accumulator.prefix.tokenLength = max(
                    accumulator.prefix.tokenLength,
                    prefix.tokenLength
                )
                for block in entry.descriptors {
                    accumulator.blocksByID[block.blockID] = block
                }
                logicalEntries[key] = accumulator
            }
            let entries = logicalEntries.values.map { accumulator in
                RuntimePagedKVPoolEntryProjection(
                    prefix: accumulator.prefix,
                    blocks: accumulator.blocksByID.values.sorted {
                        if $0.tokenStart == $1.tokenStart {
                            return $0.blockID < $1.blockID
                        }
                        return $0.tokenStart < $1.tokenStart
                    }
                )
            }.sorted {
                if $0.prefix.prefixID == $1.prefix.prefixID {
                    return CacheLogicalPrefixKey($0.prefix).stableComponents
                        .lexicographicallyPrecedes(
                            CacheLogicalPrefixKey($1.prefix).stableComponents
                        )
                }
                return $0.prefix.prefixID < $1.prefix.prefixID
            }
            return RuntimePagedKVPoolSnapshot(
                stats: stats,
                projection: RuntimePagedKVPoolProjection(entries: entries)
            )
        }
    }

    func stats() -> RuntimePagedKVPoolStats {
        snapshot().stats
    }

    func projection() -> RuntimePagedKVPoolProjection {
        snapshot().projection
    }

    func setPinned(_ requested: Melix_Worker_V1_PrefixRef, pinned: Bool) -> Bool {
        lock.withLock {
            let snapshots = entriesByID.values.filter { candidate in
                guard let stored = candidate.logicalPrefix else { return false }
                return pagedKVPrefixMatches(requested: requested, stored: stored)
            }
            guard !snapshots.isEmpty else { return false }
            for snapshot in snapshots {
                guard var prefix = snapshot.logicalPrefix else { continue }
                let key = CacheLogicalPrefixKey(prefix)
                prefix.pinned = pinned
                snapshot.logicalPrefix = prefix
                if pinned {
                    pinnedLogicalPrefixes.insert(key)
                } else {
                    pinnedLogicalPrefixes.remove(key)
                }
            }
            return true
        }
    }

    func purge(
        scope: Melix_Worker_V1_CacheScope,
        cacheKey: Melix_Worker_V1_CacheKey,
        includePinned: Bool
    ) -> UInt64 {
        lock.withLock {
            let matchingEntryIDs = entriesByID.values.compactMap { snapshot -> String? in
                guard let prefix = snapshot.logicalPrefix,
                      pagedKVPurgeMatches(scope: scope, cacheKey: cacheKey, prefix: prefix),
                      includePinned || !isPinned(snapshot) else {
                    return nil
                }
                return snapshot.entryID
            }
            guard !matchingEntryIDs.isEmpty else { return 0 }
            let removedBlocks = Set(
                matchingEntryIDs.compactMap { entriesByID[$0] }.flatMap(\.blocks).map(ObjectIdentifier.init)
            )
            for entryID in matchingEntryIDs {
                entriesByID.removeValue(forKey: entryID)
            }
            prunePinnedLogicalPrefixes()
            let retainedBlockIDs = Set(entriesByID.values.flatMap(\.blocks).map(ObjectIdentifier.init))
            let purgedBlockCount = removedBlocks.subtracting(retainedBlockIDs).count
            pruneReleasedBlocks()
            return UInt64(purgedBlockCount)
        }
    }

    func removeAll(compatibilitySignaturePrefix: String? = nil) {
        lock.withLock {
            guard let compatibilitySignaturePrefix else {
                entriesByID.removeAll()
                pinnedLogicalPrefixes.removeAll()
                pruneReleasedBlocks()
                return
            }
            entriesByID = entriesByID.filter {
                !$0.value.compatibilitySignature.hasPrefix(compatibilitySignaturePrefix)
            }
            prunePinnedLogicalPrefixes()
            pruneReleasedBlocks()
        }
    }

    private func isPinned(_ snapshot: PagedKVPrefixSnapshot) -> Bool {
        guard let prefix = snapshot.logicalPrefix else { return false }
        return prefix.pinned || pinnedLogicalPrefixes.contains(CacheLogicalPrefixKey(prefix))
    }

    private func prunePinnedLogicalPrefixes() {
        let liveKeys = Set(entriesByID.values.compactMap { snapshot in
            snapshot.logicalPrefix.map(CacheLogicalPrefixKey.init)
        })
        pinnedLogicalPrefixes.formIntersection(liveKeys)
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

    private func makePrivateAllocationOwner() -> PagedKVPrivateAllocationOwner {
        PagedKVPrivateAllocationOwner { [weak self] ownerID, bytes in
            self?.updatePrivateAllocation(ownerID: ownerID, bytes: bytes)
        }
    }

    private func updatePrivateAllocation(ownerID: String, bytes: UInt64) {
        lock.withLock {
            if bytes == 0 {
                privateBytesByOwnerID.removeValue(forKey: ownerID)
            } else {
                privateBytesByOwnerID[ownerID] = bytes
            }
            peakResidentBytes = max(peakResidentBytes, currentResidentBytes())
        }
    }

    private func currentResidentBytes() -> UInt64 {
        blocksByIdentity.values.reduce(UInt64(0)) { $0 + $1.bytes }
            + privateBytesByOwnerID.values.reduce(UInt64(0), +)
    }

}

private func pagedKVPrefixMatches(
    requested: Melix_Worker_V1_PrefixRef,
    stored: Melix_Worker_V1_PrefixRef
) -> Bool {
    let requestedHasLogicalIdentity = !requested.scope.scopeID.isEmpty
        || !requested.scope.modelID.isEmpty
        || !requested.cacheKey.scopeID.isEmpty
        || !requested.cacheKey.prefixHash.isEmpty
        || !requested.cacheKey.fingerprintHash.isEmpty
    guard requestedHasLogicalIdentity else { return false }
    return CacheLogicalPrefixKey(requested) == CacheLogicalPrefixKey(stored)
        && (requested.prefixID.isEmpty || requested.prefixID == stored.prefixID)
}

private func pagedKVScopeMatches(
    _ scope: Melix_Worker_V1_CacheScope,
    prefix: Melix_Worker_V1_PrefixRef
) -> Bool {
    if scope.scopeID.isEmpty && scope.modelID.isEmpty {
        return true
    }
    if !scope.scopeID.isEmpty {
        return scope.scopeID == prefix.scope.scopeID
    }
    return scope.modelID == prefix.scope.modelID
}

private func pagedKVPurgeMatches(
    scope: Melix_Worker_V1_CacheScope,
    cacheKey: Melix_Worker_V1_CacheKey,
    prefix: Melix_Worker_V1_PrefixRef
) -> Bool {
    let targetsOneLogicalPrefix = !cacheKey.scopeID.isEmpty
        || !cacheKey.prefixHash.isEmpty
        || !cacheKey.fingerprintHash.isEmpty
    if targetsOneLogicalPrefix {
        var requested = Melix_Worker_V1_PrefixRef()
        requested.scope = scope
        requested.cacheKey = cacheKey
        return CacheLogicalPrefixKey(requested) == CacheLogicalPrefixKey(prefix)
    }
    return pagedKVScopeMatches(scope, prefix: prefix)
}

func pagedKVCacheLayoutIsSupported(_ caches: [KVCache]) -> Bool {
    !caches.isEmpty
        && caches.allSatisfy { cache in
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
        for tokenID in tokenIDs[start..<end] {
            var value = Int64(tokenID).littleEndian
            withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
        }
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}

private func pagedKVHash(_ components: [String]) -> String {
    let encoded = ([String(components.count)] + components).map { component in
        "\(component.utf8.count):\(component)"
    }.joined()
    return SHA256.hash(data: Data(encoded.utf8))
        .prefix(16)
        .map { String(format: "%02x", $0) }
        .joined()
}

private func pagedKVElapsedMicros(since startedAt: TimeInterval) -> Int {
    max(0, Int(((Date.timeIntervalSinceReferenceDate - startedAt) * 1_000_000).rounded()))
}
