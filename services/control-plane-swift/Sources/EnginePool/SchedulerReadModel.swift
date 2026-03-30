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
        var queuedRequests: UInt32 = 0
        var activeRequests: UInt32 = 0
        var admittedRequests: UInt32 = 0
        var rejectedRequests: UInt32 = 0
        var queueDelaySamplesMs: [Double] = []
    }

    private struct RequestRecord: Sendable {
        var laneID: String
        var phase: Melix_Controlplane_V1_RequestPhase
        var admissionState: Melix_Controlplane_V1_AdmissionState
        var priorityScore: Double
        var queuedAt: Date?
        var batchCohortID: String = ""
        var batchCapacity: UInt32 = 1
        var affinityClass: String = "cold"
    }

    private let laneDefinitions: [String: SchedulerLaneDefinition]
    private let laneOrder: [SchedulerLaneDefinition]
    private let eventPublisher: EventPublisher?
    private let metricsStore: MetricsStore?
    private let now: @Sendable () -> Date

    private var laneStats: [String: LaneStats]
    private var activeRequestIDs: Set<String>
    private var requestRecords: [String: RequestRecord]
    private var requestProgressSnapshots: [String: Melix_Controlplane_V1_RequestProgressEvent]
    private var batchRequestIDsByCohort: [String: Set<String>]
    private var admittedRequests: UInt32
    private var rejectedRequests: UInt32
    private var lastAdmissionLatencyMs: Double
    private var lastQueueDelayMs: Double
    private var batchEligibleRequestCount: Double
    private var batchMergedRequestCount: Double
    private var batchAffinityPreferredCount: Double
    private var lastContinuousBatchSize: UInt32
    private var lastContinuousBatchOccupancyPct: Double
    private var lastPrefillProcessedTokens: UInt32
    private var lastPrefillTotalTokens: UInt32
    private var lastPrefillProgressPct: Double
    private var lastPrefillActiveRequests: UInt32
    private var lastPrefillWaitingRequests: UInt32
    private var lastRestoreStageCode: Double
    private var lastObservedCachePressure: Double

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
        self.activeRequestIDs = []
        self.requestRecords = [:]
        self.requestProgressSnapshots = [:]
        self.batchRequestIDsByCohort = [:]
        self.admittedRequests = 0
        self.rejectedRequests = 0
        self.lastAdmissionLatencyMs = 0
        self.lastQueueDelayMs = 0
        self.batchEligibleRequestCount = 0
        self.batchMergedRequestCount = 0
        self.batchAffinityPreferredCount = 0
        self.lastContinuousBatchSize = 0
        self.lastContinuousBatchOccupancyPct = 0
        self.lastPrefillProcessedTokens = 0
        self.lastPrefillTotalTokens = 0
        self.lastPrefillProgressPct = 0
        self.lastPrefillActiveRequests = 0
        self.lastPrefillWaitingRequests = 0
        self.lastRestoreStageCode = 0
        self.lastObservedCachePressure = 0
    }

    public func recordQueued(
        requestID: String,
        laneHint: String,
        priority: Int32,
        queuePosition: UInt32 = 1,
        workerID: String? = nil
    ) async {
        let lane = normalizedLane(for: laneHint)
        let priorityScore = normalizedPriority(priority, lane: lane)

        laneStats[lane.laneID, default: LaneStats()].queuedRequests += 1
        requestRecords[requestID] = RequestRecord(
            laneID: lane.laneID,
            phase: .requestQueued,
            admissionState: .admissionQueued,
            priorityScore: priorityScore,
            queuedAt: now()
        )

        var progress = Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = .requestQueued
        progress.lane = lane.laneID
        progress.priorityScore = priorityScore
        progress.backpressure = currentBackpressure()
        progress.workerID = workerID ?? ""
        progress.admissionState = .admissionQueued
        progress.queuePosition = queuePosition
        populateSchedulerSnapshot(into: &progress)
        requestProgressSnapshots[requestID] = progress

        await updateMetrics(backpressure: currentBackpressure())
        await publish(progress, source: "scheduler")
    }

    public func recordRejected(
        requestID: String,
        laneHint: String,
        priority: Int32,
        workerID: String? = nil
    ) async -> AdmissionDecision {
        let lane = normalizedLane(for: laneHint)
        let priorityScore = normalizedPriority(priority, lane: lane)
        var backpressure = currentBackpressure()

        rejectedRequests += 1
        laneStats[lane.laneID, default: LaneStats()].rejectedRequests += 1
        if let existing = requestRecords[requestID], existing.phase == .requestQueued {
            laneStats[existing.laneID, default: LaneStats()].queuedRequests = max(
                0,
                laneStats[existing.laneID, default: LaneStats()].queuedRequests - 1
            )
        }
        backpressure = currentBackpressure()
        await updateMetrics(backpressure: backpressure)

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = .requestRejected
        progress.lane = lane.laneID
        progress.priorityScore = priorityScore
        progress.backpressure = backpressure
        progress.workerID = workerID ?? ""
        progress.admissionState = .admissionRejected
        progress.queuePosition = totalActiveRequests == 0 ? 0 : 1
        populateSchedulerSnapshot(into: &progress)
        requestRecords[requestID] = RequestRecord(
            laneID: lane.laneID,
            phase: .requestRejected,
            admissionState: .admissionRejected,
            priorityScore: priorityScore,
            queuedAt: requestRecords[requestID]?.queuedAt,
            batchCohortID: requestRecords[requestID]?.batchCohortID ?? "",
            batchCapacity: requestRecords[requestID]?.batchCapacity ?? 1,
            affinityClass: requestRecords[requestID]?.affinityClass ?? "cold"
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
        let queuedAt = requestRecords[requestID]?.queuedAt
        let queueDelayMs = queuedAt.map { max(0, now().timeIntervalSince($0) * 1000) } ?? 0
        let backpressureBeforeAdmission = currentBackpressure()

        activeRequestIDs.insert(requestID)
        admittedRequests += 1
        lastAdmissionLatencyMs = admissionLatencyMs
        lastQueueDelayMs = queueDelayMs
        if let previous = requestRecords[requestID], previous.phase == .requestQueued {
            laneStats[previous.laneID, default: LaneStats()].queuedRequests = max(
                0,
                laneStats[previous.laneID, default: LaneStats()].queuedRequests - 1
            )
        }
        laneStats[lane.laneID, default: LaneStats()].activeRequests += 1
        laneStats[lane.laneID, default: LaneStats()].admittedRequests += 1
        laneStats[lane.laneID, default: LaneStats()].queueDelaySamplesMs.append(queueDelayMs)
        await updateMetrics(backpressure: backpressureBeforeAdmission)

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = .requestAdmitted
        progress.lane = lane.laneID
        progress.queueDelayMs = queueDelayMs
        progress.queuePosition = 0
        progress.priorityScore = priorityScore
        progress.backpressure = backpressureBeforeAdmission
        progress.workerID = workerID ?? ""
        progress.admissionState = .admissionAdmitted
        populateSchedulerSnapshot(into: &progress)
        requestRecords[requestID] = RequestRecord(
            laneID: lane.laneID,
            phase: .requestAdmitted,
            admissionState: .admissionAdmitted,
            priorityScore: priorityScore,
            queuedAt: queuedAt,
            batchCohortID: requestRecords[requestID]?.batchCohortID ?? "",
            batchCapacity: requestRecords[requestID]?.batchCapacity ?? 1,
            affinityClass: requestRecords[requestID]?.affinityClass ?? "cold"
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

    public func recordContinuousBatchAdmission(
        requestID: String,
        cohortID: String,
        batchPosition: UInt32,
        batchSize: UInt32,
        batchCapacity: UInt32,
        eligible: Bool,
        mergedIntoBatch: Bool,
        affinityClass: String
    ) async {
        guard var record = requestRecords[requestID] else {
            return
        }

        let normalizedCapacity = max(batchCapacity, 1)
        record.batchCohortID = cohortID
        record.batchCapacity = normalizedCapacity
        record.affinityClass = affinityClass
        requestRecords[requestID] = record

        if !cohortID.isEmpty {
            var cohortRequests = batchRequestIDsByCohort[cohortID, default: []]
            cohortRequests.insert(requestID)
            batchRequestIDsByCohort[cohortID] = cohortRequests
        }

        if eligible {
            batchEligibleRequestCount += 1
            if affinityClass != "cold" {
                batchAffinityPreferredCount += 1
            }
        }
        if mergedIntoBatch {
            batchMergedRequestCount += 1
        }

        lastContinuousBatchSize = batchSize
        lastContinuousBatchOccupancyPct = Double(batchSize) / Double(normalizedCapacity) * 100

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.queuePosition = batchPosition
        populateSchedulerSnapshot(into: &progress)
        requestProgressSnapshots[requestID] = progress

        await updateMetrics(backpressure: currentBackpressure())
    }

    public func recordPrefillProgress(
        requestID: String,
        processedTokens: UInt32,
        totalTokens: UInt32,
        restoreStage: String,
        cachePressure: Double,
        source: String = "scheduler"
    ) async {
        guard var record = requestRecords[requestID] else {
            return
        }
        guard !isTerminal(record.phase) else {
            return
        }

        let normalizedTotalTokens = max(totalTokens, processedTokens)
        let progressPct = normalizedTotalTokens == 0
            ? 0
            : min(Double(processedTokens) / Double(normalizedTotalTokens) * 100, 100)

        lastPrefillProcessedTokens = processedTokens
        lastPrefillTotalTokens = normalizedTotalTokens
        lastPrefillProgressPct = progressPct
        lastPrefillActiveRequests = totalActiveRequests
        lastPrefillWaitingRequests = totalQueuedRequests
        lastRestoreStageCode = restoreStageMetricCode(for: restoreStage)
        lastObservedCachePressure = cachePressure

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = .requestPrefilling
        progress.lane = record.laneID
        progress.backpressure = currentBackpressure()
        progress.prefillProcessedTokens = processedTokens
        progress.prefillTotalTokens = normalizedTotalTokens
        progress.prefillProgressPct = progressPct
        progress.restoreStage = restoreStage
        progress.cachePressure = cachePressure
        populateSchedulerSnapshot(into: &progress)

        record.phase = .requestPrefilling
        requestRecords[requestID] = record
        requestProgressSnapshots[requestID] = progress

        await updateMetrics(backpressure: currentBackpressure())
        await publish(progress, source: source)
    }

    public func recordPhaseTransition(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        laneHint: String? = nil,
        workerID: String? = nil,
        decodeHandle: String? = nil,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode? = nil,
        accelerationProfileID: String? = nil,
        draftModelID: String? = nil,
        source: String = "scheduler"
    ) async {
        guard var record = requestRecords[requestID] else {
            return
        }
        guard !isTerminal(record.phase) else {
            return
        }

        let lane = laneHint.map(normalizedLane(for:)) ?? laneDefinitions[record.laneID] ?? Self.defaultLanes[0]
        if activeRequestIDs.contains(requestID), record.laneID != lane.laneID {
            laneStats[record.laneID, default: LaneStats()].activeRequests = max(
                0,
                laneStats[record.laneID, default: LaneStats()].activeRequests - 1
            )
            laneStats[lane.laneID, default: LaneStats()].activeRequests += 1
        }

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = phase
        progress.lane = lane.laneID
        progress.backpressure = currentBackpressure()
        if let workerID, !workerID.isEmpty {
            progress.workerID = workerID
        }
        if let decodeHandle, !decodeHandle.isEmpty {
            progress.decodeHandle = decodeHandle
        }
        if let accelerationMode {
            progress.accelerationMode = accelerationMode
        }
        if let accelerationProfileID, !accelerationProfileID.isEmpty {
            progress.accelerationProfileID = accelerationProfileID
        }
        if let draftModelID, !draftModelID.isEmpty {
            progress.draftModelID = draftModelID
        }
        populateSchedulerSnapshot(into: &progress)

        record.laneID = lane.laneID
        record.phase = phase
        requestRecords[requestID] = record
        requestProgressSnapshots[requestID] = progress

        await updateMetrics(backpressure: currentBackpressure())
        await publish(progress, source: source)
    }

    public func recordTerminalState(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        workerID: String? = nil
    ) async {
        guard let record = requestRecords[requestID] else {
            return
        }
        if isTerminal(record.phase) {
            guard record.phase == .requestCompleted, phase == .requestAborted else {
                return
            }

            var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
            progress.requestID = requestID
            progress.phase = .requestAborted
            progress.lane = record.laneID
            progress.workerID = workerID ?? progress.workerID
            populateSchedulerSnapshot(into: &progress)
            requestRecords[requestID] = RequestRecord(
                laneID: record.laneID,
                phase: .requestAborted,
                admissionState: record.admissionState,
                priorityScore: record.priorityScore,
                queuedAt: record.queuedAt
            )
            requestProgressSnapshots[requestID] = progress
            await publish(progress, source: "scheduler")
            return
        }

        if activeRequestIDs.remove(requestID) != nil {
            laneStats[record.laneID, default: LaneStats()].activeRequests = max(
                0,
                laneStats[record.laneID, default: LaneStats()].activeRequests - 1
            )
        }
        if !record.batchCohortID.isEmpty {
            var cohortRequests = batchRequestIDsByCohort[record.batchCohortID, default: []]
            cohortRequests.remove(requestID)
            if cohortRequests.isEmpty {
                batchRequestIDsByCohort.removeValue(forKey: record.batchCohortID)
            } else {
                batchRequestIDsByCohort[record.batchCohortID] = cohortRequests
            }
        }
        if record.phase == .requestQueued {
            laneStats[record.laneID, default: LaneStats()].queuedRequests = max(
                0,
                laneStats[record.laneID, default: LaneStats()].queuedRequests - 1
            )
        }

        await updateMetrics(backpressure: currentBackpressure())

        var progress = requestProgressSnapshots[requestID] ?? Melix_Controlplane_V1_RequestProgressEvent()
        progress.requestID = requestID
        progress.phase = phase
        progress.lane = record.laneID
        progress.workerID = workerID ?? progress.workerID
        populateSchedulerSnapshot(into: &progress)
        requestRecords[requestID] = RequestRecord(
            laneID: record.laneID,
            phase: phase,
            admissionState: record.admissionState,
            priorityScore: record.priorityScore,
            queuedAt: record.queuedAt
        )
        requestProgressSnapshots[requestID] = progress
        await publish(progress, source: "scheduler")
    }

    public func snapshot() -> Melix_Controlplane_V1_QueueSummary {
        var summary = Melix_Controlplane_V1_QueueSummary()
        summary.queuedRequests = totalQueuedRequests
        summary.activeRequests = totalActiveRequests
        summary.admissionLatencyMs = lastAdmissionLatencyMs
        summary.backpressure = currentBackpressure()
        summary.admittedRequests = admittedRequests
        summary.rejectedRequests = rejectedRequests
        summary.lanes = laneOrder.map { lane in
            var result = Melix_Controlplane_V1_QueueLaneSummary()
            let stats = laneStats[lane.laneID, default: LaneStats()]
            result.laneID = lane.laneID
            result.laneClass = lane.laneClass
            result.queuedRequests = stats.queuedRequests
            result.activeRequests = stats.activeRequests
            result.queueDelayMsP50 = percentile(50, samples: stats.queueDelaySamplesMs)
            result.queueDelayMsP95 = percentile(95, samples: stats.queueDelaySamplesMs)
            let totalDecisions = stats.admittedRequests + stats.rejectedRequests
            result.admissionRate = totalDecisions == 0
                ? 1
                : Double(stats.admittedRequests) / Double(totalDecisions)
            result.backpressure = (stats.activeRequests > 0 || stats.queuedRequests > 0) ? 1 : 0
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

    public func activeMultimodalRequestCount(excluding requestID: String? = nil) -> UInt32 {
        UInt32(requestRecords.reduce(into: 0) { partialResult, item in
            let (trackedRequestID, record) = item
            guard activeRequestIDs.contains(trackedRequestID) else {
                return
            }
            guard trackedRequestID != requestID else {
                return
            }
            guard isMultimodalLane(record.laneID) else {
                return
            }
            partialResult += 1
        })
    }

    public func hasActiveMultimodalRequests(excluding requestID: String? = nil) -> Bool {
        activeMultimodalRequestCount(excluding: requestID) > 0
    }

    private var totalQueuedRequests: UInt32 {
        laneStats.values.reduce(0) { $0 + $1.queuedRequests }
    }

    private var totalActiveRequests: UInt32 {
        laneStats.values.reduce(0) { $0 + $1.activeRequests }
    }

    private var multimodalQueuedRequests: UInt32 {
        laneStats.reduce(0) { partialResult, item in
            partialResult + (isMultimodalLane(item.key) ? item.value.queuedRequests : 0)
        }
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
        (totalActiveRequests == 0 && totalQueuedRequests == 0) ? 0 : 1
    }

    private func isMultimodalLane(_ laneID: String) -> Bool {
        laneID.hasPrefix("multimodal.")
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
        await metricsStore.set(lastQueueDelayMs, forKey: "scheduler.queue_delay_ms")
        await metricsStore.set(Double(rejectedRequests), forKey: "scheduler.rejected_requests")
        await metricsStore.set(Double(totalQueuedRequests), forKey: "scheduler.queued_requests")
        await metricsStore.set(Double(totalActiveRequests), forKey: "scheduler.active_requests")
        await metricsStore.set(backpressure, forKey: "scheduler.backpressure")
        let activeDepth = Double(laneStats.values.map(\.activeRequests).max() ?? 0)
        await metricsStore.set(activeDepth, forKey: "scheduler.active_lane_depth")
        await metricsStore.set(Double(activeMultimodalRequestCount()), forKey: "scheduler.multimodal_active_requests")
        await metricsStore.set(Double(multimodalQueuedRequests), forKey: "scheduler.multimodal_queued_requests")
        await metricsStore.set(
            percentile(
                95,
                samples: laneOrder
                    .filter { isMultimodalLane($0.laneID) }
                    .flatMap { laneStats[$0.laneID, default: LaneStats()].queueDelaySamplesMs }
            ),
            forKey: "scheduler.multimodal_queue_delay_ms"
        )
        let multimodalBackpressure = (activeMultimodalRequestCount() > 0 || multimodalQueuedRequests > 0) ? 1.0 : 0.0
        await metricsStore.set(multimodalBackpressure, forKey: "scheduler.multimodal_backpressure")
        await metricsStore.set(multimodalBackpressure, forKey: "scheduler.text_protection_active")
        await metricsStore.set(
            Double(batchRequestIDsByCohort.count),
            forKey: "scheduler.continuous_batch_active_cohorts"
        )
        await metricsStore.set(
            admittedRequests == 0
                ? 0
                : batchEligibleRequestCount / Double(admittedRequests) * 100,
            forKey: "scheduler.continuous_batch_eligible_rate"
        )
        await metricsStore.set(
            batchEligibleRequestCount == 0
                ? 0
                : batchMergedRequestCount / batchEligibleRequestCount * 100,
            forKey: "scheduler.continuous_batch_merge_rate"
        )
        await metricsStore.set(
            Double(lastContinuousBatchSize),
            forKey: "scheduler.continuous_batch_size"
        )
        await metricsStore.set(
            lastContinuousBatchOccupancyPct,
            forKey: "scheduler.continuous_batch_occupancy_pct"
        )
        await metricsStore.set(
            batchEligibleRequestCount == 0
                ? 0
                : batchAffinityPreferredCount / batchEligibleRequestCount * 100,
            forKey: "scheduler.batch_affinity_preferred_rate"
        )
        await metricsStore.set(
            Double(lastPrefillProcessedTokens),
            forKey: "scheduler.prefill_progress_processed_tokens"
        )
        await metricsStore.set(
            Double(lastPrefillTotalTokens),
            forKey: "scheduler.prefill_progress_total_tokens"
        )
        await metricsStore.set(
            lastPrefillProgressPct,
            forKey: "scheduler.prefill_progress_pct"
        )
        await metricsStore.set(
            Double(lastPrefillActiveRequests),
            forKey: "scheduler.prefill_active_requests"
        )
        await metricsStore.set(
            Double(lastPrefillWaitingRequests),
            forKey: "scheduler.prefill_waiting_requests"
        )
        await metricsStore.set(
            lastRestoreStageCode,
            forKey: "scheduler.restore_stage_code"
        )
        await metricsStore.set(
            lastObservedCachePressure,
            forKey: "scheduler.cache_pressure"
        )
    }

    private func populateSchedulerSnapshot(
        into progress: inout Melix_Controlplane_V1_RequestProgressEvent
    ) {
        progress.activeRequests = totalActiveRequests
        progress.waitingRequests = totalQueuedRequests
        if progress.cachePressure == 0 {
            progress.cachePressure = lastObservedCachePressure
        }
    }

    private func restoreStageMetricCode(for restoreStage: String) -> Double {
        switch restoreStage.lowercased() {
        case "restored":
            return 1
        case "partial":
            return 2
        default:
            return 0
        }
    }

    private func percentile(_ percentile: Double, samples: [Double]) -> Double {
        guard !samples.isEmpty else {
            return 0
        }
        let sorted = samples.sorted()
        let index = Int(((percentile / 100) * Double(sorted.count - 1)).rounded(.toNearestOrAwayFromZero))
        return sorted[min(max(index, 0), sorted.count - 1)]
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
        SchedulerLaneDefinition(
            laneID: "multimodal.vision.background",
            laneClass: "background-vision",
            defaultPriorityScore: 30
        ),
        SchedulerLaneDefinition(
            laneID: "multimodal.audio.transcription.background",
            laneClass: "background-audio-transcription",
            defaultPriorityScore: 25
        ),
        SchedulerLaneDefinition(
            laneID: "multimodal.audio.speech.background",
            laneClass: "background-audio-speech",
            defaultPriorityScore: 25
        ),
    ]
}
