import Foundation
import MelixControlPlaneProtocol

public struct SchedulerLaneDefinition: Sendable, Equatable {
    public let laneID: String
    public let laneClass: String
    public let defaultPriorityScore: Double

    public init(laneID: String, laneClass: String, defaultPriorityScore: Double) {
        self.laneID = laneID
        self.laneClass = laneClass
        self.defaultPriorityScore = defaultPriorityScore
    }
}

public struct AdmissionDecision: Sendable, Equatable {
    public let admitted: Bool
    public let laneID: String
    public let laneClass: String
    public let queuePosition: UInt32
    public let priorityScore: Double
    public let backpressure: Double
    public let admissionState: Melix_Controlplane_V1_AdmissionState
}

public actor SchedulerReadModel {
    public typealias EventPublisher = @Sendable (Melix_Controlplane_V1_ControlPlaneEvent) async -> Void

    private struct LaneStats: Sendable {
        var activeRequests: UInt32 = 0
        var admittedRequests: UInt32 = 0
        var rejectedRequests: UInt32 = 0
    }

    private struct RequestRecord: Sendable {
        var laneID: String
        var phase: Melix_Controlplane_V1_RequestPhase
        var admissionState: Melix_Controlplane_V1_AdmissionState
    }

    private let laneDefinitions: [String: SchedulerLaneDefinition]
    private let laneOrder: [SchedulerLaneDefinition]
    private let eventPublisher: EventPublisher?
    private let metricsStore: MetricsStore?
    private let now: @Sendable () -> Date

    private var laneStats: [String: LaneStats]
    private var activeRequestID: String?
    private var requestRecords: [String: RequestRecord]
    private var requestProgressSnapshots: [String: Melix_Controlplane_V1_RequestProgressEvent]
    private var admittedRequests: UInt32
    private var rejectedRequests: UInt32
    private var lastAdmissionLatencyMs: Double

    public init(
        laneDefinitions: [SchedulerLaneDefinition] = SchedulerReadModel.defaultLanes,
        metricsStore: MetricsStore? = nil,
        eventPublisher: EventPublisher? = nil,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.laneOrder = laneDefinitions
        self.laneDefinitions = Dictionary(
            uniqueKeysWithValues: laneDefinitions.map { ($0.laneID, $0) }
        )
        self.metricsStore = metricsStore
        self.eventPublisher = eventPublisher
        self.now = now
        self.laneStats = Dictionary(
            uniqueKeysWithValues: laneDefinitions.map { ($0.laneID, LaneStats()) }
        )
        self.requestRecords = [:]
        self.requestProgressSnapshots = [:]
        self.admittedRequests = 0
        self.rejectedRequests = 0
        self.lastAdmissionLatencyMs = 0
    }

    public func recordRejected(
        requestID: String,
        laneHint: String,
        priority: Int32,
        workerID: String? = nil
    ) async -> AdmissionDecision {
        let lane = normalizedLane(for: laneHint)
        let priorityScore = normalizedPriority(priority, lane: lane)
        let backpressure = currentBackpressure()

        rejectedRequests += 1
        laneStats[lane.laneID, default: LaneStats()].rejectedRequests += 1
        await updateMetrics(backpressure: backpressure)

        var progress = Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = .requestRejected
        progress.lane = lane.laneID
        progress.priorityScore = priorityScore
        progress.backpressure = backpressure
        progress.workerID = workerID ?? ""
        progress.admissionState = .admissionRejected
        progress.queuePosition = activeRequestID == nil ? 0 : 1
        requestRecords[requestID] = RequestRecord(
            laneID: lane.laneID,
            phase: .requestRejected,
            admissionState: .admissionRejected
        )
        requestProgressSnapshots[requestID] = progress
        await publish(progress, source: "scheduler")

        return AdmissionDecision(
            admitted: false,
            laneID: lane.laneID,
            laneClass: lane.laneClass,
            queuePosition: progress.queuePosition,
            priorityScore: priorityScore,
            backpressure: backpressure,
            admissionState: .admissionRejected
        )
    }

    public func recordAdmitted(
        requestID: String,
        laneHint: String,
        priority: Int32,
        workerID: String? = nil,
        admissionLatencyMs: Double = 0
    ) async -> AdmissionDecision {
        let lane = normalizedLane(for: laneHint)
        let priorityScore = normalizedPriority(priority, lane: lane)
        let backpressureBeforeAdmission = currentBackpressure()

        activeRequestID = requestID
        admittedRequests += 1
        lastAdmissionLatencyMs = admissionLatencyMs
        laneStats[lane.laneID, default: LaneStats()].activeRequests = 1
        laneStats[lane.laneID, default: LaneStats()].admittedRequests += 1
        await updateMetrics(backpressure: backpressureBeforeAdmission)

        var progress = Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = .requestAdmitted
        progress.lane = lane.laneID
        progress.priorityScore = priorityScore
        progress.backpressure = backpressureBeforeAdmission
        progress.workerID = workerID ?? ""
        progress.admissionState = .admissionAdmitted
        requestRecords[requestID] = RequestRecord(
            laneID: lane.laneID,
            phase: .requestAdmitted,
            admissionState: .admissionAdmitted
        )
        requestProgressSnapshots[requestID] = progress
        await publish(progress, source: "scheduler")

        return AdmissionDecision(
            admitted: true,
            laneID: lane.laneID,
            laneClass: lane.laneClass,
            queuePosition: 0,
            priorityScore: priorityScore,
            backpressure: backpressureBeforeAdmission,
            admissionState: .admissionAdmitted
        )
    }

    public func recordTerminalState(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        workerID: String? = nil
    ) async {
        guard let record = requestRecords[requestID] else {
            return
        }
        guard !isTerminal(record.phase) else {
            return
        }

        if activeRequestID == requestID {
            activeRequestID = nil
            laneStats[record.laneID, default: LaneStats()].activeRequests = 0
        }

        await updateMetrics(backpressure: currentBackpressure())

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = phase
        progress.lane = record.laneID
        progress.workerID = workerID ?? progress.workerID
        requestRecords[requestID] = RequestRecord(
            laneID: record.laneID,
            phase: phase,
            admissionState: record.admissionState
        )
        requestProgressSnapshots[requestID] = progress
        await publish(progress, source: "scheduler")
    }

    public func snapshot() -> Melix_Controlplane_V1_QueueSummary {
        var summary = Melix_Controlplane_V1_QueueSummary()
        summary.queuedRequests = 0
        summary.activeRequests = activeRequestID == nil ? 0 : 1
        summary.admissionLatencyMs = lastAdmissionLatencyMs
        summary.backpressure = currentBackpressure()
        summary.admittedRequests = admittedRequests
        summary.rejectedRequests = rejectedRequests
        summary.lanes = laneOrder.map { lane in
            var result = Melix_Controlplane_V1_QueueLaneSummary()
            let stats = laneStats[lane.laneID, default: LaneStats()]
            result.laneID = lane.laneID
            result.laneClass = lane.laneClass
            result.queuedRequests = 0
            result.activeRequests = stats.activeRequests
            result.queueDelayMsP50 = 0
            result.queueDelayMsP95 = 0
            let totalDecisions = stats.admittedRequests + stats.rejectedRequests
            result.admissionRate = totalDecisions == 0
                ? 1
                : Double(stats.admittedRequests) / Double(totalDecisions)
            result.backpressure = activeRequestID == nil ? 0 : (activeLaneID == lane.laneID ? 1 : 0)
            result.priorityScore = lane.defaultPriorityScore
            return result
        }
        return summary
    }

    public func progressSnapshot(
        for requestID: String
    ) -> Melix_Controlplane_V1_RequestProgressEvent? {
        requestProgressSnapshots[requestID]
    }

    private var activeLaneID: String? {
        guard let activeRequestID else { return nil }
        return requestRecords[activeRequestID]?.laneID
    }

    private func normalizedLane(for laneHint: String) -> SchedulerLaneDefinition {
        if let lane = laneDefinitions[laneHint] {
            return lane
        }
        if laneHint == "text.interactive" {
            return laneDefinitions["text.decode.interactive"] ?? Self.defaultLanes[0]
        }
        return laneDefinitions["text.decode.interactive"] ?? Self.defaultLanes[0]
    }

    private func normalizedPriority(_ priority: Int32, lane: SchedulerLaneDefinition) -> Double {
        priority == 0 ? lane.defaultPriorityScore : Double(priority)
    }

    private func currentBackpressure() -> Double {
        activeRequestID == nil ? 0 : 1
    }

    private func isTerminal(_ phase: Melix_Controlplane_V1_RequestPhase) -> Bool {
        switch phase {
        case .requestCompleted, .requestAborted, .requestFailed, .requestRejected:
            return true
        default:
            return false
        }
    }

    private func publish(
        _ progress: Melix_Controlplane_V1_RequestProgressEvent,
        source: String
    ) async {
        guard let eventPublisher else { return }
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "request.progress"
        event.source = source
        event.requestID = progress.requestID
        event.emittedAtUnixMs = Int64(now().timeIntervalSince1970 * 1000)
        event.requestProgress = progress
        await eventPublisher(event)
    }

    private func updateMetrics(backpressure: Double) async {
        guard let metricsStore else { return }
        await metricsStore.set(lastAdmissionLatencyMs, forKey: "scheduler.admission_latency_ms")
        await metricsStore.set(Double(rejectedRequests), forKey: "scheduler.rejected_requests")
        await metricsStore.set(backpressure, forKey: "scheduler.backpressure")
        let activeDepth = activeLaneID.map { laneID in
            Double(laneStats[laneID, default: LaneStats()].activeRequests)
        } ?? 0
        await metricsStore.set(activeDepth, forKey: "scheduler.active_lane_depth")
    }

    public static let defaultLanes: [SchedulerLaneDefinition] = [
        SchedulerLaneDefinition(
            laneID: "text.decode.interactive",
            laneClass: "interactive-decode",
            defaultPriorityScore: 100
        ),
        SchedulerLaneDefinition(
            laneID: "text.prefill.hot",
            laneClass: "hot-prefill",
            defaultPriorityScore: 60
        ),
        SchedulerLaneDefinition(
            laneID: "text.prefill.background",
            laneClass: "background-prefill",
            defaultPriorityScore: 20
        ),
    ]
}
