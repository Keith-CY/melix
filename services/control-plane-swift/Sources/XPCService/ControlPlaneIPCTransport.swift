import Darwin
import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix
import MelixControlPlaneProtocol

public enum ControlPlaneIPCTransportError: Error, Equatable, Sendable {
    case invalidSocketPath(String)
    case unsafeSocketPath(String)
    case unavailable(String)
    case invalidMessage(String)
}

extension ControlPlaneIPCTransportError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .invalidSocketPath(message),
             let .unsafeSocketPath(message),
             let .unavailable(message),
             let .invalidMessage(message):
            message
        }
    }
}

/// Private source-tree IPC transport. Packaged builds keep the XPC contract;
/// this UDS service gives the development launcher the same daemon ownership
/// boundary without constructing a second ControlPlaneService in the app.
public final class ControlPlaneIPCGRPCProvider:
    Melix_Controlplane_V1_ControlPlaneIPCService.SimpleServiceProtocol,
    @unchecked Sendable
{
    private let service: any ControlPlaneExecuting
    private let chats = ControlPlaneIPCChatRegistry()

    public init(service: any ControlPlaneExecuting) {
        self.service = service
    }

    public func handshake(
        request: Melix_Controlplane_V1_HandshakeRequest,
        context _: ServerContext
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        try await service.handshake(request)
    }

    public func execute(
        request: Melix_Controlplane_V1_ControlPlaneRequest,
        context _: ServerContext
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        try await service.execute(request)
    }

    public func subscribe(
        request: Melix_Controlplane_V1_SubscribeRequest,
        response: RPCWriter<Melix_Controlplane_V1_ControlPlaneEvent>,
        context _: ServerContext
    ) async throws {
        let subscription = await service.subscribe(request)
        defer {
            Task {
                await self.service.unsubscribe(subscription.subscriptionID)
            }
        }
        for await event in subscription.stream {
            try Task.checkCancellation()
            try await response.write(event)
        }
    }

    public func startChat(
        request: Melix_Controlplane_V1_ControlPlaneIPCChatRequest,
        response: RPCWriter<Melix_Controlplane_V1_ControlPlaneIPCChatEvent>,
        context _: ServerContext
    ) async throws {
        let chatRequest = try Self.decodeChatRequest(request)
        let transportRequestID = request.transportRequestID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard transportRequestID.hasPrefix("ipc-chat-start-"),
              transportRequestID.utf8.count <= 256
        else {
            throw RPCError(
                code: .invalidArgument,
                message: "Chat transport request ID is invalid."
            )
        }
        let startTask = Task {
            try await service.startChat(chatRequest)
        }
        do {
            try await chats.registerPending(
                requestID: transportRequestID,
                cancel: {
                    startTask.cancel()
                    return ControlPlaneChatCancellationReceipt(
                        requestID: transportRequestID,
                        disposition: .accepted
                    )
                }
            )
        } catch {
            startTask.cancel()
            throw error
        }
        let execution: ControlPlaneChatExecution
        do {
            execution = try await startTask.value
            try await chats.promote(
                pendingRequestID: transportRequestID,
                execution: execution
            )
        } catch {
            await chats.markTerminal(requestIDs: [transportRequestID])
            throw error
        }
        let registeredRequestIDs = [transportRequestID, execution.requestID]
        do {
            var started = Melix_Controlplane_V1_ControlPlaneIPCChatEvent()
            started.started.requestID = execution.requestID
            started.started.modelID = execution.modelID
            try await response.write(started)

            var sequence: UInt64 = 0
            for try await event in execution.stream {
                try Task.checkCancellation()
                sequence += 1
                var transported = Melix_Controlplane_V1_ControlPlaneIPCChatEvent()
                transported.event = Self.encodeChatEvent(
                    event,
                    requestID: execution.requestID,
                    sequence: sequence
                )
                try await response.write(transported)
            }
            await chats.markTerminal(requestIDs: registeredRequestIDs)
        } catch {
            _ = await chats.cancel(requestID: execution.requestID)
            await chats.markTerminal(requestIDs: registeredRequestIDs)
            throw error
        }
    }

    public func cancelChat(
        request: Melix_Controlplane_V1_ControlPlaneIPCCancelChatRequest,
        context _: ServerContext
    ) async throws -> Melix_Controlplane_V1_ControlPlaneIPCCancelChatResponse {
        let trimmed = request.requestID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.utf8.count <= 256 else {
            throw RPCError(code: .invalidArgument, message: "Chat request ID must be bounded and non-empty.")
        }
        let receipt = await chats.cancel(requestID: trimmed)
        var response = Melix_Controlplane_V1_ControlPlaneIPCCancelChatResponse()
        response.requestID = trimmed
        response.disposition = Self.encodeCancellationDisposition(receipt.disposition)
        return response
    }

    public func startAgentRun(
        request: Melix_Controlplane_V1_ControlPlaneIPCStartAgentRunRequest,
        context _: ServerContext
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        let actorID = request.actorID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !actorID.isEmpty, actorID.utf8.count <= 256 else {
            throw RPCError(code: .invalidArgument, message: "Agent actor ID must be bounded and non-empty.")
        }
        return try await service.startAgentRun(
            request.command,
            actorID: actorID,
            remoteTarget: request.hasRemoteTarget
                ? Self.decodeRemoteTarget(request.remoteTarget)
                : nil
        )
    }

    static func encodeChatRequest(
        _ request: ControlPlaneChatRequest
    ) throws -> Melix_Controlplane_V1_ControlPlaneIPCChatRequest {
        var encoded = Melix_Controlplane_V1_ControlPlaneIPCChatRequest()
        encoded.modelID = request.modelID
        encoded.serverSessionID = request.serverSessionID
        encoded.messages = request.messages.map { message in
            var encodedMessage = Melix_Controlplane_V1_ControlPlaneIPCChatMessage()
            encodedMessage.role = message.role
            encodedMessage.content = message.content
            if let name = message.name {
                encodedMessage.name = name
                encodedMessage.hasName_p = true
            }
            encodedMessage.toolCalls = message.toolCalls.map { call in
                var encodedCall = Melix_Controlplane_V1_ControlPlaneIPCChatToolCall()
                encodedCall.callID = call.callID
                encodedCall.type = call.type
                encodedCall.toolName = call.toolName
                encodedCall.argumentsJson = call.argumentsJSON
                return encodedCall
            }
            if let toolCallID = message.toolCallID {
                encodedMessage.toolCallID = toolCallID
                encodedMessage.hasToolCallID_p = true
            }
            return encodedMessage
        }
        encoded.tools = request.tools.map { tool in
            var encodedTool = Melix_Controlplane_V1_ControlPlaneIPCChatToolDefinition()
            encodedTool.name = tool.name
            encodedTool.description_p = tool.description
            encodedTool.parametersJson = tool.parametersJSON
            return encodedTool
        }
        if let toolChoice = request.toolChoice {
            encoded.toolChoice = toolChoice
            encoded.hasToolChoice_p = true
        }
        encoded.parallelToolCalls = request.parallelToolCalls
        if let enableThinking = request.enableThinking {
            encoded.enableThinking = enableThinking
            encoded.hasEnableThinking_p = true
        }
        if let reasoningEffort = request.reasoningEffort {
            encoded.reasoningEffort = reasoningEffort
            encoded.hasReasoningEffort_p = true
        }
        if let chatTemplateKwargs = request.chatTemplateKwargs {
            let data = try JSONEncoder().encode(chatTemplateKwargs)
            guard let json = String(data: data, encoding: .utf8) else {
                throw ControlPlaneIPCTransportError.invalidMessage(
                    "Chat-template configuration could not be encoded as UTF-8."
                )
            }
            encoded.chatTemplateKwargsJson = json
            encoded.hasChatTemplateKwargsJson_p = true
        }
        if let resumeRequestID = request.resumeRequestID {
            encoded.resumeRequestID = resumeRequestID
            encoded.hasResumeRequestID_p = true
        }
        if let temperature = request.temperature {
            encoded.temperature = temperature
            encoded.hasTemperature_p = true
        }
        if let topP = request.topP {
            encoded.topP = topP
            encoded.hasTopP_p = true
        }
        if let maxTokens = request.maxTokens {
            encoded.maxTokens = maxTokens
            encoded.hasMaxTokens_p = true
        }
        if let remoteTarget = request.remoteTarget {
            encoded.remoteTarget = encodeRemoteTarget(remoteTarget)
        }
        return encoded
    }

    static func decodeChatRequest(
        _ request: Melix_Controlplane_V1_ControlPlaneIPCChatRequest
    ) throws -> ControlPlaneChatRequest {
        guard request.modelID.utf8.count <= 512,
              request.serverSessionID.utf8.count <= 512,
              request.messages.count <= 1_024,
              request.tools.count <= 512
        else {
            throw RPCError(code: .resourceExhausted, message: "Chat IPC request exceeds bounded cardinality.")
        }
        let chatTemplateKwargs: ChatTemplateRequestConfiguration?
        if request.hasChatTemplateKwargsJson_p {
            guard let data = request.chatTemplateKwargsJson.data(using: .utf8),
                  data.count <= 256 * 1_024
            else {
                throw RPCError(code: .resourceExhausted, message: "Chat-template IPC payload is too large.")
            }
            do {
                chatTemplateKwargs = try JSONDecoder().decode(
                    ChatTemplateRequestConfiguration.self,
                    from: data
                )
            } catch {
                throw RPCError(code: .invalidArgument, message: "Chat-template IPC payload is invalid.")
            }
        } else {
            chatTemplateKwargs = nil
        }
        return ControlPlaneChatRequest(
            modelID: request.modelID,
            serverSessionID: request.serverSessionID,
            messages: request.messages.map { message in
                ControlPlaneChatRequest.Message(
                    role: message.role,
                    content: message.content,
                    name: message.hasName_p ? message.name : nil,
                    toolCalls: message.toolCalls.map { call in
                        ControlPlaneChatRequest.Message.ToolCall(
                            callID: call.callID,
                            type: call.type,
                            toolName: call.toolName,
                            argumentsJSON: call.argumentsJson
                        )
                    },
                    toolCallID: message.hasToolCallID_p ? message.toolCallID : nil
                )
            },
            tools: request.tools.map { tool in
                ControlPlaneChatRequest.ToolDefinition(
                    name: tool.name,
                    description: tool.description_p,
                    parametersJSON: tool.parametersJson
                )
            },
            toolChoice: request.hasToolChoice_p ? request.toolChoice : nil,
            parallelToolCalls: request.parallelToolCalls,
            enableThinking: request.hasEnableThinking_p ? request.enableThinking : nil,
            reasoningEffort: request.hasReasoningEffort_p ? request.reasoningEffort : nil,
            chatTemplateKwargs: chatTemplateKwargs,
            resumeRequestID: request.hasResumeRequestID_p ? request.resumeRequestID : nil,
            temperature: request.hasTemperature_p ? request.temperature : nil,
            topP: request.hasTopP_p ? request.topP : nil,
            maxTokens: request.hasMaxTokens_p ? request.maxTokens : nil,
            remoteTarget: request.hasRemoteTarget
                ? decodeRemoteTarget(request.remoteTarget)
                : nil
        )
    }

    static func encodeRemoteTarget(
        _ target: ControlPlaneChatRequest.RemoteTarget
    ) -> Melix_Controlplane_V1_ControlPlaneIPCRemoteTarget {
        var encoded = Melix_Controlplane_V1_ControlPlaneIPCRemoteTarget()
        encoded.serverID = target.serverID
        encoded.providerKind = target.providerKind
        encoded.baseURL = target.baseURL
        encoded.apiKey = target.apiKey
        encoded.modelID = target.modelID
        encoded.timeoutSeconds = target.timeoutSeconds
        encoded.rateLimitPerMinute = target.rateLimitPerMinute
        return encoded
    }

    static func decodeRemoteTarget(
        _ target: Melix_Controlplane_V1_ControlPlaneIPCRemoteTarget
    ) -> ControlPlaneChatRequest.RemoteTarget {
        ControlPlaneChatRequest.RemoteTarget(
            serverID: target.serverID,
            providerKind: target.providerKind,
            baseURL: target.baseURL,
            apiKey: target.apiKey,
            modelID: target.modelID,
            timeoutSeconds: target.timeoutSeconds,
            rateLimitPerMinute: target.rateLimitPerMinute
        )
    }

    static func encodeChatEvent(
        _ event: ControlPlaneChatStreamEvent,
        requestID: String,
        sequence: UInt64
    ) -> Melix_Controlplane_V1_ControlPlaneIPCChatDelta {
        var encoded = Melix_Controlplane_V1_ControlPlaneIPCChatDelta()
        encoded.requestID = requestID
        encoded.seq = sequence
        switch event {
        case let .queued(lane, queuePosition, backpressure):
            encoded.kind = .controlPlaneIpcChatQueued
            encoded.lane = lane
            encoded.queuePosition = queuePosition
            encoded.backpressure = backpressure
        case let .admitted(lane, workerID, queueDelayMs):
            encoded.kind = .controlPlaneIpcChatAdmitted
            encoded.lane = lane
            encoded.workerID = workerID
            encoded.queueDelayMs = queueDelayMs
        case let .prefillStarted(inputTokens):
            encoded.kind = .controlPlaneIpcChatPrefillStarted
            encoded.inputTokens = inputTokens
        case let .decodeStarted(decodeHandle, maxOutputTokens):
            encoded.kind = .controlPlaneIpcChatDecodeStarted
            encoded.decodeHandle = decodeHandle
            encoded.maxOutputTokens = maxOutputTokens
        case let .tokenDelta(text):
            encoded.kind = .controlPlaneIpcChatToken
            encoded.text = text
        case let .reasoningDelta(text):
            encoded.kind = .controlPlaneIpcChatReasoning
            encoded.text = text
        case let .toolCallDelta(callID, toolName, argumentsFragment):
            encoded.kind = .controlPlaneIpcChatToolCall
            encoded.callID = callID
            encoded.toolName = toolName
            encoded.argumentsFragment = argumentsFragment
        case let .annotationDelta(annotationID, kind, startOffset, endOffset, payloadJSON):
            encoded.kind = .controlPlaneIpcChatAnnotation
            encoded.annotationID = annotationID
            encoded.annotationKind = kind
            encoded.startOffset = startOffset
            encoded.endOffset = endOffset
            encoded.payloadJson = payloadJSON
        case let .toolResultDelta(callID, status, resultJSON):
            encoded.kind = .controlPlaneIpcChatToolResult
            encoded.callID = callID
            encoded.status = status
            encoded.resultJson = resultJSON
        case let .usage(
            promptTokens,
            completionTokens,
            cachedPromptTokens,
            mediaFeatureCacheHits,
            mediaFeatureCacheMisses,
            mediaFeatureEncoderCallsSaved,
            mediaFeatureWorkSavedBytes
        ):
            encoded.kind = .controlPlaneIpcChatUsage
            encoded.promptTokens = promptTokens
            encoded.completionTokens = completionTokens
            encoded.cachedPromptTokens = cachedPromptTokens
            encoded.mediaFeatureCacheHits = mediaFeatureCacheHits
            encoded.mediaFeatureCacheMisses = mediaFeatureCacheMisses
            encoded.mediaFeatureEncoderCallsSaved = mediaFeatureEncoderCallsSaved
            encoded.mediaFeatureWorkSavedBytes = mediaFeatureWorkSavedBytes
        case let .completed(finishReason, assistantText, reasoningText):
            encoded.kind = .controlPlaneIpcChatCompleted
            encoded.finishReason = finishReason
            encoded.assistantText = assistantText
            encoded.reasoningText = reasoningText
        case let .failed(code, message):
            encoded.kind = .controlPlaneIpcChatFailed
            encoded.errorCode = code
            encoded.errorMessage = message
        case .heartbeat:
            encoded.kind = .controlPlaneIpcChatHeartbeat
        }
        return encoded
    }

    static func decodeChatEvent(
        _ event: Melix_Controlplane_V1_ControlPlaneIPCChatDelta
    ) throws -> ControlPlaneChatStreamEvent {
        switch event.kind {
        case .controlPlaneIpcChatQueued:
            return .queued(
                lane: event.lane,
                queuePosition: event.queuePosition,
                backpressure: event.backpressure
            )
        case .controlPlaneIpcChatAdmitted:
            return .admitted(
                lane: event.lane,
                workerID: event.workerID,
                queueDelayMs: event.queueDelayMs
            )
        case .controlPlaneIpcChatPrefillStarted:
            return .prefillStarted(inputTokens: event.inputTokens)
        case .controlPlaneIpcChatDecodeStarted:
            return .decodeStarted(
                decodeHandle: event.decodeHandle,
                maxOutputTokens: event.maxOutputTokens
            )
        case .controlPlaneIpcChatToken:
            return .tokenDelta(event.text)
        case .controlPlaneIpcChatReasoning:
            return .reasoningDelta(event.text)
        case .controlPlaneIpcChatToolCall:
            return .toolCallDelta(
                callID: event.callID,
                toolName: event.toolName,
                argumentsFragment: event.argumentsFragment
            )
        case .controlPlaneIpcChatAnnotation:
            return .annotationDelta(
                annotationID: event.annotationID,
                kind: event.annotationKind,
                startOffset: event.startOffset,
                endOffset: event.endOffset,
                payloadJSON: event.payloadJson
            )
        case .controlPlaneIpcChatToolResult:
            return .toolResultDelta(
                callID: event.callID,
                status: event.status,
                resultJSON: event.resultJson
            )
        case .controlPlaneIpcChatUsage:
            return .usage(
                promptTokens: event.promptTokens,
                completionTokens: event.completionTokens,
                cachedPromptTokens: event.cachedPromptTokens,
                mediaFeatureCacheHits: event.mediaFeatureCacheHits,
                mediaFeatureCacheMisses: event.mediaFeatureCacheMisses,
                mediaFeatureEncoderCallsSaved: event.mediaFeatureEncoderCallsSaved,
                mediaFeatureWorkSavedBytes: event.mediaFeatureWorkSavedBytes
            )
        case .controlPlaneIpcChatCompleted:
            return .completed(
                finishReason: event.finishReason,
                assistantText: event.assistantText,
                reasoningText: event.reasoningText
            )
        case .controlPlaneIpcChatFailed:
            return .failed(code: event.errorCode, message: event.errorMessage)
        case .controlPlaneIpcChatHeartbeat:
            return .heartbeat
        case .unspecified, .UNRECOGNIZED:
            throw ControlPlaneIPCTransportError.invalidMessage(
                "Chat IPC stream emitted an unknown event kind."
            )
        }
    }

    private static func encodeCancellationDisposition(
        _ disposition: ControlPlaneChatCancellationDisposition
    ) -> Melix_Controlplane_V1_ControlPlaneIPCChatCancellationDisposition {
        switch disposition {
        case .accepted: .controlPlaneIpcChatCancellationAccepted
        case .alreadyTerminal: .controlPlaneIpcChatCancellationAlreadyTerminal
        case .notFound: .controlPlaneIpcChatCancellationNotFound
        case .unavailable: .controlPlaneIpcChatCancellationUnavailable
        }
    }
}

