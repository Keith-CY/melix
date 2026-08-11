import Foundation
import MelixWorkerProtocol
import Testing

@testable import MelixControlPlaneCore

@Suite("Agent adapter boundaries", .serialized)
struct AgentAdapterBoundaryTests {
    @Test("catalog construction and Computer scoping fail closed at every identity boundary")
    func catalogConstructionAndComputerScopingFailClosed() throws {
        let valid = adapterDescriptor()

        #expect(throws: ControlPlaneAgentAdapterError.emptyCatalog) {
            _ = try AgentRuntimeToolCatalog(digest: "empty", descriptors: [])
        }
        for descriptor in [
            adapterDescriptor(name: " "),
            adapterDescriptor(schemaDigest: " "),
            adapterDescriptor(inputSchemaJSON: "not-json"),
        ] {
            #expect(throws: ControlPlaneAgentAdapterError.self) {
                _ = try AgentRuntimeToolCatalog(
                    digest: "invalid",
                    descriptors: [descriptor]
                )
            }
        }
        #expect(throws: ControlPlaneAgentAdapterError.duplicateToolName("fixture")) {
            _ = try AgentRuntimeToolCatalog(
                digest: "duplicate",
                descriptors: [valid, valid]
            )
        }

        let catalog = try AgentRuntimeToolCatalog(
            digest: "fixture-catalog",
            descriptors: [
                valid,
                adapterDescriptor(
                    sourceID: "computer",
                    adapterKind: "computer",
                    name: "computer_use",
                    inputSchemaJSON: computerSchema,
                    schemaDigest: "computer-schema",
                    riskClass: "critical"
                ),
            ]
        )
        #expect(
            catalog.admissionResult(for: adapterCall(toolName: "missing"))
                == .recoverable(.unknownTool)
        )
        #expect(
            catalog.admissionResult(
                for: adapterCall(toolName: "fixture", schemaDigest: "stale")
            ) == .terminal(.toolSchemaDigestMismatch(callID: "call-fixture"))
        )
        #expect(catalog.descriptor(named: "computer_use")?.riskClass == "critical")

        let target = try adapterTarget(windowID: 7)
        #expect(throws: ControlPlaneAgentAdapterError.self) {
            _ = try catalog.withTrustedComputerUseTargets([target, target])
        }
        #expect(throws: ControlPlaneAgentAdapterError.self) {
            _ = try catalog.withTrustedComputerUseTargets(
                try (0..<17).map { try adapterTarget(windowID: UInt32($0 + 1)) }
            )
        }

        let malformedComputer = try AgentRuntimeToolCatalog(
            digest: "malformed-computer",
            descriptors: [
                adapterDescriptor(
                    sourceID: "computer",
                    adapterKind: "computer",
                    name: "computer_use",
                    inputSchemaJSON: #"{"type":"object"}"#,
                    schemaDigest: "malformed-computer-schema"
                ),
            ]
        )
        #expect(throws: ControlPlaneAgentAdapterError.self) {
            _ = try malformedComputer.withTrustedComputerUseTargets([target])
        }

        let scoped = try catalog.withTrustedComputerUseTargets([target])
        let scopedSchemaDigest = try #require(
            scoped.descriptor(named: "computer_use")?.schemaDigest
        )
        #expect(scopedSchemaDigest != "computer-schema")
        #expect(
            AgentFacingToolSchemaDigest.workerSchemaDigest(
                from: scopedSchemaDigest
            ) == "computer-schema"
        )
        for malformedDigest in [
            "melix.agent-schema.v1:",
            "melix.agent-schema.v1:not-base64:\(String(repeating: "a", count: 64))",
            "melix.agent-schema.v1:Y29tcHV0ZXItc2NoZW1h:\(String(repeating: "A", count: 64))",
            "melix.agent-schema.v1:Y29tcHV0ZXItc2NoZW1h:short",
        ] {
            #expect(
                AgentFacingToolSchemaDigest.workerSchemaDigest(
                    from: malformedDigest
                ) == malformedDigest
            )
        }
        for arguments in [
            #"{"operation":"capture_frame","target":{}}"#,
            #"{"operation":"capture_frame","target":{"bundle_id":"com.example.Editor","process_id":42,"process_launch_identity":"launch-1","window_id":7,"window_title":"Draft"}}"#,
            #"{"operation":"press_element","session_id":"session-1","target":{"bundle_id":"com.example.Editor","process_id":42,"process_launch_identity":"launch-1","window_id":7,"window_title":"Draft"},"element":{"handle_id":"button-1"}}"#,
            #"{"operation":"press_element","session_id":"session-1","target":{"bundle_id":"com.example.Editor","process_id":42,"process_launch_identity":"launch-1","window_id":7,"window_title":"Draft"},"expected_observation_id":"observation-1","expected_frame_generation":1,"element":{}}"#,
            #"{"operation":"close_session"}"#,
            #"{"operation":"open_session","session_id":"model-supplied"}"#,
            #"{"operation":"unexpected"}"#,
        ] {
            #expect(
                scoped.admissionResult(
                    for: adapterCall(
                        sourceID: "computer",
                        toolName: "computer_use",
                        schemaDigest: scopedSchemaDigest,
                        argumentsJSON: arguments
                    )
                ) == .recoverable(.schemaViolation)
            )
        }

        let exactTarget = #"{"bundle_id":"com.example.Target","process_id":107,"process_launch_identity":"launch-7","window_id":7,"window_title":"Window 7"}"#
        for arguments in [
            #"{"operation":"get_permissions"}"#,
            #"{"operation":"open_session"}"#,
            #"{"operation":"capture_frame","session_id":"session-1","target":\#(exactTarget)}"#,
            #"{"operation":"press_element","session_id":"session-1","target":\#(exactTarget),"expected_observation_id":"observation-1","expected_frame_generation":1,"element":{"handle_id":"button-1"}}"#,
            #"{"operation":"close_session","session_id":"session-1"}"#,
        ] {
            guard case .admitted = scoped.admissionResult(
                for: adapterCall(
                    sourceID: "computer",
                    toolName: "computer_use",
                    schemaDigest: scopedSchemaDigest,
                    argumentsJSON: arguments
                )
            ) else {
                Issue.record("Expected exact Computer Use arguments to be admitted: \(arguments)")
                continue
            }
        }

        let changedProjectionCatalog = try AgentRuntimeToolCatalog(
            digest: "fixture-catalog-projection-v2",
            descriptors: [
                adapterDescriptor(
                    sourceID: "computer",
                    adapterKind: "computer",
                    name: "computer_use",
                    inputSchemaJSON: computerSchema.replacingOccurrences(
                        of: #"{"type":"object""#,
                        with: #"{"$comment":"projection-v2","type":"object""#
                    ),
                    schemaDigest: "computer-schema",
                    riskClass: "critical"
                ),
            ]
        ).withTrustedComputerUseTargets([target])
        let changedSchemaDigest = try #require(
            changedProjectionCatalog.descriptor(named: "computer_use")?
                .schemaDigest
        )
        #expect(changedSchemaDigest != scopedSchemaDigest)
        let originalCall = adapterCall(
            sourceID: "computer",
            toolName: "computer_use",
            schemaDigest: scopedSchemaDigest,
            argumentsJSON: #"{"operation":"get_permissions"}"#
        )
        let changedCall = adapterCall(
            sourceID: "computer",
            toolName: "computer_use",
            schemaDigest: changedSchemaDigest,
            argumentsJSON: #"{"operation":"get_permissions"}"#
        )
        #expect(
            AgentApprovalBinding.make(
                runID: "run-projection-binding",
                call: originalCall,
                policyRevision: "policy-1",
                scopeDigest: "scope-1"
            ).bindingDigest
                != AgentApprovalBinding.make(
                    runID: "run-projection-binding",
                    call: changedCall,
                    policyRevision: "policy-1",
                    scopeDigest: "scope-1"
                ).bindingDigest
        )
        #expect(
            changedProjectionCatalog.admissionResult(for: originalCall)
                == .terminal(
                    .toolSchemaDigestMismatch(callID: originalCall.callID)
                )
        )
    }

    @Test("model port maps transport and stream boundary failures deterministically")
    func modelPortMapsEveryBoundaryFailure() async throws {
        let catalog = try AgentRuntimeToolCatalog(
            digest: "model-boundary",
            descriptors: [adapterDescriptor()]
        )

        for expected in [AgentPortFailure.cancelled, .unavailable] {
            let port = ControlPlaneAgentModelPort(
                configuration: adapterModelConfiguration,
                catalog: catalog,
                startChat: { _ in
                    if expected == .cancelled {
                        throw CancellationError()
                    }
                    throw AdapterBoundaryError.fixture
                }
            )
            await #expect(throws: expected) {
                _ = try await port.performTurn(adapterTurnRequest())
            }
        }

        let preCancelledProbe = AdapterCancellationProbe()
        let preCancelled = ControlPlaneAgentModelPort(
            configuration: adapterModelConfiguration,
            catalog: catalog,
            startChat: { request in
                adapterExecution(
                    modelID: request.modelID,
                    events: [],
                    cancellationProbe: preCancelledProbe
                )
            }
        )
        await preCancelled.cancelTurn(runID: "run-model-boundary")
        await #expect(throws: AgentPortFailure.cancelled) {
            _ = try await preCancelled.performTurn(adapterTurnRequest())
        }
        #expect(await preCancelledProbe.count() == 1)

        let ignoredEvents: [ControlPlaneChatStreamEvent] = [
            .queued(lane: "fixture", queuePosition: 1, backpressure: 0),
            .admitted(lane: "fixture", workerID: "worker", queueDelayMs: 1),
            .prefillStarted(inputTokens: 1),
            .decodeStarted(decodeHandle: "decode", maxOutputTokens: 8),
            .annotationDelta(
                annotationID: "note",
                kind: "citation",
                startOffset: 0,
                endOffset: 1,
                payloadJSON: "{}"
            ),
            .toolResultDelta(callID: "call", status: "completed", resultJSON: "{}"),
            .usage(
                promptTokens: 1,
                completionTokens: 1,
                cachedPromptTokens: 0,
                mediaFeatureCacheHits: 0,
                mediaFeatureCacheMisses: 0,
                mediaFeatureEncoderCallsSaved: 0,
                mediaFeatureWorkSavedBytes: 0
            ),
            .heartbeat,
        ]
        let scenarios: [[ControlPlaneChatStreamEvent]] = [
            [.tokenDelta(String(repeating: "x", count: 4 * 1_024 * 1_024 + 1))],
            [.toolCallDelta(callID: " ", toolName: "fixture", argumentsFragment: "{}")],
            (0..<17).map {
                .toolCallDelta(
                    callID: "call-\($0)",
                    toolName: "fixture",
                    argumentsFragment: "{}"
                )
            },
            [
                .toolCallDelta(callID: "call", toolName: "fixture", argumentsFragment: "{"),
                .toolCallDelta(callID: "call", toolName: "other", argumentsFragment: "}"),
            ],
            [.toolCallDelta(
                callID: "call",
                toolName: "fixture",
                argumentsFragment: String(repeating: "x", count: 512 * 1_024 + 1)
            )],
            [.completed(
                finishReason: "stop",
                assistantText: String(repeating: "x", count: 4 * 1_024 * 1_024 + 1),
                reasoningText: ""
            )],
            [.failed(code: "fixture", message: "failed")],
            ignoredEvents,
        ]
        for (index, events) in scenarios.enumerated() {
            let probe = AdapterCancellationProbe()
            let port = ControlPlaneAgentModelPort(
                configuration: adapterModelConfiguration,
                catalog: catalog,
                startChat: { request in
                    adapterExecution(
                        requestID: "model-boundary-\(index)",
                        modelID: request.modelID,
                        events: events,
                        cancellationProbe: probe
                    )
                }
            )
            await #expect(throws: AgentPortFailure.self) {
                _ = try await port.performTurn(adapterTurnRequest())
            }
            #expect(await probe.count() == (index == scenarios.count - 1 ? 0 : 1))
        }

        let messageProbe = AdapterChatRequestProbe()
        let successful = ControlPlaneAgentModelPort(
            configuration: adapterModelConfiguration,
            catalog: catalog,
            startChat: { request in
                await messageProbe.record(request)
                return adapterExecution(
                    modelID: request.modelID,
                    events: [
                        .completed(
                            finishReason: "stop",
                            assistantText: "done",
                            reasoningText: ""
                        ),
                    ]
                )
            }
        )
        let result = try await successful.performTurn(
            adapterTurnRequest(messages: [
                .system("system"),
                .assistant("assistant"),
                .assistantToolCall(
                    callID: "call-one",
                    toolName: "fixture",
                    argumentsJSON: "{}"
                ),
                .assistantToolCall(
                    callID: "call-two",
                    toolName: "fixture",
                    argumentsJSON: "{}"
                ),
                .toolResult(
                    callID: "call-one",
                    toolName: "fixture",
                    outputJSON: #"{"ok":true}"#
                ),
                .guardrailNudge(
                    AgentToolHealingNudge(
                        callID: "call-heal",
                        failure: .schemaViolation,
                        attemptIndex: 1,
                        maxRetryNudges: 2
                    )
                ),
            ])
        )
        #expect(result.assistantText == "done")
        let messages = try #require(await messageProbe.request()?.messages)
        #expect(messages.map(\.role) == ["system", "assistant", "tool", "user"])
        #expect(messages[1].toolCalls.map(\.callID) == ["call-one", "call-two"])
    }

    @Test("tool execution port validates every terminal phase and cancellation projection")
    func toolExecutionPortValidatesTerminalPhasesAndCancellation() async throws {
        let request = adapterExecutionRequest()
        let applicationErrorObservation = #"{"schema_version":"melix.agentic_tool_observation.v1","status":"failed","payload":{"is_error":true}}"#
        let applicationErrorWorker = AdapterBoundaryWorker(
            executionMode: .events(
                adapterTerminalEvents(
                    request: request,
                    phase: .agentToolExecutionCompleted,
                    status: "completed",
                    observationJSON: applicationErrorObservation
                )
            )
        )
        let applicationErrorResult = try await adapterExecutionPort(
            worker: applicationErrorWorker
        ).execute(request)
        #expect(applicationErrorResult.outputJSON == applicationErrorObservation)

        let terminalCases: [(
            Melix_Worker_V1_AgentToolExecutionPhase,
            String,
            AgentPortFailure
        )] = [
            (.agentToolExecutionCancelled, "cancelled", .cancelled),
            (.agentToolExecutionTimeout, "timeout", .timedOut),
            (.agentToolExecutionFailed, "failed", .rejected),
        ]
        for (phase, status, expected) in terminalCases {
            let worker = AdapterBoundaryWorker(
                executionMode: .events(
                    adapterTerminalEvents(
                        request: request,
                        phase: phase,
                        status: status
                    )
                )
            )
            let port = adapterExecutionPort(worker: worker)
            await #expect(throws: expected) {
                _ = try await port.execute(request)
            }
        }

        let errorTerminal = AdapterBoundaryWorker(
            executionMode: .events(
                adapterTerminalEvents(
                    request: request,
                    phase: .agentToolExecutionFailed,
                    status: "failed",
                    useErrorPayload: true
                )
            )
        )
        await #expect(throws: AgentPortFailure.rejected) {
            _ = try await adapterExecutionPort(worker: errorTerminal).execute(request)
        }

        let invalidStreams: [[Melix_Worker_V1_AgentToolExecutionEvent]] = [
            [adapterWorkerEvent(request: request, sequence: 2, phase: .agentToolExecutionQueued)],
            [adapterWorkerEvent(request: request, sequence: 1, phase: .agentToolExecutionStarted)],
            [adapterWorkerEvent(request: request, sequence: 1, phase: .UNRECOGNIZED(999))],
            adapterTerminalEvents(
                request: request,
                phase: .agentToolExecutionFailed,
                status: "wrong-status"
            ),
            adapterTerminalEvents(
                request: request,
                phase: .agentToolExecutionFailed,
                status: "failed",
                omitPayload: true
            ),
            adapterTerminalEvents(
                request: request,
                phase: .agentToolExecutionFailed,
                status: "failed",
                useInvalidErrorPayload: true
            ),
        ]
        for events in invalidStreams {
            let worker = AdapterBoundaryWorker(executionMode: .events(events))
            await #expect(throws: AgentPortFailure.invalidResponse) {
                _ = try await adapterExecutionPort(worker: worker).execute(request)
            }
        }
        let failingWorker = AdapterBoundaryWorker(executionMode: .throwsError)
        await #expect(throws: AgentPortFailure.unavailable) {
            _ = try await adapterExecutionPort(worker: failingWorker).execute(request)
        }

        let computerRequest = adapterExecutionRequest(
            sourceID: "computer",
            toolName: "computer_use",
            argumentsJSON: "not-json"
        )
        await #expect(throws: AgentPortFailure.rejected) {
            _ = try await adapterExecutionPort(
                worker: AdapterBoundaryWorker(),
                signer: ComputerUseToolAuthorizationSigner()
            ).execute(computerRequest)
        }
        await #expect(throws: AgentPortFailure.rejected) {
            _ = try await adapterExecutionPort(
                worker: AdapterBoundaryWorker(),
                signer: nil
            ).execute(computerRequest)
        }

        let cancellationWorker = AdapterBoundaryWorker()
        let cancellationPort = adapterExecutionPort(worker: cancellationWorker)
        for disposition in [
            Melix_Worker_V1_ToolCancellationDisposition.toolCancellationTooLate,
            .toolCancellationScopeMismatch,
        ] {
            await cancellationWorker.setCancellationDisposition(disposition)
            let receipt = await cancellationPort.cancel(
                runID: request.runID,
                callID: request.call.callID
            )
            #expect(receipt.disposition == (
                disposition == .toolCancellationTooLate ? .tooLate : .scopeMismatch
            ))
        }

        await cancellationWorker.setRunCancellationMode(.correlated)
        let correlated = await cancellationPort.cancelRun(runID: request.runID)
        #expect(correlated.callReceipts.count == 1)
        #expect(correlated.sideEffectState == .committed)
        await cancellationWorker.setRunCancellationMode(.mismatchedCall)
        #expect(
            await cancellationPort.cancelRun(runID: request.runID).disposition
                == .unavailable
        )
        await cancellationWorker.setRunCancellationMode(.mismatchedEnvelope)
        #expect(
            await cancellationPort.cancelRun(runID: request.runID).disposition
                == .unavailable
        )
        await cancellationWorker.setRunCancellationMode(.throwsError)
        #expect(
            await cancellationPort.cancelRun(runID: request.runID).disposition
                == .unavailable
        )
    }
}

