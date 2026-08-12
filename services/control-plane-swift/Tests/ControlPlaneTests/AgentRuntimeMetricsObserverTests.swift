import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Agent runtime metrics observer")
struct AgentRuntimeMetricsObserverTests {
    @Test("records first tool, approval, correlation, and terminal metrics once")
    func recordsLifecycleMetrics() async {
        let observer = AgentRuntimeMetricsObserver()
        let metrics = MetricsStore()

        await observer.observe(
            snapshot: Melix_Controlplane_V1_AgentRunSnapshot(),
            metricsStore: metrics
        )

        var created = Melix_Controlplane_V1_AgentRunSnapshot()
        created.runID = "run-metrics-1"
        created.state = "created"
        created.startedAtUnixMs = 1_000
        created.updatedAtUnixMs = 1_000
        await observer.observe(snapshot: created, metricsStore: metrics)

        var tool = Melix_Controlplane_V1_AgentToolCallSnapshot()
        tool.callID = "call-1"
        tool.sourceID = "builtin"
        tool.toolName = "environment_info"
        tool.state = "waiting_for_approval"
        var pending = created
        pending.state = "waiting_for_approval"
        pending.updatedAtUnixMs = 1_050
        pending.toolCallCount = 1
        pending.toolCalls = [tool]
        pending.pendingApproval.binding.runID = pending.runID
        pending.pendingApproval.binding.callID = tool.callID
        pending.pendingApproval.binding.bindingDigest = "binding-1"
        await observer.observe(snapshot: pending, metricsStore: metrics)
        await observer.observe(snapshot: pending, metricsStore: metrics)

        var completed = pending
        completed.state = "completed"
        completed.updatedAtUnixMs = 1_100
        completed.clearPendingApproval()
        completed.toolCalls[0].state = "completed"
        await observer.observe(snapshot: completed, metricsStore: metrics)

        var values = await metrics.snapshot().values
        #expect(values["agent.run.started_count"] == 1)
        #expect(values["agent.run.tool_call_count"] == 1)
        #expect(values["agent.run.first_tool_call_ms"] == 50)
        #expect(values["agent.run.call_id_correlation_rate"] == 1)
        #expect(values["agent.approval.required_count"] == 1)
        #expect(values["agent.approval.bypass_count"] == 0)
        #expect(values["agent.run.terminal_count"] == 1)
        #expect(values["agent.run.completed_count"] == 1)
        #expect(values["agent.run.terminal_duplicate_event_count"] == 0)

        await observer.observe(snapshot: completed, metricsStore: metrics)
        values = await metrics.snapshot().values
        #expect(values["agent.run.started_count"] == 1)
        #expect(values["agent.run.terminal_count"] == 1)
        #expect(values["agent.run.terminal_duplicate_event_count"] == 1)
    }

    @Test("reports partial correlation and terminal outcome classes")
    func reportsCorrelationAndTerminalClasses() async {
        let observer = AgentRuntimeMetricsObserver()
        let metrics = MetricsStore()

        for (runID, state) in [
            ("run-failed", "failed"),
            ("run-cancelled", "cancelled"),
        ] {
            var first = Melix_Controlplane_V1_AgentToolCallSnapshot()
            first.callID = "shared"
            var second = Melix_Controlplane_V1_AgentToolCallSnapshot()
            second.callID = ""
            var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
            snapshot.runID = runID
            snapshot.state = state
            snapshot.toolCallCount = 2
            snapshot.toolCalls = [first, second]
            await observer.observe(snapshot: snapshot, metricsStore: metrics)
        }

        let values = await metrics.snapshot().values
        #expect(values["agent.run.call_id_correlation_rate"] == 0.5)
        #expect(values["agent.run.failed_count"] == 1)
        #expect(values["agent.run.cancelled_count"] == 1)
    }

    @Test("records admission, transition, healing, and post-cancel late events at typed boundaries")
    func recordsDetailedRunAndCancellationMetrics() async {
        let observer = AgentRuntimeMetricsObserver()
        let metrics = MetricsStore()

        var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        snapshot.runID = "run-detailed-metrics"
        snapshot.state = "created"
        snapshot.startedAtUnixMs = 1_000
        snapshot.updatedAtUnixMs = 1_000
        await observer.observe(
            snapshot: snapshot,
            changeKind: "started",
            metricsStore: metrics
        )

        snapshot.state = "model_turn"
        snapshot.modelTurnCount = 1
        snapshot.updatedAtUnixMs = 1_020
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_completed",
            metricsStore: metrics
        )

        var tool = Melix_Controlplane_V1_AgentToolCallSnapshot()
        tool.callID = "call-detailed"
        tool.state = "requested"
        snapshot.toolCallCount = 1
        snapshot.toolCalls = [tool]
        snapshot.updatedAtUnixMs = 1_027
        await observer.observe(
            snapshot: snapshot,
            changeKind: "tool_call",
            metricsStore: metrics
        )

        snapshot.toolCalls[0].state = "completed"
        snapshot.updatedAtUnixMs = 1_040
        await observer.observe(
            snapshot: snapshot,
            changeKind: "tool_call_completed",
            metricsStore: metrics
        )

