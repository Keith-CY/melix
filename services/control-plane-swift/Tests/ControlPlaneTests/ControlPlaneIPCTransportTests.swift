import Darwin
import Foundation
import MelixControlPlaneProtocol
import Testing

@testable import MelixControlPlaneCore

@Suite("Control Plane daemon IPC", .serialized)
struct ControlPlaneIPCTransportTests {
    @Test("chat start metadata has a bounded wait and cancels the server request")
    func chatStartMetadataTimeoutCancelsServerRequest() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cp-ipc-timeout-\(UUID().uuidString.prefix(8).lowercased())",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        _ = chmod(root.path, 0o700)
        defer { try? FileManager.default.removeItem(at: root) }

        let socketPath = root.appendingPathComponent("control.sock").path
        let service = IPCFixtureControlPlaneService()
        let server = try ControlPlaneIPCUDSServer(
            socketPath: socketPath,
            service: ControlPlaneIPCGRPCProvider(service: service)
        )
        try await server.start()
        defer { Task { await server.stop() } }

        let remote = ControlPlaneIPCExecutionClient(
            socketPath: socketPath,
            startMetadataTimeout: .milliseconds(100)
        )
        do {
            _ = try await remote.startChat(
                ControlPlaneChatRequest(
                    modelID: "model-never-starts",
                    messages: [.init(role: "user", content: "wait")]
                )
            )
            Issue.record("Expected a bounded start-metadata timeout")
        } catch let error as ControlPlaneIPCTransportError {
            guard case .unavailable = error else {
                Issue.record("Expected an unavailable timeout, got \(error)")
                return
            }
        }

