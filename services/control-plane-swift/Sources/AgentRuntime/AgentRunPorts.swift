import Foundation

public protocol AgentModelTurnPort: Sendable {
    func performTurn(_ request: AgentModelTurnRequest) async throws -> AgentModelTurnResult
    func cancelTurn(runID: String) async
}

public enum AgentModelTurnStreamEvent: Sendable, Equatable {
    case textDelta(String)
    case reasoningDelta(String)
    case toolCallDelta(callID: String, toolName: String, argumentsFragment: String)
}

public protocol AgentStreamingModelTurnPort: AgentModelTurnPort {
    func performTurn(
        _ request: AgentModelTurnRequest,
        onEvent: @escaping @Sendable (AgentModelTurnStreamEvent) async -> Void
    ) async throws -> AgentModelTurnResult
}

public protocol AgentToolExecutionPort: Sendable {
    func execute(_ request: AgentToolExecutionRequest) async throws -> AgentToolExecutionResult
    func cancel(runID: String, callID: String) async -> AgentToolCancellationReceipt
    func cancelRun(runID: String) async -> AgentRunToolCancellationReceipt
}

public extension AgentToolExecutionPort {
    func cancelRun(runID: String) async -> AgentRunToolCancellationReceipt {
        AgentRunToolCancellationReceipt(
            runID: runID,
            disposition: .unavailable,
            sideEffectState: .unknown
        )
    }
}

public protocol AgentApprovalPolicyPort: Sendable {
    func approvalEvaluation(
        for call: AgentToolCall,
        runID: String
    ) async -> AgentApprovalPolicyEvaluation
}

public extension AgentApprovalPolicyPort {
    /// Re-evaluates both the durable policy revision and the non-model scope
    /// immediately before an approval is accepted or a tool is executed.
    /// Implementations that supply a scope digest get full scope replay
    /// protection; revision-only fakes remain source compatible.
    func isApprovalBindingCurrent(
        _ binding: AgentApprovalBinding,
        for call: AgentToolCall,
        runID: String,
        expectedRequirement: AgentApprovalRequirement
    ) async -> Bool {
        let current = await approvalEvaluation(for: call, runID: runID)
        let revision = current.policyRevision.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !revision.isEmpty,
              revision == binding.policyRevision,
              current.requirement == expectedRequirement
        else {
            return false
        }
        return AgentApprovalBinding.make(
            runID: runID,
            call: call,
            policyRevision: revision,
            scopeDigest: current.scopeDigest
        ) == binding
    }
}

public protocol AgentApprovalPolicyManaging: AgentApprovalPolicyPort {
    func persistAlwaysAllow(for call: AgentToolCall, runID: String) async throws -> String

    func persistAlwaysAllow(
        for call: AgentToolCall,
        runID: String,
        expectedRevision: String
    ) async throws -> String

    func persistAlwaysAllow(
        for call: AgentToolCall,
        runID: String,
        expectedRevision: String,
        deadlineUnixMs: Int64
    ) async throws -> String
}

public extension AgentApprovalPolicyManaging {
    func persistAlwaysAllow(
        for call: AgentToolCall,
        runID: String,
        expectedRevision: String,
        deadlineUnixMs: Int64
    ) async throws -> String {
        if deadlineUnixMs > 0,
           deadlineUnixMs <= Int64(Date().timeIntervalSince1970 * 1_000) {
            throw ApprovalPolicyStoreError.deadlineExceeded
        }
        return try await persistAlwaysAllow(
            for: call,
            runID: runID,
            expectedRevision: expectedRevision
        )
    }
}
