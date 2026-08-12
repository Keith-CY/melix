import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol
import Testing

@testable import MelixControlPlaneCore

@Suite("Agent runtime boundaries", .serialized)
struct AgentRuntimeBoundaryTests {
    @Test("default cancellation ports fail closed with exact run identity")
    func defaultCancellationPortsFailClosedWithExactRunIdentity() async throws {
        let port = RuntimeBoundaryDefaultToolPort()
        let call = AgentToolCall(
            callID: "call-default",
            toolName: "fixture",
            schemaDigest: "schema-default",
            argumentsJSON: "{}"
        )
        let binding = AgentApprovalBinding.make(
            runID: "run-default",
            call: call,
            policyRevision: "1",
            scopeDigest: "scope"
        )
        let execution = try await port.execute(.init(
            runID: "run-default",
            call: call,
            admission: .init(
                kind: .allow,
                binding: binding,
                approvalChoice: nil,
                grantDigest: "grant"
            )
        ))
        #expect(execution.outputJSON == "{}")
        #expect((await port.cancel(runID: "run-default", callID: "call-default")).runID == "run-default")
        let runReceipt = await port.cancelRun(runID: "run-default")
        #expect(runReceipt.runID == "run-default")
        #expect(runReceipt.disposition == .unavailable)
        #expect(runReceipt.sideEffectState == .unknown)

        let policy = RuntimeBoundaryPolicy(requirement: .notRequired)
        await #expect(throws: ApprovalPolicyStoreError.deadlineExceeded) {
            _ = try await policy.persistAlwaysAllow(
                for: call,
                runID: "run-default",
                expectedRevision: "1",
                deadlineUnixMs: 1
            )
        }

