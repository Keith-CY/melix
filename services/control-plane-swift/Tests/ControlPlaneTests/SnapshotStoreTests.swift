import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Snapshot Stores")
struct SnapshotStoreTests {
    @Test("cache metadata store defaults to an empty typed snapshot")
    func cacheMetadataStoreDefaultsToEmptySnapshot() async {
        let store = CacheMetadataStore()

        let snapshot = await store.cacheSnapshot()
        let summary = await store.cacheSummary()

        #expect(snapshot.summary.blockCount == 0)
        #expect(snapshot.summary.quantizedBytes == 0)
        #expect(snapshot.summary.compressionRatio == 0)
        #expect(summary.blockCount == 0)
        #expect(summary.l2RestoreHitRate == 0)
    }

    @Test("cache metadata store replaces the live snapshot")
    func cacheMetadataStoreReplacesSnapshot() async {
        let store = CacheMetadataStore()
        var snapshot = Melix_Controlplane_V1_CacheSnapshot()
        snapshot.summary.l1Bytes = 128
        snapshot.summary.blockCount = 3
        snapshot.summary.quantizedBytes = 64

        await store.replace(snapshot: snapshot)

        let updated = await store.cacheSnapshot()
        #expect(updated.summary.l1Bytes == 128)
        #expect(updated.summary.blockCount == 3)
        #expect(updated.summary.quantizedBytes == 64)
    }

    @Test("cache metadata store preserves restore plans across replacements and trims appended plans")
    func cacheMetadataStorePreservesAndTrimsRestorePlans() async {
        var existingSnapshot = Melix_Controlplane_V1_CacheSnapshot()
        existingSnapshot.recentRestorePlans = (0..<10).map { index in
            var plan = Melix_Controlplane_V1_CacheRestorePlan()
            plan.planID = "existing-\(index)"
            plan.restoredTokenCount = UInt32(index)
            return plan
        }
        let store = CacheMetadataStore(snapshot: existingSnapshot)

        var replacement = Melix_Controlplane_V1_CacheSnapshot()
        replacement.summary.blockCount = 4
        await store.replace(snapshot: replacement)

        var latest = Melix_Controlplane_V1_CacheRestorePlan()
        latest.planID = "latest"
        latest.restoredTokenCount = 99
        await store.appendRecentRestorePlan(latest)

        let snapshot = await store.cacheSnapshot()
        #expect(snapshot.summary.blockCount == 4)
        #expect(snapshot.recentRestorePlans.count == 10)
        #expect(snapshot.recentRestorePlans.first?.planID == "latest")
        #expect(snapshot.recentRestorePlans.last?.planID == "existing-8")
    }

    @Test("session graph store exposes sorted summaries and session state")
    func sessionGraphStoreExposesSortedSummaries() async {
        let store = SessionGraphStore(sessions: [makeSessionState(id: "session-b"), makeSessionState(id: "session-a")])

        let summaries = await store.sessionSummaries()
        let state = await store.state(for: "session-b")

        #expect(summaries.map(\.sessionID) == ["session-a", "session-b"])
        #expect(summaries.last?.branchCount == 2)
        #expect(summaries.last?.latestSnapshotID == "snap-session-b")
        #expect(state?.activeBranchID == "branch-main")
        #expect(state?.availableSnapshots.first?.sessionID == "session-b")
    }

    @Test("session graph store replaces session state by identifier")
    func sessionGraphStoreReplacesState() async {
        let store = SessionGraphStore(sessions: [makeSessionState(id: "session-1")])
        var replacement = makeSessionState(id: "session-1")
        replacement.activeBranchID = "branch-alt"
        replacement.latestRequestID = "req-updated"

        await store.replace(session: replacement)

        let state = await store.state(for: "session-1")
        #expect(state?.activeBranchID == "branch-alt")
        #expect(state?.latestRequestID == "req-updated")
    }

