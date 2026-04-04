import Foundation
import MelixControlPlaneProtocol

public actor ServerSessionRuntimeStore {
    public static let defaultServerSessionID = "server-session-1"

    private let nowUnixMS: @Sendable () -> Int64
    private var runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState]
    private var lastActivityAtUnixMSByServerSessionID: [String: Int64]
    private var activeRequestInhibitedSessions: Set<String>

    public init(
        runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = [],
        nowUnixMS: @escaping @Sendable () -> Int64 = {
            Int64(Date().timeIntervalSince1970 * 1000)
        }
    ) {
        self.nowUnixMS = nowUnixMS
        let seededSessions = runtimeSessions.isEmpty
            ? [Self.defaultRuntimeSession(updatedAtUnixMS: nowUnixMS())]
            : runtimeSessions
        self.runtimeSessions = seededSessions
        self.lastActivityAtUnixMSByServerSessionID = Dictionary(
            uniqueKeysWithValues: seededSessions.map { session in
                (session.serverSessionID, session.updatedAtUnixMs)
            }
        )
        self.activeRequestInhibitedSessions = []
    }

    public func snapshot(
        hasActiveRequests: Bool = false
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        resolveIdlePolicy(hasActiveRequests: hasActiveRequests)
        return runtimeSessions
    }

    @discardableResult
    public func noteGatewayAccessApplied(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        mutate(serverSessionID: serverSessionID) { session, now in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .policyApply
            session.idleTimerSeconds = 0
            session.updatedAtUnixMs = now
        }
    }

    @discardableResult
    public func noteRequestActivity(
        serverSessionID: String = defaultServerSessionID,
        wakeReason: Melix_Controlplane_V1_ServerWakeReason = .requestActivity
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        mutate(serverSessionID: serverSessionID) { session, now in
            guard session.lifecycleState != .stopped else {
                session.idleTimerSeconds = 0
                return
            }
            if session.lifecycleState == .sleeping || session.lifecycleState == .paused || session.powerState != .active {
                session.lifecycleState = .ready
                session.powerState = .active
                session.wakeReason = wakeReason
                session.updatedAtUnixMs = now
            }
            session.idleTimerSeconds = 0
        }
    }

    @discardableResult
    public func startServerSession(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        activate(serverSessionID: serverSessionID, wakeReason: .operatorResume)
    }

    @discardableResult
    public func pauseServerSession(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        mutate(serverSessionID: serverSessionID) { session, now in
            session.lifecycleState = .paused
            session.powerState = .active
            session.idleTimerSeconds = 0
            session.updatedAtUnixMs = now
        }
    }

    @discardableResult
    public func resumeServerSession(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        activate(serverSessionID: serverSessionID, wakeReason: .operatorResume)
    }

    @discardableResult
    public func wakeServerSession(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        activate(serverSessionID: serverSessionID, wakeReason: .operatorResume)
    }

    @discardableResult
    public func stopServerSession(
        serverSessionID: String
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        mutate(serverSessionID: serverSessionID) { session, now in
            session.lifecycleState = .stopped
            session.powerState = .stopped
            session.idleTimerSeconds = 0
            session.updatedAtUnixMs = now
        }
    }

    @discardableResult
    public func updateIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        mutate(serverSessionID: serverSessionID) { session, now in
            session.autoSleepEnabled = autoSleepEnabled
            session.lightSleepAfterSeconds = lightSleepAfterSeconds
            session.deepSleepAfterSeconds = deepSleepAfterSeconds
            session.idleTimerSeconds = 0
            session.updatedAtUnixMs = now
        }
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

    @discardableResult
    private func activate(
        serverSessionID: String,
        wakeReason: Melix_Controlplane_V1_ServerWakeReason
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        mutate(serverSessionID: serverSessionID) { session, now in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = wakeReason
            session.idleTimerSeconds = 0
            session.updatedAtUnixMs = now
        }
    }

    @discardableResult
    private func mutate(
        serverSessionID: String,
        update: (inout Melix_Controlplane_V1_ServerSessionRuntimeState, Int64) -> Void
    ) -> [Melix_Controlplane_V1_ServerSessionRuntimeState] {
        let now = nowUnixMS()
        let index = ensureRuntimeSessionIndex(
            serverSessionID: resolvedServerSessionID(serverSessionID),
            updatedAtUnixMS: now
        )
        let resolvedServerSessionID = runtimeSessions[index].serverSessionID
        lastActivityAtUnixMSByServerSessionID[resolvedServerSessionID] = now
        update(&runtimeSessions[index], now)
        return runtimeSessions
    }

    private func ensureRuntimeSessionIndex(
        serverSessionID: String,
        updatedAtUnixMS: Int64
    ) -> Int {
        if let existingIndex = runtimeSessions.firstIndex(where: { $0.serverSessionID == serverSessionID }) {
            return existingIndex
        }
        let session = Self.defaultRuntimeSession(
            serverSessionID: serverSessionID,
            updatedAtUnixMS: updatedAtUnixMS
        )
        runtimeSessions.append(session)
        lastActivityAtUnixMSByServerSessionID[serverSessionID] = updatedAtUnixMS
        return runtimeSessions.count - 1
    }

    private func resolvedServerSessionID(_ serverSessionID: String) -> String {
        let trimmed = serverSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? Self.defaultServerSessionID : trimmed
    }

    private func resolveIdlePolicy(hasActiveRequests: Bool) {
        let now = nowUnixMS()
        if hasActiveRequests {
            for index in runtimeSessions.indices {
                let serverSessionID = runtimeSessions[index].serverSessionID
                activeRequestInhibitedSessions.insert(serverSessionID)
                lastActivityAtUnixMSByServerSessionID[serverSessionID] = now
                runtimeSessions[index].idleTimerSeconds = 0
            }
            return
        }

        if !activeRequestInhibitedSessions.isEmpty {
            for serverSessionID in activeRequestInhibitedSessions {
                lastActivityAtUnixMSByServerSessionID[serverSessionID] = now
            }
            activeRequestInhibitedSessions.removeAll()
        }

        for index in runtimeSessions.indices {
            let serverSessionID = runtimeSessions[index].serverSessionID
            let lastActivityAtUnixMS = lastActivityAtUnixMSByServerSessionID[serverSessionID]
                ?? runtimeSessions[index].updatedAtUnixMs
            let idleSeconds = UInt32(max(0, (now - lastActivityAtUnixMS) / 1000))
            runtimeSessions[index].idleTimerSeconds = idleSeconds

            guard runtimeSessions[index].autoSleepEnabled else {
                continue
            }
            guard runtimeSessions[index].lifecycleState != .paused else {
                continue
            }
            guard runtimeSessions[index].lifecycleState != .stopped else {
                continue
            }
            guard runtimeSessions[index].lifecycleState != .error else {
                continue
            }

            let deepSleepAfterSeconds = runtimeSessions[index].deepSleepAfterSeconds
            let lightSleepAfterSeconds = runtimeSessions[index].lightSleepAfterSeconds
            let targetPowerState: Melix_Controlplane_V1_ServerSessionPowerState?
            if deepSleepAfterSeconds > 0, idleSeconds >= deepSleepAfterSeconds {
                targetPowerState = .deepSleep
            } else if lightSleepAfterSeconds > 0, idleSeconds >= lightSleepAfterSeconds {
                targetPowerState = .lightSleep
            } else {
                targetPowerState = nil
            }

            guard let targetPowerState else {
                continue
            }
            if runtimeSessions[index].lifecycleState != .sleeping || runtimeSessions[index].powerState != targetPowerState {
                runtimeSessions[index].lifecycleState = .sleeping
                runtimeSessions[index].powerState = targetPowerState
                runtimeSessions[index].updatedAtUnixMs = now
            }
        }
    }
}
