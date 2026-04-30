import Foundation

public struct ReasoningContinuityRecord: Sendable, Equatable {
    public let sessionID: String
    public let branchID: String
    public let requestID: String
    public let continuityKey: String
    public let reasoningText: String

    public init(
        sessionID: String,
        branchID: String,
        requestID: String,
        continuityKey: String,
        reasoningText: String
    ) {
        self.sessionID = sessionID
        self.branchID = branchID
        self.requestID = requestID
        self.continuityKey = continuityKey
        self.reasoningText = reasoningText
    }
}

public actor ReasoningContinuityStore {
    public static let defaultMaxEntries = 10_000
    public static let defaultMaxReasoningTextUTF8Bytes = 100 * 1024

    // Latest wins per session/branch. The store intentionally does not retain
    // per-branch history beyond the most recent successful reasoning record,
    // and it caps total retained branches to bound hidden in-memory state.
    private let maxEntries: Int
    private let maxReasoningTextUTF8Bytes: Int
    private var latestByBranch: [String: ReasoningContinuityRecord] = [:]
    private var branchOrder: [String] = []

    public init(
        maxEntries: Int = ReasoningContinuityStore.defaultMaxEntries,
        maxReasoningTextUTF8Bytes: Int = ReasoningContinuityStore.defaultMaxReasoningTextUTF8Bytes
    ) {
        self.maxEntries = max(0, maxEntries)
        self.maxReasoningTextUTF8Bytes = max(0, maxReasoningTextUTF8Bytes)
    }

    @discardableResult
    public func record(
        sessionID: String,
        branchID: String,
        requestID: String,
        reasoningText: String
    ) -> ReasoningContinuityRecord? {
        let normalizedSessionID = normalized(sessionID)
        guard let normalizedSessionID else {
            return nil
        }
        let normalizedRequestID = normalized(requestID)
        guard let normalizedRequestID else {
            return nil
        }
        let trimmedReasoning = reasoningText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedReasoning.isEmpty else {
            return nil
        }
        let boundedReasoning = boundedUTF8Prefix(trimmedReasoning, maxBytes: maxReasoningTextUTF8Bytes)
        guard !boundedReasoning.isEmpty else {
            return nil
        }

        let normalizedBranchID = normalized(branchID) ?? "branch-main"
        let key = branchKey(sessionID: normalizedSessionID, branchID: normalizedBranchID)
        let record = ReasoningContinuityRecord(
            sessionID: normalizedSessionID,
            branchID: normalizedBranchID,
            requestID: normalizedRequestID,
            continuityKey: "\(key)::\(normalizedRequestID)",
            reasoningText: boundedReasoning
        )
        if latestByBranch[key] != nil {
            branchOrder.removeAll { $0 == key }
        }
        latestByBranch[key] = record
        branchOrder.append(key)
        evictOverflow()
        return record
    }

    public func latest(
        sessionID: String,
        branchID: String
    ) -> ReasoningContinuityRecord? {
        guard let normalizedSessionID = normalized(sessionID) else {
            return nil
        }
        let normalizedBranchID = normalized(branchID) ?? "branch-main"
        return latestByBranch[branchKey(sessionID: normalizedSessionID, branchID: normalizedBranchID)]
    }

    private func normalized(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func branchKey(sessionID: String, branchID: String) -> String {
        "\(sessionID)::\(branchID)"
    }

    private func evictOverflow() {
        guard maxEntries > 0 else {
            latestByBranch.removeAll()
            branchOrder.removeAll()
            return
        }
        while latestByBranch.count > maxEntries, let evictedKey = branchOrder.first {
            branchOrder.removeFirst()
            latestByBranch.removeValue(forKey: evictedKey)
        }
    }

    private func boundedUTF8Prefix(_ value: String, maxBytes: Int) -> String {
        guard maxBytes > 0 else {
            return ""
        }
        guard value.utf8.count > maxBytes else {
            return value
        }

        var byteCount = 0
        var endIndex = value.startIndex
        while endIndex < value.endIndex {
            let nextIndex = value.index(after: endIndex)
            let nextByteCount = value[endIndex..<nextIndex].utf8.count
            if byteCount + nextByteCount > maxBytes {
                break
            }
            byteCount += nextByteCount
            endIndex = nextIndex
        }
        return String(value[..<endIndex])
    }
}
