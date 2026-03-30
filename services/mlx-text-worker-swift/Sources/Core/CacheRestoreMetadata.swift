import MelixWorkerProtocol

func resolvedRestoreSnapshotID(
    from request: Melix_Worker_V1_RestoreBoundarySnapshotRequest
) -> String {
    if !request.snapshotID.isEmpty {
        return request.snapshotID
    }
    return request.restoreBoundary.snapshot.snapshotID
}

func makeRestoreBoundaryRef(
    snapshot: Melix_Worker_V1_SnapshotRef,
    blockTable: Melix_Worker_V1_BlockTable
) -> Melix_Worker_V1_RestoreBoundaryRef {
    var boundary = Melix_Worker_V1_RestoreBoundaryRef()
    boundary.snapshot = snapshot
    boundary.cacheKey = blockTable.cacheKey
    boundary.scopeID = effectiveScopeID(for: blockTable)
    boundary.boundaryKind = "boundary_snapshot"
    return boundary
}

func makeCacheRestorePlan(
    snapshot: Melix_Worker_V1_SnapshotRef,
    blockTableID: String,
    blockTable: Melix_Worker_V1_BlockTable,
    tier: String,
    partial: Bool = false
) -> Melix_Worker_V1_CacheRestorePlan {
    let normalizedTable = normalizedBlockTable(blockTable)

    var plan = Melix_Worker_V1_CacheRestorePlan()
    plan.planID = blockTableID.isEmpty ? "restore-\(snapshot.snapshotID)" : "restore-\(blockTableID)"
    plan.boundary = makeRestoreBoundaryRef(snapshot: snapshot, blockTable: normalizedTable)
    plan.blockTableID = blockTableID
    plan.blockTable = normalizedTable
    plan.pages = normalizedTable.pages
    plan.restoredTokenCount = normalizedTable.totalTokenCount
    plan.partial = partial
    plan.tier = tier
    return plan
}

func normalizedBlockTable(
    _ blockTable: Melix_Worker_V1_BlockTable
) -> Melix_Worker_V1_BlockTable {
    var normalized = blockTable
    if normalized.pages.isEmpty {
        normalized.pages = makePageRefs(from: normalized.blocks)
    }
    if normalized.totalTokenCount == 0 {
        normalized.totalTokenCount = normalized.blocks.reduce(0) { partial, block in
            max(partial, UInt32(max(block.tokenEnd, 0)))
        }
    }
    if normalized.scopeID.isEmpty {
        normalized.scopeID = normalized.cacheKey.scopeID
    }
    return normalized
}

func makePageRefs(
    from blocks: [Melix_Worker_V1_BlockRef]
) -> [Melix_Worker_V1_PageRef] {
    blocks.map { block in
        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-\(block.blockID)"
        page.blockIds = [block.blockID]
        page.tokenStart = UInt32(max(block.tokenStart, 0))
        page.tokenEnd = UInt32(max(block.tokenEnd, 0))
        page.bytes = block.bytes
        return page
    }
}

private func effectiveScopeID(
    for blockTable: Melix_Worker_V1_BlockTable
) -> String {
    if !blockTable.scopeID.isEmpty {
        return blockTable.scopeID
    }
    return blockTable.cacheKey.scopeID
}