        let worker = RuntimeBoundaryDefaultRunCancellationWorker()
        _ = try await worker.listAgentTools(request: .init())
        let stream = try await worker.executeAgentTool(request: .init())
        for try await _ in stream {}
        _ = try await worker.cancelAgentTool(request: .init())
        await #expect(throws: WorkerClientError.unavailable) {
            _ = try await worker.cancelAgentRunTools(request: .init())
        }
    }

    @Test("start validates every bounded envelope field before catalog or model work")
    func startValidatesEveryBoundedEnvelopeField() async throws {
        let worker = RuntimeBoundaryWorker()
        let policy = RuntimeBoundaryPolicy(requirement: .notRequired)
        let dependencies = runtimeBoundaryDependencies(worker: worker, policy: policy)

        var cases: [(String, Melix_Controlplane_V1_StartAgentRun, String)] = []
        var command = runtimeBoundaryCommand()
        command.modelID = " "
        cases.append(("model", command, "operator"))
        command = runtimeBoundaryCommand()
        command.sessionID = " "
        cases.append(("session", command, "operator"))
        cases.append(("actor", runtimeBoundaryCommand(), " "))
        command = runtimeBoundaryCommand()
        command.sessionID = "invalid\0owner"
        cases.append(("owner", command, "operator"))
        command = runtimeBoundaryCommand()
        command.mode = .ask
        cases.append(("mode", command, "operator"))
        command = runtimeBoundaryCommand()
        command.messages = []
        cases.append(("messages", command, "operator"))
        command = runtimeBoundaryCommand()
        command.maxModelTurns = 65
        cases.append(("limits", command, "operator"))
        command = runtimeBoundaryCommand()
        command.messages[0].role = "developer"
        cases.append(("role", command, "operator"))
        command = runtimeBoundaryCommand()
        command.messages[0].role = String(repeating: "r", count: 513)
        cases.append(("role-size", command, "operator"))
        command = runtimeBoundaryCommand()
        command.messages[0].content = String(repeating: "x", count: 4 * 1_024 * 1_024 + 1)
        cases.append(("message-size", command, "operator"))
        command = runtimeBoundaryCommand()
        command.messages[0].toolArgumentsJson = String(repeating: "x", count: 512 * 1_024 + 1)
        cases.append(("arguments-size", command, "operator"))
        command = runtimeBoundaryCommand()
        command.computerUseTargets = [.init()]
        cases.append(("invalid-target", command, "operator"))
        command = runtimeBoundaryCommand()
        command.computerUseTargets = [
            runtimeBoundaryComputerTarget(windowID: 7),
            runtimeBoundaryComputerTarget(windowID: 8),
        ]
        cases.append(("multiple-targets", command, "operator"))

        for (label, invalid, actorID) in cases {
            let runtime = ControlPlaneAgentRuntime(
                runIDGenerator: { "run-invalid-\(label)" }
            )
            await #expect(throws: ControlPlaneAgentRuntimeError.self) {
                _ = try await runtime.start(
                    command: invalid,
                    actorID: actorID,
                    dependencies: dependencies
                )
            }
        }

        let invalidRunID = ControlPlaneAgentRuntime(runIDGenerator: { " " })
        await #expect(throws: ControlPlaneAgentRuntimeError.self) {
            _ = try await invalidRunID.start(
                command: runtimeBoundaryCommand(),
                actorID: "operator",
                dependencies: dependencies
            )
        }
        #expect(await worker.catalogRequestCount() == 0)
    }

    @Test("runtime preserves every initial message role and source transport identity")
    func runtimePreservesMessagesAndSourceTransportIdentity() async throws {
        let worker = RuntimeBoundaryWorker()
        let policy = RuntimeBoundaryPolicy(requirement: .notRequired)
        let chat = RuntimeBoundaryChat(mode: .complete)
        let runtime = ControlPlaneAgentRuntime(
            runIDGenerator: { "run-full-envelope" }
        )
        var command = runtimeBoundaryCommand()
        command.messages = [
            .with { $0.role = "system"; $0.content = "system" },
            .with { $0.role = "user"; $0.content = "user" },
            .with { $0.role = "assistant"; $0.content = "assistant" },
            .with {
                $0.role = "assistant"
                $0.toolCallID = "call-prior"
                $0.toolName = "fixture"
                $0.toolArgumentsJson = "{}"
            },
            .with {
                $0.role = "tool"
                $0.toolCallID = "call-prior"
                $0.toolName = "fixture"
                $0.content = #"{"ok":true}"#
            },
        ]

        var stdio = Melix_Worker_V1_AgentToolSourceConfig()
        stdio.sourceID = "stdio"
        stdio.enabled = true
        stdio.requestTimeoutMs = 1_000
        stdio.connectTimeoutMs = 500
        stdio.maxResultBytes = 4_096
        stdio.configurationRevision = "1"
        stdio.redactionTerms = ["secret"]
        stdio.stdio.command = "/usr/bin/false"
        stdio.stdio.arguments = ["--fixture"]
        stdio.stdio.workingDirectory = "/tmp"
        stdio.stdio.environmentReferences = ["TOKEN": "MELIX_TOKEN"]
        var http = Melix_Worker_V1_AgentToolSourceConfig()
        http.sourceID = "http"
        http.enabled = true
        http.streamableHTTP.url = "https://example.test/mcp"
        http.streamableHTTP.headers = ["X-Fixture": "1"]
        http.streamableHTTP.headerEnvironmentReferences = ["Authorization": "MELIX_AUTH"]
        var catalogOnly = Melix_Worker_V1_AgentToolSourceConfig()
        catalogOnly.sourceID = "catalog-only"
        catalogOnly.enabled = false

        let started = try await runtime.start(
            command: command,
            actorID: "operator",
            dependencies: runtimeBoundaryDependencies(
                worker: worker,
                policy: policy,
                sourceConfigs: [http, catalogOnly, stdio],
                startChat: { request in try await chat.start(request) }
            )
        )
        let terminal = try await runtimeBoundarySnapshot(
            runtime: runtime,
            runID: started.runID,
            terminal: true
        )
        #expect(
            terminal.state == "completed",
            Comment(rawValue: "\(terminal.error.code): \(terminal.error.message)")
        )
        let request = try #require(await chat.lastRequest())
        #expect(request.messages.map(\.role) == ["system", "user", "assistant", "tool"])
        #expect(request.messages[2].toolCalls.first?.callID == "call-prior")
        #expect(await worker.catalogRequestCount() >= 2)
    }

    @Test("approval decisions reject missing state and accept each explicit operator choice")
    func approvalDecisionBoundariesAreExplicit() async throws {
        let worker = RuntimeBoundaryWorker()
        let policy = RuntimeBoundaryPolicy(requirement: .required)
        let chat = RuntimeBoundaryChat(mode: .toolThenComplete)
        let runtime = ControlPlaneAgentRuntime(
            runIDGenerator: { "run-approval-boundary" }
        )
        let started = try await runtime.start(
            command: runtimeBoundaryCommand(),
            actorID: "operator",
            dependencies: runtimeBoundaryDependencies(
                worker: worker,
                policy: policy,
                startChat: { request in try await chat.start(request) }
            )
        )
        let pending = try await runtimeBoundarySnapshot(
            runtime: runtime,
            runID: started.runID,
            state: "waiting_for_approval"
        )
        let binding = try #require(pending.pendingApproval.binding as Melix_Controlplane_V1_AgentApprovalBinding?)

        var decision = Melix_Controlplane_V1_DecideAgentApproval()
        decision.binding = binding
        decision.choice = .agentApprovalAllowOnce
        await #expect(throws: ControlPlaneAgentRuntimeError.self) {
            _ = try await runtime.decideApproval(
                command: decision,
                actorID: " "
            )
        }
        var wrong = decision
        wrong.binding.argumentDigest = "wrong"
        await #expect(throws: ControlPlaneAgentRuntimeError.invalidApprovalBinding) {
            _ = try await runtime.decideApproval(
                command: wrong,
                actorID: "operator"
            )
        }
        var missingChoice = decision
        missingChoice.choice = .unspecified
        await #expect(throws: ControlPlaneAgentRuntimeError.self) {
            _ = try await runtime.decideApproval(
                command: missingChoice,
                actorID: "operator"
            )
        }
        _ = try await runtime.decideApproval(
            command: decision,
            actorID: "operator"
        )
        _ = try await runtimeBoundarySnapshot(
            runtime: runtime,
            runID: started.runID,
            terminal: true
        )

        await #expect(throws: ControlPlaneAgentRuntimeError.approvalNotPending) {
            _ = try await runtime.decideApproval(
                command: decision,
                actorID: "operator"
            )
        }
        var unknown = decision
        unknown.binding.runID = "missing-run"
        await #expect(throws: ControlPlaneAgentRuntimeError.unknownRun("missing-run")) {
            _ = try await runtime.decideApproval(
                command: unknown,
                actorID: "operator"
            )
        }

        let denyPolicy = RuntimeBoundaryPolicy(requirement: .required)
        let denyChat = RuntimeBoundaryChat(mode: .toolThenComplete)
        let denyRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "run-approval-deny" }
        )
        let denyStarted = try await denyRuntime.start(
            command: runtimeBoundaryCommand(),
            actorID: "operator",
            dependencies: runtimeBoundaryDependencies(
                worker: worker,
                policy: denyPolicy,
                startChat: { request in try await denyChat.start(request) }
            )
        )
        let denyPending = try await runtimeBoundarySnapshot(
            runtime: denyRuntime,
            runID: denyStarted.runID,
            state: "waiting_for_approval"
        )
        var deny = Melix_Controlplane_V1_DecideAgentApproval()
        deny.binding = denyPending.pendingApproval.binding
        deny.choice = .agentApprovalDeny
        _ = try await denyRuntime.decideApproval(command: deny, actorID: "operator")
        let denied = try await runtimeBoundarySnapshot(
            runtime: denyRuntime,
            runID: denyStarted.runID,
            terminal: true
        )
        #expect(denied.state == "failed")
    }

    @Test("durable identity conflicts, failed start commits, and archived cancellation stay fail closed")
    func durableStartAndArchivedCancellationBoundaries() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-runtime-boundary-durable-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        let store = AgentRunDurableStore(rootURL: root)

        var duplicate = Melix_Controlplane_V1_AgentRunSnapshot()
        duplicate.runID = "run-durable-duplicate"
        duplicate.state = "completed"
        try await store.persistSnapshot(duplicate)
        let duplicateRunID = duplicate.runID
        let duplicateRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { duplicateRunID },
            durableStore: store
        )
        await #expect(throws: ControlPlaneAgentRuntimeError.self) {
            _ = try await duplicateRuntime.start(
                command: runtimeBoundaryCommand(),
                actorID: "operator",
                dependencies: runtimeBoundaryDependencies(
                    worker: RuntimeBoundaryWorker(),
                    policy: RuntimeBoundaryPolicy(requirement: .notRequired)
                )
            )
        }

        var archivedTerminal = Melix_Controlplane_V1_AgentRunSnapshot()
        archivedTerminal.runID = "run-archived-terminal"
        archivedTerminal.state = "failed"
        try await store.persistSnapshot(archivedTerminal)
        var archivedActive = Melix_Controlplane_V1_AgentRunSnapshot()
        archivedActive.runID = "run-archived-active"
        archivedActive.state = "model_turn"
        archivedActive.revision = 7
        archivedActive.pendingApproval.sourceID = "mcp"
        var interruptedTool = Melix_Controlplane_V1_AgentToolCallSnapshot()
        interruptedTool.callID = "call-interrupted"
        interruptedTool.sourceID = "mcp"
        interruptedTool.toolName = "notes.write"
        interruptedTool.state = "running"
        archivedActive.toolCalls = [interruptedTool]
        archivedActive.computerUseSession.sessionID = "computer-session"
        archivedActive.computerUseSession.sessionState =
            .agentComputerUseSessionOpen
        archivedActive.computerUseSession.lastOperation =
            .agentComputerUsePressElement
        archivedActive.computerUseSession.lastResult =
            .agentComputerUseResultCompleted
        archivedActive.computerUseSession.lastActionID = "call-interrupted"
        archivedActive.computerUseSession.lastCallID = "call-interrupted"
        try await store.persistSnapshot(archivedActive)
        let archiveRuntime = ControlPlaneAgentRuntime(durableStore: store)
        let alreadyTerminal = await archiveRuntime.cancel(
            runID: archivedTerminal.runID,
            reason: .operatorRequested
        )
        let interrupted = await archiveRuntime.cancel(
            runID: archivedActive.runID,
            reason: .system("fixture")
        )
        #expect(alreadyTerminal.disposition == "already_terminal")
        #expect(alreadyTerminal.sideEffectState == .agentToolSideEffectNone)
        #expect(interrupted.disposition == "already_terminal")
        #expect(interrupted.sideEffectState == .agentToolSideEffectUnknown)

        let recovered = try #require(
            try await store.snapshot(runID: archivedActive.runID)
        )
        #expect(recovered.state == "failed")
        #expect(recovered.error.code == "agent_run_interrupted_by_restart")
        #expect(!recovered.hasPendingApproval)
        #expect(recovered.toolCalls.first?.state == "failed")
        #expect(
            recovered.toolCalls.first?.error.code
                == "agent_run_interrupted_by_restart"
        )
        #expect(
            recovered.computerUseSession.sessionState
                == .agentComputerUseSessionUnavailable
        )
        #expect(
            recovered.computerUseSession.lastResult
                == .agentComputerUseResultFailed
        )
        #expect(recovered.computerUseSession.lastActionID.isEmpty)
        #expect(recovered.computerUseSession.lastCallID.isEmpty)
        #expect(recovered.revision == 9)

        let restartedRuntime = ControlPlaneAgentRuntime(durableStore: store)
        let restartedSnapshot = try await restartedRuntime.snapshot(
            runID: archivedActive.runID
        )
        #expect(restartedSnapshot.state == recovered.state)
        #expect(restartedSnapshot.revision == recovered.revision)
        #expect(restartedSnapshot.hasCancellationReceipt)
        #expect(restartedSnapshot.cancellationReceipt == interrupted)
        let restartedListed = await restartedRuntime.snapshots(limit: 10)
            .first(where: { $0.runID == archivedActive.runID })
        #expect(restartedListed?.state == "failed")
        #expect(restartedListed?.cancellationReceipt == interrupted)
        #expect(
            await restartedRuntime.cancel(
                runID: archivedActive.runID,
                reason: .operatorRequested
            ) == interrupted
        )

        let failureRoot = root.appendingPathComponent("failed-start", isDirectory: true)
        var failingSystemCalls = AgentRunDurableStoreSystemCalls.live
        failingSystemCalls.write = { _, _, _ in -1 }
        let failingStore = AgentRunDurableStore(
            rootURL: failureRoot,
            systemCalls: failingSystemCalls
        )
        let registry = AgentApprovalContextRegistry()
        var source = Melix_Worker_V1_AgentToolSourceConfig()
        source.sourceID = "boundary-source"
        source.enabled = true
        source.stdio.command = "/usr/bin/false"
        let failingRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "run-failed-start-commit" },
            durableStore: failingStore
        )
        await #expect(throws: ControlPlaneAgentRuntimeError.journalPersistenceFailed) {
            _ = try await failingRuntime.start(
                command: runtimeBoundaryCommand(),
                actorID: "operator",
                dependencies: runtimeBoundaryDependencies(
                    worker: RuntimeBoundaryWorker(),
                    policy: RuntimeBoundaryPolicy(requirement: .notRequired),
                    approvalContextRegistry: registry,
                    sourceConfigs: [source]
                )
            )
        }
        let leaked = await registry.context(
            for: AgentToolCall(
                callID: "context-check",
                sourceID: "builtin",
                toolName: "fixture",
                riskClass: "low",
                schemaDigest: "fixture-schema",
                argumentsJSON: "{}"
            ),
            runID: "run-failed-start-commit"
        )
        #expect(leaked == nil)
    }

    @Test("archived active runs reconcile to durable terminal truth on read")
    func archivedActiveRunsReconcileOnRead() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-runtime-boundary-restart-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        let store = AgentRunDurableStore(rootURL: root)

        var direct = Melix_Controlplane_V1_AgentRunSnapshot()
        direct.runID = "run-restart-direct"
        direct.state = "waiting_for_approval"
        direct.revision = 2
        direct.pendingApproval.sourceID = "mcp"
        try await store.persistSnapshot(direct)

        var listed = Melix_Controlplane_V1_AgentRunSnapshot()
        listed.runID = "run-restart-list"
        listed.state = "tool_running"
        listed.revision = 4
        try await store.persistSnapshot(listed)

        let runtime = ControlPlaneAgentRuntime(durableStore: store)
        let directRecovered = try await runtime.snapshot(runID: direct.runID)
        #expect(directRecovered.state == "failed")
        #expect(!directRecovered.hasPendingApproval)
        #expect(directRecovered.revision == 3)

        let listedRecovered = try #require(
            await runtime.snapshots(limit: 10).first(where: {
                $0.runID == listed.runID
            })
        )
        #expect(listedRecovered.state == "failed")
        #expect(listedRecovered.revision == 5)
        #expect(
            try await store.snapshot(runID: listed.runID)
                == listedRecovered
        )

        let restarted = ControlPlaneAgentRuntime(durableStore: store)
        #expect(
            try await restarted.snapshot(runID: direct.runID)
                == directRecovered
        )
        let cancellation = await restarted.cancel(
            runID: direct.runID,
            reason: .operatorRequested
        )
        #expect(cancellation.disposition == "already_terminal")
        #expect(cancellation.sideEffectState == .agentToolSideEffectUnknown)
        let afterCancellation = try await restarted.snapshot(
            runID: direct.runID
        )
        #expect(afterCancellation.hasCancellationReceipt)
        #expect(afterCancellation.cancellationReceipt == cancellation)
    }

    @Test("Computer target admission and persistent approval require one exact trusted scope")
    func computerTargetAndPersistentApprovalBoundaries() async throws {
        let computerWorker = RuntimeBoundaryWorker(
            sourceID: "computer",
            adapterKind: "computer",
            toolName: "computer_use",
            riskClass: "low",
            inputSchemaJSON: runtimeBoundaryComputerSchema
        )
        var source = Melix_Worker_V1_AgentToolSourceConfig()
        source.sourceID = "computer-boundary-source"
        source.enabled = true
        source.stdio.command = "/usr/bin/false"
        var selected = runtimeBoundaryCommand()
        selected.computerUseTargets = [runtimeBoundaryComputerTarget(windowID: 41)]
        let targetRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "run-computer-target-unavailable" }
        )
        await #expect(throws: ControlPlaneAgentRuntimeError.self) {
            _ = try await targetRuntime.start(
                command: selected,
                actorID: "operator",
                dependencies: runtimeBoundaryDependencies(
                    worker: computerWorker,
                    policy: RuntimeBoundaryPolicy(requirement: .notRequired),
                    sourceConfigs: [source]
                )
            )
        }

        let cases: [(String, String, Bool)] = [
            (
                "target",
                #"{"operation":"press_element","target":{"bundle_id":"com.example.Target"}}"#,
                true
            ),
            (
                "allowed-target",
                #"{"operation":"press_element","allowed_targets":[{"bundle_id":"com.example.Target"}]}"#,
                true
            ),
            (
                "multiple-targets",
                #"{"operation":"press_element","allowed_targets":[{"bundle_id":"com.example.One"},{"bundle_id":"com.example.Two"}]}"#,
                false
            ),
            (
                "missing-target",
                #"{"operation":"press_element","target":{}}"#,
                false
            ),
        ]
        for (label, arguments, expectedEligibility) in cases {
            let call = AgentToolCall(
                callID: "call-computer-\(label)",
                sourceID: "computer",
                toolName: "computer_use",
                riskClass: "low",
                schemaDigest: "computer-schema",
                argumentsJSON: arguments
            )
            let presentation = AgentApprovalPresentation.make(
                call: call,
                sessionID: "boundary-session",
                branchID: "boundary-branch"
            )
            let eligibility = ControlPlaneAgentRuntime.persistentAllowEligibility(
                call: call,
                presentation: presentation
            )
            #expect(
                eligibility.eligible == expectedEligibility,
                Comment(rawValue: label)
            )
        }
        let malformedCall = AgentToolCall(
            callID: "call-computer-malformed",
            sourceID: "computer",
            toolName: "computer_use",
            riskClass: "low",
            schemaDigest: "computer-schema",
            argumentsJSON: "not-json"
        )
        let forcedReadPresentation = AgentApprovalPresentation(
            operationKind: "read",
            redactedArgumentsJSON: "{}",
            targetScopes: [],
            argumentsTruncated: true
        )
        #expect(
            !ControlPlaneAgentRuntime.persistentAllowEligibility(
                call: malformedCall,
                presentation: forcedReadPresentation
            ).eligible
        )
    }

    @Test("retention and run-wide cancellation project every terminal receipt")
    func retentionAndRunCancellationProjection() async throws {
        let IDs = RuntimeBoundaryRunIDSequence([
            "run-retention-one",
            "run-retention-two",
        ])
        let retentionRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { IDs.next() },
            memoryRetentionLimit: 1
        )
        let dependencies = runtimeBoundaryDependencies(
            worker: RuntimeBoundaryWorker(),
            policy: RuntimeBoundaryPolicy(requirement: .notRequired)
        )
        let first = try await retentionRuntime.start(
            command: runtimeBoundaryCommand(),
            actorID: "operator",
            dependencies: dependencies
        )
        _ = try await runtimeBoundarySnapshot(
            runtime: retentionRuntime,
            runID: first.runID,
            terminal: true
        )
        let second = try await retentionRuntime.start(
            command: runtimeBoundaryCommand(),
            actorID: "operator",
            dependencies: dependencies
        )
        _ = try await runtimeBoundarySnapshot(
            runtime: retentionRuntime,
            runID: second.runID,
            terminal: true
        )
        await #expect(throws: ControlPlaneAgentRuntimeError.unknownRun(first.runID)) {
            _ = try await retentionRuntime.snapshot(runID: first.runID)
        }

        let cancellationWorker = RuntimeBoundaryWorker(
            hangExecution: true,
            includeRunCancellationCall: true
        )
        let cancellationChat = RuntimeBoundaryChat(mode: .toolThenComplete)
        let cancellationRuntime = ControlPlaneAgentRuntime(
            runIDGenerator: { "run-cancellation-projection" }
        )
        let started = try await cancellationRuntime.start(
            command: runtimeBoundaryCommand(),
            actorID: "operator",
            dependencies: runtimeBoundaryDependencies(
                worker: cancellationWorker,
                policy: RuntimeBoundaryPolicy(requirement: .notRequired),
                startChat: { request in try await cancellationChat.start(request) }
            )
        )
        _ = try await runtimeBoundarySnapshot(
            runtime: cancellationRuntime,
            runID: started.runID,
            state: "tool_running"
        )
        let receipt = await cancellationRuntime.cancel(
            runID: started.runID,
            reason: .deadlineExceeded
        )
        #expect(receipt.runTools.calls.count == 1)
        #expect(receipt.runTools.calls[0].callID == "call-boundary")
        #expect(receipt.runTools.calls[0].sourceID == "builtin")
        #expect(receipt.runTools.calls[0].sideEffectCommitted)
        #expect(receipt.runTools.sideEffectState == .agentToolSideEffectCommitted)
    }
}

