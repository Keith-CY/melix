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
    private struct QueueEntry: Sendable {
        let requestID: String
        let cohortID: String
        let maxBatchSize: UInt32
    }

    private var activeRequestIDs: [String]
    private var activeCohortID: String?
    private var activeBatchCapacity: UInt32
    private var queuedEntries: [QueueEntry]
    private var waiters: [String: CheckedContinuation<AdmissionGrant, Never>]

    public init() {
        self.activeRequestIDs = []
        self.activeBatchCapacity = 1
        self.queuedEntries = []
        self.waiters = [:]
    }

    public func nextQueuePosition(
        cohortID: String = "",
        maxBatchSize: UInt32 = 1
    ) -> UInt32 {
        if activeRequestIDs.isEmpty {
            return 1
        }
        if canJoinActiveBatch(cohortID: cohortID, maxBatchSize: maxBatchSize) {
            return 1
        }
        return UInt32(queuedEntries.count + 1)
    }

    public func acquire(
        requestID: String,
        cohortID: String = "",
        maxBatchSize: UInt32 = 1
    ) async -> AdmissionGrant {
        if activeRequestIDs.isEmpty {
            let normalizedCapacity = normalizedBatchCapacity(maxBatchSize)
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
                    maxBatchSize: normalizedBatchCapacity(maxBatchSize)
                )
            )
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

        while let next = queuedEntries.first {
            queuedEntries.removeFirst()
            guard waiters[next.requestID] != nil else {
                continue
            }

            let cohortID = next.cohortID
            let batchCapacity = next.maxBatchSize
            var admittedBatch: [QueueEntry] = [next]
            while admittedBatch.count < Int(batchCapacity),
                  let queued = queuedEntries.first,
                  queued.cohortID == cohortID {
                queuedEntries.removeFirst()
                admittedBatch.append(queued)
            }

            activeRequestIDs = admittedBatch.map(\.requestID)
            activeCohortID = cohortID
            activeBatchCapacity = batchCapacity

            for (index, entry) in admittedBatch.enumerated() {
                guard let waiter = waiters.removeValue(forKey: entry.requestID) else {
                    continue
                }
                waiter.resume(
                    returning: AdmissionGrant(
                        outcome: .admitted,
                        batchPosition: UInt32(index + 1),
                        batchSize: UInt32(admittedBatch.count),
                        batchCapacity: batchCapacity,
                        mergedIntoBatch: index > 0
                    )
                )
            }
            break
        }
    }

    private func normalizedBatchCapacity(_ capacity: UInt32) -> UInt32 {
        max(capacity, 1)
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