        for _ in 0..<100 {
            if await service.startChatWasCancelled() {
                break
            }
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await service.startChatWasCancelled())
    }

    @Test("late start metadata cannot revive a timed-out chat")
    func lateStartMetadataCannotReviveTimedOutChat() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cp-ipc-late-start-\(UUID().uuidString.prefix(8).lowercased())",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        _ = chmod(root.path, 0o700)
        defer { try? FileManager.default.removeItem(at: root) }

        let socketPath = root.appendingPathComponent("control.sock").path
        let service = IPCFixtureControlPlaneService()
        let server = try ControlPlaneIPCUDSServer(
            socketPath: socketPath,
            service: ControlPlaneIPCGRPCProvider(service: service)
        )
        try await server.start()
        defer { Task { await server.stop() } }

        let remote = ControlPlaneIPCExecutionClient(
            socketPath: socketPath,
            startMetadataTimeout: .milliseconds(100)
        )
        do {
            _ = try await remote.startChat(
                ControlPlaneChatRequest(
                    modelID: "model-late-start",
                    messages: [.init(role: "user", content: "wait")]
                )
            )
            Issue.record("Expected a bounded start-metadata timeout")
        } catch let error as ControlPlaneIPCTransportError {
            guard case .unavailable = error else {
                Issue.record("Expected an unavailable timeout, got \(error)")
                return
            }
        }

        await service.releaseLateStart()
        for _ in 0..<100 {
            if await service.lateExecutionWasCancelled() {
                break
            }
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await service.lateExecutionWasCancelled())
    }

    @Test("private UDS carries handshake, events, chat, cancellation, execute, and agent start")
    func privateUDSCarriesTheOperatorContract() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cp-ipc-\(UUID().uuidString.prefix(8).lowercased())",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        _ = chmod(root.path, 0o700)
        defer { try? FileManager.default.removeItem(at: root) }

        let socketPath = root.appendingPathComponent("control.sock").path
        let service = IPCFixtureControlPlaneService()
        let provider = ControlPlaneIPCGRPCProvider(service: service)
        let server = try ControlPlaneIPCUDSServer(
            socketPath: socketPath,
            service: provider
        )
        try await server.start()
        defer { Task { await server.stop() } }

        let attributes = try FileManager.default.attributesOfItem(atPath: socketPath)
        let permissions = try #require(attributes[.posixPermissions] as? NSNumber)
        #expect(permissions.intValue & 0o077 == 0)

        let remote = ControlPlaneIPCExecutionClient(socketPath: socketPath)
        let appClient = LocalControlPlaneXPCClient(service: remote)
        let handshake = try await appClient.handshake()
        #expect(handshake.daemonInstanceID == "ipc-daemon-fixture")

        let subscription = await appClient.subscribe(lastSeenSeq: 41)
        let event = await firstEvent(from: subscription)
        #expect(event?.eventType == "ipc.fixture")
        #expect(await service.lastSeenSequence() == 41)

        var executeRequest = Melix_Controlplane_V1_ControlPlaneRequest()
        executeRequest.requestID = "ipc-execute"
        executeRequest.commandType = "agent.get_operations"
        executeRequest.agent.getOperations = Melix_Controlplane_V1_GetAgentOperations()
        let executeResponse = try await remote.execute(executeRequest)
        #expect(executeResponse.ok)
        #expect(executeResponse.requestID == "ipc-execute")

        let remoteTarget = ControlPlaneChatRequest.RemoteTarget(
            serverID: "remote-fixture",
            providerKind: "openai-compatible",
            baseURL: "https://example.test/v1",
            apiKey: "secret-stays-in-private-ipc",
            modelID: "remote-model",
            timeoutSeconds: 17,
            rateLimitPerMinute: 9
        )
        let chat = try await appClient.startChat(
            ControlPlaneChatRequest(
                modelID: "model-complete",
                serverSessionID: "server-session",
                messages: [
                    .init(
                        role: "assistant",
                        content: "",
                        name: "fixture",
                        toolCalls: [
                            .init(
                                callID: "call-1",
                                toolName: "weather",
                                argumentsJSON: #"{"city":"Tokyo"}"#
                            ),
                        ],
                        toolCallID: "parent-call"
                    ),
                ],
                tools: [
                    .init(
                        name: "weather",
                        description: "Read weather.",
                        parametersJSON: #"{"type":"object"}"#
                    ),
                ],
                toolChoice: "auto",
                enableThinking: false,
                reasoningEffort: "medium",
                temperature: 0.25,
                topP: 0.8,
                maxTokens: 99,
                remoteTarget: remoteTarget
            )
        )
        #expect(chat.requestID == "ipc-chat-model-complete")
        let chatEvents = try await collectChatEvents(chat.stream)
        #expect(chatEvents == [
            .tokenDelta("hello"),
            .completed(
                finishReason: "stop",
                assistantText: "hello",
                reasoningText: ""
            ),
        ])
        let receivedChat = try #require(await service.lastChatRequest())
        #expect(receivedChat.messages.first?.name == "fixture")
        #expect(receivedChat.messages.first?.toolCalls.first?.callID == "call-1")
        #expect(receivedChat.toolChoice == "auto")
        #expect(receivedChat.enableThinking == false)
        #expect(receivedChat.remoteTarget == remoteTarget)

        let hanging = try await appClient.startChat(
            ControlPlaneChatRequest(
                modelID: "model-hang",
                messages: [.init(role: "user", content: "wait")]
            )
        )
        let cancellation = await hanging.cancel()
        #expect(cancellation.disposition == .accepted)
        #expect(await service.hangingChatWasCancelled())

        let retrying = try await appClient.startChat(
            ControlPlaneChatRequest(
                modelID: "model-retry-cancel",
                messages: [.init(role: "user", content: "retry")]
            )
        )
        #expect((await retrying.cancel()).disposition == .unavailable)
        #expect((await retrying.cancel()).disposition == .accepted)
        #expect(await service.retryCancellationCount() == 2)

        var start = Melix_Controlplane_V1_StartAgentRun()
        start.sessionID = "session-agent"
        start.branchID = "branch-agent"
        start.modelID = "model-agent"
        start.deferActivation = true
        start.messages = [
            .with {
                $0.role = "user"
                $0.content = "run"
            },
        ]
        let run = try await appClient.startAgentRun(start, remoteTarget: remoteTarget)
        #expect(run.runID == "ipc-agent-run")
        let receivedAgent = try #require(await service.lastAgentStart())
        #expect(receivedAgent.actorID == "local-operator")
        #expect(receivedAgent.command.sessionID == "session-agent")
        #expect(receivedAgent.command.deferActivation)
        #expect(receivedAgent.remoteTarget == remoteTarget)

        let activated = try await appClient.activateAgentRun(
            runID: "ipc-agent-run"
        )
        #expect(activated.runID == "ipc-agent-run")

        let approval = try await appClient.decideAgentApproval(.with {
            $0.binding.runID = "ipc-agent-run"
            $0.binding.callID = "ipc-approval"
            $0.choice = .agentApprovalAllowOnce
        })
        #expect(approval.binding.callID == "ipc-approval")
        let cancellationReceipt = try await appClient.cancelAgentRun(
            runID: "ipc-agent-run",
            reason: "operator_requested"
        )
        #expect(cancellationReceipt.runID == "ipc-agent-run")
        #expect(try await appClient.agentRun(runID: "ipc-agent-run").runID == "ipc-agent-run")
        #expect(
            try await appClient.agentRuns(
                sessionID: "session-agent",
                limit: 5
            ).map(\.runID) == ["ipc-agent-run"]
        )
        let inventory = try await appClient.nonterminalAgentRuns(
            sessionID: "session-agent",
            limit: 5
        )
        #expect(inventory.runs.map(\.runID) == ["ipc-agent-run"])
        #expect(inventory.isComplete)
        #expect(try await appClient.agentApprovalPolicy().revision == 7)
        #expect(
            try await appClient.replaceAgentApprovalPolicy(
                rules: [.with {
                    $0.id = "ipc-policy-rule"
                    $0.effect = .agentApprovalPolicyAllow
                }],
                expectedRevision: 7
            ).revision == 8
        )
        #expect(try await appClient.agentOperations().catalogDigest == "ipc-catalog")
        let agentCommands = await service.executedAgentCommandTypes()
        #expect(agentCommands == [
            "agent.get_operations",
            "agent.activate",
            "agent.decide_approval",
            "agent.cancel",
            "agent.get",
            "agent.list",
            "agent.list",
            "agent.get_approval_policy",
            "agent.replace_approval_policy",
            "agent.get_operations",
        ])

        await server.stop()
        #expect(!FileManager.default.fileExists(atPath: socketPath))
    }

    @Test("private UDS rejects a unary response with changed correlation fields")
    func privateUDSRejectsChangedResponseCorrelation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cp-ipc-correlation-\(UUID().uuidString.prefix(8).lowercased())",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        _ = chmod(root.path, 0o700)
        defer { try? FileManager.default.removeItem(at: root) }

        let socketPath = root.appendingPathComponent("control.sock").path
        let server = try ControlPlaneIPCUDSServer(
            socketPath: socketPath,
            service: ControlPlaneIPCGRPCProvider(service: IPCFixtureControlPlaneService())
        )
        try await server.start()
        defer { Task { await server.stop() } }

        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "ipc-mismatched-response"
        request.commandType = "agent.get_operations"
        request.agent.getOperations = Melix_Controlplane_V1_GetAgentOperations()

        let remote = ControlPlaneIPCExecutionClient(socketPath: socketPath)
        do {
            _ = try await remote.execute(request)
            Issue.record("Expected changed response correlation to be rejected")
        } catch let error as ControlPlaneIPCTransportError {
            #expect(error == .invalidMessage(
                "Control plane IPC response correlation does not match the request."
            ))
        }
    }

    @Test("private UDS lifecycle rejects live contention, preserves replacements, and recovers stale sockets")
    func privateUDSLifecycleOwnsOnlyItsBoundInode() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cp-ipc-lifecycle-\(UUID().uuidString.prefix(8).lowercased())",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        _ = chmod(root.path, 0o700)
        defer { try? FileManager.default.removeItem(at: root) }

        let livePath = root.appendingPathComponent("live.sock").path
        let liveServer = try ControlPlaneIPCUDSServer(
            socketPath: livePath,
            service: ControlPlaneIPCGRPCProvider(service: IPCFixtureControlPlaneService())
        )
        try await liveServer.start()
        let liveIdentity = try ipcTestSocketIdentity(at: livePath)
        let competitor = try ControlPlaneIPCUDSServer(
            socketPath: livePath,
            service: ControlPlaneIPCGRPCProvider(service: IPCFixtureControlPlaneService())
        )
        do {
            try await competitor.start()
            Issue.record("Expected a second live IPC server to fail closed")
        } catch let error as ControlPlaneIPCTransportError {
            guard case .unavailable = error else {
                Issue.record("Expected an unavailable lifecycle lease, received \(error)")
                await liveServer.stop()
                return
            }
        }
        #expect(try ipcTestSocketIdentity(at: livePath) == liveIdentity)
        await competitor.stop()
        await liveServer.stop()

        let externallyLivePath = root.appendingPathComponent("externally-live.sock").path
        let externallyLiveDescriptor = try bindIPCTestUnixSocket(
            at: externallyLivePath,
            listening: true
        )
        defer {
            _ = Darwin.close(externallyLiveDescriptor)
            _ = Darwin.unlink(externallyLivePath)
        }
        let externallyLiveIdentity = try ipcTestSocketIdentity(at: externallyLivePath)
        let externallyBlockedServer = try ControlPlaneIPCUDSServer(
            socketPath: externallyLivePath,
            service: ControlPlaneIPCGRPCProvider(service: IPCFixtureControlPlaneService())
        )
        do {
            try await externallyBlockedServer.start()
            Issue.record("Expected a live pre-existing IPC socket to fail closed")
        } catch let error as ControlPlaneIPCTransportError {
            guard case .unavailable = error else {
                Issue.record("Expected unavailable for a live socket, received \(error)")
                return
            }
        }
        #expect(
            try ipcTestSocketIdentity(at: externallyLivePath)
                == externallyLiveIdentity
        )
        await externallyBlockedServer.stop()

        let replacementPath = root.appendingPathComponent("replacement.sock").path
        let replacementServer = try ControlPlaneIPCUDSServer(
            socketPath: replacementPath,
            service: ControlPlaneIPCGRPCProvider(service: IPCFixtureControlPlaneService())
        )
        try await replacementServer.start()
        #expect(Darwin.unlink(replacementPath) == 0)
        let replacementDescriptor = try bindIPCTestUnixSocket(
            at: replacementPath,
            listening: true
        )
        defer {
            _ = Darwin.close(replacementDescriptor)
            _ = Darwin.unlink(replacementPath)
        }
        let replacementIdentity = try ipcTestSocketIdentity(at: replacementPath)

        await replacementServer.stop()

        #expect(FileManager.default.fileExists(atPath: replacementPath))
        #expect(
            try ipcTestSocketIdentity(at: replacementPath) == replacementIdentity
        )

        let stalePath = root.appendingPathComponent("stale.sock").path
        let staleDescriptor = try bindIPCTestUnixSocket(
            at: stalePath,
            listening: false
        )
        let staleIdentity = try ipcTestSocketIdentity(at: stalePath)
        _ = Darwin.close(staleDescriptor)
        let recoveredServer = try ControlPlaneIPCUDSServer(
            socketPath: stalePath,
            service: ControlPlaneIPCGRPCProvider(service: IPCFixtureControlPlaneService())
        )

        try await recoveredServer.start()

        #expect(try ipcTestSocketIdentity(at: stalePath) != staleIdentity)
        await recoveredServer.stop()
        #expect(!FileManager.default.fileExists(atPath: stalePath))
    }

    @Test("chat request and every normalized stream event round-trip without optional-value drift")
    func chatMappingRoundTrips() throws {
        for error in [
            ControlPlaneIPCTransportError.invalidSocketPath("invalid"),
            .unsafeSocketPath("unsafe"),
            .unavailable("unavailable"),
            .invalidMessage("message"),
        ] {
            #expect(error.errorDescription != nil)
        }

        let request = ControlPlaneChatRequest(
            modelID: "mapping-model",
            serverSessionID: "mapping-session",
            messages: [
                .init(
                    role: "assistant",
                    content: "",
                    name: "assistant-name",
                    toolCalls: [
                        .init(
                            callID: "mapping-call",
                            toolName: "mapping-tool",
                            argumentsJSON: "{}"
                        ),
                    ],
                    toolCallID: "mapping-parent"
                ),
            ],
            tools: [
                .init(
                    name: "mapping-tool",
                    description: "Map values.",
                    parametersJSON: #"{"type":"object"}"#
                ),
            ],
            toolChoice: "required",
            parallelToolCalls: false,
            enableThinking: true,
            reasoningEffort: "high",
            chatTemplateKwargs: ChatTemplateRequestConfiguration(
                values: ["enable_fixture": .bool(true)]
            ),
            resumeRequestID: "resume-mapping",
            temperature: 0.4,
            topP: 0.9,
            maxTokens: 128,
            remoteTarget: .init(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://example.test/v1",
                apiKey: "private",
                modelID: "remote-model"
            )
        )
        let encodedRequest = try ControlPlaneIPCGRPCProvider.encodeChatRequest(request)
        let decodedRequest = try ControlPlaneIPCGRPCProvider.decodeChatRequest(encodedRequest)
        #expect(decodedRequest == request)

        var tooMany = Melix_Controlplane_V1_ControlPlaneIPCChatRequest()
        tooMany.modelID = String(repeating: "m", count: 513)
        #expect(throws: Error.self) {
            _ = try ControlPlaneIPCGRPCProvider.decodeChatRequest(tooMany)
        }
        var invalidTemplate = Melix_Controlplane_V1_ControlPlaneIPCChatRequest()
        invalidTemplate.hasChatTemplateKwargsJson_p = true
        invalidTemplate.chatTemplateKwargsJson = "not-json"
        #expect(throws: Error.self) {
            _ = try ControlPlaneIPCGRPCProvider.decodeChatRequest(invalidTemplate)
        }
        invalidTemplate.chatTemplateKwargsJson = String(
            repeating: "x",
            count: 256 * 1_024 + 1
        )
        #expect(throws: Error.self) {
            _ = try ControlPlaneIPCGRPCProvider.decodeChatRequest(invalidTemplate)
        }

        let values: [ControlPlaneChatStreamEvent] = [
            .queued(lane: "lane", queuePosition: 2, backpressure: 0.4),
            .admitted(lane: "lane", workerID: "worker", queueDelayMs: 3.5),
            .prefillStarted(inputTokens: 10),
            .decodeStarted(decodeHandle: "decode", maxOutputTokens: 20),
            .tokenDelta("token"),
            .reasoningDelta("reason"),
            .toolCallDelta(callID: "call", toolName: "tool", argumentsFragment: "{}"),
            .annotationDelta(
                annotationID: "a",
                kind: "citation",
                startOffset: 1,
                endOffset: 2,
                payloadJSON: "{}"
            ),
            .toolResultDelta(callID: "call", status: "ok", resultJSON: "{}"),
            .usage(
                promptTokens: 1,
                completionTokens: 2,
                cachedPromptTokens: 3,
                mediaFeatureCacheHits: 4,
                mediaFeatureCacheMisses: 5,
                mediaFeatureEncoderCallsSaved: 6,
                mediaFeatureWorkSavedBytes: 7
            ),
            .completed(finishReason: "stop", assistantText: "done", reasoningText: "why"),
            .failed(code: "failed", message: "message"),
            .heartbeat,
        ]
        for (index, value) in values.enumerated() {
            let encoded = ControlPlaneIPCGRPCProvider.encodeChatEvent(
                value,
                requestID: "request",
                sequence: UInt64(index + 1)
            )
            #expect(try ControlPlaneIPCGRPCProvider.decodeChatEvent(encoded) == value)
        }
        var unknown = Melix_Controlplane_V1_ControlPlaneIPCChatDelta()
        unknown.kind = .UNRECOGNIZED(999)
        #expect(throws: ControlPlaneIPCTransportError.self) {
            _ = try ControlPlaneIPCGRPCProvider.decodeChatEvent(unknown)
        }
    }
}

