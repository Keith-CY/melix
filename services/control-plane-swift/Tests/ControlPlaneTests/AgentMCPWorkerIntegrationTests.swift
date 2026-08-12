import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol
import Testing

@testable import MelixControlPlaneCore

@Suite("Agent MCP worker integration", .serialized)
struct AgentMCPWorkerIntegrationTests {
    @Test("real stdio MCP crosses worker RPC and completes the Agent loop")
    func realStdioMCPCompletesAgentLoopAndCancels() async throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["MELIX_RUN_AGENT_MCP_E2E"] == "1" else {
            return
        }
        let socketPath = try #require(
            environment["MELIX_AGENT_MCP_E2E_WORKER_SOCKET"]
        )
        let fixturePath = try #require(
            environment["MELIX_AGENT_MCP_E2E_FIXTURE"]
        )
        let pythonPath = try #require(
            environment["MELIX_AGENT_MCP_E2E_PYTHON"]
        )
        let repoRoot = try #require(
            environment["MELIX_AGENT_MCP_E2E_REPO_ROOT"]
        )
        let secret = try #require(
            environment["MELIX_AGENT_MCP_E2E_SECRET"]
        )

        let bridge = PythonBridgeWorkerClient(socketPath: socketPath)
        #expect(await bridge.canDispatchRequests())
        let worker = RecordingAgentToolWorker(client: bridge)
        let source = makeStdioSource(
            pythonPath: pythonPath,
            fixturePath: fixturePath,
            workingDirectory: repoRoot
        )

        let completionChat = E2EChatStarter(mode: .completion)
        let completionRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "agent-mcp-e2e-completion" }
        )
        let completion: Melix_Controlplane_V1_AgentRunSnapshot
        do {
            completion = try await completionRuntime.start(
                command: makeAgentCommand(
                    sessionID: "agent-mcp-e2e-session",
                    branchID: "agent-mcp-e2e-branch",
                    prompt: "Use the bounded MCP echo tool."
                ),
                actorID: "agent-mcp-e2e-operator",
                dependencies: ControlPlaneAgentRuntimeStartDependencies(
                    worker: worker,
                    approvalPolicy: E2EAllowPolicy(),
                    sourceConfigs: [source],
                    startChat: { request in
                        try await completionChat.start(request)
                    }
                )
            )
        } catch {
            let workerFailures = await worker.failures()
            throw AgentMCPWorkerIntegrationError.workerTrace(
                "runtime=\(String(reflecting: error)); "
                    + "worker=\(workerFailures.joined(separator: " | "))"
            )
        }
        let completed = try await waitForSnapshot(
            runtime: completionRuntime,
            runID: completion.runID,
            state: "completed"
        )
        #expect(completed.assistantText == "MCP continuation complete.")
        #expect(completed.modelTurnCount == 2)
        #expect(completed.toolCallCount == 1)
        let completedTool = try #require(completed.toolCalls.first)
        #expect(completedTool.callID == "call-mcp-e2e-completion")
        #expect(completedTool.sourceID == "agent-e2e")
        #expect(completedTool.state == "completed")
        #expect(!completedTool.schemaDigest.isEmpty)
        #expect(!completedTool.evidenceReference.isEmpty)

        let completionRequests = await completionChat.requests()
        #expect(completionRequests.count == 2)
        guard let continuationRequest = completionRequests.last else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "continuation chat request"
            )
        }
        let assistantMessages = continuationRequest.messages.filter {
            $0.role == "assistant"
        }
        let assistantCalls = assistantMessages.flatMap(\.toolCalls)
        guard let assistantCall = assistantCalls.first else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "assistant tool call"
            )
        }
        #expect(assistantCall.callID == "call-mcp-e2e-completion")
        let toolMessages = continuationRequest.messages.filter {
            $0.role == "tool"
        }
        let correlatedToolMessages = toolMessages.filter {
            $0.toolCallID == "call-mcp-e2e-completion"
        }
        guard let toolMessage = correlatedToolMessages.first else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "correlated tool result message"
            )
        }
        #expect(toolMessage.content.contains("continuation-marker"))
        #expect(!toolMessage.content.contains(secret))
        #expect(toolMessage.content.contains("[REDACTED]"))
        #expect(toolMessage.content.utf8.count < 32_768)

        let listRequests = try await waitForListRequests(
            worker: worker,
            count: 2
        )
        guard let listRequest = listRequests.first else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "worker list-tools request"
            )
        }
        #expect(listRequest.id.sessionID == "agent-mcp-e2e-session")
        #expect(listRequest.id.branchID == "agent-mcp-e2e-branch")
        #expect(listRequest.ownerActorID == "agent-mcp-e2e-operator")
        #expect(listRequest.leaseTtlMs > 0)
        #expect(!listRequest.releaseSources)
        let completionReleaseRequest = listRequests[1]
        #expect(completionReleaseRequest.releaseSources)
        #expect(completionReleaseRequest.leaseTtlMs == 1)
        #expect(completionReleaseRequest.id.sessionID == listRequest.id.sessionID)
        #expect(completionReleaseRequest.id.branchID == listRequest.id.branchID)
        #expect(completionReleaseRequest.ownerActorID == listRequest.ownerActorID)
        let executeRequests = await worker.executeRequests()
        guard let executeRequest = executeRequests.first else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "worker execute-tool request"
            )
        }
        #expect(executeRequest.context.admissionState == "allow")
        #expect(executeRequest.context.sessionID == listRequest.id.sessionID)
        #expect(executeRequest.context.branchID == listRequest.id.branchID)
        #expect(executeRequest.context.actorID == listRequest.ownerActorID)
        #expect(executeRequest.callID == "call-mcp-e2e-completion")
        #expect(executeRequest.sourceID == "agent-e2e")
        #expect(!executeRequest.expectedSchemaDigest.isEmpty)

        let cancellationChat = E2EChatStarter(mode: .cancellation)
        let cancellationRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "agent-mcp-e2e-cancellation" }
        )
        let cancellation = try await cancellationRuntime.start(
            command: makeAgentCommand(
                sessionID: "agent-mcp-cancel-session",
                branchID: "agent-mcp-cancel-branch",
                prompt: "Start the delayed MCP echo tool."
            ),
            actorID: "agent-mcp-e2e-operator",
            dependencies: ControlPlaneAgentRuntimeStartDependencies(
                worker: worker,
                approvalPolicy: E2EAllowPolicy(),
                sourceConfigs: [source],
                startChat: { request in
                    try await cancellationChat.start(request)
                }
            )
        )
        _ = try await waitForSnapshot(
            runtime: cancellationRuntime,
            runID: cancellation.runID,
            state: "tool_running"
        )
        try await Task.sleep(for: .milliseconds(100))
        let cancellationReceipt = await cancellationRuntime.cancel(
            runID: cancellation.runID,
            reason: .operatorRequested
        )
        let successfulCancellationDispositions = [
            "accepted",
            "already_terminal",
        ]
        #expect(
            successfulCancellationDispositions.contains(
                cancellationReceipt.disposition
            )
        )
        #expect(
            cancellationReceipt.sideEffectState
                == .agentToolSideEffectUnknown
        )
        #expect(!cancellationReceipt.sideEffectCommitted)
        #expect(
            cancellationReceipt.tool.sideEffectState
                == .agentToolSideEffectUnknown
        )
        #expect(!cancellationReceipt.tool.sideEffectCommitted)
        #expect(
            cancellationReceipt.tool.callID
                == "call-mcp-e2e-cancellation"
        )
        let cancelled = try await waitForSnapshot(
            runtime: cancellationRuntime,
            runID: cancellation.runID,
            state: "cancelled"
        )
        #expect(cancelled.state == "cancelled")
        let cancelRequests = await worker.cancelRequests()
        guard let cancelRequest = cancelRequests.first else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "worker cancel-tool request"
            )
        }
        #expect(cancelRequest.runID == cancellation.runID)
        #expect(cancelRequest.callID == "call-mcp-e2e-cancellation")
        #expect(cancelRequest.sessionID == "agent-mcp-cancel-session")
        #expect(cancelRequest.branchID == "agent-mcp-cancel-branch")
        #expect(cancelRequest.actorID == "agent-mcp-e2e-operator")
        let runCancelRequests = await worker.cancelRunRequests()
        #expect(
            runCancelRequests.contains {
                $0.runID == completion.runID
            }
        )
        guard let runCancelRequest = runCancelRequests.first(where: {
            $0.runID == cancellation.runID
        }) else {
            throw AgentMCPWorkerIntegrationError.missingValue(
                "worker cancel-run-tools request"
            )
        }
        #expect(runCancelRequest.runID == cancellation.runID)
        #expect(!runCancelRequest.cancellationID.isEmpty)
        #expect(runCancelRequest.sessionID == cancelRequest.sessionID)
        #expect(runCancelRequest.branchID == cancelRequest.branchID)
        #expect(runCancelRequest.actorID == cancelRequest.actorID)
        let cancellationListRequests = try await waitForListRequests(
            worker: worker,
            count: 4
        )
        let cancellationLeaseRequest = cancellationListRequests[2]
        let cancellationReleaseRequest = cancellationListRequests[3]
        #expect(!cancellationLeaseRequest.releaseSources)
        #expect(cancellationLeaseRequest.id.sessionID == cancelRequest.sessionID)
        #expect(cancellationLeaseRequest.id.branchID == cancelRequest.branchID)
        #expect(cancellationLeaseRequest.ownerActorID == cancelRequest.actorID)
        #expect(cancellationReleaseRequest.releaseSources)
        #expect(cancellationReleaseRequest.leaseTtlMs == 1)
        #expect(
            cancellationReleaseRequest.id.sessionID
                == cancellationLeaseRequest.id.sessionID
        )
        #expect(
            cancellationReleaseRequest.id.branchID
                == cancellationLeaseRequest.id.branchID
        )
        #expect(
            cancellationReleaseRequest.ownerActorID
                == cancellationLeaseRequest.ownerActorID
        )

        let applicationErrorChat = E2EChatStarter(mode: .applicationError)
        let applicationErrorRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "agent-mcp-e2e-application-error" }
        )
        let applicationError = try await applicationErrorRuntime.start(
            command: makeAgentCommand(
                sessionID: "agent-mcp-error-session",
                branchID: "agent-mcp-error-branch",
                prompt: "Call the MCP tool that reports an application error."
            ),
            actorID: "agent-mcp-e2e-operator",
            dependencies: ControlPlaneAgentRuntimeStartDependencies(
                worker: worker,
                approvalPolicy: E2EAllowPolicy(),
                sourceConfigs: [source],
                startChat: { request in
                    try await applicationErrorChat.start(request)
                }
            )
        )
        let recovered = try await waitForSnapshot(
            runtime: applicationErrorRuntime,
            runID: applicationError.runID,
            state: "completed"
        )
        #expect(recovered.assistantText == "MCP application error observed.")
        #expect(recovered.modelTurnCount == 2)
        #expect(recovered.toolCallCount == 1)
        let recoveredTool = try #require(recovered.toolCalls.first)
        #expect(recoveredTool.state == "completed")
        #expect(
            recoveredTool.resultSummary
                == "MCP tool reported an application error."
        )

        let applicationErrorRequests = await applicationErrorChat.requests()
        #expect(applicationErrorRequests.count == 2)
        let applicationErrorContinuation = try #require(
            applicationErrorRequests.last
        )
        let applicationErrorToolMessage = try #require(
            applicationErrorContinuation.messages.first {
                $0.role == "tool"
                    && $0.toolCallID == "call-mcp-e2e-application-error"
            }
        )
        let applicationErrorObservationData = Data(
            applicationErrorToolMessage.content.utf8
        )
        let applicationErrorObservation = try #require(
            JSONSerialization.jsonObject(with: applicationErrorObservationData)
                as? [String: Any]
        )
        #expect(applicationErrorObservation["status"] as? String == "failed")
        let applicationErrorPayload = try #require(
            applicationErrorObservation["payload"] as? [String: Any]
        )
        #expect(applicationErrorPayload["is_error"] as? Bool == true)

        let applicationErrorListRequests = try await waitForListRequests(
            worker: worker,
            count: 6
        )
        #expect(!applicationErrorListRequests[4].releaseSources)
        #expect(applicationErrorListRequests[5].releaseSources)
    }
}