public actor ControlPlaneIPCExecutionClient: ControlPlaneExecuting {
    private let socketPath: String
    private let startMetadataTimeout: Duration
    private var subscriptionTasks: [String: Task<Void, Never>] = [:]

    public init(
        socketPath: String,
        startMetadataTimeout: Duration = .seconds(30)
    ) {
        self.socketPath = socketPath
        self.startMetadataTimeout = startMetadataTimeout
    }

    public func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        try await unary(options: Self.options(seconds: 5)) { client in
            try await client.handshake(request, options: Self.options(seconds: 5))
        }
    }

    public func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        let options = Self.options(
            seconds: Self.remainingSeconds(deadlineUnixMs: request.deadlineUnixMs) ?? 30
        )
        let response = try await unary(options: options) { client in
            try await client.execute(request, options: options)
        }
        guard response.requestID == request.requestID,
              response.commandType == request.commandType
        else {
            throw ControlPlaneIPCTransportError.invalidMessage(
                "Control plane IPC response correlation does not match the request."
            )
        }
        return response
    }

    public func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest
    ) async -> ControlPlaneSubscription {
        let subscriptionID = "ipc-sub-\(UUID().uuidString.lowercased())"
        let socketPath = self.socketPath
        let stream = AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> { continuation in
            let task = Task {
                do {
                    try await Self.withClient(socketPath: socketPath) { client in
                        try await client.subscribe(request) { response in
                            for try await event in response.messages {
                                try Task.checkCancellation()
                                continuation.yield(event)
                            }
                        }
                    }
                } catch {
                    // Subscription reconnect is owned by RuntimeViewModel. A
                    // terminated stream is the fail-closed signal it expects.
                }
                continuation.finish()
            }
            self.installSubscriptionTask(task, id: subscriptionID)
            continuation.onTermination = { _ in
                task.cancel()
                Task {
                    await self.unsubscribe(subscriptionID)
                }
            }
        }
        return ControlPlaneSubscription(subscriptionID: subscriptionID, stream: stream)
    }

    public func unsubscribe(_ subscriptionID: String) async {
        subscriptionTasks.removeValue(forKey: subscriptionID)?.cancel()
    }

    public func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        var encodedRequest = try ControlPlaneIPCGRPCProvider.encodeChatRequest(request)
        let transportRequestID = "ipc-chat-start-\(UUID().uuidString.lowercased())"
        encodedRequest.transportRequestID = transportRequestID
        let encoded = encodedRequest
        let start = ControlPlaneIPCChatStartLatch()
        let socketPath = self.socketPath
        let preStartCancellation = ControlPlaneIPCClientChatCancellation(
            socketPath: socketPath,
            requestID: transportRequestID
        )
        let pair = AsyncThrowingStream<ControlPlaneChatStreamEvent, Error>
            .makeStream()
        let streamTask = Task {
            do {
                try await Self.withClient(socketPath: socketPath) { client in
                    try await client.startChat(encoded) { response in
                        for try await transported in response.messages {
                            switch transported.payload {
                            case let .started(metadata):
                                try await start.succeed(metadata)
                            case let .event(event):
                                guard await start.hasStarted() else {
                                    throw ControlPlaneIPCTransportError.invalidMessage(
                                        "Chat stream emitted data before start metadata."
                                    )
                                }
                                pair.continuation.yield(
                                    try ControlPlaneIPCGRPCProvider.decodeChatEvent(event)
                                )
                            case nil:
                                throw ControlPlaneIPCTransportError.invalidMessage(
                                    "Chat stream emitted an empty event."
                                )
                            }
                        }
                    }
                }
                await start.failIfPending(
                    ControlPlaneIPCTransportError.unavailable(
                        "Chat stream ended before start metadata."
                    )
                )
                pair.continuation.finish()
            } catch {
                await start.failIfPending(error)
                pair.continuation.finish(throwing: error)
            }
        }
        pair.continuation.onTermination = { _ in
            streamTask.cancel()
        }
        let timeout = startMetadataTimeout
        let timeoutTask = Task {
            do {
                try await Task.sleep(for: timeout)
            } catch {
                return
            }
            let didTimeout = await start.beginFailure(
                ControlPlaneIPCTransportError.unavailable(
                    "Chat did not return start metadata before the IPC deadline."
                )
            )
            guard didTimeout else { return }
            _ = await preStartCancellation.cancel()
            await start.completeFailure()
            streamTask.cancel()
        }
        let metadata: Melix_Controlplane_V1_ControlPlaneIPCChatStarted
        do {
            metadata = try await withTaskCancellationHandler {
                try await start.wait()
            } onCancel: {
                Task { _ = await preStartCancellation.cancel() }
                streamTask.cancel()
                timeoutTask.cancel()
                Task {
                    await start.failIfPending(CancellationError())
                }
            }
        } catch {
            timeoutTask.cancel()
            streamTask.cancel()
            pair.continuation.finish(throwing: error)
            throw error
        }
        timeoutTask.cancel()
        let cancellation = ControlPlaneIPCClientChatCancellation(
            socketPath: socketPath,
            requestID: metadata.requestID
        )
        return ControlPlaneChatExecution(
            requestID: metadata.requestID,
            modelID: metadata.modelID,
            stream: pair.stream,
            cancel: {
                await cancellation.cancel()
            }
        )
    }

    public func startAgentRun(
        _ command: Melix_Controlplane_V1_StartAgentRun,
        actorID: String,
        remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        var request = Melix_Controlplane_V1_ControlPlaneIPCStartAgentRunRequest()
        request.command = command
        request.actorID = actorID
        if let remoteTarget {
            request.remoteTarget = ControlPlaneIPCGRPCProvider.encodeRemoteTarget(remoteTarget)
        }
        let rpcRequest = request
        let seconds = Self.remainingSeconds(deadlineUnixMs: command.deadlineUnixMs) ?? 30
        let options = Self.options(seconds: seconds)
        return try await unary(options: options) { client in
            try await client.startAgentRun(rpcRequest, options: options)
        }
    }

    private func installSubscriptionTask(_ task: Task<Void, Never>, id: String) {
        subscriptionTasks[id]?.cancel()
        subscriptionTasks[id] = task
    }

    private func unary<Result: Sendable>(
        options _: CallOptions,
        operation: @Sendable @escaping (
            Melix_Controlplane_V1_ControlPlaneIPCService.Client<HTTP2ClientTransport.Posix>
        ) async throws -> Result
    ) async throws -> Result {
        try await Self.withClient(socketPath: socketPath, operation: operation)
    }

    fileprivate static func withClient<Result: Sendable>(
        socketPath: String,
        operation: @Sendable @escaping (
            Melix_Controlplane_V1_ControlPlaneIPCService.Client<HTTP2ClientTransport.Posix>
        ) async throws -> Result
    ) async throws -> Result {
        let socket = try ControlPlaneIPCSocket(path: socketPath)
        try socket.validateForConnection()
        do {
            return try await withGRPCClient(
                transport: .http2NIOPosix(
                    target: .unixDomainSocket(path: socket.path),
                    transportSecurity: .plaintext
                )
            ) { client in
                try await operation(
                    Melix_Controlplane_V1_ControlPlaneIPCService.Client(wrapping: client)
                )
            }
        } catch let error as ControlPlaneIPCTransportError {
            throw error
        } catch {
            throw ControlPlaneIPCTransportError.unavailable(
                "Control plane IPC failed: \(error.localizedDescription)"
            )
        }
    }

    private static func options(seconds: Int) -> CallOptions {
        var options = CallOptions.defaults
        options.timeout = .seconds(max(seconds, 1))
        return options
    }

    private static func remainingSeconds(deadlineUnixMs: Int64) -> Int? {
        guard deadlineUnixMs > 0 else { return nil }
        let remainingMilliseconds = deadlineUnixMs
            - Int64(Date().timeIntervalSince1970 * 1_000)
        guard remainingMilliseconds > 0 else { return 1 }
        return max(Int((remainingMilliseconds + 999) / 1_000), 1)
    }
}