private actor IPCFixtureControlPlaneService: ControlPlaneExecuting {
    struct AgentStart: Sendable {
        let command: Melix_Controlplane_V1_StartAgentRun
        let actorID: String
        let remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    }

    private var lastSeen: UInt64?
    private var receivedChat: ControlPlaneChatRequest?
    private var receivedAgent: AgentStart?
    private var executedCommands: [String] = []
    private let cancellationProbe = IPCFixtureCancellationProbe()
    private let startCancellationProbe = IPCFixtureCancellationProbe()
    private let lateStartGate = IPCFixtureGate()
    private let lateExecutionCancellationProbe = IPCFixtureCancellationProbe()
    private let retryCancellationProbe = IPCFixtureCancellationProbe()

    func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = request.protocolVersion
        response.daemonInstanceID = "ipc-daemon-fixture"
        return response
    }

    func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest
    ) async -> ControlPlaneSubscription {
        lastSeen = request.lastSeenSeq
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "ipc.fixture"
        return ControlPlaneSubscription(
            subscriptionID: "fixture-subscription",
            stream: AsyncStream { continuation in
                continuation.yield(event)
                continuation.finish()
            }
        )
    }

    func unsubscribe(_: String) async {}

    func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        executedCommands.append(request.commandType)
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.requestID = request.requestID == "ipc-mismatched-response"
            ? "ipc-other-request"
            : request.requestID
        response.commandType = request.requestID == "ipc-mismatched-response"
            ? "agent.list"
            : request.commandType
        response.ok = true
        switch request.agent.kind {
        case .activate(let activation):
            response.agent.run.runID = activation.runID
        case .decideApproval(let decision):
            response.agent.approval.binding = decision.binding
            response.agent.approval.choice = decision.choice
            response.agent.approval.decisionID = "ipc-decision"
        case .cancel(let cancellation):
            response.agent.cancellation.runID = cancellation.runID
            response.agent.cancellation.disposition = "accepted"
        case .get(let get):
            response.agent.run.runID = get.runID
        case .list(let list):
            response.agent.runs = [.with {
                $0.runID = "ipc-agent-run"
                $0.sessionID = "session-agent"
            }]
            response.agent.runsComplete = list.nonterminalOnly
        case .getApprovalPolicy:
            response.agent.approvalPolicy.revision = 7
        case .replaceApprovalPolicy:
            response.agent.approvalPolicy.revision = 8
        case .getOperations:
            response.agent.operations.catalogDigest = "ipc-catalog"
        case .start, nil:
            break
        }
        return response
    }

    func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        receivedChat = request
        let requestID = "ipc-chat-\(request.modelID)"
        if request.modelID == "model-never-starts" {
            let cancellationProbe = startCancellationProbe
            return try await withTaskCancellationHandler {
                try await Task.sleep(for: .seconds(60))
                throw ControlPlaneIPCTransportError.unavailable(
                    "Fixture should be cancelled before returning metadata."
                )
            } onCancel: {
                cancellationProbe.cancel()
            }
        }
        if request.modelID == "model-late-start" {
            let cancellationProbe = lateExecutionCancellationProbe
            await lateStartGate.wait()
            let pair = AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>.makeStream()
            return ControlPlaneChatExecution(
                requestID: requestID,
                modelID: request.modelID,
                stream: pair.stream,
                cancel: {
                    cancellationProbe.cancel()
                    pair.continuation.finish()
                    return ControlPlaneChatCancellationReceipt(
                        requestID: requestID,
                        disposition: .accepted
                    )
                }
            )
        }
        if request.modelID == "model-hang" {
            let hangCancellationProbe = cancellationProbe
            let pair = AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>.makeStream()
            pair.continuation.yield(.tokenDelta("ready"))
            return ControlPlaneChatExecution(
                requestID: requestID,
                modelID: request.modelID,
                stream: pair.stream,
                cancel: {
                    hangCancellationProbe.cancel()
                    pair.continuation.finish()
                    return ControlPlaneChatCancellationReceipt(
                        requestID: requestID,
                        disposition: .accepted
                    )
                }
            )
        }
        if request.modelID == "model-retry-cancel" {
            let retryProbe = retryCancellationProbe
            let pair = AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>.makeStream()
            pair.continuation.yield(.tokenDelta("ready"))
            return ControlPlaneChatExecution(
                requestID: requestID,
                modelID: request.modelID,
                stream: pair.stream,
                cancel: {
                    let count = retryProbe.cancel()
                    if count >= 2 {
                        pair.continuation.finish()
                    }
                    return ControlPlaneChatCancellationReceipt(
                        requestID: requestID,
                        disposition: count >= 2 ? .accepted : .unavailable
                    )
                }
            )
        }
        return ControlPlaneChatExecution(
            requestID: requestID,
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                continuation.yield(.tokenDelta("hello"))
                continuation.yield(
                    .completed(
                        finishReason: "stop",
                        assistantText: "hello",
                        reasoningText: ""
                    )
                )
                continuation.finish()
            }
        )
    }

    func startAgentRun(
        _ command: Melix_Controlplane_V1_StartAgentRun,
        actorID: String,
        remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        receivedAgent = AgentStart(
            command: command,
            actorID: actorID,
            remoteTarget: remoteTarget
        )
        var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        snapshot.runID = "ipc-agent-run"
        snapshot.sessionID = command.sessionID
        return snapshot
    }

    func lastSeenSequence() -> UInt64? { lastSeen }
    func lastChatRequest() -> ControlPlaneChatRequest? { receivedChat }
    func lastAgentStart() -> AgentStart? { receivedAgent }
    func executedAgentCommandTypes() -> [String] {
        executedCommands.filter { $0.hasPrefix("agent.") }
    }
    func hangingChatWasCancelled() async -> Bool {
        cancellationProbe.wasCancelled()
    }
    func startChatWasCancelled() async -> Bool {
        startCancellationProbe.wasCancelled()
    }
    func releaseLateStart() async { await lateStartGate.release() }
    func lateExecutionWasCancelled() async -> Bool {
        lateExecutionCancellationProbe.wasCancelled()
    }
    func retryCancellationCount() async -> Int {
        retryCancellationProbe.cancellationCount()
    }
}

