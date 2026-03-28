import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Scheduler Read Model")
struct SchedulerReadModelTests {
    @Test("progress events publish through the configured event publisher")
    func progressEventsPublishThroughConfiguredEventPublisher() async {
        let recorder = SchedulerEventRecorder()
        let readModel = SchedulerReadModel(
            metricsStore: MetricsStore(),
            eventPublisher: { event in
                await recorder.append(event)
            }
        )

        await readModel.recordPhaseTransition(
            requestID: "missing-progress",
            phase: .requestPrefilling,
            source: "swift-text-worker"
        )
        await readModel.recordQueued(
            requestID: "req-published",
            laneHint: "text.interactive",
            priority: 0,
            queuePosition: 1,
            workerID: "swift-text-worker"
        )
        _ = await readModel.recordAdmitted(
            requestID: "req-published",
            laneHint: "text.interactive",
            priority: 0,
            workerID: "swift-text-worker",
            admissionLatencyMs: 3
        )
        await readModel.recordPhaseTransition(
            requestID: "req-published",
            phase: .requestPrefilling,
            workerID: "swift-text-worker",
            accelerationMode: .acceleratedPrefill,
            source: "swift-text-worker"
        )

        let events = await recorder.snapshot()
        #expect(events.count == 3)
        #expect(events.allSatisfy { $0.eventType == "request.progress" })
        #expect(events.allSatisfy { $0.requestID == "req-published" })
        #expect(events.last?.source == "swift-text-worker")
        #expect(events.last?.requestProgress.phase == .requestPrefilling)
        #expect(events.last?.requestProgress.accelerationMode == .acceleratedPrefill)
    }

    @Test("queued admitted and phase transitions preserve queue delay and active lane state")
    func queuedAdmittedAndPhaseTransitionsPreserveQueueDelayAndActiveLaneState() async {
        let clock = TestClock()
        let readModel = SchedulerReadModel(
            now: clock.now
        )

        await readModel.recordQueued(
            requestID: "req-phase",
            laneHint: "text.decode.interactive",
            priority: 100,
            queuePosition: 1
        )
        _ = await readModel.recordAdmitted(
            requestID: "req-phase",
            laneHint: "text.decode.interactive",
            priority: 100,
            workerID: "swift-text-worker",
            admissionLatencyMs: 2
        )
        await readModel.recordPhaseTransition(
            requestID: "req-phase",
            phase: Melix_Controlplane_V1_RequestPhase.requestPrefilling,
            laneHint: "text.prefill.hot",
            workerID: "swift-text-worker",
            accelerationMode: Melix_Controlplane_V1_AccelerationMode.acceleratedPrefill,
            accelerationProfileID: "lookup-v1"
        )
        await readModel.recordPhaseTransition(
            requestID: "req-phase",
            phase: Melix_Controlplane_V1_RequestPhase.requestDecoding,
            laneHint: "text.decode.interactive",
            workerID: "swift-text-worker",
            decodeHandle: "decode-123",
            accelerationMode: Melix_Controlplane_V1_AccelerationMode.speculativeDecode,
            draftModelID: "draft-q4"
        )

        let progress = await readModel.progressSnapshot(for: "req-phase")
        let snapshot = await readModel.snapshot()
        let prefillLane = snapshot.lanes.first(where: { $0.laneID == "text.prefill.hot" })
        let decodeLane = snapshot.lanes.first(where: { $0.laneID == "text.decode.interactive" })

        #expect(progress?.phase == .requestDecoding)
        #expect(progress?.queueDelayMs == 1000)
        #expect(progress?.workerID == "swift-text-worker")
        #expect(progress?.decodeHandle == "decode-123")
        #expect(progress?.accelerationMode == .speculativeDecode)
        #expect(progress?.draftModelID == "draft-q4")
        #expect(snapshot.queuedRequests == 0)
        #expect(snapshot.activeRequests == 1)
        #expect(snapshot.lanes.first(where: { $0.laneID == "text.decode.interactive" })?.queueDelayMsP50 == 1000)
        #expect(snapshot.lanes.first(where: { $0.laneID == "text.decode.interactive" })?.queueDelayMsP95 == 1000)
        #expect(prefillLane?.activeRequests == 0)
        #expect(decodeLane?.activeRequests == 1)
    }

    @Test("admitted and terminal requests update queue snapshots and progress")
    func admittedAndTerminalRequestsUpdateQueueSnapshotsAndProgress() async {
        let readModel = SchedulerReadModel()

        let decision = await readModel.recordAdmitted(
            requestID: "req-1",
            laneHint: "text.interactive",
            priority: 0,
            workerID: "swift-text-worker",
            admissionLatencyMs: 4.5
        )
        let admittedProgress = await readModel.progressSnapshot(for: "req-1")
        let admittedSnapshot = await readModel.snapshot()

        #expect(decision.admitted)
        #expect(decision.laneID == "text.decode.interactive")
        #expect(decision.laneClass == "interactive-decode")
        #expect(admittedProgress?.phase == .requestAdmitted)
        #expect(admittedProgress?.admissionState == .admissionAdmitted)
        #expect(admittedProgress?.workerID == "swift-text-worker")
        #expect(admittedSnapshot.activeRequests == 1)
        #expect(admittedSnapshot.admittedRequests == 1)
        #expect(admittedSnapshot.backpressure == 1)
        #expect(
            admittedSnapshot.lanes.first(where: { $0.laneID == "text.decode.interactive" })?.activeRequests == 1
        )

