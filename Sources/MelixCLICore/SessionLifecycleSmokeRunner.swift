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
    public let providerID: String
    public let modelID: String
    public let metrics: [String: Double]
    public let scenarios: [String: SessionLifecycleSmokeScenario]

    public init(
        ok: Bool,
        providerID: String,
        modelID: String,
        metrics: [String: Double],
        scenarios: [String: SessionLifecycleSmokeScenario]
    ) {
        self.ok = ok
        self.providerID = providerID
        self.modelID = modelID
        self.metrics = metrics
        self.scenarios = scenarios
    }
}

public struct SessionLifecycleSmokeRunner: Sendable {
    private static let exportedControlPlaneMetricKeys = [
        "control_plane.server_start_ms",
        "control_plane.server_pause_ms",
        "control_plane.server_resume_ms",
        "control_plane.server_wake_ms",
        "control_plane.server_stop_ms",
        "control_plane.server_idle_policy_ms",
    ]

    private static let requiredControlPlaneMetricKeys: Set<String> = [
        "control_plane.server_start_ms",
        "control_plane.server_pause_ms",
        "control_plane.server_resume_ms",
        "control_plane.server_stop_ms",
        "control_plane.server_idle_policy_ms",
    ]

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
        providerID: String = MelixProviderDefaults.defaultProviderID,
        modelID: String = "melix-dev-text"
    ) async throws -> SessionLifecycleSmokeReport {
        _ = try await client.handshake()
        _ = try await client.loadModel(modelID: modelID)

        let pauseStartedAt = now()
        let pausedSnapshot = try await client.pauseServerSession(serverSessionID: providerID)
        let pausedSession = try runtimeSession(in: pausedSnapshot, providerID: providerID)
        let pauseAckMS = elapsedMS(since: pauseStartedAt)

        var blockedStatus = "unexpected_success"
        do {
            _ = try await client.startChat(
                ControlPlaneChatRequest(
                    modelID: modelID,
                    messages: [.init(role: "user", content: "confirm the paused server blocks chat")],
                    providerID: providerID
                )
            )
        } catch ControlPlaneChatExecutionError.unavailable {
            blockedStatus = "unavailable"
        } catch ControlPlaneChatExecutionError.unavailableReason(let reason)
            where reason.localizedCaseInsensitiveContains("server_paused") {
            blockedStatus = "unavailable"
        }

        _ = try await client.resumeServerSession(serverSessionID: providerID)

        let idleStartedAt = now()
        _ = try await client.updateServerIdlePolicy(
            serverSessionID: providerID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )
        let sleepingSession = try await waitForLifecycle(
            providerID: providerID,
            expectedLifecycle: .sleeping,
            timeoutSeconds: 3
        )
        let idleToSleepMS = elapsedMS(since: idleStartedAt)

        _ = try await client.updateServerIdlePolicy(
            serverSessionID: providerID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 10,
            deepSleepAfterSeconds: 30
        )

        let wakeStartedAt = now()
        let wakeExecution = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: modelID,
                messages: [.init(role: "user", content: "wake the server")],
                providerID: providerID
            )
        )
        async let wakeAssistantTask = collectAssistantText(from: wakeExecution)
        let readyAfterWake = try await waitForLifecycle(
            providerID: providerID,
            expectedLifecycle: .ready,
            timeoutSeconds: 2
        )
        let wakeToReadyMS = elapsedMS(since: wakeStartedAt)
        let wakeAssistant = try await wakeAssistantTask

        _ = try await client.updateServerIdlePolicy(
            serverSessionID: providerID,
            autoSleepEnabled: false,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )

        let restartStartedAt = now()
        _ = try await stopServerSessionWhenQuiescent(providerID: providerID, timeoutSeconds: 2)
        let restartedSnapshot = try await client.startServerSession(serverSessionID: providerID)
        let restartedSession = try runtimeSession(in: restartedSnapshot, providerID: providerID)
        let restartRecoveryMS = elapsedMS(since: restartStartedAt)
        let restartExecution = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: modelID,
                messages: [.init(role: "user", content: "confirm restart recovery")],
                providerID: providerID
            )
        )
        let restartAssistant = try await collectAssistantText(from: restartExecution)

        await flushMetrics()
        var metrics = try await readExportedMetrics(
            requiring: Self.requiredControlPlaneMetricKeys,
            timeoutSeconds: 1
        )
        metrics["lifecycle.pause_ack_ms"] = pauseAckMS
        metrics["lifecycle.idle_to_light_sleep_ms"] = idleToSleepMS
        metrics["lifecycle.wake_to_ready_ms"] = wakeToReadyMS
        metrics["lifecycle.restart_recovery_ms"] = restartRecoveryMS

        return SessionLifecycleSmokeReport(
            ok: true,
            providerID: providerID,
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
        providerID: String
    ) throws -> Melix_Controlplane_V1_ProviderRuntimeState {
        let trimmedID = normalizedServerSessionID(providerID)
        guard let session = snapshot.providers.first(where: { $0.providerID == trimmedID }) else {
            throw SessionLifecycleSmokeRunnerError.missingRuntimeSession(trimmedID)
        }
        return session
    }

    private func waitForLifecycle(
        providerID: String,
        expectedLifecycle: Melix_Controlplane_V1_ProviderLifecycleState,
        timeoutSeconds: TimeInterval
    ) async throws -> Melix_Controlplane_V1_ProviderRuntimeState {
        let deadline = now() + timeoutSeconds
        var observedLifecycle = Melix_Controlplane_V1_ProviderLifecycleState.unspecified

        while now() <= deadline {
            let snapshot = try await client.serverSnapshot()
            let session = try runtimeSession(in: snapshot, providerID: providerID)
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
        providerID: String,
        timeoutSeconds: TimeInterval
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        let deadline = now() + timeoutSeconds
        while now() <= deadline {
            do {
                return try await client.stopServerSession(serverSessionID: providerID)
            } catch let error as ControlPlaneXPCClientError {
                if case .requestFailed(let code, _) = error, code == "conflict" {
                    try await sleep(0.05)
                    continue
                }
                throw error
            }
        }
        return try await client.stopServerSession(serverSessionID: providerID)
    }

    private func readExportedMetrics(
        requiring requiredKeys: Set<String> = [],
        timeoutSeconds: TimeInterval = 0
    ) async throws -> [String: Double] {
        let trimmedPath = metricsPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedPath.isEmpty else {
            return [:]
        }

        let pollInterval: TimeInterval = 0.05
        let deadline = max(0, timeoutSeconds)
        var waited: TimeInterval = 0
        var metrics = readExportedMetricsOnce(from: trimmedPath)

        while !requiredKeys.isSubset(of: Set(metrics.keys)), waited < deadline {
            let waitSeconds = min(pollInterval, deadline - waited)
            try await sleep(waitSeconds)
            waited += waitSeconds
            metrics = readExportedMetricsOnce(from: trimmedPath)
        }

        return metrics
    }

    private func readExportedMetricsOnce(from path: String) -> [String: Double] {
        let url = URL(fileURLWithPath: path)
        guard
            let data = try? Data(contentsOf: url),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let values = payload["values"] as? [String: Any]
        else {
            return [:]
        }

        var metrics: [String: Double] = [:]
        for key in Self.exportedControlPlaneMetricKeys {
            if let value = values[key] as? NSNumber {
                metrics[key] = value.doubleValue
            }
        }
        return metrics
    }

    private func elapsedMS(since startedAt: Double) -> Double {
        max(0, (now() - startedAt) * 1_000)
    }

    private func normalizedServerSessionID(_ providerID: String) -> String {
        let trimmedID = providerID.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmedID.isEmpty ? MelixProviderDefaults.defaultProviderID : trimmedID
    }
}

private extension Melix_Controlplane_V1_ProviderLifecycleState {
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

private extension Melix_Controlplane_V1_ProviderPowerState {
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

private extension Melix_Controlplane_V1_ProviderWakeReason {
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