    @Test("session graph store creates sessions and derived branches with lineage metadata")
    func sessionGraphStoreCreatesSessionsAndBranches() async throws {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(
            metricsStore: metricsStore,
            nowUnixMs: { 1_000 },
            sessionIDGenerator: { "session-created" },
            branchIDGenerator: { "branch-derived" }
        )

        let session = await store.createSession()
        let branched = try await store.createBranch(sessionID: session.sessionID, parentBranchID: "branch-main")
        let metrics = await metricsStore.snapshot()

        #expect(session.sessionID == "session-created")
        #expect(session.activeBranchID == "branch-main")
        #expect(branched.activeBranchID == "branch-derived")
        #expect(branched.branches.count == 2)
        #expect(branched.branches.last?.parentBranchID == "branch-main")
        #expect(metrics.values["session_graph.session_count"] == 1)
        #expect(metrics.values["session_graph.branch_count"] == 2)
    }

    @Test("session graph store tracks tool and resume metadata")
    func sessionGraphStoreTracksToolAndResumeMetadata() async throws {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(
            metricsStore: metricsStore,
            nowUnixMs: { 2_000 },
            sessionIDGenerator: { "session-stateful" }
        )
        _ = await store.createSession()

        let withTool = try await store.registerToolResult(
            sessionID: "session-stateful",
            branchID: "branch-main",
            toolCallID: "tool-123"
        )
        let resumed = try await store.resumeAfterTool(
            sessionID: "session-stateful",
            branchID: "branch-main",
            snapshotID: "snap-resume"
        )
        let metrics = await metricsStore.snapshot()

        #expect(withTool.latestToolCallID == "tool-123")
        #expect(withTool.branches.first?.lastToolCallID == "tool-123")
        #expect(resumed.latestSnapshotID == "snap-resume")
        #expect(resumed.branches.first?.resumeSnapshotID == "snap-resume")
        #expect(resumed.availableSnapshots.first?.snapshotID == "snap-resume")
        #expect(metrics.values["session_graph.resume_snapshot_count"] == 1)
    }