private enum AdapterBoundaryError: Error {
    case fixture
}

private let computerSchema = #"{"type":"object","properties":{"operation":{"type":"string","enum":["get_permissions","list_targets","open_session","capture_frame","press_element","close_session"]},"allowed_targets":{"type":"array"},"target":{"type":"object"}},"required":["operation"],"additionalProperties":false}"#

private let adapterModelConfiguration = ControlPlaneAgentModelConfiguration(
    modelID: "model-boundary",
    serverSessionID: "server-boundary"
)

private func adapterDescriptor(
    sourceID: String = "builtin",
    adapterKind: String = "builtin",
    name: String = "fixture",
    inputSchemaJSON: String = #"{"type":"object"}"#,
    schemaDigest: String = "fixture-schema",
    riskClass: String = "local_read_or_compute"
) -> AgentRuntimeToolDescriptor {
    AgentRuntimeToolDescriptor(
        sourceID: sourceID,
        adapterKind: adapterKind,
        name: name,
        title: "Fixture",
        description: "Run fixture.",
        inputSchemaJSON: inputSchemaJSON,
        schemaDigest: schemaDigest,
        riskClass: riskClass
    )
}

private func adapterCall(
    sourceID: String = "builtin",
    toolName: String = "fixture",
    schemaDigest: String = "fixture-schema",
    argumentsJSON: String = "{}"
) -> AgentToolCall {
    AgentToolCall(
        callID: "call-fixture",
        sourceID: sourceID,
        toolName: toolName,
        schemaDigest: schemaDigest,
        argumentsJSON: argumentsJSON
    )
}

