import Foundation
import MelixControlPlaneProtocol

public enum SessionGraphStoreError: Error, Equatable {
    case unknownSessionID
    case unknownBranchID
}

public actor SessionGraphStore {
    private var sessions: [String: Melix_Controlplane_V1_SessionState]
    private let metricsStore: MetricsStore?
    private let nowUnixMs: @Sendable () -> Int64
    private let sessionIDGenerator: @Sendable () -> String
    private let branchIDGenerator: @Sendable () -> String

    public init(
        sessions: [Melix_Controlplane_V1_SessionState] = [],
        metricsStore: MetricsStore? = nil,
        nowUnixMs: @escaping @Sendable () -> Int64 = {
            Int64(Date().timeIntervalSince1970 * 1000)
        },
        sessionIDGenerator: @escaping @Sendable () -> String = {
            "session-\(UUID().uuidString)"
        },
        branchIDGenerator: @escaping @Sendable () -> String = {
            "branch-\(UUID().uuidString)"
        }
    ) {
        self.sessions = Dictionary(uniqueKeysWithValues: sessions.map { ($0.sessionID, $0) })
        self.metricsStore = metricsStore
        self.nowUnixMs = nowUnixMs
        self.sessionIDGenerator = sessionIDGenerator
        self.branchIDGenerator = branchIDGenerator
    }

    public func sessionSummaries() -> [Melix_Controlplane_V1_SessionSummary] {
        sessions.values
            .map(Self.summary(from:))
            .sorted { $0.sessionID < $1.sessionID }
    }

    public func state(for sessionID: String) -> Melix_Controlplane_V1_SessionState? {
        sessions[sessionID]
    }

    public func replace(session: Melix_Controlplane_V1_SessionState) async {
        sessions[session.sessionID] = session
        await refreshMetrics()
    }

    public func createSession() async -> Melix_Controlplane_V1_SessionState {
        let timestamp = nowUnixMs()
        let sessionID = uniqueSessionID()

        var branch = Melix_Controlplane_V1_BranchState()
        branch.branchID = "branch-main"
        branch.label = "main"
        branch.createdAtUnixMs = timestamp
        branch.updatedAtUnixMs = timestamp

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = sessionID
        session.branches = [branch]
        session.activeBranchID = branch.branchID
        session.createdAtUnixMs = timestamp
        session.updatedAtUnixMs = timestamp

        sessions[sessionID] = session
        await refreshMetrics()
        return session
    }

    public func createBranch(
        sessionID: String,
        parentBranchID: String
    ) async throws -> Melix_Controlplane_V1_SessionState {
        var session = try requireSession(sessionID)
        let timestamp = nowUnixMs()
        let resolvedParent = parentBranchID.isEmpty ? session.activeBranchID : parentBranchID

        guard let parentIndex = session.branches.firstIndex(where: { $0.branchID == resolvedParent }) else {
            throw SessionGraphStoreError.unknownBranchID
        }

        let parent = session.branches[parentIndex]
        var branch = Melix_Controlplane_V1_BranchState()
        branch.branchID = uniqueBranchID(in: session)
        branch.parentBranchID = resolvedParent
        branch.headRequestID = parent.headRequestID
        branch.headCheckpointID = parent.headCheckpointID
        branch.resumeSnapshotID = parent.resumeSnapshotID
        branch.lastToolCallID = parent.lastToolCallID
        branch.label = branch.branchID
        branch.createdAtUnixMs = timestamp
        branch.updatedAtUnixMs = timestamp
        branch.headCacheKey = parent.headCacheKey

        session.branches.append(branch)
        session.activeBranchID = branch.branchID
        session.updatedAtUnixMs = timestamp
        if !branch.resumeSnapshotID.isEmpty {
            session.latestSnapshotID = branch.resumeSnapshotID
        }
        if !branch.headCheckpointID.isEmpty {
            session.latestCheckpointID = branch.headCheckpointID
        }

        sessions[sessionID] = session
        await refreshMetrics()
        return session
    }

    public func closeSession(sessionID: String) async -> Melix_Controlplane_V1_SessionState? {
        let removed = sessions.removeValue(forKey: sessionID)
        await refreshMetrics()
        return removed
    }

    public func registerToolResult(
        sessionID: String,
        branchID: String,
        toolCallID: String
    ) async throws -> Melix_Controlplane_V1_SessionState {
        try await mutateSession(sessionID: sessionID, preferredBranchID: branchID) { session, branch, timestamp in
            session.activeBranchID = branch.branchID
            session.updatedAtUnixMs = timestamp
            session.latestToolCallID = toolCallID
            branch.lastToolCallID = toolCallID
            branch.updatedAtUnixMs = timestamp
        }
    }

    public func resumeAfterTool(
        sessionID: String,
        branchID: String,
        snapshotID: String
    ) async throws -> Melix_Controlplane_V1_SessionState {
        try await mutateSession(sessionID: sessionID, preferredBranchID: branchID) { session, branch, timestamp in
            session.activeBranchID = branch.branchID
            session.updatedAtUnixMs = timestamp
            session.latestSnapshotID = snapshotID
            branch.resumeSnapshotID = snapshotID
            branch.updatedAtUnixMs = timestamp

            var snapshot = Melix_Controlplane_V1_SnapshotRef()
            snapshot.snapshotID = snapshotID
            snapshot.sessionID = session.sessionID
            snapshot.branchID = branch.branchID
            upsertSnapshot(&session, snapshot: snapshot)
        }
    }

    public func recordRequestStart(
        sessionID: String,
        branchID: String,
        requestID: String
    ) async -> Melix_Controlplane_V1_SessionState {
        var session = ensureSession(sessionID: sessionID, preferredBranchID: branchID)
        let timestamp = nowUnixMs()
        let branchIndex = ensureBranchIndex(in: &session, preferredBranchID: branchID, timestamp: timestamp)
        session.activeBranchID = session.branches[branchIndex].branchID
        session.latestRequestID = requestID
        session.updatedAtUnixMs = timestamp
        session.branches[branchIndex].headRequestID = requestID
        session.branches[branchIndex].updatedAtUnixMs = timestamp
        sessions[sessionID] = session
        await refreshMetrics()
        return session
    }

    public func recordSnapshotHydration(
        sessionID: String,
        branchID: String,
        snapshot: Melix_Controlplane_V1_SnapshotRef,
        headCacheKey: Melix_Controlplane_V1_CacheKey? = nil
    ) async -> Melix_Controlplane_V1_SessionState {
        var session = ensureSession(sessionID: sessionID, preferredBranchID: branchID)
        let timestamp = nowUnixMs()
        let branchIndex = ensureBranchIndex(in: &session, preferredBranchID: branchID, timestamp: timestamp)
        let resolvedBranchID = session.branches[branchIndex].branchID

        session.activeBranchID = resolvedBranchID
        session.updatedAtUnixMs = timestamp
        if !snapshot.requestID.isEmpty {
            session.latestRequestID = snapshot.requestID
            session.branches[branchIndex].headRequestID = snapshot.requestID
        }
        if !snapshot.snapshotID.isEmpty {
            session.latestSnapshotID = snapshot.snapshotID
            session.branches[branchIndex].resumeSnapshotID = snapshot.snapshotID
        }
        if !snapshot.checkpointID.isEmpty {
            session.latestCheckpointID = snapshot.checkpointID
            session.branches[branchIndex].headCheckpointID = snapshot.checkpointID
        }
        if let headCacheKey {
            session.branches[branchIndex].headCacheKey = headCacheKey
        }
        session.branches[branchIndex].updatedAtUnixMs = timestamp

        var normalizedSnapshot = snapshot
        normalizedSnapshot.sessionID = session.sessionID
        normalizedSnapshot.branchID = resolvedBranchID
        upsertSnapshot(&session, snapshot: normalizedSnapshot)

        sessions[sessionID] = session
        await refreshMetrics()
        return session
    }

    private static func summary(
        from state: Melix_Controlplane_V1_SessionState
    ) -> Melix_Controlplane_V1_SessionSummary {
        var summary = Melix_Controlplane_V1_SessionSummary()
        summary.sessionID = state.sessionID
        summary.activeBranchID = state.activeBranchID
        summary.branchCount = UInt32(state.branches.count)
        summary.latestRequestID = state.latestRequestID
        summary.latestSnapshotID = state.latestSnapshotID
        return summary
    }

    private func requireSession(_ sessionID: String) throws -> Melix_Controlplane_V1_SessionState {
        guard let session = sessions[sessionID] else {
            throw SessionGraphStoreError.unknownSessionID
        }
        return session
    }

    private func ensureSession(
        sessionID: String,
        preferredBranchID: String
    ) -> Melix_Controlplane_V1_SessionState {
        if let existing = sessions[sessionID] {
            return existing
        }

        let timestamp = nowUnixMs()
        let rootBranchID = preferredBranchID.isEmpty ? "branch-main" : preferredBranchID

        var branch = Melix_Controlplane_V1_BranchState()
        branch.branchID = rootBranchID
        branch.label = rootBranchID == "branch-main" ? "main" : rootBranchID
        branch.createdAtUnixMs = timestamp
        branch.updatedAtUnixMs = timestamp

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = sessionID
        session.branches = [branch]
        session.activeBranchID = rootBranchID
        session.createdAtUnixMs = timestamp
        session.updatedAtUnixMs = timestamp
        return session
    }

    private func ensureBranchIndex(
        in session: inout Melix_Controlplane_V1_SessionState,
        preferredBranchID: String,
        timestamp: Int64
    ) -> Int {
        let requestedBranchID = preferredBranchID.isEmpty ? session.activeBranchID : preferredBranchID
        if let existing = session.branches.firstIndex(where: { $0.branchID == requestedBranchID }) {
            return existing
        }

        let parentBranchID = session.activeBranchID
        var branch = Melix_Controlplane_V1_BranchState()
        branch.branchID = requestedBranchID
        branch.parentBranchID = parentBranchID
        branch.label = requestedBranchID
        branch.createdAtUnixMs = timestamp
        branch.updatedAtUnixMs = timestamp
        if let parent = session.branches.first(where: { $0.branchID == parentBranchID }) {
            branch.headRequestID = parent.headRequestID
            branch.headCheckpointID = parent.headCheckpointID
            branch.resumeSnapshotID = parent.resumeSnapshotID
            branch.lastToolCallID = parent.lastToolCallID
            branch.headCacheKey = parent.headCacheKey
        }
        session.branches.append(branch)
        return session.branches.endIndex - 1
    }

    private func mutateSession(
        sessionID: String,
        preferredBranchID: String,
        update: (
            inout Melix_Controlplane_V1_SessionState,
            inout Melix_Controlplane_V1_BranchState,
            Int64
        ) -> Void
    ) async throws -> Melix_Controlplane_V1_SessionState {
        var session = try requireSession(sessionID)
        let timestamp = nowUnixMs()
        let branchID = preferredBranchID.isEmpty ? session.activeBranchID : preferredBranchID

        guard let branchIndex = session.branches.firstIndex(where: { $0.branchID == branchID }) else {
            throw SessionGraphStoreError.unknownBranchID
        }

        var branch = session.branches[branchIndex]
        update(&session, &branch, timestamp)
        session.branches[branchIndex] = branch
        sessions[sessionID] = session
        await refreshMetrics()
        return session
    }

    private func upsertSnapshot(
        _ session: inout Melix_Controlplane_V1_SessionState,
        snapshot: Melix_Controlplane_V1_SnapshotRef
    ) {
        guard !snapshot.snapshotID.isEmpty else {
            return
        }

        if let index = session.availableSnapshots.firstIndex(where: { $0.snapshotID == snapshot.snapshotID }) {
            session.availableSnapshots[index] = snapshot
        } else {
            session.availableSnapshots.append(snapshot)
        }
    }

    private func uniqueSessionID() -> String {
        var candidate = sessionIDGenerator()
        var index = 1
        while sessions[candidate] != nil {
            candidate = "\(candidate)-\(index)"
            index += 1
        }
        return candidate
    }

    private func uniqueBranchID(in session: Melix_Controlplane_V1_SessionState) -> String {
        var candidate = branchIDGenerator()
        var index = 1
        while session.branches.contains(where: { $0.branchID == candidate }) {
            candidate = "\(candidate)-\(index)"
            index += 1
        }
        return candidate
    }

    private func refreshMetrics() async {
        guard let metricsStore else {
            return
        }

        let sessionCount = Double(sessions.count)
        let branchCount = Double(sessions.values.reduce(0) { $0 + $1.branches.count })
        let resumeSnapshotCount = Double(
            sessions.values.reduce(0) { partial, session in
                partial + session.branches.filter { !$0.resumeSnapshotID.isEmpty }.count
            }
        )
        let activeBranchChanges = Double(
            sessions.values.reduce(0) { partial, session in
                partial + (session.activeBranchID.isEmpty ? 0 : 1)
            }
        )

        await metricsStore.set(sessionCount, forKey: "session_graph.session_count")
        await metricsStore.set(branchCount, forKey: "session_graph.branch_count")
        await metricsStore.set(resumeSnapshotCount, forKey: "session_graph.resume_snapshot_count")
        await metricsStore.set(activeBranchChanges, forKey: "session_graph.active_branch_changes")
    }
}
