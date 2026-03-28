import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Scheduler Read Model")
struct SchedulerReadModelTests {
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
}
