import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

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
