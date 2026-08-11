import Testing

@testable import MelixControlPlaneCore

@Suite("Agent Run Admission Suspension", .serialized)
struct AgentRunAdmissionSuspensionTests {
    @Test("a suspended coordinator performs no provider work before resume")
    func suspendedCoordinatorWaitsForExplicitResume() async throws {
        let model = AdmissionRecordingModelPort()
        let coordinator = AgentRunCoordinator(
            modelTurns: model,
            tools: AdmissionUnusedToolPort(),
            approvalPolicy: AdmissionAllowPolicy(),
            runIDGenerator: { "agent-run-suspended-resume" }
        )

        let execution = try await coordinator.start(
            try admissionRunRequest(),
            suspended: true
        )
        await Task.yield()
        #expect(await model.requestCount() == 0)

        await coordinator.resume(runID: execution.runID)
        let events = await collectAdmissionEvents(execution.events)
        #expect(await model.requestCount() == 1)
        #expect(events.contains(where: {
            if case .completed = $0 { return true }
            return false
        }))
    }

    @Test("cancelling a suspended coordinator never starts the provider")
    func suspendedCoordinatorCanBeCancelledBeforeResume() async throws {
        let model = AdmissionRecordingModelPort()
        let coordinator = AgentRunCoordinator(
            modelTurns: model,
            tools: AdmissionUnusedToolPort(),
            approvalPolicy: AdmissionAllowPolicy(),
            runIDGenerator: { "agent-run-suspended-cancel" }
        )

        let execution = try await coordinator.start(
            try admissionRunRequest(),
            suspended: true
        )
        let receipt = await coordinator.cancel(
            runID: execution.runID,
            reason: .operatorRequested
        )
        await coordinator.resume(runID: execution.runID)
        let events = await collectAdmissionEvents(execution.events)

        #expect(receipt.disposition == .accepted)
        #expect(receipt.sideEffectState == .none)
        #expect(await model.requestCount() == 0)
        #expect(events.filter {
            if case .cancelled = $0 { return true }
            return false
        }.count == 1)
    }
}

private actor AdmissionRecordingModelPort: AgentModelTurnPort {
    private var requests: [AgentModelTurnRequest] = []

    func performTurn(
        _ request: AgentModelTurnRequest
    ) async throws -> AgentModelTurnResult {
        requests.append(request)
        return AgentModelTurnResult(assistantText: "done")
    }

    func cancelTurn(runID: String) async {
        _ = runID
    }

    func requestCount() -> Int {
        requests.count
    }
}

private struct AdmissionUnusedToolPort: AgentToolExecutionPort {
    func execute(
        _ request: AgentToolExecutionRequest
    ) async throws -> AgentToolExecutionResult {
        _ = request
        throw AgentPortFailure.internalFailure
    }

    func cancel(
        runID: String,
        callID: String
    ) async -> AgentToolCancellationReceipt {
        AgentToolCancellationReceipt(
            runID: runID,
            callID: callID,
            disposition: .notFound,
            sideEffectState: .none
        )
    }

    func cancelRun(runID: String) async -> AgentRunToolCancellationReceipt {
        AgentRunToolCancellationReceipt(
            runID: runID,
            disposition: .accepted,
            sideEffectState: .none
        )
    }
}

private struct AdmissionAllowPolicy: AgentApprovalPolicyPort {
    func approvalEvaluation(
        for call: AgentToolCall,
        runID: String
    ) async -> AgentApprovalPolicyEvaluation {
        _ = call
        _ = runID
        return AgentApprovalPolicyEvaluation(
            requirement: .notRequired,
            policyRevision: "admission-policy-v1"
        )
    }
}

private func admissionRunRequest() throws -> AgentRunRequest {
    AgentRunRequest(
        messages: [.user("wait for admission")],
        toolCatalog: try AgentRuntimeToolCatalog(
            digest: "admission-catalog-v1",
            descriptors: [
                AgentRuntimeToolDescriptor(
                    sourceID: "builtin",
                    adapterKind: "builtin",
                    name: "admission.noop",
                    title: "Admission No-op",
                    description: "A fixture tool that the model never calls.",
                    inputSchemaJSON: #"{"type":"object"}"#,
                    schemaDigest: "admission-noop-v1",
                    riskClass: "low"
                ),
            ]
        )
    )
}

private func collectAdmissionEvents(
    _ stream: AsyncStream<AgentRunEvent>
) async -> [AgentRunEvent] {
    var events: [AgentRunEvent] = []
    for await event in stream {
        events.append(event)
    }
    return events
}