public actor ControlPlaneIPCUDSServer {
    public nonisolated let socketPath: String

    private let socket: ControlPlaneIPCSocket
    private let server: GRPCServer<HTTP2ServerTransport.Posix>
    private var serveTask: Task<Void, Error>?

    public init(
        socketPath: String,
        service: any RegistrableRPCService
    ) throws {
        let socket = try ControlPlaneIPCSocket(path: socketPath)
        self.socketPath = socket.path
        self.socket = socket
        self.server = GRPCServer(
            transport: .http2NIOPosix(
                address: .unixDomainSocket(path: socket.path),
                transportSecurity: .plaintext
            ),
            services: [service]
        )
    }

    public func start() async throws {
        guard serveTask == nil else {
            throw ControlPlaneIPCTransportError.unavailable(
                "Control plane IPC server is already running."
            )
        }
        try socket.prepareForBinding()
        let server = self.server
        let task = Task { try await server.serve() }
        serveTask = task
        do {
            _ = try await server.listeningAddress
            try socket.sealBoundSocket()
        } catch {
            try? socket.stageReplacementForServerShutdown()
            server.beginGracefulShutdown()
            _ = try? await task.value
            try? socket.restoreReplacementAfterServerShutdown()
            serveTask = nil
            try? socket.removeOwnedSocket()
            throw error
        }
    }

    public func wait() async throws {
        guard let serveTask else {
            throw ControlPlaneIPCTransportError.unavailable(
                "Control plane IPC server has not started."
            )
        }
        defer {
            self.serveTask = nil
            try? socket.removeOwnedSocket()
        }
        try await serveTask.value
    }

    public func stop() async {
        guard let serveTask else {
            try? socket.removeOwnedSocket()
            return
        }
        do {
            try socket.stageReplacementForServerShutdown()
        } catch {
            return
        }
        server.beginGracefulShutdown()
        _ = try? await serveTask.value
        try? socket.restoreReplacementAfterServerShutdown()
        self.serveTask = nil
        try? socket.removeOwnedSocket()
    }
}