private final class IPCFixtureCancellationProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0

    @discardableResult
    func cancel() -> Int {
        lock.lock()
        defer { lock.unlock() }
        count += 1
        return count
    }
    func wasCancelled() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return count > 0
    }
    func cancellationCount() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return count
    }
}

private actor IPCFixtureGate {
    private var released = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        guard !released else { return }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func release() {
        guard !released else { return }
        released = true
        let current = waiters
        waiters.removeAll()
        for waiter in current { waiter.resume() }
    }
}

private func firstEvent(
    from stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
) async -> Melix_Controlplane_V1_ControlPlaneEvent? {
    for await event in stream { return event }
    return nil
}

private func collectChatEvents(
    _ stream: AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>
) async throws -> [ControlPlaneChatStreamEvent] {
    var values: [ControlPlaneChatStreamEvent] = []
    for try await value in stream { values.append(value) }
    return values
}

private struct IPCTestSocketIdentity: Equatable {
    let device: dev_t
    let inode: ino_t
    let generation: UInt32
    let birthSeconds: Int
    let birthNanoseconds: Int
}

private func ipcTestSocketIdentity(at path: String) throws -> IPCTestSocketIdentity {
    var status = stat()
    guard Darwin.lstat(path, &status) == 0 else {
        throw NSError(
            domain: NSPOSIXErrorDomain,
            code: Int(errno),
            userInfo: [NSFilePathErrorKey: path]
        )
    }
    return IPCTestSocketIdentity(
        device: status.st_dev,
        inode: status.st_ino,
        generation: status.st_gen,
        birthSeconds: status.st_birthtimespec.tv_sec,
        birthNanoseconds: status.st_birthtimespec.tv_nsec
    )
}

