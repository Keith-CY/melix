import MelixControlPlaneProtocol

public actor CacheMetadataStore {
    private var snapshot: Melix_Controlplane_V1_CacheSnapshot

    public init(snapshot: Melix_Controlplane_V1_CacheSnapshot = CacheMetadataStore.emptySnapshot()) {
        self.snapshot = snapshot
    }

    public func cacheSnapshot() -> Melix_Controlplane_V1_CacheSnapshot {
        snapshot
    }

    public func cacheSummary() -> Melix_Controlplane_V1_CacheSummary {
        snapshot.summary
    }

    public func replace(snapshot: Melix_Controlplane_V1_CacheSnapshot) {
        self.snapshot = snapshot
    }

    public static func emptySnapshot() -> Melix_Controlplane_V1_CacheSnapshot {
        var snapshot = Melix_Controlplane_V1_CacheSnapshot()
        snapshot.summary = emptySummary()
        return snapshot
    }

    public static func emptySummary() -> Melix_Controlplane_V1_CacheSummary {
        var summary = Melix_Controlplane_V1_CacheSummary()
        summary.l1Bytes = 0
        summary.l2Bytes = 0
        summary.l1HitRate = 0
        summary.l2HitRate = 0
        summary.dedupRatio = 0
        summary.pinnedPrefixHitRate = 0
        summary.checkpointCount = 0
        summary.blockCount = 0
        summary.quantizedBytes = 0
        summary.compressionRatio = 0
        summary.l2RestoreHitRate = 0
        return summary
    }
}
