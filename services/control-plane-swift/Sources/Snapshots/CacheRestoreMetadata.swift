import MelixControlPlaneProtocol
import MelixWorkerProtocol

func makeControlPlaneRestorePlan(
    from workerPlan: Melix_Worker_V1_CacheRestorePlan
) -> Melix_Controlplane_V1_CacheRestorePlan {
    var plan = Melix_Controlplane_V1_CacheRestorePlan()
    plan.planID = workerPlan.planID
    plan.boundary = makeControlPlaneRestoreBoundary(from: workerPlan.boundary)
    plan.blockTable = makeControlPlaneBlockTable(
        from: workerPlan.blockTable,
        blockTableID: workerPlan.blockTableID
    )
    plan.restoredTokenCount = workerPlan.restoredTokenCount
    plan.partial = workerPlan.partial
    plan.tier = workerPlan.tier
    plan.cacheMode = makeControlPlaneCacheMode(from: workerPlan.cacheMode)
    return plan
}

func makeControlPlaneRestoreBoundary(
    from workerBoundary: Melix_Worker_V1_RestoreBoundaryRef
) -> Melix_Controlplane_V1_CacheRestoreBoundary {
    var boundary = Melix_Controlplane_V1_CacheRestoreBoundary()
    boundary.snapshot = makeControlPlaneSnapshotRef(from: workerBoundary.snapshot)
    boundary.prefixHash = workerBoundary.cacheKey.prefixHash
    boundary.scopeID = workerBoundary.scopeID
    boundary.boundaryKind = workerBoundary.boundaryKind
    return boundary
}

func makeControlPlaneBlockTable(
    from workerTable: Melix_Worker_V1_BlockTable,
    blockTableID: String
) -> Melix_Controlplane_V1_BlockTable {
    var table = Melix_Controlplane_V1_BlockTable()
    table.blockTableID = blockTableID
    table.blocks = workerTable.blocks.map(makeControlPlaneCacheBlockRef(from:))
    table.pages = workerTable.pages.map(makeControlPlanePageRef(from:))
    table.prefixHash = workerTable.cacheKey.prefixHash
    table.scopeID = workerTable.scopeID.isEmpty ? workerTable.cacheKey.scopeID : workerTable.scopeID
    table.totalTokenCount = workerTable.totalTokenCount
    return table
}

func makeControlPlanePageRef(
    from workerPage: Melix_Worker_V1_PageRef
) -> Melix_Controlplane_V1_PageRef {
    var page = Melix_Controlplane_V1_PageRef()
    page.pageID = workerPage.pageID
    page.blockIds = workerPage.blockIds
    page.tokenStart = workerPage.tokenStart
    page.tokenEnd = workerPage.tokenEnd
    page.bytes = workerPage.bytes
    return page
}

private func makeControlPlaneSnapshotRef(
    from workerSnapshot: Melix_Worker_V1_SnapshotRef
) -> Melix_Controlplane_V1_SnapshotRef {
    var snapshot = Melix_Controlplane_V1_SnapshotRef()
    snapshot.snapshotID = workerSnapshot.snapshotID
    snapshot.tokenBoundary = workerSnapshot.tokenBoundary
    snapshot.requestID = workerSnapshot.requestID
    snapshot.sessionID = workerSnapshot.sessionID
    snapshot.branchID = workerSnapshot.branchID
    snapshot.checkpointID = workerSnapshot.checkpointID
    return snapshot
}

private func makeControlPlaneCacheBlockRef(
    from workerBlock: Melix_Worker_V1_BlockRef
) -> Melix_Controlplane_V1_CacheBlockRef {
    var block = Melix_Controlplane_V1_CacheBlockRef()
    block.blockID = workerBlock.blockID
    block.tokenLength = UInt32(max(workerBlock.tokenEnd - workerBlock.tokenStart, 0))
    block.bytes = workerBlock.bytes
    return block
}