    @Test("session graph store rejects unknown session and branch mutations")
    func sessionGraphStoreRejectsUnknownMutations() async throws {
        let store = SessionGraphStore(
            sessions: [makeSessionState(id: "session-1")],
            nowUnixMs: { 4_000 }
        )

        await #expect(throws: SessionGraphStoreError.unknownSessionID) {
            _ = try await store.createBranch(sessionID: "missing-session", parentBranchID: "branch-main")
        }
        await #expect(throws: SessionGraphStoreError.unknownBranchID) {
            _ = try await store.createBranch(sessionID: "session-1", parentBranchID: "branch-missing")
        }
        await #expect(throws: SessionGraphStoreError.unknownSessionID) {
            _ = try await store.registerToolResult(
                sessionID: "missing-session",
                branchID: "branch-main",
                toolCallID: "tool-missing"
            )
        }
        await #expect(throws: SessionGraphStoreError.unknownBranchID) {
            _ = try await store.resumeAfterTool(
                sessionID: "session-1",
                branchID: "branch-missing",
                snapshotID: "snap-missing"
            )
        }
    }

    @Test("session graph store deduplicates generated identifiers and closing updates metrics")
    func sessionGraphStoreDeduplicatesGeneratedIdentifiers() async throws {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(
            sessions: [makeSessionState(id: "session-fixed")],
            metricsStore: metricsStore,
            nowUnixMs: { 5_000 },
            sessionIDGenerator: { "session-fixed" },
            branchIDGenerator: { "branch-main" }
        )

        let created = await store.createSession()
        let branched = try await store.createBranch(
            sessionID: "session-fixed",
            parentBranchID: "branch-main"
        )
        let closed = await store.closeSession(sessionID: "session-fixed")
        let missing = await store.closeSession(sessionID: "missing-session")
        let metrics = await metricsStore.snapshot()

        #expect(created.sessionID == "session-fixed-1")
        #expect(branched.activeBranchID == "branch-main-1")
        #expect(closed?.sessionID == "session-fixed")
        #expect(missing == nil)
        #expect(metrics.values["session_graph.session_count"] == 1)
        #expect(metrics.values["session_graph.branch_count"] == 1)
    }

    @Test("session graph store hydrates request and snapshot metadata for missing sessions")
    func sessionGraphStoreHydratesRequestAndSnapshotMetadata() async {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(metricsStore: metricsStore, nowUnixMs: { 3_000 })

        let started = await store.recordRequestStart(
            sessionID: "session-hydrated",
            branchID: "branch-review",
            requestID: "req-hydrated"
        )

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-hydrated"
        snapshot.requestID = "req-hydrated"
        snapshot.checkpointID = "ckpt-hydrated"

        let hydrated = await store.recordSnapshotHydration(
            sessionID: "session-hydrated",
            branchID: "branch-review",
            snapshot: snapshot
        )
        let metrics = await metricsStore.snapshot()

        #expect(started.activeBranchID == "branch-review")
        #expect(started.branches.first?.branchID == "branch-review")
        #expect(hydrated.latestRequestID == "req-hydrated")
        #expect(hydrated.latestSnapshotID == "snap-hydrated")
        #expect(hydrated.latestCheckpointID == "ckpt-hydrated")
        #expect(hydrated.branches.first?.headRequestID == "req-hydrated")
        #expect(hydrated.availableSnapshots.first?.branchID == "branch-review")
        #expect(metrics.values["session_graph.active_branch_changes"] == 1)
    }

    @Test("session graph store refreshes existing snapshots and branch cache keys")
    func sessionGraphStoreRefreshesExistingSnapshots() async {
        let store = SessionGraphStore(
            sessions: [makeSessionState(id: "session-1")],
            nowUnixMs: { 6_000 }
        )

        var scope = Melix_Controlplane_V1_CacheScopeKey()
        scope.modelID = "melix-dev-text"
        scope.tokenizerHash = "tok-v2"

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.scope = scope

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-session-1"
        snapshot.requestID = "req-refresh"
        snapshot.checkpointID = "ckpt-refresh"

        let hydrated = await store.recordSnapshotHydration(
            sessionID: "session-1",
            branchID: "branch-main",
            snapshot: snapshot,
            headCacheKey: cacheKey
        )

        #expect(hydrated.availableSnapshots.count == 1)
        #expect(hydrated.availableSnapshots.first?.requestID == "req-refresh")
        #expect(hydrated.branches.first?.headCacheKey.scope.tokenizerHash == "tok-v2")
        #expect(hydrated.latestCheckpointID == "ckpt-refresh")
    }

    @Test("control-plane restore metadata bridges worker restore plans")
    func controlPlaneRestoreMetadataBridgesWorkerPlans() throws {
        var cacheKey = Melix_Worker_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA, 0xBB])
        cacheKey.scopeID = "scope-worker"

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-0"
        block.tokenStart = 0
        block.tokenEnd = 16
        block.bytes = 1024

        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-0"
        page.blockIds = ["blk-0"]
        page.tokenStart = 0
        page.tokenEnd = 16
        page.bytes = 1024

        var table = Melix_Worker_V1_BlockTable()
        table.blocks = [block]
        table.cacheKey = cacheKey
        table.scopeID = "scope-worker"
        table.pages = [page]
        table.totalTokenCount = 16

        var snapshot = Melix_Worker_V1_SnapshotRef()
        snapshot.snapshotID = "snap-1"
        snapshot.requestID = "req-1"
        snapshot.sessionID = "session-1"
        snapshot.branchID = "branch-main"
        snapshot.tokenBoundary = 16

        var boundary = Melix_Worker_V1_RestoreBoundaryRef()
        boundary.snapshot = snapshot
        boundary.cacheKey = cacheKey
        boundary.scopeID = "scope-worker"
        boundary.boundaryKind = "boundary_snapshot"

        var workerPlan = Melix_Worker_V1_CacheRestorePlan()
        workerPlan.planID = "restore-bt-1"
        workerPlan.boundary = boundary
        workerPlan.blockTableID = "bt-1"
        workerPlan.blockTable = table
        workerPlan.pages = [page]
        workerPlan.restoredTokenCount = 16
        workerPlan.partial = false
        workerPlan.tier = "l2"

        let controlPlan = makeControlPlaneRestorePlan(from: workerPlan)
        let decoded = try Melix_Controlplane_V1_CacheRestorePlan(
            serializedBytes: controlPlan.serializedData()
        )

        #expect(decoded.planID == "restore-bt-1")
        #expect(decoded.boundary.snapshot.snapshotID == "snap-1")
        #expect(decoded.boundary.scopeID == "scope-worker")
        #expect(decoded.blockTable.blockTableID == "bt-1")
        #expect(decoded.blockTable.pages.first?.pageID == "page-0")
        #expect(decoded.blockTable.totalTokenCount == 16)
        #expect(decoded.tier == "l2")
    }

    @Test("control-plane restore metadata preserves copy-on-write block and page identifiers")
    func controlPlaneRestoreMetadataPreservesCopyOnWriteIdentifiers() throws {
        var cacheKey = Melix_Worker_V1_CacheKey()
        cacheKey.prefixHash = Data([0xCC])
        cacheKey.scopeID = "scope-cow"

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-0::cow-snap-1"
        block.tokenStart = 0
        block.tokenEnd = 16
        block.bytes = 1024

        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-blk-0::cow-snap-1"
        page.blockIds = ["blk-0::cow-snap-1"]
        page.tokenStart = 0
        page.tokenEnd = 16
        page.bytes = 1024

        var table = Melix_Worker_V1_BlockTable()
        table.blocks = [block]
        table.cacheKey = cacheKey
        table.scopeID = "scope-cow"
        table.pages = [page]
        table.totalTokenCount = 16

        var snapshot = Melix_Worker_V1_SnapshotRef()
        snapshot.snapshotID = "snap-cow"

        var boundary = Melix_Worker_V1_RestoreBoundaryRef()
        boundary.snapshot = snapshot
        boundary.cacheKey = cacheKey
        boundary.scopeID = "scope-cow"
        boundary.boundaryKind = "boundary_snapshot"

        var workerPlan = Melix_Worker_V1_CacheRestorePlan()
        workerPlan.planID = "restore-bt-cow"
        workerPlan.boundary = boundary
        workerPlan.blockTableID = "bt-1::cow-snap-1"
        workerPlan.blockTable = table
        workerPlan.pages = [page]
        workerPlan.restoredTokenCount = 16
        workerPlan.tier = "l2"

        let controlPlan = makeControlPlaneRestorePlan(from: workerPlan)

        #expect(controlPlan.blockTable.blockTableID == "bt-1::cow-snap-1")
        #expect(controlPlan.blockTable.blocks.first?.blockID == "blk-0::cow-snap-1")
        #expect(controlPlan.blockTable.pages.first?.pageID == "page-blk-0::cow-snap-1")
        #expect(controlPlan.blockTable.pages.first?.blockIds == ["blk-0::cow-snap-1"])
    }

    private func makeSessionState(id: String) -> Melix_Controlplane_V1_SessionState {
        var scope = Melix_Controlplane_V1_CacheScopeKey()
        scope.modelID = "melix-dev-text"

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.scope = scope

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-\(id)"
        snapshot.sessionID = id
        snapshot.branchID = "branch-main"

        var mainBranch = Melix_Controlplane_V1_BranchState()
        mainBranch.branchID = "branch-main"
        mainBranch.headRequestID = "req-\(id)"
        mainBranch.resumeSnapshotID = snapshot.snapshotID
        mainBranch.headCacheKey = cacheKey

        var altBranch = Melix_Controlplane_V1_BranchState()
        altBranch.branchID = "branch-alt"
        altBranch.parentBranchID = "branch-main"
        altBranch.headRequestID = "req-alt-\(id)"

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = id
        session.activeBranchID = "branch-main"
        session.latestRequestID = "req-\(id)"
        session.latestSnapshotID = snapshot.snapshotID
        session.branches = [mainBranch, altBranch]
        session.availableSnapshots = [snapshot]
        return session
    }
}
