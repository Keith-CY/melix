import MelixControlPlaneProtocol

public actor SessionGraphStore {
    private var sessions: [String: Melix_Controlplane_V1_SessionState]

    public init(sessions: [Melix_Controlplane_V1_SessionState] = []) {
        self.sessions = Dictionary(uniqueKeysWithValues: sessions.map { ($0.sessionID, $0) })
    }

    public func sessionSummaries() -> [Melix_Controlplane_V1_SessionSummary] {
        sessions.values
            .map(Self.summary(from:))
            .sorted { $0.sessionID < $1.sessionID }
    }

    public func state(for sessionID: String) -> Melix_Controlplane_V1_SessionState? {
        sessions[sessionID]
    }

    public func replace(session: Melix_Controlplane_V1_SessionState) {
        sessions[session.sessionID] = session
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
}