private func adapterTarget(windowID: UInt32) throws -> TrustedComputerUseTarget {
    try TrustedComputerUseTarget(
        bundleID: "com.example.Target",
        processID: Int32(windowID + 100),
        processLaunchIdentity: "launch-\(windowID)",
        windowID: windowID,
        windowTitle: "Window \(windowID)",
        applicationName: "Target"
    )
}

private func adapterTurnRequest(
    messages: [AgentRunMessage] = [.user("hello")]
) -> AgentModelTurnRequest {
    AgentModelTurnRequest(
        runID: "run-model-boundary",
        turnIndex: 1,
        messages: messages
    )
}

private actor AdapterCancellationProbe {
    private var value = 0

    func cancel(requestID: String) -> ControlPlaneChatCancellationReceipt {
        value += 1
        return ControlPlaneChatCancellationReceipt(
            requestID: requestID,
            disposition: .accepted
        )
    }

    func count() -> Int { value }
}

private actor AdapterChatRequestProbe {
    private var value: ControlPlaneChatRequest?

    func record(_ request: ControlPlaneChatRequest) { value = request }
    func request() -> ControlPlaneChatRequest? { value }
}

private func adapterExecution(
    requestID: String = "model-boundary",
    modelID: String,
    events: [ControlPlaneChatStreamEvent],
    cancellationProbe: AdapterCancellationProbe? = nil
) -> ControlPlaneChatExecution {
    ControlPlaneChatExecution(
        requestID: requestID,
        modelID: modelID,
        stream: AsyncThrowingStream { continuation in
            for event in events { continuation.yield(event) }
            continuation.finish()
        },
        cancel: {
            guard let cancellationProbe else {
                return ControlPlaneChatCancellationReceipt(
                    requestID: requestID,
                    disposition: .notFound
                )
            }
            return await cancellationProbe.cancel(requestID: requestID)
        }
    )
}

