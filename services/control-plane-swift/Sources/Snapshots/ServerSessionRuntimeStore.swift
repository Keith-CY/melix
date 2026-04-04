import Foundation
import MelixControlPlaneProtocol

public actor ServerSessionRuntimeStore {
    public static let defaultServerSessionID = "server-session-1"

    private let nowUnixMS: @Sendable () -> Int64
    private var runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState]

    public init(
        runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = [],
        nowUnixMS: @escaping @Sendable () -> Int64 = {
            Int64(Date().timeIntervalSince1970 * 1000)
        }
    ) {
        self.nowUnixMS = nowUnixMS
        if runtimeSessions.isEmpty {
            self.runtimeSessions = [Self.defaultRuntimeSession(updatedAtUnixMS: nowUnixMS())]
        } else {
            self.runtimeSessions = runtimeSessions
        }
    }

    public func snapshot() -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        runtimeSessions
    }

    @discardableResult
    public func noteGatewayAccessApplied(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        var session = runtimeSessions.first ?? Self.defaultRuntimeSession(updatedAtUnixMS: nowUnixMS())
        if !serverSessionID.isEmpty {
            session.serverSessionID = serverSessionID
        }
        session.lifecycleState = .ready
        session.powerState = .active
        session.wakeReason = .policyApply
        session.updatedAtUnixMs = nowUnixMS()
        runtimeSessions = [session]
        return runtimeSessions
    }

    public static func defaultRuntimeSession(
        serverSessionID: String = defaultServerSessionID,
        updatedAtUnixMS: Int64
    ) -> Melix_Controlplane_V1_ServerSessionRuntimeState {
        var session = Melix_Controlplane_V1_ServerSessionRuntimeState()
        session.serverSessionID = serverSessionID
        session.lifecycleState = .ready
        session.powerState = .active
        session.wakeReason = .initialBoot
        session.idleTimerSeconds = 0
        session.autoSleepEnabled = false
        session.lightSleepAfterSeconds = 300
        session.deepSleepAfterSeconds = 1800
        session.updatedAtUnixMs = updatedAtUnixMS
        return session
    }
}