private actor RuntimeBoundaryDefaultToolPort: AgentToolExecutionPort {
    func execute(_ request: AgentToolExecutionRequest) async throws -> AgentToolExecutionResult {
        .init(outputJSON: request.call.argumentsJSON)
    }

    func cancel(runID: String, callID: String) async -> AgentToolCancellationReceipt {
        .init(
            runID: runID,
            callID: callID,
            disposition: .alreadyTerminal,
            sideEffectState: .none
        )
    }
}

private actor RuntimeBoundaryDefaultRunCancellationWorker:
    AgentToolRuntimeWorkerClientProtocol
{
    func listAgentTools(
        request _: Melix_Worker_V1_ListAgentToolsRequest
    ) async throws -> Melix_Worker_V1_ToolCatalogReceipt {
        .init()
    }

    func executeAgentTool(
        request _: Melix_Worker_V1_ExecuteAgentToolRequest
    ) async throws -> AsyncThrowingStream<
        Melix_Worker_V1_AgentToolExecutionEvent,
        Error
    > {
        AsyncThrowingStream { $0.finish() }
    }

    func cancelAgentTool(
        request _: Melix_Worker_V1_CancelAgentToolRequest
    ) async throws -> Melix_Worker_V1_CancelAgentToolResponse {
        .init()
    }
}