        snapshot.modelTurnCount = 2
        snapshot.updatedAtUnixMs = 1_044
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_started",
            metricsStore: metrics
        )

        snapshot.updatedAtUnixMs = 1_050
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_completed",
            metricsStore: metrics
        )
        snapshot.updatedAtUnixMs = 1_053
        await observer.observe(
            snapshot: snapshot,
            changeKind: "tool_call_healing_nudge",
            metricsStore: metrics
        )
        snapshot.modelTurnCount = 3
        snapshot.updatedAtUnixMs = 1_058
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_started",
            metricsStore: metrics
        )

        snapshot.state = "cancelled"
        snapshot.updatedAtUnixMs = 1_060
        await observer.observe(
            snapshot: snapshot,
            changeKind: "state",
            metricsStore: metrics
        )
        await observer.observe(
            snapshot: snapshot,
            changeKind: "cancelled",
            metricsStore: metrics
        )

        snapshot.updatedAtUnixMs = 1_061
        await observer.observe(
            snapshot: snapshot,
            changeKind: "assistant_delta",
            metricsStore: metrics
        )
        await observer.observe(
            snapshot: snapshot,
            changeKind: "cancelled",
            metricsStore: metrics
        )

        let values = await metrics.snapshot().values
        #expect(values["agent.run.tool_admission_ms"] == 3)
        #expect(values["agent.run.turn_transition_ms"] == 5)
        #expect(values["agent.run.healing_nudge_count"] == 1)
        #expect(values["agent.cancel.late_event_count"] == 1)
        #expect(values["agent.run.terminal_count"] == 1)
        #expect(values["agent.run.terminal_duplicate_event_count"] == 1)
        #expect(values["agent.cancel.ui_to_control_plane_ms"] == nil)
        #expect(values["agent.cancel.worker_to_adapter_ms"] == nil)
    }

    @Test("invalid clocks are ignored and terminal admission failures retain typed timing")
    func invalidClocksAndTerminalAdmissionFailureAreBounded() async {
        let observer = AgentRuntimeMetricsObserver()
        let metrics = MetricsStore()
        var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        snapshot.runID = "run-invalid-metric-clock"
        snapshot.state = "model_turn"
        snapshot.updatedAtUnixMs = 0
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_completed",
            metricsStore: metrics
        )

        var tool = Melix_Controlplane_V1_AgentToolCallSnapshot()
        tool.callID = "call-invalid-clock"
        tool.state = "requested"
        snapshot.toolCallCount = 1
        snapshot.toolCalls = [tool]
        snapshot.updatedAtUnixMs = 10
        await observer.observe(
            snapshot: snapshot,
            changeKind: "tool_call",
            metricsStore: metrics
        )
        snapshot.updatedAtUnixMs = 20
        await observer.observe(
            snapshot: snapshot,
            changeKind: "tool_call_completed",
            metricsStore: metrics
        )
        snapshot.updatedAtUnixMs = 19
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_started",
            metricsStore: metrics
        )

        snapshot.updatedAtUnixMs = 30
        await observer.observe(
            snapshot: snapshot,
            changeKind: "model_turn_completed",
            metricsStore: metrics
        )
        snapshot.state = "failed"
        snapshot.error.code = "agent_tool_call_invalid"
        snapshot.updatedAtUnixMs = 36
        await observer.observe(
            snapshot: snapshot,
            changeKind: "failed",
            metricsStore: metrics
        )

        let values = await metrics.snapshot().values
        #expect(values["agent.run.tool_admission_ms"] == 6)
        #expect(values["agent.run.turn_transition_ms"] == 0)
        #expect(values["agent.run.healing_nudge_count"] == 0)
    }

    @Test("new runs do not reset global invariant counters")
    func newRunsPreserveInvariantCounters() async {
        let observer = AgentRuntimeMetricsObserver()
        let metrics = MetricsStore()

        var completed = Melix_Controlplane_V1_AgentRunSnapshot()
        completed.runID = "run-terminal-one"
        completed.state = "completed"
        await observer.observe(snapshot: completed, metricsStore: metrics)
        await observer.observe(snapshot: completed, metricsStore: metrics)

        var created = Melix_Controlplane_V1_AgentRunSnapshot()
        created.runID = "run-created-later"
        created.state = "created"
        await observer.observe(snapshot: created, metricsStore: metrics)

        let values = await metrics.snapshot().values
        #expect(values["agent.run.terminal_duplicate_event_count"] == 1)
        #expect(values["agent.approval.bypass_count"] == 0)
    }

    @Test("retained observations stay within the configured bound")
    func observationsAreBounded() async {
        let observer = AgentRuntimeMetricsObserver(retentionLimit: 3)
        let metrics = MetricsStore()

        for index in 0..<10 {
            var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
            snapshot.runID = "run-bounded-\(index)"
            snapshot.state = index.isMultiple(of: 2) ? "completed" : "created"
            await observer.observe(snapshot: snapshot, metricsStore: metrics)
        }

        let values = await metrics.snapshot().values
        #expect(values["agent.run.started_count"] == 10)
        #expect(values["agent.run.observation_count"] == 3)
    }
}