private func adapterExecutionRequest(
    sourceID: String = "builtin",
    toolName: String = "fixture",
    argumentsJSON: String = "{}"
) -> AgentToolExecutionRequest {
    let call = AgentToolCall(
        callID: "call-execution",
        sourceID: sourceID,
        toolName: toolName,
        schemaDigest: "fixture-schema",
        argumentsJSON: argumentsJSON
    )
    let binding = AgentApprovalBinding.make(
        runID: "run-execution",
        call: call,
        policyRevision: "1",
        scopeDigest: "scope"
    )
    return AgentToolExecutionRequest(
        runID: "run-execution",
        call: call,
        admission: AgentToolAdmission(
            kind: .allow,
            binding: binding,
            approvalChoice: nil,
            grantDigest: "grant"
        )
    )
}

private func adapterExecutionPort(
    worker: AdapterBoundaryWorker,
    signer: ComputerUseToolAuthorizationSigner? = nil
) -> WorkerAgentToolExecutionPort {
    WorkerAgentToolExecutionPort(
        worker: worker,
        context: WorkerAgentToolExecutionContext(
            sessionID: "session",
            branchID: "branch",
            actorID: "actor",
            deadlineUnixMs: 0,
            computerUseAuthorizationSigner: signer
        )
    )
}

private func adapterWorkerEvent(
    request: AgentToolExecutionRequest,
    sequence: UInt64,
    phase: Melix_Worker_V1_AgentToolExecutionPhase
) -> Melix_Worker_V1_AgentToolExecutionEvent {
    .with {
        $0.runID = request.runID
        $0.callID = request.call.callID
        $0.seq = sequence
        $0.phase = phase
        $0.emittedAtUnixMs = 1_800_000_000_000 + Int64(sequence)
    }
}