private enum E2EChatMode: Sendable, Equatable {
    case completion
    case cancellation
    case applicationError
}

private enum AgentMCPWorkerIntegrationError: Error {
    case missingTool(String)
    case missingValue(String)
    case timedOut(String)
    case workerTrace(String)
}

private actor E2EChatStarter {
    private let mode: E2EChatMode
    private var recorded: [ControlPlaneChatRequest] = []

    init(mode: E2EChatMode) {
        self.mode = mode
    }

    func start(
        _ request: ControlPlaneChatRequest
    ) throws -> ControlPlaneChatExecution {
        recorded.append(request)
        if recorded.count == 1 {
            let suffix: String
            let callID: String
            let arguments: String
            switch mode {
            case .completion:
                suffix = "bounded_secret_echo"
                callID = "call-mcp-e2e-completion"
                arguments = #"{"marker":"continuation-marker","payload_size":256}"#
            case .cancellation:
                suffix = "delayed_echo"
                callID = "call-mcp-e2e-cancellation"
                arguments = #"{"marker":"cancel-marker","delay_ms":10000}"#
            case .applicationError:
                suffix = "application_error"
                callID = "call-mcp-e2e-application-error"
                arguments = "{}"
            }
            guard let toolName = request.tools.first(where: {
                $0.name.hasSuffix(suffix)
            })?.name else {
                throw AgentMCPWorkerIntegrationError.missingTool(suffix)
            }
            return ControlPlaneChatExecution(
                requestID: "agent-mcp-e2e-turn-1",
                modelID: request.modelID,
                stream: AsyncThrowingStream { continuation in
                    continuation.yield(
                        .toolCallDelta(
                            callID: callID,
                            toolName: toolName,
                            argumentsFragment: arguments
                        )
                    )
                    continuation.yield(
                        .completed(
                            finishReason: "tool_calls",
                            assistantText: "",
                            reasoningText: ""
                        )
                    )
                    continuation.finish()
                }
            )
        }
        return ControlPlaneChatExecution(
            requestID: "agent-mcp-e2e-turn-2",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                let assistantText = mode == .applicationError
                    ? "MCP application error observed."
                    : "MCP continuation complete."
                continuation.yield(.tokenDelta(assistantText))
                continuation.yield(
                    .completed(
                        finishReason: "stop",
                        assistantText: assistantText,
                        reasoningText: ""
                    )
                )
                continuation.finish()
            }
        )
    }

    func requests() -> [ControlPlaneChatRequest] {
        recorded
    }
}

