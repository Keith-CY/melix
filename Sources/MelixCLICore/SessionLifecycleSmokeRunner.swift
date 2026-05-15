import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum SessionLifecycleSmokeRunnerError: Error, Equatable {
    case missingRuntimeSession(String)
    case lifecycleTimeout(expected: String, observed: String)
    case chatDidNotComplete
}

public struct SessionLifecycleSmokeScenario: Encodable, Equatable, Sendable {
    public let lifecycle: String
    public let powerState: String
    public let wakeReason: String
    public let blockedStatus: String
    public let assistantText: String

    public init(
        lifecycle: String,
        powerState: String,
        wakeReason: String = "",
        blockedStatus: String = "",
        assistantText: String = ""
    ) {
        self.lifecycle = lifecycle
        self.powerState = powerState
        self.wakeReason = wakeReason
        self.blockedStatus = blockedStatus
        self.assistantText = assistantText
    }
}

public struct SessionLifecycleSmokeReport: Encodable, Equatable, Sendable {
    public let ok: Bool
    public let serverSessionID: String
    public let modelID: String
    public let metrics: [String: Double]
    public let scenarios: [String: SessionLifecycleSmokeScenario]

    public init(
        ok: Bool,
        serverSessionID: String,
        modelID: String,
        metrics: [String: Double],
        scenarios: [String: SessionLifecycleSmokeScenario]
    ) {
        self.ok = ok
        self.serverSessionID = serverSessionID
        self.modelID = modelID
        self.metrics = metrics
        self.scenarios = scenarios
    }
}

public struct SessionLifecycleSmokeRunner: Sendable {
    private let client: any ControlPlaneXPCClient
    private let metricsPath: String
    private let now: @Sendable () -> Double
    private let sleep: @Sendable (TimeInterval) async throws -> Void
    private let flushMetrics: @Sendable () async -> Void

    public init(
        client: any ControlPlaneXPCClient,
        metricsPath: String = "",
        now: @escaping @Sendable () -> Double = { ProcessInfo.processInfo.systemUptime },
        sleep: @escaping @Sendable (TimeInterval) async throws -> Void = { seconds in
            let nanoseconds = UInt64(max(seconds, 0) * 1_000_000_000)
            try await Task.sleep(nanoseconds: nanoseconds)
        },
        flushMetrics: @escaping @Sendable () async -> Void = {}
    ) {
        self.client = client
        self.metricsPath = metricsPath
        self.now = now
        self.sleep = sleep
        self.flushMetrics = flushMetrics
    }

