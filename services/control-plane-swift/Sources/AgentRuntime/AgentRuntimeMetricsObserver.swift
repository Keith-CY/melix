import Foundation
import MelixControlPlaneProtocol

public actor AgentRuntimeMetricsObserver {
    private struct RunObservation {
        var recordedFirstToolCall = false
        var requiredApprovalBindings: Set<String> = []
        var healingNudgeCount = 0
        var toolAdmissionStartedAtUnixMs: Int64?
        var turnTransitionStartedAtUnixMs: Int64?
        var terminalState: String?
    }

    private let retentionLimit: Int
    private var runs: [String: RunObservation] = [:]
    private var runOrder: [String] = []

    public init(retentionLimit: Int = 512) {
        self.retentionLimit = min(max(retentionLimit, 1), 10_000)
    }

    public func observe(
        snapshot: Melix_Controlplane_V1_AgentRunSnapshot,
        changeKind: String = "snapshot",
        metricsStore: MetricsStore
    ) async {
        guard !snapshot.runID.isEmpty else {
            return
        }
        let normalizedChangeKind = changeKind.trimmingCharacters(
            in: .whitespacesAndNewlines
        ).lowercased()
        let isNewRun = runs[snapshot.runID] == nil
        var observation = runs[snapshot.runID] ?? RunObservation()

        if isNewRun {
            retainNewRun(snapshot.runID)
            await metricsStore.increment("agent.run.started_count")
        }

        if observation.terminalState == "cancelled",
           !Self.isTerminalSignal(normalizedChangeKind) {
            await metricsStore.increment("agent.cancel.late_event_count")
            runs[snapshot.runID] = observation
            await metricsStore.set(
                Double(runs.count),
                forKey: "agent.run.observation_count"
            )
            return
        }

        switch normalizedChangeKind {
        case "model_turn_completed":
            observation.toolAdmissionStartedAtUnixMs =
                Self.validTimestamp(snapshot.updatedAtUnixMs)
        case "tool_call":
            if snapshot.toolCalls.contains(where: { $0.state == "requested" }) {
                await recordLatency(
                    startUnixMs: observation.toolAdmissionStartedAtUnixMs,
                    endUnixMs: snapshot.updatedAtUnixMs,
                    key: "agent.run.tool_admission_ms",
                    metricsStore: metricsStore
                )
                observation.toolAdmissionStartedAtUnixMs = nil
            }
        case "tool_call_healing_nudge":
            await recordLatency(
                startUnixMs: observation.toolAdmissionStartedAtUnixMs,
                endUnixMs: snapshot.updatedAtUnixMs,
                key: "agent.run.tool_admission_ms",
                metricsStore: metricsStore
            )
            observation.toolAdmissionStartedAtUnixMs = nil
            observation.healingNudgeCount += 1
            observation.turnTransitionStartedAtUnixMs =
                Self.validTimestamp(snapshot.updatedAtUnixMs)
        case "tool_call_completed":
            observation.turnTransitionStartedAtUnixMs =
                Self.validTimestamp(snapshot.updatedAtUnixMs)
        case "model_turn_started":
            await recordLatency(
                startUnixMs: observation.turnTransitionStartedAtUnixMs,
                endUnixMs: snapshot.updatedAtUnixMs,
                key: "agent.run.turn_transition_ms",
                metricsStore: metricsStore
            )
            observation.turnTransitionStartedAtUnixMs = nil
        case "failed":
            if Self.isToolAdmissionFailure(snapshot.error.code) {
                await recordLatency(
                    startUnixMs: observation.toolAdmissionStartedAtUnixMs,
                    endUnixMs: snapshot.updatedAtUnixMs,
                    key: "agent.run.tool_admission_ms",
                    metricsStore: metricsStore
                )
                observation.toolAdmissionStartedAtUnixMs = nil
            }
        default:
            break
        }

        await metricsStore.set(
            Double(snapshot.toolCallCount),
            forKey: "agent.run.tool_call_count"
        )
        await metricsStore.set(
            Double(observation.healingNudgeCount),
            forKey: "agent.run.healing_nudge_count"
        )
        await metricsStore.set(
            Self.callIDCorrelationRate(snapshot.toolCalls),
            forKey: "agent.run.call_id_correlation_rate"
        )

        if !observation.recordedFirstToolCall,
           snapshot.toolCallCount > 0,
           snapshot.startedAtUnixMs > 0,
           snapshot.updatedAtUnixMs >= snapshot.startedAtUnixMs {
            observation.recordedFirstToolCall = true
            await metricsStore.set(
                Double(snapshot.updatedAtUnixMs - snapshot.startedAtUnixMs),
                forKey: "agent.run.first_tool_call_ms"
            )
        }

        if snapshot.hasPendingApproval {
            let bindingDigest = snapshot.pendingApproval.binding.bindingDigest
            if !bindingDigest.isEmpty,
               observation.requiredApprovalBindings.insert(bindingDigest).inserted {
                await metricsStore.increment("agent.approval.required_count")
            }
        }
        if Self.isTerminal(snapshot.state),
           Self.isTerminalSignal(normalizedChangeKind) {
            if observation.terminalState == nil {
                observation.terminalState = snapshot.state
                await metricsStore.increment("agent.run.terminal_count")
                switch snapshot.state {
                case "completed":
                    await metricsStore.increment("agent.run.completed_count")
                case "cancelled":
                    await metricsStore.increment("agent.run.cancelled_count")
                default:
                    await metricsStore.increment("agent.run.failed_count")
                }
            } else {
                await metricsStore.increment(
                    "agent.run.terminal_duplicate_event_count"
                )
            }
        }

        runs[snapshot.runID] = observation
        await metricsStore.set(
            Double(runs.count),
            forKey: "agent.run.observation_count"
        )
    }

    private func retainNewRun(_ runID: String) {
        guard runs.count >= retentionLimit else {
            runOrder.append(runID)
            return
        }
        let evictionIndex = runOrder.firstIndex(where: {
            runs[$0]?.terminalState != nil
        }) ?? runOrder.startIndex
        let evictedRunID = runOrder.remove(at: evictionIndex)
        runs.removeValue(forKey: evictedRunID)
        runOrder.append(runID)
    }

    private static func callIDCorrelationRate(
        _ calls: [Melix_Controlplane_V1_AgentToolCallSnapshot]
    ) -> Double {
        guard !calls.isEmpty else {
            return 1
        }
        let validIDs = calls.map(\.callID).filter { !$0.isEmpty }
        let uniqueIDs = Set(validIDs)
        guard validIDs.count == calls.count,
              uniqueIDs.count == calls.count else {
            return Double(uniqueIDs.count) / Double(calls.count)
        }
        return 1
    }

    private static func isTerminal(_ state: String) -> Bool {
        ["completed", "failed", "cancelled"].contains(state)
    }

    private static func isTerminalSignal(_ changeKind: String) -> Bool {
        ["snapshot", "completed", "failed", "cancelled"].contains(changeKind)
    }

    private static func validTimestamp(_ unixMs: Int64) -> Int64? {
        unixMs > 0 ? unixMs : nil
    }

    private static func isToolAdmissionFailure(_ code: String) -> Bool {
        [
            "agent_tool_call_limit_exceeded",
            "agent_tool_call_healing_exhausted",
            "agent_tool_schema_digest_mismatch",
            "agent_tool_call_invalid",
        ].contains(code)
    }

    private func recordLatency(
        startUnixMs: Int64?,
        endUnixMs: Int64,
        key: String,
        metricsStore: MetricsStore
    ) async {
        guard let startUnixMs,
              startUnixMs > 0,
              endUnixMs >= startUnixMs
        else {
            return
        }
        await metricsStore.set(
            Double(endUnixMs - startUnixMs),
            forKey: key
        )
    }
}