private actor E2EAllowPolicy: AgentApprovalPolicyManaging {
    func approvalEvaluation(
        for _: AgentToolCall,
        runID _: String
    ) -> AgentApprovalPolicyEvaluation {
        AgentApprovalPolicyEvaluation(
            requirement: .notRequired,
            policyRevision: "agent-mcp-e2e-policy-v1",
            scopeDigest: "agent-mcp-e2e-scope"
        )
    }

    func persistAlwaysAllow(
        for _: AgentToolCall,
        runID _: String
    ) -> String {
        "agent-mcp-e2e-policy-v1"
    }

    func persistAlwaysAllow(
        for _: AgentToolCall,
        runID _: String,
        expectedRevision _: String
    ) async throws -> String {
        "agent-mcp-e2e-policy-v1"
    }
}

private actor RecordingAgentToolWorker: AgentToolRuntimeWorkerClientProtocol {
    private let client: PythonBridgeWorkerClient
    private var listed: [Melix_Worker_V1_ListAgentToolsRequest] = []
    private var executed: [Melix_Worker_V1_ExecuteAgentToolRequest] = []
    private var cancelled: [Melix_Worker_V1_CancelAgentToolRequest] = []
    private var cancelledRuns: [
        Melix_Worker_V1_CancelAgentRunToolsRequest
    ] = []
    private var recordedFailures: [String] = []

    init(client: PythonBridgeWorkerClient) {
        self.client = client
    }

    func listAgentTools(
        request: Melix_Worker_V1_ListAgentToolsRequest
    ) async throws -> Melix_Worker_V1_ToolCatalogReceipt {
        listed.append(request)
        do {
            return try await client.listAgentTools(request: request)
        } catch {
            recordedFailures.append(
                "listAgentTools: \(String(reflecting: error))"
            )
            throw error
        }
    }

    func executeAgentTool(
        request: Melix_Worker_V1_ExecuteAgentToolRequest
    ) async throws -> AsyncThrowingStream<
        Melix_Worker_V1_AgentToolExecutionEvent,
        Error
    > {
        executed.append(request)
        return try await client.executeAgentTool(request: request)
    }

    func cancelAgentTool(
        request: Melix_Worker_V1_CancelAgentToolRequest
    ) async throws -> Melix_Worker_V1_CancelAgentToolResponse {
        cancelled.append(request)
        return try await client.cancelAgentTool(request: request)
    }

    func cancelAgentRunTools(
        request: Melix_Worker_V1_CancelAgentRunToolsRequest
    ) async throws -> Melix_Worker_V1_CancelAgentRunToolsResponse {
        cancelledRuns.append(request)
        return try await client.cancelAgentRunTools(request: request)
    }

    func listRequests() -> [Melix_Worker_V1_ListAgentToolsRequest] {
        listed
    }

    func executeRequests() -> [Melix_Worker_V1_ExecuteAgentToolRequest] {
        executed
    }

    func cancelRequests() -> [Melix_Worker_V1_CancelAgentToolRequest] {
        cancelled
    }

    func cancelRunRequests() -> [
        Melix_Worker_V1_CancelAgentRunToolsRequest
    ] {
        cancelledRuns
    }

    func failures() -> [String] {
        recordedFailures
    }
}

