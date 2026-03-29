import Foundation
import MelixControlPlaneProtocol

public protocol ImageJobAdmissionControlling: Sendable {
    func acquire(
        requestID: String,
        laneHint: String,
        workerID: String,
        priority: Int32
    ) async throws
    func finish(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        workerID: String?
    ) async
    func cancel(requestID: String) async -> ImageJobCancelDisposition
}

public extension ImageJobAdmissionControlling {
    func acquire(
        requestID: String,
        laneHint: String,
        workerID: String
    ) async throws {
        try await acquire(
            requestID: requestID,
            laneHint: laneHint,
            workerID: workerID,
            priority: 0
        )
    }

    func finish(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase
    ) async {
        await finish(requestID: requestID, phase: phase, workerID: nil)
    }
}

public enum ImageJobAdmissionError: Error, Equatable {
    case cancelled
    case saturated
}

public enum ImageJobCancelDisposition: Equatable, Sendable {
    case notFound
    case queued
    case running
}

public actor ImageJobAdmissionController {
    private struct ActiveRequest {
        let laneHint: String
        let workerID: String
    }

    private struct QueuedRequest {
        let requestID: String
        let laneHint: String
        let workerID: String
        let priority: Int32
        let queuedAt: Date
        let continuation: CheckedContinuation<Void, Error>
    }

    private let maxConcurrentJobs: Int
    private let maxQueuedJobs: Int
    private let schedulerReadModel: SchedulerReadModel?
    private let metricsStore: MetricsStore?
    private let now: @Sendable () -> Date

    private var activeRequests: [String: ActiveRequest]
    private var queuedRequests: [QueuedRequest]

    public init(
        maxConcurrentJobs: Int = 1,
        maxQueuedJobs: Int = 1,
        schedulerReadModel: SchedulerReadModel? = nil,
        metricsStore: MetricsStore? = nil,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.maxConcurrentJobs = max(1, maxConcurrentJobs)
        self.maxQueuedJobs = max(0, maxQueuedJobs)
        self.schedulerReadModel = schedulerReadModel
        self.metricsStore = metricsStore
        self.now = now
        self.activeRequests = [:]
        self.queuedRequests = []
    }

    public func acquire(
        requestID: String,
        laneHint: String,
        workerID: String,
        priority: Int32 = 0
    ) async throws {
        if activeRequests[requestID] != nil || queuedRequests.contains(where: { $0.requestID == requestID }) {
            return
        }

        if activeRequests.count < maxConcurrentJobs && queuedRequests.isEmpty {
            activeRequests[requestID] = ActiveRequest(laneHint: laneHint, workerID: workerID)
            await schedulerReadModel?.recordQueued(
                requestID: requestID,
                laneHint: laneHint,
                priority: priority,
                queuePosition: 0,
                workerID: workerID
            )
            _ = await schedulerReadModel?.recordAdmitted(
                requestID: requestID,
                laneHint: laneHint,
                priority: priority,
                workerID: workerID
            )
            await metricsStore?.set(0, forKey: "images.queue_wait_ms")
            await updateMetrics()
            return
        }

        if queuedRequests.count >= maxQueuedJobs {
            _ = await schedulerReadModel?.recordRejected(
                requestID: requestID,
                laneHint: laneHint,
                priority: priority,
                workerID: workerID
            )
            await metricsStore?.increment("images.rejected_requests")
            await updateMetrics()
            throw ImageJobAdmissionError.saturated
        }

        let queuedAt = now()
        let queuePosition = UInt32(queuedRequests.count + 1)
        await schedulerReadModel?.recordQueued(
            requestID: requestID,
            laneHint: laneHint,
            priority: priority,
            queuePosition: queuePosition,
            workerID: workerID
        )
        await updateMetrics(activeCount: activeRequests.count, queuedCount: queuedRequests.count + 1)

        try await withCheckedThrowingContinuation { continuation in
            queuedRequests.append(
                QueuedRequest(
                    requestID: requestID,
                    laneHint: laneHint,
                    workerID: workerID,
                    priority: priority,
                    queuedAt: queuedAt,
                    continuation: continuation
                )
            )
        }
    }

    public func finish(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        workerID: String? = nil
    ) async {
        let resolvedWorkerID = workerID ?? activeRequests[requestID]?.workerID
        activeRequests.removeValue(forKey: requestID)
        await schedulerReadModel?.recordTerminalState(
            requestID: requestID,
            phase: phase,
            workerID: resolvedWorkerID
        )
        await admitNextQueuedIfPossible()
        await updateMetrics()
    }

    public func cancel(requestID: String) async -> ImageJobCancelDisposition {
        if let queuedIndex = queuedRequests.firstIndex(where: { $0.requestID == requestID }) {
            let queued = queuedRequests.remove(at: queuedIndex)
            await schedulerReadModel?.recordTerminalState(
                requestID: requestID,
                phase: .requestAborted,
                workerID: queued.workerID
            )
            queued.continuation.resume(throwing: ImageJobAdmissionError.cancelled)
            await admitNextQueuedIfPossible()
            await updateMetrics()
            return .queued
        }

        if activeRequests[requestID] != nil {
            return .running
        }

        return .notFound
    }

    public func snapshot() -> (active: Int, queued: Int) {
        (activeRequests.count, queuedRequests.count)
    }

    private func admitNextQueuedIfPossible() async {
        while activeRequests.count < maxConcurrentJobs, queuedRequests.isEmpty == false {
            let queued = queuedRequests.removeFirst()
            activeRequests[queued.requestID] = ActiveRequest(
                laneHint: queued.laneHint,
                workerID: queued.workerID
            )
            _ = await schedulerReadModel?.recordAdmitted(
                requestID: queued.requestID,
                laneHint: queued.laneHint,
                priority: queued.priority,
                workerID: queued.workerID
            )
            let queueWaitMs = max(0, now().timeIntervalSince(queued.queuedAt) * 1000)
            await metricsStore?.set(queueWaitMs, forKey: "images.queue_wait_ms")
            queued.continuation.resume()
        }
    }

    private func updateMetrics() async {
        await updateMetrics(activeCount: activeRequests.count, queuedCount: queuedRequests.count)
    }

    private func updateMetrics(activeCount: Int, queuedCount: Int) async {
        await metricsStore?.set(Double(activeCount), forKey: "images.active_jobs")
        await metricsStore?.set(Double(queuedCount), forKey: "images.queue_depth")
        let backpressure = queuedCount == 0 ? 0.0 : 1.0
        await metricsStore?.set(backpressure, forKey: "images.queue_backpressure")
    }
}

extension ImageJobAdmissionController: ImageJobAdmissionControlling {}