        await readModel.recordTerminalState(
            requestID: "req-1",
            phase: .requestCompleted,
            workerID: "swift-text-worker"
        )

        let completedProgress = await readModel.progressSnapshot(for: "req-1")
        let completedSnapshot = await readModel.snapshot()

        #expect(completedProgress?.phase == .requestCompleted)
        #expect(completedProgress?.workerID == "swift-text-worker")
        #expect(completedSnapshot.activeRequests == 0)
        #expect(completedSnapshot.backpressure == 0)
        #expect(
            completedSnapshot.lanes.first(where: { $0.laneID == "text.decode.interactive" })?.activeRequests == 0
        )
    }

    @Test("rejections keep active lane depth metrics tied to the active lane")
    func rejectionsKeepActiveLaneDepthMetricsTiedToTheActiveLane() async {
        let metricsStore = MetricsStore()
        let readModel = SchedulerReadModel(metricsStore: metricsStore)

        _ = await readModel.recordAdmitted(
            requestID: "req-active",
            laneHint: "text.decode.interactive",
            priority: 100,
            workerID: "swift-text-worker",
            admissionLatencyMs: 2
        )
        _ = await readModel.recordRejected(
            requestID: "req-rejected",
            laneHint: "text.prefill.hot",
            priority: 60
        )

        let metrics = await metricsStore.snapshot()
        let snapshot = await readModel.snapshot()
        let rejectedProgress = await readModel.progressSnapshot(for: "req-rejected")

        #expect(metrics.values["scheduler.active_lane_depth"] == 1)
        #expect(metrics.values["scheduler.backpressure"] == 1)
        #expect(metrics.values["scheduler.rejected_requests"] == 1)
        #expect(snapshot.activeRequests == 1)
        #expect(snapshot.rejectedRequests == 1)
        #expect(rejectedProgress?.phase == .requestRejected)
        #expect(rejectedProgress?.queuePosition == 1)
        #expect(rejectedProgress?.admissionState == .admissionRejected)
    }

    @Test("unknown lanes normalize and terminal requests ignore later transitions")
    func unknownLanesNormalizeAndTerminalRequestsIgnoreLaterTransitions() async {
        let readModel = SchedulerReadModel()

        await readModel.recordQueued(
            requestID: "req-normalized",
            laneHint: "unknown-lane",
            priority: 0,
            queuePosition: 3
        )
        _ = await readModel.recordAdmitted(
            requestID: "req-normalized",
            laneHint: "unknown-lane",
            priority: 0,
            workerID: "swift-text-worker",
            admissionLatencyMs: 1
        )
        await readModel.recordTerminalState(
            requestID: "req-normalized",
            phase: .requestCompleted,
            workerID: "swift-text-worker"
        )
        await readModel.recordPhaseTransition(
            requestID: "req-normalized",
            phase: .requestDecoding,
            laneHint: "text.prefill.hot",
            workerID: "ignored-worker"
        )
        await readModel.recordTerminalState(
            requestID: "missing-request",
            phase: .requestFailed,
            workerID: "missing"
        )

        let progress = await readModel.progressSnapshot(for: "req-normalized")
        let snapshot = await readModel.snapshot()

        #expect(progress?.phase == .requestCompleted)
        #expect(progress?.lane == "text.decode.interactive")
        #expect(progress?.workerID == "swift-text-worker")
        #expect(snapshot.activeRequests == 0)
    }

    @Test("aborted terminal state overrides a previously completed request")
    func abortedTerminalStateOverridesAPreviouslyCompletedRequest() async {
        let recorder = SchedulerEventRecorder()
        let readModel = SchedulerReadModel(
            eventPublisher: { event in
                await recorder.append(event)
            }
        )

        _ = await readModel.recordAdmitted(
            requestID: "req-terminal-upgrade",
            laneHint: "text.decode.interactive",
            priority: 0,
            workerID: "swift-text-worker",
            admissionLatencyMs: 1
        )
        await readModel.recordTerminalState(
            requestID: "req-terminal-upgrade",
            phase: .requestCompleted,
            workerID: "swift-text-worker"
        )
        await readModel.recordTerminalState(
            requestID: "req-terminal-upgrade",
            phase: .requestAborted,
            workerID: "swift-text-worker"
        )

        let progress = await readModel.progressSnapshot(for: "req-terminal-upgrade")
        let events = await recorder.snapshot()

        #expect(progress?.phase == .requestAborted)
        #expect(events.last?.requestProgress.phase == .requestAborted)
    }
}

private final class TestClock: @unchecked Sendable {
    private var tick = 0

    func now() -> Date {
        defer { tick += 1 }
        return Date(timeIntervalSince1970: Double(tick))
    }
}

private actor SchedulerEventRecorder {
    private var events: [Melix_Controlplane_V1_ControlPlaneEvent] = []

    func append(_ event: Melix_Controlplane_V1_ControlPlaneEvent) {
        events.append(event)
    }

    func snapshot() -> [Melix_Controlplane_V1_ControlPlaneEvent] {
        events
    }
}