private func bindIPCTestUnixSocket(
    at path: String,
    listening: Bool
) throws -> Int32 {
    let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard descriptor >= 0 else {
        throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
    }
    do {
        var address = sockaddr_un()
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        address.sun_family = sa_family_t(AF_UNIX)
        let pathCapacity = MemoryLayout.size(ofValue: address.sun_path)
        path.withCString { source in
            withUnsafeMutablePointer(to: &address.sun_path) { destination in
                destination.withMemoryRebound(
                    to: CChar.self,
                    capacity: pathCapacity
                ) { bytes in
                    _ = strlcpy(bytes, source, pathCapacity)
                }
            }
        }
        let bindResult = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                Darwin.bind(
                    descriptor,
                    socketAddress,
                    socklen_t(MemoryLayout<sockaddr_un>.size)
                )
            }
        }
        guard bindResult == 0 else {
            throw NSError(
                domain: NSPOSIXErrorDomain,
                code: Int(errno),
                userInfo: [NSFilePathErrorKey: path]
            )
        }
        guard Darwin.chmod(path, 0o600) == 0 else {
            throw NSError(
                domain: NSPOSIXErrorDomain,
                code: Int(errno),
                userInfo: [NSFilePathErrorKey: path]
            )
        }
        if listening {
            guard Darwin.listen(descriptor, 1) == 0 else {
                throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
            }
        }
        return descriptor
    } catch {
        _ = Darwin.close(descriptor)
        throw error
    }
}
