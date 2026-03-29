import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Image Job Read Model")
struct ImageJobReadModelTests {
    @Test("queued running and completed image jobs are preserved in snapshots")
    func queuedRunningAndCompletedImageJobsArePreservedInSnapshots() async throws {
        let clock = ImageJobTestClock()
        let readModel = ImageJobReadModel(now: clock.now)

        await readModel.recordQueued(
            requestID: "req-image-1",
            jobID: "job-image-1",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background",
            promptDigest: "prompt:abc"
        )
        await readModel.recordRunning(
            jobID: "job-image-1",
            workerID: "python-image-worker",
            stage: "denoise",
            pct: 0.5,
            completedSteps: 10,
            totalSteps: 20
        )

        var artifact = Melix_Controlplane_V1_ImageArtifactRef()
        artifact.artifactID = "artifact-1"
        artifact.jobID = "job-image-1"
        artifact.role = .imageArtifactGenerated
        artifact.mimeType = "image/png"
        artifact.format = "png"
        artifact.width = 1024
        artifact.height = 1024
        artifact.byteLength = 4096
        artifact.storageUri = ".runtime/images/job-image-1/output-0.png"
        artifact.variantIndex = 0

        await readModel.recordCompleted(
            jobID: "job-image-1",
            artifacts: [artifact]
        )

        let snapshot = await readModel.snapshot()
        let job = try #require(snapshot.first(where: { $0.jobID == "job-image-1" }))

        #expect(job.state == .imageJobCompleted)
        #expect(job.workerID == "python-image-worker")
        #expect(job.lane == "image.generate.background")
        #expect(job.progress.stage == "completed")
        #expect(job.progress.pct == 1)
        #expect(job.cancelable == false)
        #expect(job.artifacts.count == 1)
        #expect(job.artifacts.first?.artifactID == "artifact-1")
        #expect(job.promptDigest == "prompt:abc")
    }

    @Test("canceled and failed image jobs remain terminal")
    func canceledAndFailedImageJobsRemainTerminal() async throws {
        let readModel = ImageJobReadModel()

        await readModel.recordQueued(
            requestID: "req-image-cancel",
            jobID: "job-image-cancel",
            modelID: "melix-dev-image",
            operation: "image_edit",
            lane: "image.edit.background"
        )
        await readModel.recordCanceled(jobID: "job-image-cancel")

        await readModel.recordQueued(
            requestID: "req-image-fail",
            jobID: "job-image-fail",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = "runtime_failed"
        error.message = "GPU pressure exceeded budget."
        await readModel.recordFailed(jobID: "job-image-fail", error: error)

        let canceled = try #require(await readModel.job(jobID: "job-image-cancel"))
        let failed = try #require(await readModel.job(requestID: "req-image-fail"))

        #expect(canceled.state == .imageJobCanceled)
        #expect(canceled.cancelable == false)
        #expect(canceled.progress.stage == "canceled")
        #expect(failed.state == .imageJobFailed)
        #expect(failed.cancelable == false)
        #expect(failed.error.code == "runtime_failed")
        #expect(failed.progress.stage == "failed")
    }

    @Test("image job state changes publish through the configured event publisher")
    func imageJobStateChangesPublishThroughConfiguredEventPublisher() async throws {
        let recorder = ImageJobEventRecorder()
        let clock = ImageJobTestClock()
        let readModel = ImageJobReadModel(
            eventPublisher: { event in
                await recorder.append(event)
            },
            now: clock.now
        )

        await readModel.recordQueued(
            requestID: "req-image-events",
            jobID: "job-image-events",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        await readModel.recordRunning(
            jobID: "job-image-events",
            workerID: "python-image-worker",
            stage: "decode",
            pct: 0.25,
            completedSteps: 5,
            totalSteps: 20
        )

        let events = await recorder.snapshot()
        #expect(events.count == 2)
        #expect(events.allSatisfy { $0.eventType == "image.job.state_changed" })
        #expect(events.allSatisfy { $0.source == "image-jobs" })
        #expect(events.last?.imageJob.job.jobID == "job-image-events")
        #expect(events.last?.imageJob.job.state == .imageJobRunning)
        #expect(events.last?.imageJob.job.progress.stage == "decode")
    }

    @Test("server snapshot builder carries image job summaries")
    func serverSnapshotBuilderCarriesImageJobSummaries() async throws {
        var job = Melix_Controlplane_V1_ImageJobSummary()
        job.jobID = "job-image-snapshot"
        job.requestID = "req-image-snapshot"
        job.modelID = "melix-dev-image"
        job.operation = "image_generate"
        job.state = .imageJobQueued

        let snapshot = ServerSnapshotBuilder().build(
            models: [],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            imageJobs: [job]
        )

        #expect(snapshot.imageJobs.count == 1)
        #expect(snapshot.imageJobs.first?.jobID == "job-image-snapshot")
    }
}

private final class ImageJobTestClock: @unchecked Sendable {
    private var tick = 0

    func now() -> Date {
        defer { tick += 1 }
        return Date(timeIntervalSince1970: Double(tick))
    }
}

private actor ImageJobEventRecorder {
    private var events: [Melix_Controlplane_V1_ControlPlaneEvent] = []

    func append(_ event: Melix_Controlplane_V1_ControlPlaneEvent) {
        events.append(event)
    }

    func snapshot() -> [Melix_Controlplane_V1_ControlPlaneEvent] {
        events
    }
}
