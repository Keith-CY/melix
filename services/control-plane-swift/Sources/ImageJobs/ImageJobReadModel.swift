import Foundation
import MelixControlPlaneProtocol

public actor ImageJobReadModel {
    public typealias EventPublisher = @Sendable (Melix_Controlplane_V1_ControlPlaneEvent) async -> Void

    private let eventPublisher: EventPublisher?
    private let now: @Sendable () -> Date

    private var jobsByID: [String: Melix_Controlplane_V1_ImageJobSummary]
    private var requestToJobID: [String: String]

    public init(
        eventPublisher: EventPublisher? = nil,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.eventPublisher = eventPublisher
        self.now = now
        self.jobsByID = [:]
        self.requestToJobID = [:]
    }

    public func recordQueued(
        requestID: String,
        jobID: String,
        modelID: String,
        operation: String,
        lane: String,
        promptDigest: String = "",
        recipe: Melix_Controlplane_V1_ImageJobRecipeSummary = Melix_Controlplane_V1_ImageJobRecipeSummary(),
        timeoutSeconds: UInt32 = 0,
        sourceArtifactID: String = "",
        sourceJobID: String = "",
        promptDelta: String = "",
        editMode: Melix_Controlplane_V1_ImageEditMode = .unspecified,
        cancelable: Bool = true
    ) async {
        let timestamp = unixMilliseconds()
        var job = jobsByID[jobID] ?? Melix_Controlplane_V1_ImageJobSummary()
        job.jobID = jobID
        job.requestID = requestID
        job.modelID = modelID
        job.operation = operation
        job.state = .imageJobQueued
        job.lane = lane
        job.cancelable = cancelable
        job.promptDigest = promptDigest
        job.recipe = recipe
        job.timeoutSeconds = timeoutSeconds
        job.sourceArtifactID = sourceArtifactID
        job.sourceJobID = sourceJobID
        job.promptDelta = promptDelta
        job.editMode = editMode
        if job.createdAtUnixMs == 0 {
            job.createdAtUnixMs = timestamp
        }
        job.updatedAtUnixMs = timestamp
        if job.progress.stage.isEmpty {
            job.progress = progress(stage: "queued", pct: 0)
        }

        jobsByID[jobID] = job
        requestToJobID[requestID] = jobID
        await publish(job)
    }

    public func recordRunning(
        jobID: String,
        workerID: String,
        stage: String = "running",
        pct: Float,
        completedSteps: UInt32 = 0,
        totalSteps: UInt32 = 0
    ) async {
        guard var job = jobsByID[jobID] else {
            return
        }
        job.state = .imageJobRunning
        job.workerID = workerID
        job.progress = progress(
            stage: stage,
            pct: pct,
            completedSteps: completedSteps,
            totalSteps: totalSteps
        )
        job.updatedAtUnixMs = unixMilliseconds()
        jobsByID[jobID] = job
        await publish(job)
    }

    public func recordCanceled(jobID: String) async {
        guard var job = jobsByID[jobID] else {
            return
        }
        job.state = .imageJobCanceled
        job.cancelable = false
        job.progress.stage = "canceled"
        job.updatedAtUnixMs = unixMilliseconds()
        jobsByID[jobID] = job
        await publish(job)
    }

    public func recordFailed(
        jobID: String,
        error: Melix_Controlplane_V1_ErrorStatus
    ) async {
        guard var job = jobsByID[jobID] else {
            return
        }
        job.state = .imageJobFailed
        job.cancelable = false
        job.error = error
        job.progress.stage = error.code == "deadline_exceeded" ? "timed_out" : "failed"
        job.updatedAtUnixMs = unixMilliseconds()
        jobsByID[jobID] = job
        await publish(job)
    }

    public func recordCompleted(
        jobID: String,
        artifacts: [Melix_Controlplane_V1_ImageArtifactRef]
    ) async {
        guard var job = jobsByID[jobID] else {
            return
        }
        job.state = .imageJobCompleted
        job.cancelable = false
        job.artifacts = artifacts
        job.progress = progress(stage: "completed", pct: 1, completedSteps: 1, totalSteps: 1)
        job.updatedAtUnixMs = unixMilliseconds()
        jobsByID[jobID] = job
        await publish(job)
    }

    public func snapshot() -> [Melix_Controlplane_V1_ImageJobSummary] {
        jobsByID.values.sorted { lhs, rhs in
            if lhs.createdAtUnixMs == rhs.createdAtUnixMs {
                return lhs.jobID < rhs.jobID
            }
            return lhs.createdAtUnixMs < rhs.createdAtUnixMs
        }
    }

    public func job(jobID: String) -> Melix_Controlplane_V1_ImageJobSummary? {
        jobsByID[jobID]
    }

    public func job(requestID: String) -> Melix_Controlplane_V1_ImageJobSummary? {
        guard let jobID = requestToJobID[requestID] else {
            return nil
        }
        return jobsByID[jobID]
    }

    public func artifact(artifactID: String) -> Melix_Controlplane_V1_ImageArtifactRef? {
        for job in jobsByID.values {
            if let artifact = job.artifacts.first(where: { $0.artifactID == artifactID }) {
                return artifact
            }
        }
        return nil
    }

    private func publish(_ job: Melix_Controlplane_V1_ImageJobSummary) async {
        guard let eventPublisher else {
            return
        }
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "image.job.state_changed"
        event.source = "image-jobs"
        event.requestID = job.requestID

        var payload = Melix_Controlplane_V1_ImageJobStateChanged()
        payload.job = job
        event.imageJob = payload

        await eventPublisher(event)
    }

    private func unixMilliseconds() -> Int64 {
        Int64((now().timeIntervalSince1970 * 1000).rounded())
    }

    private func progress(
        stage: String,
        pct: Float,
        completedSteps: UInt32 = 0,
        totalSteps: UInt32 = 0
    ) -> Melix_Controlplane_V1_ImageJobProgress {
        var progress = Melix_Controlplane_V1_ImageJobProgress()
        progress.stage = stage
        progress.pct = pct
        progress.completedSteps = completedSteps
        progress.totalSteps = totalSteps
        return progress
    }
}