private func runtimeBoundaryCommand() -> Melix_Controlplane_V1_StartAgentRun {
    .with {
        $0.sessionID = "boundary-session"
        $0.branchID = "boundary-branch"
        $0.serverSessionID = "boundary-server"
        $0.modelID = "boundary-model"
        $0.mode = .act
        $0.messages = [.with { $0.role = "user"; $0.content = "Run fixture." }]
    }
}

private func runtimeBoundaryComputerTarget(
    windowID: UInt32
) -> Melix_Controlplane_V1_AgentComputerUseTarget {
    .with {
        $0.bundleID = "com.example.Target"
        $0.processID = Int32(windowID + 100)
        $0.processLaunchIdentity = "launch-\(windowID)"
        $0.windowID = windowID
        $0.windowTitle = "Window \(windowID)"
        $0.applicationName = "Target"
    }
}

private func runtimeBoundaryDependencies(
    worker: RuntimeBoundaryWorker,
    policy: RuntimeBoundaryPolicy,
    approvalContextRegistry: AgentApprovalContextRegistry? = nil,
    sourceConfigs: [Melix_Worker_V1_AgentToolSourceConfig] = [],
    startChat: @escaping ControlPlaneAgentModelPort.StartChat = { request in
        ControlPlaneChatExecution(
            requestID: "boundary-default-chat",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                continuation.yield(.completed(
                    finishReason: "stop",
                    assistantText: "done",
                    reasoningText: ""
                ))
                continuation.finish()
            }
        )
    }
) -> ControlPlaneAgentRuntimeStartDependencies {
    ControlPlaneAgentRuntimeStartDependencies(
        worker: worker,
        approvalPolicy: policy,
        approvalContextRegistry: approvalContextRegistry,
        sourceConfigs: sourceConfigs,
        startChat: startChat
    )
}

