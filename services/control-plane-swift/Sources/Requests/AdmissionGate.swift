public enum AdmissionOutcome: Equatable, Sendable {
    case admitted
    case cancelled
}

public actor AdmissionGate {
    private var activeRequestID: String?
    private var queuedRequestIDs: [String]
    private var waiters: [String: CheckedContinuation<AdmissionOutcome, Never>]

    public init() {
        self.queuedRequestIDs = []
        self.waiters = [:]
    }

    public func nextQueuePosition() -> UInt32 {
        activeRequestID == nil ? 1 : UInt32(queuedRequestIDs.count + 1)
    }

    public func acquire(requestID: String) async -> AdmissionOutcome {
        if activeRequestID == nil {
            activeRequestID = requestID
            return .admitted
        }

        if !queuedRequestIDs.contains(requestID) {
            queuedRequestIDs.append(requestID)
        }

        return await withCheckedContinuation { continuation in
            waiters[requestID] = continuation
        }
    }

    public func release(requestID: String) {
        if activeRequestID == requestID {
            activeRequestID = nil
            admitNextIfPossible()
            return
        }

        if let index = queuedRequestIDs.firstIndex(of: requestID) {
            queuedRequestIDs.remove(at: index)
            waiters.removeValue(forKey: requestID)?.resume(returning: .cancelled)
        }
    }

    public func snapshot() -> (activeRequestID: String?, queuedRequestIDs: [String]) {
        (activeRequestID, queuedRequestIDs)
    }

    private func admitNextIfPossible() {
        guard activeRequestID == nil else {
            return
        }

        while let next = queuedRequestIDs.first {
            queuedRequestIDs.removeFirst()
            guard let waiter = waiters.removeValue(forKey: next) else {
                continue
            }
            activeRequestID = next
            waiter.resume(returning: .admitted)
            break
        }
    }
}