private actor ControlPlaneIPCChatRegistry {
    typealias Cancel = @Sendable () async -> ControlPlaneChatCancellationReceipt

    private struct ActiveRegistration: Sendable {
        let groupID: String
        let requestIDs: Set<String>
        let cancel: Cancel
    }

    private struct CancellingRegistration: Sendable {
        let groupID: String
        let requestIDs: Set<String>
        let cancel: Cancel
        let task: Task<ControlPlaneChatCancellationReceipt, Never>
    }

    private var active: [String: ActiveRegistration] = [:]
    private var cancelling: [String: CancellingRegistration] = [:]
    private var terminal: [String] = []
    private let terminalLimit = 1_024

    func registerPending(
        requestID: String,
        cancel: @escaping Cancel
    ) async throws {
        guard active[requestID] == nil, cancelling[requestID] == nil else {
            throw RPCError(code: .alreadyExists, message: "Chat request ID is already registered.")
        }
        if terminal.contains(requestID) {
            _ = await cancel()
            throw CancellationError()
        }
        active[requestID] = ActiveRegistration(
            groupID: requestID,
            requestIDs: [requestID],
            cancel: cancel
        )
    }

    func promote(
        pendingRequestID: String,
        execution: ControlPlaneChatExecution
    ) async throws {
        let executionRequestID = execution.requestID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard let pending = active[pendingRequestID],
              !executionRequestID.isEmpty,
              executionRequestID.utf8.count <= 256,
              executionRequestID == pendingRequestID
                || (active[executionRequestID] == nil
                    && cancelling[executionRequestID] == nil),
              !terminal.contains(executionRequestID)
        else {
            _ = await execution.cancel()
            throw RPCError(code: .alreadyExists, message: "Chat request ID is already registered.")
        }
        let requestIDs: Set<String> = [pendingRequestID, executionRequestID]
        let promoted = ActiveRegistration(
            groupID: pending.groupID,
            requestIDs: requestIDs,
            cancel: execution.cancel
        )
        for requestID in requestIDs {
            active[requestID] = promoted
        }
    }

    func cancel(requestID: String) async -> ControlPlaneChatCancellationReceipt {
        if let inFlight = cancelling[requestID] {
            let receipt = await inFlight.task.value
            resolveCancellation(inFlight, receipt: receipt)
            return receipt
        }
        if let registration = active[requestID] {
            for registeredRequestID in registration.requestIDs {
                active.removeValue(forKey: registeredRequestID)
            }
            let task = Task { await registration.cancel() }
            let inFlight = CancellingRegistration(
                groupID: registration.groupID,
                requestIDs: registration.requestIDs,
                cancel: registration.cancel,
                task: task
            )
            for registeredRequestID in registration.requestIDs {
                cancelling[registeredRequestID] = inFlight
            }
            let receipt = await task.value
            resolveCancellation(inFlight, receipt: receipt)
            return receipt
        }
        if requestID.hasPrefix("ipc-chat-start-") {
            markTerminal(requestIDs: [requestID])
            return ControlPlaneChatCancellationReceipt(
                requestID: requestID,
                disposition: .accepted
            )
        }
        return ControlPlaneChatCancellationReceipt(
            requestID: requestID,
            disposition: terminal.contains(requestID) ? .alreadyTerminal : .notFound
        )
    }

    func markTerminal(requestIDs: [String]) {
        var relatedRequestIDs = Set(requestIDs)
        for requestID in requestIDs {
            if let registration = active[requestID] {
                relatedRequestIDs.formUnion(registration.requestIDs)
            }
            if let registration = cancelling[requestID] {
                relatedRequestIDs.formUnion(registration.requestIDs)
            }
        }
        for requestID in relatedRequestIDs {
            active.removeValue(forKey: requestID)
            cancelling.removeValue(forKey: requestID)
        }
        appendTerminal(relatedRequestIDs)
    }

    private func resolveCancellation(
        _ registration: CancellingRegistration,
        receipt: ControlPlaneChatCancellationReceipt
    ) {
        let stillInFlight = registration.requestIDs.contains { requestID in
            cancelling[requestID]?.groupID == registration.groupID
        }
        guard stillInFlight else { return }
        for requestID in registration.requestIDs {
            guard cancelling[requestID]?.groupID == registration.groupID else { continue }
            cancelling.removeValue(forKey: requestID)
        }
        if receipt.disposition == .unavailable {
            let restored = ActiveRegistration(
                groupID: registration.groupID,
                requestIDs: registration.requestIDs,
                cancel: registration.cancel
            )
            for requestID in registration.requestIDs where !terminal.contains(requestID) {
                active[requestID] = restored
            }
            return
        }
        appendTerminal(registration.requestIDs)
    }

    private func appendTerminal(_ requestIDs: Set<String>) {
        for requestID in requestIDs {
            terminal.removeAll { $0 == requestID }
            terminal.append(requestID)
        }
        if terminal.count > terminalLimit {
            terminal.removeFirst(terminal.count - terminalLimit)
        }
    }
}