private func adapterTerminalEvents(
    request: AgentToolExecutionRequest,
    phase: Melix_Worker_V1_AgentToolExecutionPhase,
    status: String,
    observationJSON: String = "{}",
    useErrorPayload: Bool = false,
    omitPayload: Bool = false,
    useInvalidErrorPayload: Bool = false
) -> [Melix_Worker_V1_AgentToolExecutionEvent] {
    var terminal = adapterWorkerEvent(request: request, sequence: 3, phase: phase)
    if useErrorPayload || useInvalidErrorPayload {
        terminal.error.code = useInvalidErrorPayload ? " " : "fixture_failure"
        terminal.error.message = "failed"
    } else if !omitPayload {
        terminal.result.runID = request.runID
        terminal.result.callID = request.call.callID
        terminal.result.sourceID = request.call.sourceID
        terminal.result.toolName = request.call.toolName
        terminal.result.status = status
        terminal.result.observationJson = observationJSON
        terminal.result.receiptJson = "{}"
        terminal.result.durationMs = 1
    }
    return [
        adapterWorkerEvent(
            request: request,
            sequence: 1,
            phase: .agentToolExecutionQueued
        ),
        adapterWorkerEvent(
            request: request,
            sequence: 2,
            phase: .agentToolExecutionStarted
        ),
        terminal,
    ]
}

