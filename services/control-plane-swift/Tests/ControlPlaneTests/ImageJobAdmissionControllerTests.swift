import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Image Job Admission Controller")
struct ImageJobAdmissionControllerTests {
    @Test("second image request waits in queue until the active job finishes")
    func secondImageRequestWaitsInQueueUntilTheActiveJobFinishes() async throws {
        let metricsStore = MetricsStore()
        let controller = ImageJobAdmissionController(
            maxConcurrentJobs: 1,
            maxQueuedJobs: 1,
            metricsStore: metricsStore
        )

        try await controller.acquire(
            requestID: "req-image-1",
            laneHint: "image.generate.background",
            workerID: "python-image-worker"
        )

        let secondTask = Task {
            try await controller.acquire(
                requestID: "req-image-2",
                laneHint: "image.generate.background",
                workerID: "python-image-worker"
            )
        }

        try await Task.sleep(for: .milliseconds(50))
        let queuedSnapshot = await controller.snapshot()
        #expect(queuedSnapshot.active == 1)
        #expect(queuedSnapshot.queued == 1)
        #expect(await metricsStore.snapshot().values["images.queue_depth", default: -1] == 1)

        await controller.finish(
            requestID: "req-image-1",
            phase: .requestCompleted,
            workerID: "python-image-worker"
        )
        try await secondTask.value

        let admittedSnapshot = await controller.snapshot()
        #expect(admittedSnapshot.active == 1)
        #expect(admittedSnapshot.queued == 0)

        await controller.finish(
            requestID: "req-image-2",
            phase: .requestCompleted,
            workerID: "python-image-worker"
        )
    }

    @Test("queued image requests can be cancelled before they reach the worker")
    func queuedImageRequestsCanBeCancelledBeforeTheyReachTheWorker() async throws {
        let controller = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)

        try await controller.acquire(
            requestID: "req-image-1",
            laneHint: "image.generate.background",
            workerID: "python-image-worker"
        )

        let queuedTask = Task<Result<Void, Error>, Never> {
            do {
                try await controller.acquire(
                    requestID: "req-image-2",
                    laneHint: "image.generate.background",
                    workerID: "python-image-worker"
                )
                return .success(())
            } catch {
                return .failure(error)
            }
        }

        try await Task.sleep(for: .milliseconds(50))
        let disposition = await controller.cancel(requestID: "req-image-2")
        let result = await queuedTask.value

        #expect(disposition == .queued)
        switch result {
        case .success:
            Issue.record("Expected the queued image request to fail with cancellation.")
        case .failure(let error as ImageJobAdmissionError):
            #expect(error == .cancelled)
        case .failure(let error):
            Issue.record("Unexpected error: \(error)")
        }

        await controller.finish(
            requestID: "req-image-1",
            phase: .requestCompleted,
            workerID: "python-image-worker"
        )
    }

    @Test("image queue rejects new work when the background queue is full")
    func imageQueueRejectsNewWorkWhenTheBackgroundQueueIsFull() async throws {
        let controller = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)

        try await controller.acquire(
            requestID: "req-image-1",
            laneHint: "image.generate.background",
            workerID: "python-image-worker"
        )

        let queuedTask = Task {
            try await controller.acquire(
                requestID: "req-image-2",
                laneHint: "image.generate.background",
                workerID: "python-image-worker"
            )
        }

        try await Task.sleep(for: .milliseconds(50))

        do {
            try await controller.acquire(
                requestID: "req-image-3",
                laneHint: "image.generate.background",
                workerID: "python-image-worker"
            )
            Issue.record("Expected the third image request to be rejected.")
        } catch let error as ImageJobAdmissionError {
            #expect(error == .saturated)
        }

        await controller.finish(
            requestID: "req-image-1",
            phase: .requestCompleted,
            workerID: "python-image-worker"
        )
        try await queuedTask.value
        await controller.finish(
            requestID: "req-image-2",
            phase: .requestCompleted,
            workerID: "python-image-worker"
        )
    }
}