private func makeStdioSource(
    pythonPath: String,
    fixturePath: String,
    workingDirectory: String
) -> Melix_Worker_V1_AgentToolSourceConfig {
    .with {
        $0.sourceID = "agent-e2e"
        $0.enabled = true
        $0.stdio = .with {
            $0.command = pythonPath
            $0.arguments = [fixturePath]
            $0.workingDirectory = workingDirectory
            $0.environmentReferences = [
                "MCP_E2E_SECRET": "MELIX_AGENT_MCP_E2E_SECRET",
            ]
        }
        $0.requestTimeoutMs = 15_000
        $0.connectTimeoutMs = 30_000
        $0.maxResultBytes = 4_096
        $0.configurationRevision = "agent-mcp-e2e-v1"
    }
}

private func makeAgentCommand(
    sessionID: String,
    branchID: String,
    prompt: String
) -> Melix_Controlplane_V1_StartAgentRun {
    .with {
        $0.sessionID = sessionID
        $0.branchID = branchID
        $0.serverSessionID = "agent-mcp-e2e-server"
        $0.modelID = "agent-mcp-e2e-model"
        $0.mode = .act
        $0.maxModelTurns = 4
        $0.maxToolCalls = 2
        $0.messages = [
            .with {
                $0.role = "user"
                $0.content = prompt
            },
        ]
    }
}

private func waitForSnapshot(
    runtime: ControlPlaneAgentRuntime,
    runID: String,
    state: String
) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
    for _ in 0..<2_000 {
        let snapshot = try await runtime.snapshot(runID: runID)
        if snapshot.state == state {
            return snapshot
        }
        if ["completed", "failed", "cancelled"].contains(snapshot.state) {
            throw AgentMCPWorkerIntegrationError.timedOut(
                "expected state \(state), reached \(snapshot.state): "
                    + "\(snapshot.error.code) \(snapshot.error.message)"
            )
        }
        try await Task.sleep(for: .milliseconds(10))
    }
    throw AgentMCPWorkerIntegrationError.timedOut(
        "timed out waiting for state \(state)"
    )
}

private func waitForListRequests(
    worker: RecordingAgentToolWorker,
    count: Int
) async throws -> [Melix_Worker_V1_ListAgentToolsRequest] {
    for _ in 0..<2_000 {
        let requests = await worker.listRequests()
        if requests.count >= count {
            return requests
        }
        try await Task.sleep(for: .milliseconds(10))
    }
    throw AgentMCPWorkerIntegrationError.timedOut(
        "timed out waiting for \(count) list-tools requests"
    )
}