private func runtimeBoundarySnapshot(
    runtime: ControlPlaneAgentRuntime,
    runID: String,
    state: String? = nil,
    terminal: Bool = false
) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
    for _ in 0..<300 {
        let snapshot = try await runtime.snapshot(runID: runID)
        if snapshot.state == state
            || (terminal && ["completed", "failed", "cancelled"].contains(snapshot.state))
        {
            return snapshot
        }
        try await Task.sleep(for: .milliseconds(10))
    }
    Issue.record("Timed out waiting for runtime boundary state")
    return try await runtime.snapshot(runID: runID)
}

private actor RuntimeBoundaryPolicy: AgentApprovalPolicyManaging {
    private let requirement: AgentApprovalRequirement

    init(requirement: AgentApprovalRequirement) {
        self.requirement = requirement
    }

    func approvalEvaluation(
        for _: AgentToolCall,
        runID _: String
    ) -> AgentApprovalPolicyEvaluation {
        AgentApprovalPolicyEvaluation(
            requirement: requirement,
            policyRevision: "1",
            scopeDigest: "scope"
        )
    }

    func persistAlwaysAllow(
        for _: AgentToolCall,
        runID _: String
    ) -> String { "2" }

    func persistAlwaysAllow(
        for _: AgentToolCall,
        runID _: String,
        expectedRevision _: String
    ) -> String { "2" }
}