private actor ControlPlaneIPCChatStartLatch {
    typealias Metadata = Melix_Controlplane_V1_ControlPlaneIPCChatStarted
    private enum State {
        case pending([CheckedContinuation<Metadata, Error>])
        case failing(Error, [CheckedContinuation<Metadata, Error>])
        case started(Metadata)
        case failed(Error)
    }

    private var state: State = .pending([])

    func wait() async throws -> Metadata {
        switch state {
        case let .started(metadata): return metadata
        case let .failed(error): throw error
        case .pending, .failing:
            return try await withCheckedThrowingContinuation { continuation in
                switch state {
                case var .pending(waiters):
                    waiters.append(continuation)
                    state = .pending(waiters)
                case let .failing(error, existingWaiters):
                    var waiters = existingWaiters
                    waiters.append(continuation)
                    state = .failing(error, waiters)
                case let .started(metadata):
                    continuation.resume(returning: metadata)
                case let .failed(error):
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    func succeed(_ metadata: Metadata) throws {
        guard !metadata.requestID.isEmpty, !metadata.modelID.isEmpty else {
            throw ControlPlaneIPCTransportError.invalidMessage(
                "Chat start metadata is incomplete."
            )
        }
        switch state {
        case let .pending(waiters):
            state = .started(metadata)
            for waiter in waiters { waiter.resume(returning: metadata) }
        case let .started(existing):
            guard existing == metadata else {
                throw ControlPlaneIPCTransportError.invalidMessage(
                    "Chat stream changed its start metadata."
                )
            }
        case .failing, .failed:
            break
        }
    }

    func hasStarted() -> Bool {
        if case .started = state { return true }
        return false
    }

    @discardableResult
    func failIfPending(_ error: Error) -> Bool {
        guard beginFailure(error) else { return false }
        completeFailure()
        return true
    }

    func beginFailure(_ error: Error) -> Bool {
        guard case let .pending(waiters) = state else { return false }
        state = .failing(error, waiters)
        return true
    }

    func completeFailure() {
        guard case let .failing(error, waiters) = state else { return }
        state = .failed(error)
        for waiter in waiters { waiter.resume(throwing: error) }
    }
}

private actor ControlPlaneIPCClientChatCancellation {
    private let socketPath: String
    private let requestID: String
    private var cached: ControlPlaneChatCancellationReceipt?

    init(socketPath: String, requestID: String) {
        self.socketPath = socketPath
        self.requestID = requestID
    }

    func cancel() async -> ControlPlaneChatCancellationReceipt {
        if let cached { return cached }
        var request = Melix_Controlplane_V1_ControlPlaneIPCCancelChatRequest()
        request.requestID = requestID
        let rpcRequest = request
        do {
            let response = try await ControlPlaneIPCExecutionClient.withClient(
                socketPath: socketPath
            ) { client in
                var options = CallOptions.defaults
                options.timeout = .seconds(3)
                return try await client.cancelChat(rpcRequest, options: options)
            }
            let disposition: ControlPlaneChatCancellationDisposition
            switch response.disposition {
            case .controlPlaneIpcChatCancellationAccepted: disposition = .accepted
            case .controlPlaneIpcChatCancellationAlreadyTerminal: disposition = .alreadyTerminal
            case .controlPlaneIpcChatCancellationNotFound: disposition = .notFound
            case .controlPlaneIpcChatCancellationUnavailable,
                 .unspecified,
                 .UNRECOGNIZED:
                disposition = .unavailable
            }
            let receipt = ControlPlaneChatCancellationReceipt(
                requestID: requestID,
                disposition: disposition
            )
            if disposition != .unavailable {
                cached = receipt
            }
            return receipt
        } catch {
            return ControlPlaneChatCancellationReceipt(
                requestID: requestID,
                disposition: .unavailable
            )
        }
    }
}

private final class ControlPlaneIPCSocket: @unchecked Sendable {
    let path: String

    private let stateLock = NSLock()
    private var leaseDescriptor: Int32?
    private var boundIdentity: ControlPlaneIPCSocketIdentity?
    private var stagedReplacementPath: String?

    init(path: String) throws {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        let standardized = URL(fileURLWithPath: trimmed).standardizedFileURL.path
        guard trimmed.hasPrefix("/"), trimmed == standardized,
              trimmed != "/", trimmed.utf8.count <= 103
        else {
            throw ControlPlaneIPCTransportError.invalidSocketPath(
                "Control plane IPC socket path must be absolute, standardized, and fit sockaddr_un."
            )
        }
        self.path = trimmed
    }

    func prepareForBinding() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard leaseDescriptor == nil, boundIdentity == nil else {
            throw ControlPlaneIPCTransportError.unavailable(
                "Control plane IPC socket lifecycle is already active."
            )
        }
        let parent = URL(fileURLWithPath: path).deletingLastPathComponent()
        try FileManager.default.createDirectory(
            at: parent,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        let parentStatus = try status(parent.path)
        guard fileType(parentStatus) == S_IFDIR,
              parentStatus.st_uid == geteuid(),
              parentStatus.st_mode & 0o077 == 0
        else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC parent must be a private current-user directory."
            )
        }
        let descriptor = try acquireControlPlaneIPCSocketLease(
            lockPath: path + ".lock"
        )
        do {
            if let existing = try optionalStatus(path) {
                guard fileType(existing) == S_IFSOCK,
                      existing.st_uid == geteuid(),
                      existing.st_mode & 0o077 == 0
                else {
                    throw ControlPlaneIPCTransportError.unsafeSocketPath(
                        "Control plane IPC refuses to replace an unsafe socket path."
                    )
                }
                let existingIdentity = ControlPlaneIPCSocketIdentity(existing)
                if try controlPlaneIPCSocketIsLive(path: path) {
                    throw ControlPlaneIPCTransportError.unavailable(
                        "Another control plane IPC server is already listening on this socket."
                    )
                }
                if let current = try optionalStatus(path) {
                    guard ControlPlaneIPCSocketIdentity(current) == existingIdentity else {
                        throw ControlPlaneIPCTransportError.unavailable(
                            "Control plane IPC socket changed during stale-endpoint recovery."
                        )
                    }
                    guard unlink(path) == 0 else {
                        throw posixIPCError("Could not remove stale control plane IPC socket")
                    }
                }
            }
            leaseDescriptor = descriptor
        } catch {
            _ = Darwin.close(descriptor)
            throw error
        }
    }

    func sealBoundSocket() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard leaseDescriptor != nil else {
            throw ControlPlaneIPCTransportError.unavailable(
                "Control plane IPC socket lifecycle lease is unavailable."
            )
        }
        let current = try status(path)
        guard fileType(current) == S_IFSOCK, current.st_uid == geteuid() else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC transport did not create a current-user socket."
            )
        }
        guard chmod(path, 0o600) == 0 else {
            throw posixIPCError("Could not secure control plane IPC socket permissions")
        }
        let sealed = try status(path)
        guard ControlPlaneIPCSocketIdentity(sealed) == ControlPlaneIPCSocketIdentity(current),
              sealed.st_uid == geteuid(),
              sealed.st_mode & 0o077 == 0
        else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC socket changed or remained unsafe while sealing."
            )
        }
        boundIdentity = ControlPlaneIPCSocketIdentity(sealed)
    }

    func validateForConnection() throws {
        let parentPath = URL(fileURLWithPath: path)
            .deletingLastPathComponent()
            .path
        let parent = try status(parentPath)
        guard fileType(parent) == S_IFDIR,
              parent.st_uid == geteuid(),
              parent.st_mode & 0o077 == 0
        else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC parent must be private and owned by the current user."
            )
        }
        let socket = try status(path)
        guard fileType(socket) == S_IFSOCK,
              socket.st_uid == geteuid(),
              socket.st_mode & 0o077 == 0
        else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC endpoint must be a private current-user socket."
            )
        }
    }

    func removeOwnedSocket() throws {
        stateLock.lock()
        let descriptor = leaseDescriptor
        let ownedIdentity = boundIdentity
        leaseDescriptor = nil
        boundIdentity = nil
        defer {
            if let descriptor {
                _ = Darwin.close(descriptor)
            }
            stateLock.unlock()
        }
        guard descriptor != nil || ownedIdentity != nil else { return }
        guard let current = try optionalStatus(path) else { return }
        guard let ownedIdentity,
              ControlPlaneIPCSocketIdentity(current) == ownedIdentity
        else {
            return
        }
        guard fileType(current) == S_IFSOCK, current.st_uid == geteuid() else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC cleanup found its recorded inode with an unsafe type or owner."
            )
        }
        guard unlink(path) == 0 else {
            throw posixIPCError("Could not remove control plane IPC socket")
        }
    }

    func stageReplacementForServerShutdown() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard stagedReplacementPath == nil,
              let boundIdentity,
              let current = try optionalStatus(path),
              ControlPlaneIPCSocketIdentity(current) != boundIdentity
        else {
            return
        }
        let stagedPath = path + ".preserved-" + UUID().uuidString.lowercased()
        guard renamex_np(path, stagedPath, UInt32(RENAME_EXCL)) == 0 else {
            throw posixIPCError(
                "Could not preserve a replacement control plane IPC socket before shutdown"
            )
        }
        stagedReplacementPath = stagedPath
    }

    func restoreReplacementAfterServerShutdown() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard let stagedPath = stagedReplacementPath else { return }
        guard try optionalStatus(path) == nil else {
            throw ControlPlaneIPCTransportError.unavailable(
                "Control plane IPC socket path was occupied while restoring a preserved replacement."
            )
        }
        guard renamex_np(stagedPath, path, UInt32(RENAME_EXCL)) == 0 else {
            throw posixIPCError(
                "Could not restore the preserved replacement control plane IPC socket"
            )
        }
        stagedReplacementPath = nil
    }

    deinit {
        try? restoreReplacementAfterServerShutdown()
        try? removeOwnedSocket()
    }
}