private actor AdapterBoundaryWorker: AgentToolRuntimeWorkerClientProtocol {
    enum ExecutionMode: Sendable {
        case events([Melix_Worker_V1_AgentToolExecutionEvent])
        case throwsError
    }

    enum RunCancellationMode: Sendable {
        case correlated
        case mismatchedCall
        case mismatchedEnvelope
        case throwsError
    }

    private let executionMode: ExecutionMode
    private var cancellationDisposition:
        Melix_Worker_V1_ToolCancellationDisposition = .toolCancellationAccepted
    private var runCancellationMode: RunCancellationMode = .correlated

    init(executionMode: ExecutionMode = .events([])) {
        self.executionMode = executionMode
    }

    func listAgentTools(
        request _: Melix_Worker_V1_ListAgentToolsRequest
    ) async throws -> Melix_Worker_V1_ToolCatalogReceipt {
        Melix_Worker_V1_ToolCatalogReceipt()
    }

    func executeAgentTool(
        request _: Melix_Worker_V1_ExecuteAgentToolRequest
    ) async throws -> AsyncThrowingStream<
        Melix_Worker_V1_AgentToolExecutionEvent,
        Error
    > {
        switch executionMode {
        case .throwsError:
            throw AdapterBoundaryError.fixture
        case .events(let events):
            return AsyncThrowingStream { continuation in
                for event in events { continuation.yield(event) }
                continuation.finish()
            }
        }
    }

    func cancelAgentTool(
        request: Melix_Worker_V1_CancelAgentToolRequest
    ) async throws -> Melix_Worker_V1_CancelAgentToolResponse {
        .with {
            $0.runID = request.runID
            $0.callID = request.callID
            $0.cancellationID = request.cancellationID
            $0.disposition = cancellationDisposition
            $0.sideEffectState = .toolSideEffectNone
        }
    }

    func cancelAgentRunTools(
        request: Melix_Worker_V1_CancelAgentRunToolsRequest
    ) async throws -> Melix_Worker_V1_CancelAgentRunToolsResponse {
        if runCancellationMode == .throwsError {
            throw AdapterBoundaryError.fixture
        }
        return .with {
            $0.runID = runCancellationMode == .mismatchedEnvelope
                ? "other-run"
                : request.runID
            $0.cancellationID = request.cancellationID
            $0.disposition = .toolCancellationAccepted
            $0.sideEffectState = .toolSideEffectCommitted
            $0.computerUseDisposition = .toolCancellationAlreadyTerminal
            $0.calls = [
                .with {
                    $0.runID = runCancellationMode == .mismatchedCall
                        ? "other-run"
                        : request.runID
                    $0.callID = "call-execution"
                    $0.disposition = .toolCancellationAccepted
                    $0.sideEffectState = .toolSideEffectCommitted
                    $0.sideEffectCommitted = true
                },
            ]
        }
    }

    func setCancellationDisposition(
        _ disposition: Melix_Worker_V1_ToolCancellationDisposition
    ) {
        cancellationDisposition = disposition
    }

    func setRunCancellationMode(_ mode: RunCancellationMode) {
        runCancellationMode = mode
    }
}