private actor RuntimeBoundaryChat {
    enum Mode: Sendable {
        case complete
        case toolThenComplete
    }

    private let mode: Mode
    private let toolName: String
    private let argumentsJSON: String
    private var requests: [ControlPlaneChatRequest] = []

    init(
        mode: Mode,
        toolName: String = "fixture",
        argumentsJSON: String = "{}"
    ) {
        self.mode = mode
        self.toolName = toolName
        self.argumentsJSON = argumentsJSON
    }

    func start(_ request: ControlPlaneChatRequest) throws -> ControlPlaneChatExecution {
        requests.append(request)
        let isToolTurn = mode == .toolThenComplete && requests.count == 1
        return ControlPlaneChatExecution(
            requestID: "runtime-boundary-chat-\(requests.count)",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                if isToolTurn {
                    continuation.yield(.toolCallDelta(
                        callID: "call-boundary",
                        toolName: toolName,
                        argumentsFragment: argumentsJSON
                    ))
                    continuation.yield(.completed(
                        finishReason: "tool_calls",
                        assistantText: "",
                        reasoningText: ""
                    ))
                } else {
                    continuation.yield(.completed(
                        finishReason: "stop",
                        assistantText: "done",
                        reasoningText: ""
                    ))
                }
                continuation.finish()
            }
        )
    }

    func lastRequest() -> ControlPlaneChatRequest? { requests.last }
}