private func optionalStatus(_ path: String) throws -> stat? {
    var value = stat()
    if lstat(path, &value) == 0 { return value }
    if errno == ENOENT { return nil }
    throw posixIPCError("Could not inspect control plane IPC path")
}

private func status(_ path: String) throws -> stat {
    guard let value = try optionalStatus(path) else {
        throw ControlPlaneIPCTransportError.invalidSocketPath(
            "Required control plane IPC path does not exist: \(path)"
        )
    }
    return value
}

private func fileType(_ value: stat) -> mode_t {
    value.st_mode & mode_t(S_IFMT)
}

private struct ControlPlaneIPCSocketIdentity: Sendable, Equatable {
    let device: dev_t
    let inode: ino_t
    let generation: UInt32
    let birthSeconds: Int
    let birthNanoseconds: Int

    init(_ value: stat) {
        device = value.st_dev
        inode = value.st_ino
        generation = value.st_gen
        birthSeconds = value.st_birthtimespec.tv_sec
        birthNanoseconds = value.st_birthtimespec.tv_nsec
    }
}

private func acquireControlPlaneIPCSocketLease(lockPath: String) throws -> Int32 {
    let descriptor = lockPath.withCString { path in
        Darwin.open(
            path,
            O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW | O_EXLOCK | O_NONBLOCK,
            mode_t(S_IRUSR | S_IWUSR)
        )
    }
    guard descriptor >= 0 else {
        let code = errno
        if code == EWOULDBLOCK || code == EAGAIN {
            throw ControlPlaneIPCTransportError.unavailable(
                "Another control plane IPC server owns the socket lifecycle lease."
            )
        }
        throw posixIPCError(
            "Could not acquire the control plane IPC socket lifecycle lease",
            code: code
        )
    }
    do {
        var lockStatus = stat()
        guard fstat(descriptor, &lockStatus) == 0 else {
            throw posixIPCError("Could not inspect the control plane IPC socket lifecycle lease")
        }
        guard fileType(lockStatus) == S_IFREG,
              lockStatus.st_uid == geteuid()
        else {
            throw ControlPlaneIPCTransportError.unsafeSocketPath(
                "Control plane IPC socket lifecycle lease must be a current-user regular file."
            )
        }
        guard fchmod(descriptor, mode_t(S_IRUSR | S_IWUSR)) == 0 else {
            throw posixIPCError("Could not secure the control plane IPC socket lifecycle lease")
        }
        return descriptor
    } catch {
        _ = Darwin.close(descriptor)
        throw error
    }
}

