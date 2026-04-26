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
    // Latest wins per session/branch to keep continuity memory bounded. The
    // store intentionally does not retain per-branch history beyond the most
    // recent successful reasoning record.
    private var latestByBranch: [String: ReasoningContinuityRecord] = [:]

    public init() {}

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

        let normalizedBranchID = normalized(branchID) ?? "branch-main"
        let key = branchKey(sessionID: normalizedSessionID, branchID: normalizedBranchID)
        let record = ReasoningContinuityRecord(
            sessionID: normalizedSessionID,
            branchID: normalizedBranchID,
            requestID: normalizedRequestID,
            continuityKey: "\(key)::\(normalizedRequestID)",
            reasoningText: trimmedReasoning
        )
        latestByBranch[key] = record
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
}