private actor RuntimeBoundaryWorker: AgentToolRuntimeWorkerClientProtocol {
    private var catalogRequests = 0
    private let sourceID: String
    private let adapterKind: String
    private let toolName: String
    private let riskClass: String
    private let inputSchemaJSON: String
    private let hangExecution: Bool
    private let includeRunCancellationCall: Bool

    init(
        sourceID: String = "builtin",
        adapterKind: String = "builtin",
        toolName: String = "fixture",
        riskClass: String = "low",
        inputSchemaJSON: String = #"{"type":"object"}"#,
        hangExecution: Bool = false,
        includeRunCancellationCall: Bool = false
    ) {
        self.sourceID = sourceID
        self.adapterKind = adapterKind
        self.toolName = toolName
        self.riskClass = riskClass
        self.inputSchemaJSON = inputSchemaJSON
        self.hangExecution = hangExecution
        self.includeRunCancellationCall = includeRunCancellationCall
    }

    func listAgentTools(
        request _: Melix_Worker_V1_ListAgentToolsRequest
    ) async throws -> Melix_Worker_V1_ToolCatalogReceipt {
        catalogRequests += 1
        return .with {
            $0.catalogDigest = "runtime-boundary-catalog"
            $0.tools = [.with {
                $0.sourceID = sourceID
                $0.adapterKind = adapterKind
                $0.name = toolName
                $0.title = "Fixture"
                $0.description_p = "Run fixture."
                $0.inputSchemaJson = inputSchemaJSON
                $0.schemaDigest = "fixture-schema"
                $0.riskClass = riskClass
            }]
        }
    }

    func executeAgentTool(
        request: Melix_Worker_V1_ExecuteAgentToolRequest
    ) async throws -> AsyncThrowingStream<
        Melix_Worker_V1_AgentToolExecutionEvent,
        Error
    > {
        let queued = runtimeBoundaryWorkerEvent(request: request, seq: 1, phase: .agentToolExecutionQueued)
        let started = runtimeBoundaryWorkerEvent(request: request, seq: 2, phase: .agentToolExecutionStarted)
        var completed = runtimeBoundaryWorkerEvent(request: request, seq: 3, phase: .agentToolExecutionCompleted)
        completed.result.runID = request.context.runID
        completed.result.callID = request.callID
        completed.result.sourceID = request.sourceID
        completed.result.toolName = request.toolName
        completed.result.status = "completed"
        completed.result.observationJson = #"{"ok":true}"#
        completed.result.durationMs = 1
        return AsyncThrowingStream { continuation in
            continuation.yield(queued)
            continuation.yield(started)
            if hangExecution {
                return
            }
            continuation.yield(completed)
            continuation.finish()
        }
    }

    func cancelAgentTool(
        request: Melix_Worker_V1_CancelAgentToolRequest
    ) async throws -> Melix_Worker_V1_CancelAgentToolResponse {
        .with {
            $0.runID = request.runID
            $0.callID = request.callID
            $0.cancellationID = request.cancellationID
            $0.disposition = hangExecution
                ? .toolCancellationTooLate
                : .toolCancellationAlreadyTerminal
            $0.sideEffectState = hangExecution
                ? .toolSideEffectCommitted
                : .toolSideEffectNone
            $0.sideEffectCommitted = hangExecution
        }
    }

    func cancelAgentRunTools(
        request: Melix_Worker_V1_CancelAgentRunToolsRequest
    ) async throws -> Melix_Worker_V1_CancelAgentRunToolsResponse {
        .with {
            $0.runID = request.runID
            $0.cancellationID = request.cancellationID
            $0.disposition = includeRunCancellationCall
                ? .toolCancellationAccepted
                : .toolCancellationAlreadyTerminal
            $0.sideEffectState = includeRunCancellationCall
                ? .toolSideEffectCommitted
                : .toolSideEffectNone
            $0.computerUseDisposition = .toolCancellationAlreadyTerminal
            if includeRunCancellationCall {
                $0.calls = [.with {
                    $0.runID = request.runID
                    $0.callID = "call-boundary"
                    $0.disposition = .toolCancellationTooLate
                    $0.sideEffectState = .toolSideEffectCommitted
                    $0.sideEffectCommitted = true
                }]
            }
        }
    }

    func catalogRequestCount() -> Int { catalogRequests }
}

private final class RuntimeBoundaryRunIDSequence: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String]

    init(_ values: [String]) {
        self.values = values
    }

    func next() -> String {
        lock.lock()
        defer { lock.unlock() }
        return values.removeFirst()
    }
}

private let runtimeBoundaryComputerSchema = #"{"type":"object","properties":{"operation":{"type":"string","enum":["get_permissions","list_targets","open_session","capture_frame","press_element","close_session"]},"allowed_targets":{"type":"array"},"target":{"type":"object"}},"required":["operation"],"additionalProperties":false}"#

private func runtimeBoundaryWorkerEvent(
    request: Melix_Worker_V1_ExecuteAgentToolRequest,
    seq: UInt64,
    phase: Melix_Worker_V1_AgentToolExecutionPhase
) -> Melix_Worker_V1_AgentToolExecutionEvent {
    .with {
        $0.runID = request.context.runID
        $0.callID = request.callID
        $0.seq = seq
        $0.phase = phase
        $0.emittedAtUnixMs = 1_800_000_000_000 + Int64(seq)
    }
}