    public func run(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        modelID: String = "melix-dev-text"
    ) async throws -> SessionLifecycleSmokeReport {
        _ = try await client.handshake()
        _ = try await client.loadModel(modelID: modelID)

        let pauseStartedAt = now()
        let pausedSnapshot = try await client.pauseServerSession(serverSessionID: serverSessionID)
        let pausedSession = try runtimeSession(in: pausedSnapshot, serverSessionID: serverSessionID)
        let pauseAckMS = elapsedMS(since: pauseStartedAt)

        var blockedStatus = "unexpected_success"
        do {
            _ = try await client.startChat(
                ControlPlaneChatRequest(
                    modelID: modelID,
                    messages: [.init(role: "user", content: "confirm the paused server blocks chat")]
                )
            )
        } catch ControlPlaneChatExecutionError.unavailable {
            blockedStatus = "unavailable"
        } catch ControlPlaneChatExecutionError.unavailableReason(let reason)
            where reason.localizedCaseInsensitiveContains("server_paused") {
            blockedStatus = "unavailable"
        }

        _ = try await client.resumeServerSession(serverSessionID: serverSessionID)

        let idleStartedAt = now()
        _ = try await client.updateServerIdlePolicy(
            serverSessionID: serverSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )
        let sleepingSession = try await waitForLifecycle(
            serverSessionID: serverSessionID,
            expectedLifecycle: .sleeping,
            timeoutSeconds: 3
        )
        let idleToSleepMS = elapsedMS(since: idleStartedAt)

        _ = try await client.updateServerIdlePolicy(
            serverSessionID: serverSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 10,
            deepSleepAfterSeconds: 30
        )

        let wakeStartedAt = now()
        let wakeExecution = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: modelID,
                messages: [.init(role: "user", content: "wake the server")]
            )
        )
        async let wakeAssistantTask = collectAssistantText(from: wakeExecution)
        let readyAfterWake = try await waitForLifecycle(
            serverSessionID: serverSessionID,
            expectedLifecycle: .ready,
            timeoutSeconds: 2
        )
        let wakeToReadyMS = elapsedMS(since: wakeStartedAt)
        let wakeAssistant = try await wakeAssistantTask

        _ = try await client.updateServerIdlePolicy(
            serverSessionID: serverSessionID,
            autoSleepEnabled: false,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )

        let restartStartedAt = now()
        _ = try await stopServerSessionWhenQuiescent(serverSessionID: serverSessionID, timeoutSeconds: 2)
        let restartedSnapshot = try await client.startServerSession(serverSessionID: serverSessionID)
        let restartedSession = try runtimeSession(in: restartedSnapshot, serverSessionID: serverSessionID)
        let restartRecoveryMS = elapsedMS(since: restartStartedAt)
        let restartExecution = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: modelID,
                messages: [.init(role: "user", content: "confirm restart recovery")]
            )
        )
        let restartAssistant = try await collectAssistantText(from: restartExecution)

        await flushMetrics()
        var metrics = readExportedMetrics()
        metrics["lifecycle.pause_ack_ms"] = pauseAckMS
        metrics["lifecycle.idle_to_light_sleep_ms"] = idleToSleepMS
        metrics["lifecycle.wake_to_ready_ms"] = wakeToReadyMS
        metrics["lifecycle.restart_recovery_ms"] = restartRecoveryMS

        return SessionLifecycleSmokeReport(
            ok: true,
            serverSessionID: serverSessionID,
            modelID: modelID,
            metrics: metrics,
            scenarios: [
                "pause": SessionLifecycleSmokeScenario(
                    lifecycle: pausedSession.lifecycleState.description,
                    powerState: pausedSession.powerState.description,
                    wakeReason: pausedSession.wakeReason.description,
                    blockedStatus: blockedStatus
                ),
                "idle_sleep": SessionLifecycleSmokeScenario(
                    lifecycle: sleepingSession.lifecycleState.description,
                    powerState: sleepingSession.powerState.description,
                    wakeReason: sleepingSession.wakeReason.description
                ),
                "wake": SessionLifecycleSmokeScenario(
                    lifecycle: readyAfterWake.lifecycleState.description,
                    powerState: readyAfterWake.powerState.description,
                    wakeReason: readyAfterWake.wakeReason.description,
                    assistantText: wakeAssistant
                ),
                "restart": SessionLifecycleSmokeScenario(
                    lifecycle: restartedSession.lifecycleState.description,
                    powerState: restartedSession.powerState.description,
                    wakeReason: restartedSession.wakeReason.description,
                    assistantText: restartAssistant
                ),
            ]
        )
    }

    private func runtimeSession(
        in snapshot: Melix_Controlplane_V1_ServerSnapshot,
        serverSessionID: String
    ) throws -> Melix_Controlplane_V1_ServerSessionRuntimeState {
        let trimmedID = normalizedServerSessionID(serverSessionID)
        guard let session = snapshot.runtimeSessions.first(where: { $0.serverSessionID == trimmedID }) else {
            throw SessionLifecycleSmokeRunnerError.missingRuntimeSession(trimmedID)
        }
        return session
    }

    private func waitForLifecycle(
        serverSessionID: String,
        expectedLifecycle: Melix_Controlplane_V1_ServerSessionLifecycleState,
        timeoutSeconds: TimeInterval
    ) async throws -> Melix_Controlplane_V1_ServerSessionRuntimeState {
        let deadline = now() + timeoutSeconds
        var observedLifecycle = Melix_Controlplane_V1_ServerSessionLifecycleState.unspecified

        while now() <= deadline {
            let snapshot = try await client.serverSnapshot()
            let session = try runtimeSession(in: snapshot, serverSessionID: serverSessionID)
            observedLifecycle = session.lifecycleState
            if session.lifecycleState == expectedLifecycle {
                return session
            }
            try await sleep(0.05)
        }

        throw SessionLifecycleSmokeRunnerError.lifecycleTimeout(
            expected: expectedLifecycle.description,
            observed: observedLifecycle.description
        )
    }

    private func collectAssistantText(
        from execution: ControlPlaneChatExecution
    ) async throws -> String {
        var fallbackAssistant = ""
        for try await event in execution.stream {
            switch event {
            case .tokenDelta(let delta):
                fallbackAssistant += delta
            case .completed(_, let assistantText, _):
                return assistantText.isEmpty ? fallbackAssistant : assistantText
            default:
                continue
            }
        }

        guard !fallbackAssistant.isEmpty else {
            throw SessionLifecycleSmokeRunnerError.chatDidNotComplete
        }
        return fallbackAssistant
    }

    private func stopServerSessionWhenQuiescent(
        serverSessionID: String,
        timeoutSeconds: TimeInterval
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        let deadline = now() + timeoutSeconds
        while now() <= deadline {
            do {
                return try await client.stopServerSession(serverSessionID: serverSessionID)
            } catch let error as ControlPlaneXPCClientError {
                if case .requestFailed(let code, _) = error, code == "conflict" {
                    try await sleep(0.05)
                    continue
                }
                throw error
            }
        }
        return try await client.stopServerSession(serverSessionID: serverSessionID)
    }

    private func readExportedMetrics() -> [String: Double] {
        let trimmedPath = metricsPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedPath.isEmpty else {
            return [:]
        }
        let url = URL(fileURLWithPath: trimmedPath)
        guard
            let data = try? Data(contentsOf: url),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let values = payload["values"] as? [String: Any]
        else {
            return [:]
        }

        var metrics: [String: Double] = [:]
        for key in [
            "control_plane.server_start_ms",
            "control_plane.server_pause_ms",
            "control_plane.server_resume_ms",
            "control_plane.server_wake_ms",
            "control_plane.server_stop_ms",
            "control_plane.server_idle_policy_ms",
        ] {
            if let value = values[key] as? NSNumber {
                metrics[key] = value.doubleValue
            }
        }
        return metrics
    }

    private func elapsedMS(since startedAt: Double) -> Double {
        max(0, (now() - startedAt) * 1_000)
    }

    private func normalizedServerSessionID(_ serverSessionID: String) -> String {
        let trimmedID = serverSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmedID.isEmpty ? ServerSessionRuntimeStore.defaultServerSessionID : trimmedID
    }
}

private extension Melix_Controlplane_V1_ServerSessionLifecycleState {
    var description: String {
        switch self {
        case .ready:
            return "ready"
        case .paused:
            return "paused"
        case .sleeping:
            return "sleeping"
        case .stopped:
            return "stopped"
        case .error:
            return "error"
        case .loading:
            return "loading"
        default:
            return "unspecified"
        }
    }
}

private extension Melix_Controlplane_V1_ServerSessionPowerState {
    var description: String {
        switch self {
        case .active:
            return "active"
        case .lightSleep:
            return "light_sleep"
        case .deepSleep:
            return "deep_sleep"
        case .stopped:
            return "stopped"
        default:
            return "unspecified"
        }
    }
}

private extension Melix_Controlplane_V1_ServerWakeReason {
    var description: String {
        switch self {
        case .initialBoot:
            return "initial_boot"
        case .requestActivity:
            return "request_activity"
        case .operatorResume:
            return "operator_resume"
        case .policyApply:
            return "policy_apply"
        default:
            return "unspecified"
        }
    }
}