private func controlPlaneIPCSocketIsLive(path: String) throws -> Bool {
    let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard descriptor >= 0 else {
        throw posixIPCError("Could not create a control plane IPC socket liveness probe")
    }
    defer { _ = Darwin.close(descriptor) }
    guard Darwin.fcntl(descriptor, F_SETFD, FD_CLOEXEC) == 0 else {
        throw posixIPCError("Could not secure the control plane IPC socket liveness probe")
    }
    let statusFlags = Darwin.fcntl(descriptor, F_GETFL)
    guard statusFlags >= 0,
          Darwin.fcntl(descriptor, F_SETFL, statusFlags | O_NONBLOCK) == 0
    else {
        throw posixIPCError("Could not bound the control plane IPC socket liveness probe")
    }

    var address = sockaddr_un()
    address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    address.sun_family = sa_family_t(AF_UNIX)
    let pathCapacity = MemoryLayout.size(ofValue: address.sun_path)
    path.withCString { source in
        withUnsafeMutablePointer(to: &address.sun_path) { destination in
            destination.withMemoryRebound(to: CChar.self, capacity: pathCapacity) { bytes in
                _ = strlcpy(bytes, source, pathCapacity)
            }
        }
    }
    let result = withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
            Darwin.connect(
                descriptor,
                socketAddress,
                socklen_t(MemoryLayout<sockaddr_un>.size)
            )
        }
    }
    if result == 0 {
        return true
    }
    let code = errno
    if code == ECONNREFUSED || code == ENOENT {
        return false
    }
    if code == EINPROGRESS || code == EALREADY
        || code == EAGAIN || code == EWOULDBLOCK
    {
        return true
    }
    throw posixIPCError(
        "Could not prove that the control plane IPC socket is stale",
        code: code
    )
}

private func posixIPCError(
    _ operation: String,
    code: Int32 = errno
) -> ControlPlaneIPCTransportError {
    .unsafeSocketPath("\(operation): \(String(cString: strerror(code)))")
}
