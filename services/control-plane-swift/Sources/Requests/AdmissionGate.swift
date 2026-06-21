public enum AdmissionOutcome: Equatable, Sendable {
    case admitted
    case cancelled
}

public struct AdmissionGrant: Equatable, Sendable {
    public let outcome: AdmissionOutcome
    public let batchPosition: UInt32
    public let batchSize: UInt32
    public let batchCapacity: UInt32
    public let mergedIntoBatch: Bool

    public init(
        outcome: AdmissionOutcome,
        batchPosition: UInt32 = 0,
        batchSize: UInt32 = 0,
        batchCapacity: UInt32 = 1,
        mergedIntoBatch: Bool = false
    ) {
        self.outcome = outcome
        self.batchPosition = batchPosition
        self.batchSize = batchSize
        self.batchCapacity = batchCapacity
        self.mergedIntoBatch = mergedIntoBatch
    }
}

public actor AdmissionGate {
    public static let defaultBatchFormationWindowNanos: UInt64 = 20_000_000

    private struct QueueEntry: Sendable {
        let requestID: String
        let cohortID: String
        let maxBatchSize: UInt32
        let priorityScore: Double
        let sequence: UInt64
    }

    private struct FrontBatch: Sendable {
        let entries: [QueueEntry]
        let capacity: UInt32
    }

    private let batchFormationWindowNanos: UInt64
    private var activeRequestIDs: [String]
    private var activeCohortID: String?
    private var activeBatchCapacity: UInt32
    private var queuedEntries: [QueueEntry]
    private var waiters: [String: CheckedContinuation<AdmissionGrant, Never>]
    private var pendingFormationID: UInt64?
    private var nextFormationID: UInt64
    private var nextQueueSequence: UInt64

    public init(batchFormationWindowNanos: UInt64 = AdmissionGate.defaultBatchFormationWindowNanos) {
        self.batchFormationWindowNanos = batchFormationWindowNanos
        self.activeRequestIDs = []
        self.activeBatchCapacity = 1
        self.queuedEntries = []
        self.waiters = [:]
        self.nextFormationID = 1
        self.nextQueueSequence = 1
    }

    public func nextQueuePosition(
        cohortID: String = "",
        maxBatchSize: UInt32 = 1,
        priorityScore: Double = 0
    ) -> UInt32 {
        if activeRequestIDs.isEmpty {
            return queuedPosition(forPriorityScore: priorityScore)
        }
        if canJoinActiveBatch(cohortID: cohortID, maxBatchSize: maxBatchSize) {
            return 1
        }
        return queuedPosition(forPriorityScore: priorityScore)
    }

    public func acquire(
        requestID: String,
        cohortID: String = "",
        maxBatchSize: UInt32 = 1,
        priorityScore: Double = 0
    ) async -> AdmissionGrant {
        let normalizedCapacity = normalizedBatchCapacity(maxBatchSize)
        if activeRequestIDs.isEmpty,
           !queuedEntries.isEmpty {
            return await enqueueQueuedRequest(
                requestID: requestID,
                cohortID: cohortID,
                maxBatchSize: normalizedCapacity,
                priorityScore: priorityScore
            )
        }

        if activeRequestIDs.isEmpty {
            if shouldFormBatchBeforeAdmission(
                cohortID: cohortID,
                maxBatchSize: normalizedCapacity
            ) {
                return await enqueueQueuedRequest(
                    requestID: requestID,
                    cohortID: cohortID,
                    maxBatchSize: normalizedCapacity,
                    priorityScore: priorityScore
                )
            }
            activeRequestIDs = [requestID]
            activeCohortID = cohortID
            activeBatchCapacity = normalizedCapacity
            return AdmissionGrant(
                outcome: .admitted,
                batchPosition: 1,
                batchSize: 1,
                batchCapacity: normalizedCapacity
            )
        }

        if canJoinActiveBatch(cohortID: cohortID, maxBatchSize: maxBatchSize) {
            activeRequestIDs.append(requestID)
            let normalizedCapacity = min(activeBatchCapacity, normalizedBatchCapacity(maxBatchSize))
            activeBatchCapacity = normalizedCapacity
            return AdmissionGrant(
                outcome: .admitted,
                batchPosition: UInt32(activeRequestIDs.count),
                batchSize: UInt32(activeRequestIDs.count),
                batchCapacity: normalizedCapacity,
                mergedIntoBatch: true
            )
        }

        if !queuedEntries.contains(where: { $0.requestID == requestID }) {
            queuedEntries.append(
                QueueEntry(
                    requestID: requestID,
                    cohortID: cohortID,
                    maxBatchSize: normalizedBatchCapacity(maxBatchSize),
                    priorityScore: priorityScore,
                    sequence: nextQueueSequence
                )
            )
            nextQueueSequence &+= 1
            sortQueuedEntriesByPriority()
        }

        return await withCheckedContinuation { continuation in
            waiters[requestID] = continuation
        }
    }

    public func release(requestID: String) {
        if let activeIndex = activeRequestIDs.firstIndex(of: requestID) {
            activeRequestIDs.remove(at: activeIndex)
            if activeRequestIDs.isEmpty {
                activeCohortID = nil
                activeBatchCapacity = 1
                admitNextIfPossible()
            }
            return
        }

        if let index = queuedEntries.firstIndex(where: { $0.requestID == requestID }) {
            queuedEntries.remove(at: index)
            waiters.removeValue(forKey: requestID)?.resume(returning: AdmissionGrant(outcome: .cancelled))
            if queuedEntries.isEmpty {
                pendingFormationID = nil
            } else if activeRequestIDs.isEmpty, index == 0 {
                admitNextOrScheduleFormationFlush()
            }
        }
    }

    public func snapshot() -> (
        activeRequestID: String?,
        activeRequestIDs: [String],
        activeCohortID: String?,
        queuedRequestIDs: [String]
    ) {
        (
            activeRequestIDs.first,
            activeRequestIDs,
            activeCohortID,
            queuedEntries.map(\.requestID)
        )
    }

    private func admitNextIfPossible() {
        guard activeRequestIDs.isEmpty else {
            return
        }

        while let frontBatch = frontCompatibleBatch() {
            queuedEntries.removeFirst(frontBatch.entries.count)
            let admittedBatch = frontBatch.entries.filter { waiters[$0.requestID] != nil }
            guard !admittedBatch.isEmpty else {
                continue
            }

            activeRequestIDs = admittedBatch.map(\.requestID)
            activeCohortID = admittedBatch.first?.cohortID
            activeBatchCapacity = frontBatch.capacity
            pendingFormationID = nil

            for (index, entry) in admittedBatch.enumerated() {
                guard let waiter = waiters.removeValue(forKey: entry.requestID) else {
                    continue
                }
                waiter.resume(
                    returning: AdmissionGrant(
                        outcome: .admitted,
                        batchPosition: UInt32(index + 1),
                        batchSize: UInt32(admittedBatch.count),
                        batchCapacity: frontBatch.capacity,
                        mergedIntoBatch: index > 0
                    )
                )
            }
            break
        }
    }

    private func enqueueQueuedRequest(
        requestID: String,
        cohortID: String,
        maxBatchSize: UInt32,
        priorityScore: Double
    ) async -> AdmissionGrant {
        await withCheckedContinuation { continuation in
            if !queuedEntries.contains(where: { $0.requestID == requestID }) {
                queuedEntries.append(
                    QueueEntry(
                        requestID: requestID,
                        cohortID: cohortID,
                        maxBatchSize: maxBatchSize,
                        priorityScore: priorityScore,
                        sequence: nextQueueSequence
                    )
                )
                nextQueueSequence &+= 1
                sortQueuedEntriesByPriority()
            }
            waiters[requestID] = continuation

            admitNextOrScheduleFormationFlush()
        }
    }

    private func shouldFormBatchBeforeAdmission(
        cohortID: String,
        maxBatchSize: UInt32
    ) -> Bool {
        batchFormationWindowNanos > 0
            && maxBatchSize > 1
            && !cohortID.isEmpty
    }

    private func queuedFrontCohortIsFull() -> Bool {
        guard let frontBatch = frontCompatibleBatch() else {
            return false
        }
        if UInt32(frontBatch.entries.count) >= frontBatch.capacity {
            return true
        }
        return queuedEntries.count > frontBatch.entries.count
    }

    private func admitNextOrScheduleFormationFlush() {
        if shouldScheduleFormationFlush() && !queuedFrontCohortIsFull() {
            scheduleFormationFlushIfNeeded()
        } else {
            admitNextIfPossible()
        }
    }

    private func frontCompatibleBatch() -> FrontBatch? {
        guard let first = queuedEntries.first else {
            return nil
        }

        var entries = [first]
        var capacity = first.maxBatchSize
        for entry in queuedEntries.dropFirst() {
            guard entry.cohortID == first.cohortID else {
                break
            }
            let nextCapacity = min(capacity, entry.maxBatchSize)
            guard entries.count + 1 <= Int(nextCapacity) else {
                break
            }
            entries.append(entry)
            capacity = nextCapacity
            if entries.count >= Int(capacity) {
                break
            }
        }

        return FrontBatch(entries: entries, capacity: capacity)
    }

    private func scheduleFormationFlushIfNeeded() {
        guard pendingFormationID == nil,
              shouldScheduleFormationFlush()
        else {
            return
        }

        let formationID = nextFormationID
        nextFormationID &+= 1
        pendingFormationID = formationID
        let windowNanos = batchFormationWindowNanos
        Task {
            try? await Task.sleep(nanoseconds: windowNanos)
            self.flushFormationIfCurrent(formationID)
        }
    }

    private func shouldScheduleFormationFlush() -> Bool {
        guard let first = queuedEntries.first else {
            return false
        }
        return shouldFormBatchBeforeAdmission(
            cohortID: first.cohortID,
            maxBatchSize: first.maxBatchSize
        )
    }

    private func flushFormationIfCurrent(_ formationID: UInt64) {
        guard pendingFormationID == formationID else {
            return
        }
        admitNextIfPossible()
    }

    private func normalizedBatchCapacity(_ capacity: UInt32) -> UInt32 {
        max(capacity, 1)
    }

    private func queuedPosition(forPriorityScore priorityScore: Double) -> UInt32 {
        let precedingCount = queuedEntries.filter { entry in
            entry.priorityScore >= priorityScore
        }.count
        return UInt32(precedingCount + 1)
    }

    private func sortQueuedEntriesByPriority() {
        queuedEntries.sort { lhs, rhs in
            if lhs.priorityScore != rhs.priorityScore {
                return lhs.priorityScore > rhs.priorityScore
            }
            return lhs.sequence < rhs.sequence
        }
    }

    private func canJoinActiveBatch(
        cohortID: String,
        maxBatchSize: UInt32
    ) -> Bool {
        guard !activeRequestIDs.isEmpty else {
            return false
        }
        guard queuedEntries.isEmpty else {
            return false
        }
        let normalizedCapacity = normalizedBatchCapacity(maxBatchSize)
        guard activeCohortID == cohortID else {
            return false
        }
        let effectiveCapacity = min(activeBatchCapacity, normalizedCapacity)
        return UInt32(activeRequestIDs.count) < effectiveCapacity
    }
}
