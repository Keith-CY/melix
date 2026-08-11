import CryptoKit
import Foundation
import MelixWorkerProtocol

public enum ControlPlaneAgentAdapterError: Error, Sendable, Equatable {
    case emptyCatalog
    case duplicateToolName(String)
    case unknownTool(String)
    case invalidToolSchema(String)
    case incompleteModelTurn
    case unavailableWorker
    case invalidToolResult
}

/// Keeps the worker's execution contract digest recoverable while binding the
/// Agent model, approval receipt, and durable policy to the exact schema that
/// Melix actually projected. A projection-only change therefore cannot reuse
/// an older approval or Always Allow rule, while the worker still receives the
/// base digest it owns.
enum AgentFacingToolSchemaDigest {
    private static let prefix = "melix.agent-schema.v1:"

    static func make(
        workerSchemaDigest: String,
        projectedSchema: Data
    ) -> String {
        let encodedWorkerDigest = Data(workerSchemaDigest.utf8)
            .base64EncodedString()
        let projectionDigest = SHA256.hash(data: projectedSchema)
            .map { String(format: "%02x", $0) }
            .joined()
        return "\(prefix)\(encodedWorkerDigest):\(projectionDigest)"
    }

    static func workerSchemaDigest(from agentFacingDigest: String) -> String {
        guard agentFacingDigest.hasPrefix(prefix) else {
            return agentFacingDigest
        }
        let encodedAndProjection = agentFacingDigest.dropFirst(prefix.count)
        guard let separator = encodedAndProjection.firstIndex(of: ":"),
              separator != encodedAndProjection.startIndex,
              encodedAndProjection.index(after: separator)
                != encodedAndProjection.endIndex,
              String(encodedAndProjection[encodedAndProjection.index(
                  after: separator
              )...]).utf8.count == 64,
              encodedAndProjection[encodedAndProjection.index(
                  after: separator
              )...].allSatisfy({ character in
                  character.isHexDigit && !character.isUppercase
              }),
              let workerData = Data(
                  base64Encoded: String(encodedAndProjection[..<separator])
              ),
              let workerDigest = String(data: workerData, encoding: .utf8),
              !workerDigest.isEmpty
        else {
            // A malformed composite must never be widened into an arbitrary
            // worker digest. Returning it unchanged makes worker admission
            // reject it as a schema mismatch.
            return agentFacingDigest
        }
        return workerDigest
    }
}

public struct AgentRuntimeToolDescriptor: Sendable, Equatable {
    public let sourceID: String
    public let adapterKind: String
    public let name: String
    public let title: String
    public let description: String
    public let inputSchemaJSON: String
    public let schemaDigest: String
    public let riskClass: String
    public let annotationsUntrusted: Bool

    public init(
        sourceID: String,
        adapterKind: String,
        name: String,
        title: String,
        description: String,
        inputSchemaJSON: String,
        schemaDigest: String,
        riskClass: String,
        annotationsUntrusted: Bool = false
    ) {
        self.sourceID = sourceID
        self.adapterKind = adapterKind
        self.name = name
        self.title = title
        self.description = description
        self.inputSchemaJSON = inputSchemaJSON
        self.schemaDigest = schemaDigest
        self.riskClass = riskClass
        self.annotationsUntrusted = annotationsUntrusted
    }

    public var operatorFacingIntendedEffect: String {
        if isMCP {
            return "Run the requested MCP tool from its configured source. "
                + "Server-provided descriptions, schemas, and annotations are untrusted; "
                + "review Melix's validated redacted argument and target summary before allowing."
        }
        let normalizedDescription = description.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        if !normalizedDescription.isEmpty {
            return normalizedDescription
        }
        return "Run the requested tool."
    }

    public var operatorFacingTitle: String {
        if isMCP {
            return name
        }
        let normalizedTitle = title.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        return normalizedTitle.isEmpty ? name : normalizedTitle
    }

    private var isMCP: Bool {
        adapterKind.trimmingCharacters(
            in: .whitespacesAndNewlines
        ).lowercased() == "mcp"
    }
}

public struct AgentRuntimeToolCatalog: Sendable, Equatable {
    public let digest: String
    public let descriptors: [AgentRuntimeToolDescriptor]
    private let descriptorsByName: [String: AgentRuntimeToolDescriptor]
    private let trustedComputerUseTargets: [TrustedComputerUseTarget]?

    public init(receipt: Melix_Worker_V1_ToolCatalogReceipt) throws {
        var descriptors: [AgentRuntimeToolDescriptor] = []
        for tool in receipt.tools {
            let descriptor = AgentRuntimeToolDescriptor(
                sourceID: tool.sourceID,
                adapterKind: tool.adapterKind,
                name: tool.name,
                title: tool.title,
                description: tool.description_p,
                inputSchemaJSON: tool.inputSchemaJson,
                schemaDigest: tool.schemaDigest,
                riskClass: Self.normalizedRiskClass(tool.riskClass),
                annotationsUntrusted: tool.annotationsUntrusted
            )
            descriptors.append(descriptor)
        }
        try self.init(digest: receipt.catalogDigest, descriptors: descriptors)
    }

    public init(
        digest: String,
        descriptors: [AgentRuntimeToolDescriptor],
        trustedComputerUseTargets: [TrustedComputerUseTarget]? = nil
    ) throws {
        var byName: [String: AgentRuntimeToolDescriptor] = [:]
        var normalizedDescriptors: [AgentRuntimeToolDescriptor] = []
        for descriptor in descriptors {
            let name = descriptor.name.trimmingCharacters(in: .whitespacesAndNewlines)
            let schemaDigest = descriptor.schemaDigest.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            guard !name.isEmpty, !schemaDigest.isEmpty else {
                throw ControlPlaneAgentAdapterError.invalidToolSchema(name)
            }
            guard byName[name] == nil else {
                throw ControlPlaneAgentAdapterError.duplicateToolName(name)
            }
            guard (try? AgentToolJSONSchemaValidator(
                allowRegularExpressions: !descriptor.annotationsUntrusted
            ).validateSchemaDefinition(descriptor.inputSchemaJSON)) != nil else {
                throw ControlPlaneAgentAdapterError.invalidToolSchema(name)
            }
            let normalized = AgentRuntimeToolDescriptor(
                sourceID: descriptor.sourceID,
                adapterKind: descriptor.adapterKind,
                name: name,
                title: descriptor.title,
                description: descriptor.description,
                inputSchemaJSON: descriptor.inputSchemaJSON,
                schemaDigest: schemaDigest,
                riskClass: Self.normalizedRiskClass(descriptor.riskClass),
                annotationsUntrusted: descriptor.annotationsUntrusted
            )
            byName[name] = normalized
            normalizedDescriptors.append(normalized)
        }
        guard !normalizedDescriptors.isEmpty else {
            throw ControlPlaneAgentAdapterError.emptyCatalog
        }
        self.digest = digest.trimmingCharacters(in: .whitespacesAndNewlines)
        self.descriptors = normalizedDescriptors.sorted { $0.name < $1.name }
        self.descriptorsByName = byName
        self.trustedComputerUseTargets = trustedComputerUseTargets
    }

    public func withTrustedComputerUseTargets(
        _ targets: [TrustedComputerUseTarget]
    ) throws -> AgentRuntimeToolCatalog {
        let uniqueTargets = Array(Set(targets)).sorted { $0.targetID < $1.targetID }
        guard uniqueTargets.count == targets.count, uniqueTargets.count <= 16 else {
            throw ControlPlaneAgentAdapterError.invalidToolSchema("computer_use")
        }
        let scopedDescriptors = try descriptors.compactMap { descriptor in
            guard descriptor.sourceID == "computer",
                  descriptor.name == "computer_use" else {
                return descriptor
            }
            guard !uniqueTargets.isEmpty else {
                return nil
            }
            return try Self.operatorScopedComputerUseDescriptor(descriptor)
        }
        return try AgentRuntimeToolCatalog(
            digest: digest,
            descriptors: scopedDescriptors,
            trustedComputerUseTargets: uniqueTargets
        )
    }

    public func descriptor(named name: String) -> AgentRuntimeToolDescriptor? {
        descriptorsByName[name]
    }

    func admissionResult(for call: AgentToolCall) -> AgentToolCatalogAdmissionResult {
        guard let descriptor = descriptor(named: call.toolName) else {
            return .recoverable(.unknownTool)
        }
        guard call.schemaDigest == descriptor.schemaDigest else {
            return .terminal(.toolSchemaDigestMismatch(callID: call.callID))
        }
        do {
            try AgentToolJSONSchemaValidator(
                allowRegularExpressions: !descriptor.annotationsUntrusted
            ).validate(
                argumentsJSON: call.argumentsJSON,
                schemaJSON: descriptor.inputSchemaJSON
            )
            let canonicalArguments = try canonicalArgumentsJSON(
                call.argumentsJSON,
                descriptor: descriptor
            )
            return .admitted(
                AgentToolCall(
                    callID: call.callID,
                    sourceID: descriptor.sourceID,
                    toolName: descriptor.name,
                    title: descriptor.operatorFacingTitle,
                    intendedEffect: descriptor.operatorFacingIntendedEffect,
                    riskClass: descriptor.riskClass,
                    schemaDigest: descriptor.schemaDigest,
                    argumentsJSON: canonicalArguments
                )
            )
        } catch {
            return .recoverable(.schemaViolation)
        }
    }

    private static func normalizedRiskClass(_ rawValue: String) -> String {
        switch rawValue.trimmingCharacters(
            in: .whitespacesAndNewlines
        ).lowercased() {
        case "low", "local_read_or_compute":
            return "low"
        case "medium", "network_read":
            return "medium"
        case "high", "argument_dependent", "computer_control":
            return "high"
        case "critical":
            return "critical"
        default:
            return "unknown"
        }
    }

    public var chatToolDefinitions: [ControlPlaneChatRequest.ToolDefinition] {
        descriptors.map {
            ControlPlaneChatRequest.ToolDefinition(
                name: $0.name,
                description: $0.description,
                parametersJSON: $0.inputSchemaJSON
            )
        }
    }

    private func canonicalArgumentsJSON(
        _ argumentsJSON: String,
        descriptor: AgentRuntimeToolDescriptor
    ) throws -> String {
        guard descriptor.sourceID == "computer",
              descriptor.name == "computer_use",
              let trustedComputerUseTargets else {
            return argumentsJSON
        }
        guard let data = argumentsJSON.data(using: .utf8),
              var arguments = try JSONSerialization.jsonObject(with: data)
                as? [String: Any],
              let operation = arguments["operation"] as? String
        else {
            throw ControlPlaneAgentAdapterError.invalidToolSchema("computer_use")
        }
        switch operation {
        case "open_session":
            arguments["allowed_targets"] = trustedComputerUseTargets.map(\.jsonObject)
        case "capture_frame", "press_element":
            guard let rawTarget = arguments["target"] as? [String: Any],
                  let trustedTarget = trustedComputerUseTargets.first(where: {
                      $0.matchesAuthoritativeIdentity(rawTarget)
                  }) else {
                throw ControlPlaneAgentAdapterError.invalidToolSchema("computer_use")
            }
            arguments["target"] = trustedTarget.jsonObject
        case "get_permissions", "close_session":
            break
        default:
            throw ControlPlaneAgentAdapterError.invalidToolSchema("computer_use")
        }
        let canonical = try JSONSerialization.data(
            withJSONObject: arguments,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        guard let encoded = String(data: canonical, encoding: .utf8) else {
            throw ControlPlaneAgentAdapterError.invalidToolSchema("computer_use")
        }
        return encoded
    }

    private static func operatorScopedComputerUseDescriptor(
        _ descriptor: AgentRuntimeToolDescriptor
    ) throws -> AgentRuntimeToolDescriptor {
        guard let data = descriptor.inputSchemaJSON.data(using: .utf8),
              var schema = try JSONSerialization.jsonObject(with: data)
                as? [String: Any],
              var properties = schema["properties"] as? [String: Any],
              var operation = properties["operation"] as? [String: Any],
              let rawEnum = operation["enum"] as? [String]
        else {
            throw ControlPlaneAgentAdapterError.invalidToolSchema(descriptor.name)
        }
        properties.removeValue(forKey: "allowed_targets")
        operation["enum"] = rawEnum.filter { $0 != "list_targets" }
        properties["operation"] = operation
        let sessionID: [String: Any] = [
            "type": "string", "minLength": 1, "maxLength": 256,
        ]
        let target: [String: Any] = [
            "type": "object",
            "properties": [
                "bundle_id": [
                    "type": "string", "minLength": 1, "maxLength": 256,
                ],
                "process_id": ["type": "integer", "minimum": 1],
                "process_launch_identity": [
                    "type": "string", "minLength": 1, "maxLength": 256,
                ],
                "window_id": ["type": "integer", "minimum": 1],
                "window_title": [
                    "type": "string", "minLength": 1, "maxLength": 512,
                ],
                "application_name": [
                    "type": "string", "maxLength": 256,
                ],
            ],
            "required": [
                "bundle_id",
                "process_id",
                "process_launch_identity",
                "window_id",
                "window_title",
            ],
            "additionalProperties": false,
        ]
        let expectedPreviousGeneration: [String: Any] = [
            "type": "integer", "minimum": 0,
        ]
        let expectedObservationID: [String: Any] = [
            "type": "string", "minLength": 1, "maxLength": 256,
        ]
        let expectedFrameGeneration: [String: Any] = [
            "type": "integer", "minimum": 1,
        ]
        var element: [String: Any] = [
            "type": "object",
            "properties": [
                "handle_id": ["type": "string", "maxLength": 512],
                "title": ["type": "string", "maxLength": 512],
                "role": ["type": "string", "maxLength": 128],
            ],
            "additionalProperties": false,
        ]
        let attempt: [String: Any] = [
            "type": "integer", "minimum": 1,
        ]
        let reason: [String: Any] = [
            "type": "string", "maxLength": 256,
        ]
        properties["session_id"] = sessionID
        properties["target"] = target
        properties["expected_previous_generation"] = expectedPreviousGeneration
        properties["expected_observation_id"] = expectedObservationID
        properties["expected_frame_generation"] = expectedFrameGeneration
        properties["element"] = element
        properties["attempt"] = attempt
        properties["reason"] = reason
        element["anyOf"] = [
            [
                "properties": [
                    "handle_id": ["type": "string", "minLength": 1],
                ],
                "required": ["handle_id"],
            ],
            [
                "properties": [
                    "title": ["type": "string", "minLength": 1],
                ],
                "required": ["title"],
            ],
        ]
        let operationSchema: (String) -> [String: Any] = { name in
            ["type": "string", "const": name]
        }
        let branch: (
            String,
            [String: Any],
            [String]
        ) -> [String: Any] = { name, fields, required in
            var branchProperties = fields
            branchProperties["operation"] = operationSchema(name)
            return [
                "type": "object",
                "properties": branchProperties,
                "required": ["operation"] + required,
                "additionalProperties": false,
            ]
        }
        schema["oneOf"] = [
            branch("get_permissions", [:], []),
            branch("open_session", [:], []),
            branch(
                "capture_frame",
                [
                    "session_id": sessionID,
                    "target": target,
                    "expected_previous_generation": expectedPreviousGeneration,
                ],
                ["session_id", "target"]
            ),
            branch(
                "press_element",
                [
                    "session_id": sessionID,
                    "target": target,
                    "expected_observation_id": expectedObservationID,
                    "expected_frame_generation": expectedFrameGeneration,
                    "element": element,
                    "attempt": attempt,
                ],
                [
                    "session_id",
                    "target",
                    "expected_observation_id",
                    "expected_frame_generation",
                    "element",
                ]
            ),
            branch(
                "close_session",
                ["session_id": sessionID, "reason": reason],
                ["session_id"]
            ),
        ]
        schema["properties"] = properties
        let encoded = try JSONSerialization.data(
            withJSONObject: schema,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        guard let inputSchemaJSON = String(data: encoded, encoding: .utf8) else {
            throw ControlPlaneAgentAdapterError.invalidToolSchema(descriptor.name)
        }
        let agentFacingSchemaDigest = AgentFacingToolSchemaDigest.make(
            workerSchemaDigest: AgentFacingToolSchemaDigest.workerSchemaDigest(
                from: descriptor.schemaDigest
            ),
            projectedSchema: encoded
        )
        return AgentRuntimeToolDescriptor(
            sourceID: descriptor.sourceID,
            adapterKind: descriptor.adapterKind,
            name: descriptor.name,
            title: descriptor.title,
            description: "Use the operator-selected macOS window. For open_session, Melix injects the immutable allowed target; do not supply allowed_targets. Capture and semantic press remain bound to that selected window.",
            inputSchemaJSON: inputSchemaJSON,
            schemaDigest: agentFacingSchemaDigest,
            riskClass: descriptor.riskClass,
            annotationsUntrusted: descriptor.annotationsUntrusted
        )
    }
}

enum AgentToolCatalogAdmissionResult: Sendable, Equatable {
    case admitted(AgentToolCall)
    case recoverable(AgentToolCallAdmissionFailure)
    case terminal(AgentRunFailureReason)
}

public struct ControlPlaneAgentModelConfiguration: Sendable, Equatable {
    public let modelID: String
    public let serverSessionID: String
    public let remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let maxTokens: UInt32?

    public init(
        modelID: String,
        serverSessionID: String,
        remoteTarget: ControlPlaneChatRequest.RemoteTarget? = nil,
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        maxTokens: UInt32? = nil
    ) {
        self.modelID = modelID
        self.serverSessionID = serverSessionID
        self.remoteTarget = remoteTarget
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        self.maxTokens = maxTokens
    }
}

private actor ControlPlaneAgentModelCancellationGate {
    typealias CancellationAction = @Sendable () async
        -> ControlPlaneChatCancellationReceipt

    private let action: CancellationAction
    private var task: Task<ControlPlaneChatCancellationReceipt, Never>?

    init(action: @escaping CancellationAction) {
        self.action = action
    }

    func cancel() async -> ControlPlaneChatCancellationReceipt {
        if let task {
            return await task.value
        }
        let action = self.action
        let task = Task {
            await action()
        }
        self.task = task
        return await task.value
    }
}

public actor ControlPlaneAgentModelPort: AgentStreamingModelTurnPort {
    public typealias StartChat = @Sendable (
        ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution

    private let configuration: ControlPlaneAgentModelConfiguration
    private let catalog: AgentRuntimeToolCatalog
    private let startChat: StartChat
    private struct ActiveExecution: Sendable {
        let execution: ControlPlaneChatExecution
        let cancellation: ControlPlaneAgentModelCancellationGate
    }

    private var activeExecutions: [String: ActiveExecution] = [:]
    private var cancelledRunIDs: Set<String> = []

    public init(
        configuration: ControlPlaneAgentModelConfiguration,
        catalog: AgentRuntimeToolCatalog,
        startChat: @escaping StartChat
    ) {
        self.configuration = configuration
        self.catalog = catalog
        self.startChat = startChat
    }

    public func performTurn(
        _ request: AgentModelTurnRequest
    ) async throws -> AgentModelTurnResult {
        try await performTurn(request, onEvent: { _ in })
    }

    public func performTurn(
        _ request: AgentModelTurnRequest,
        onEvent: @escaping @Sendable (AgentModelTurnStreamEvent) async -> Void
    ) async throws -> AgentModelTurnResult {
        let execution: ControlPlaneChatExecution
        do {
            execution = try await startChat(
                ControlPlaneChatRequest(
                    modelID: configuration.modelID,
                    serverSessionID: configuration.serverSessionID,
                    messages: Self.chatMessages(from: request.messages),
                    tools: catalog.chatToolDefinitions,
                    toolChoice: "auto",
                    parallelToolCalls: false,
                    enableThinking: configuration.enableThinking,
                    reasoningEffort: configuration.reasoningEffort,
                    maxTokens: configuration.maxTokens,
                    remoteTarget: configuration.remoteTarget
                )
            )
        } catch is CancellationError {
            throw AgentPortFailure.cancelled
        } catch {
            throw AgentPortFailure.unavailable
        }

        let cancellation = ControlPlaneAgentModelCancellationGate(
            action: execution.cancel
        )
        if Task.isCancelled || cancelledRunIDs.remove(request.runID) != nil {
            _ = await cancellation.cancel()
            throw AgentPortFailure.cancelled
        }
        activeExecutions[request.runID] = ActiveExecution(
            execution: execution,
            cancellation: cancellation
        )
        defer {
            activeExecutions.removeValue(forKey: request.runID)
            cancelledRunIDs.remove(request.runID)
        }

        var streamedText = ""
        var terminalText: String?
        var finishReason: String?
        var didReceiveTerminalEvent = false
        var toolCallOrder: [String] = []
        var toolNames: [String: String] = [:]
        var argumentsByCallID: [String: String] = [:]
        let maximumAssistantBytes = 4 * 1_024 * 1_024
        let maximumReasoningBytes = 4 * 1_024 * 1_024
        let maximumToolArgumentBytes = 512 * 1_024
        let maximumTotalToolArgumentBytes = 2 * 1_024 * 1_024
        let maximumToolCallCount = 16
        var reasoningByteCount = 0
        var totalToolArgumentBytes = 0

        do {
            for try await event in execution.stream {
                try Task.checkCancellation()
                guard !didReceiveTerminalEvent else {
                    throw ControlPlaneAgentAdapterError.incompleteModelTurn
                }
                switch event {
                case .tokenDelta(let text):
                    guard text.utf8.count <= maximumAssistantBytes,
                          streamedText.utf8.count
                            <= maximumAssistantBytes - text.utf8.count
                    else {
                        throw ControlPlaneAgentAdapterError.incompleteModelTurn
                    }
                    streamedText += text
                    await onEvent(.textDelta(text))
                case .reasoningDelta(let text):
                    let fragmentBytes = text.utf8.count
                    guard fragmentBytes <= maximumReasoningBytes,
                          reasoningByteCount
                            <= maximumReasoningBytes - fragmentBytes
                    else {
                        throw ControlPlaneAgentAdapterError.incompleteModelTurn
                    }
                    reasoningByteCount += fragmentBytes
                    await onEvent(.reasoningDelta(text))
                case .toolCallDelta(let callID, let toolName, let argumentsFragment):
                    let normalizedCallID = callID.trimmingCharacters(
                        in: .whitespacesAndNewlines
                    )
                    let normalizedToolName = toolName.trimmingCharacters(
                        in: .whitespacesAndNewlines
                    )
                    guard !normalizedCallID.isEmpty, !normalizedToolName.isEmpty else {
                        throw ControlPlaneAgentAdapterError.incompleteModelTurn
                    }
                    if toolNames[normalizedCallID] == nil {
                        guard toolCallOrder.count < maximumToolCallCount else {
                            throw ControlPlaneAgentAdapterError.incompleteModelTurn
                        }
                        toolCallOrder.append(normalizedCallID)
                        toolNames[normalizedCallID] = normalizedToolName
                    } else if toolNames[normalizedCallID] != normalizedToolName {
                        throw ControlPlaneAgentAdapterError.incompleteModelTurn
                    }
                    let fragmentBytes = argumentsFragment.utf8.count
                    let currentBytes = argumentsByCallID[
                        normalizedCallID,
                        default: ""
                    ].utf8.count
                    guard fragmentBytes <= maximumToolArgumentBytes,
                          currentBytes <= maximumToolArgumentBytes - fragmentBytes,
                          totalToolArgumentBytes
                            <= maximumTotalToolArgumentBytes - fragmentBytes
                    else {
                        throw ControlPlaneAgentAdapterError.incompleteModelTurn
                    }
                    argumentsByCallID[normalizedCallID, default: ""] += argumentsFragment
                    totalToolArgumentBytes += fragmentBytes
                    await onEvent(
                        .toolCallDelta(
                            callID: normalizedCallID,
                            toolName: normalizedToolName,
                            argumentsFragment: argumentsFragment
                        )
                    )
                case .completed(let reason, let assistantText, _):
                    guard assistantText.utf8.count <= maximumAssistantBytes else {
                        throw ControlPlaneAgentAdapterError.incompleteModelTurn
                    }
                    didReceiveTerminalEvent = true
                    finishReason = reason
                    terminalText = assistantText
                case .failed:
                    throw AgentPortFailure.invalidResponse
                case .queued, .admitted, .prefillStarted, .decodeStarted,
                     .annotationDelta, .toolResultDelta,
                     .usage, .heartbeat:
                    break
                }
            }
            try Task.checkCancellation()
        } catch is CancellationError {
            _ = await cancellation.cancel()
            throw AgentPortFailure.cancelled
        } catch let failure as AgentPortFailure {
            _ = await cancellation.cancel()
            throw failure
        } catch {
            _ = await cancellation.cancel()
            throw AgentPortFailure.invalidResponse
        }

        guard let finishReason else {
            throw AgentPortFailure.invalidResponse
        }
        let fragments = try toolCallOrder.map { callID in
            guard let name = toolNames[callID] else {
                throw ControlPlaneAgentAdapterError.incompleteModelTurn
            }
            let descriptor = catalog.descriptor(named: name)
            return AgentToolCallFragment(
                callID: callID,
                sourceID: descriptor?.sourceID ?? "",
                toolName: descriptor?.name ?? name,
                title: descriptor?.operatorFacingTitle ?? "",
                intendedEffect: descriptor?.operatorFacingIntendedEffect ?? "",
                riskClass: descriptor?.riskClass ?? "unknown",
                schemaDigest: descriptor?.schemaDigest ?? "",
                argumentsFragment: argumentsByCallID[callID, default: ""],
                isComplete: true
            )
        }
        return AgentModelTurnResult(
            assistantText: terminalText?.isEmpty == false ? terminalText! : streamedText,
            toolCallFragments: fragments,
            finishReason: finishReason
        )
    }

    public func cancelTurn(runID: String) async {
        cancelledRunIDs.insert(runID)
        guard let activeExecution = activeExecutions[runID] else {
            return
        }
        _ = await activeExecution.cancellation.cancel()
    }

    private static func chatMessages(
        from messages: [AgentRunMessage]
    ) -> [ControlPlaneChatRequest.Message] {
        var result: [ControlPlaneChatRequest.Message] = []
        for message in messages {
            switch message {
            case .system(let text):
                result.append(.init(role: "system", content: text))
            case .user(let text):
                result.append(.init(role: "user", content: text))
            case .assistant(let text):
                result.append(.init(role: "assistant", content: text))
            case .assistantToolCall(let callID, let toolName, let argumentsJSON):
                let toolCall = ControlPlaneChatRequest.Message.ToolCall(
                    callID: callID,
                    toolName: toolName,
                    argumentsJSON: argumentsJSON
                )
                if let last = result.last, last.role == "assistant" {
                    result[result.count - 1] = .init(
                        role: last.role,
                        content: last.content,
                        name: last.name,
                        toolCalls: last.toolCalls + [toolCall],
                        toolCallID: last.toolCallID
                    )
                } else {
                    result.append(
                        .init(
                            role: "assistant",
                            content: "",
                            toolCalls: [toolCall]
                        )
                    )
                }
            case .toolResult(let callID, let toolName, let outputJSON):
                result.append(
                    .init(
                        role: "tool",
                        content: outputJSON,
                        name: toolName,
                        toolCallID: callID
                    )
                )
            case .guardrailNudge(let nudge):
                result.append(
                    .init(
                        role: "user",
                        content: nudge.safePrompt,
                        name: "melix_tool_guardrail"
                    )
                )
            }
        }
        return result
    }
}

public struct WorkerAgentToolExecutionContext: Sendable, Equatable {
    public let sessionID: String
    public let branchID: String
    public let actorID: String
    public let deadlineUnixMs: Int64
    public let trustedComputerUseTargets: [TrustedComputerUseTarget]
    public let computerUseAuthorizationSigner:
        ComputerUseToolAuthorizationSigner?

    public init(
        sessionID: String,
        branchID: String,
        actorID: String,
        deadlineUnixMs: Int64,
        trustedComputerUseTargets: [TrustedComputerUseTarget] = [],
        computerUseAuthorizationSigner:
            ComputerUseToolAuthorizationSigner? = nil
    ) {
        self.sessionID = sessionID
        self.branchID = branchID
        self.actorID = actorID
        self.deadlineUnixMs = deadlineUnixMs
        self.trustedComputerUseTargets = trustedComputerUseTargets
        self.computerUseAuthorizationSigner = computerUseAuthorizationSigner
    }
}

public struct WorkerAgentToolExecutionPort: AgentToolExecutionPort {
    private let worker: any AgentToolRuntimeWorkerClientProtocol
    private let context: WorkerAgentToolExecutionContext

    public init(
        worker: any AgentToolRuntimeWorkerClientProtocol,
        context: WorkerAgentToolExecutionContext
    ) {
        self.worker = worker
        self.context = context
    }

    public func execute(
        _ request: AgentToolExecutionRequest
    ) async throws -> AgentToolExecutionResult {
        var workerRequest = Melix_Worker_V1_ExecuteAgentToolRequest()
        workerRequest.context.runID = request.runID
        workerRequest.context.sessionID = context.sessionID
        workerRequest.context.branchID = context.branchID
        workerRequest.context.actorID = context.actorID
        workerRequest.context.admissionState = request.admission.kind == .allow
            ? "allow"
            : "approved"
        workerRequest.context.approvalGrantDigest = request.admission.grantDigest
        workerRequest.context.policyRevision = request.admission.binding.policyRevision
        workerRequest.context.deadlineUnixMs = context.deadlineUnixMs
        workerRequest.callID = request.call.callID
        workerRequest.toolName = request.call.toolName
        workerRequest.sourceID = request.call.sourceID
        workerRequest.argumentsJson = request.call.argumentsJSON
        workerRequest.expectedSchemaDigest =
            AgentFacingToolSchemaDigest.workerSchemaDigest(
                from: request.call.schemaDigest
            )
        workerRequest.idempotencyKey = request.admission.grantDigest
        if request.call.sourceID == "computer"
            || request.call.toolName == "computer_use"
        {
            guard let signer = context.computerUseAuthorizationSigner else {
                throw AgentPortFailure.rejected
            }
            let authorization: ControlPlaneToolAuthorization
            do {
                authorization = try signer.authorize(
                    request: request,
                    context: context
                )
            } catch {
                throw AgentPortFailure.rejected
            }
            workerRequest.context.controlPlaneAuthorizationKeyID =
                authorization.keyID
            workerRequest.context.controlPlaneAuthorizationAlgorithm =
                ControlPlaneToolAuthorization.algorithm
            workerRequest.context.controlPlaneAuthorizationPayload =
                authorization.payload
            workerRequest.context.controlPlaneAuthorizationSignature =
                authorization.signature
        }

        let stream: AsyncThrowingStream<
            Melix_Worker_V1_AgentToolExecutionEvent,
            Error
        >
        do {
            stream = try await worker.executeAgentTool(request: workerRequest)
        } catch {
            throw AgentPortFailure.unavailable
        }

        var expectedSequence: UInt64 = 1
        var streamState = 0
        var completedExecution: AgentToolExecutionResult?
        var terminalFailure: AgentPortFailure?
        do {
            for try await event in stream {
                try Task.checkCancellation()
                guard streamState < 3,
                      event.runID == request.runID,
                      event.callID == request.call.callID,
                      event.seq == expectedSequence,
                      event.emittedAtUnixMs > 0
                else {
                    throw ControlPlaneAgentAdapterError.invalidToolResult
                }
                expectedSequence += 1
                switch event.phase {
                case .agentToolExecutionCompleted:
                    guard streamState == 2,
                        case .result = event.payload,
                        event.result.runID == request.runID,
                        event.result.callID == request.call.callID,
                        event.result.sourceID == request.call.sourceID,
                        event.result.toolName == request.call.toolName,
                        event.result.status == "completed",
                        !event.result.observationJson.isEmpty,
                        event.result.observationJson.utf8.count <= 1_048_576,
                        event.result.durationMs.isFinite,
                        event.result.durationMs >= 0
                    else {
                        throw ControlPlaneAgentAdapterError.invalidToolResult
                    }
                    let evidenceReference = try Self.validatedEvidenceReference(
                        event.result.evidenceReference
                    )
                    let evidencePersistenceFailed = try Self.evidencePersistenceFailed(
                        receiptJSON: event.result.receiptJson,
                        evidenceReference: evidenceReference
                    )
                    completedExecution = AgentToolExecutionResult(
                        outputJSON: event.result.observationJson,
                        receiptJSON: event.result.receiptJson,
                        durationMs: event.result.durationMs,
                        evidenceReference: evidenceReference,
                        evidencePersistenceFailed: evidencePersistenceFailed
                    )
                    streamState = 3
                case .agentToolExecutionCancelled:
                    try Self.validateTerminalFailureEvent(
                        event,
                        request: request,
                        expectedStatus: "cancelled"
                    )
                    terminalFailure = .cancelled
                    streamState = 3
                case .agentToolExecutionTimeout:
                    try Self.validateTerminalFailureEvent(
                        event,
                        request: request,
                        expectedStatus: "timeout"
                    )
                    terminalFailure = .timedOut
                    streamState = 3
                case .agentToolExecutionFailed:
                    try Self.validateTerminalFailureEvent(
                        event,
                        request: request,
                        expectedStatus: "failed"
                    )
                    terminalFailure = .rejected
                    streamState = 3
                case .agentToolExecutionQueued:
                    guard streamState == 0, event.payload == nil else {
                        throw ControlPlaneAgentAdapterError.invalidToolResult
                    }
                    streamState = 1
                case .agentToolExecutionStarted:
                    guard streamState == 1, event.payload == nil else {
                        throw ControlPlaneAgentAdapterError.invalidToolResult
                    }
                    streamState = 2
                case .unspecified, .UNRECOGNIZED:
                    throw ControlPlaneAgentAdapterError.invalidToolResult
                }
            }
        } catch is CancellationError {
            throw AgentPortFailure.cancelled
        } catch let failure as AgentPortFailure {
            throw failure
        } catch {
            throw AgentPortFailure.invalidResponse
        }
        if let completedExecution, terminalFailure == nil, streamState == 3 {
            return completedExecution
        }
        if let terminalFailure, completedExecution == nil, streamState == 3 {
            throw terminalFailure
        }
        throw AgentPortFailure.invalidResponse
    }

    private static func validateTerminalFailureEvent(
        _ event: Melix_Worker_V1_AgentToolExecutionEvent,
        request: AgentToolExecutionRequest,
        expectedStatus: String
    ) throws {
        switch event.payload {
        case .result(let result):
            guard result.runID == request.runID,
                  result.callID == request.call.callID,
                  result.sourceID == request.call.sourceID,
                  result.toolName == request.call.toolName,
                  result.status == expectedStatus,
                  result.observationJson.utf8.count <= 1_048_576,
                  result.receiptJson.utf8.count <= 65_536,
                  result.durationMs.isFinite,
                  result.durationMs >= 0
            else {
                throw ControlPlaneAgentAdapterError.invalidToolResult
            }
        case .error(let error):
            guard !error.code.trimmingCharacters(
                in: .whitespacesAndNewlines
            ).isEmpty,
            error.message.utf8.count <= 4_096 else {
                throw ControlPlaneAgentAdapterError.invalidToolResult
            }
        case nil:
            throw ControlPlaneAgentAdapterError.invalidToolResult
        }
    }

    private static func validatedEvidenceReference(
        _ rawValue: String
    ) throws -> String {
        if rawValue.isEmpty {
            return ""
        }
        guard rawValue == rawValue.trimmingCharacters(in: .whitespacesAndNewlines),
              rawValue.utf8.count <= 1_024,
              rawValue.hasPrefix("state/agent-tool-evidence/"),
              !rawValue.hasPrefix("/"),
              rawValue.split(separator: "/", omittingEmptySubsequences: false)
                .allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." })
        else {
            throw ControlPlaneAgentAdapterError.invalidToolResult
        }
        return rawValue
    }

    private static func evidencePersistenceFailed(
        receiptJSON: String,
        evidenceReference: String
    ) throws -> Bool {
        guard !receiptJSON.isEmpty else {
            return false
        }
        guard receiptJSON.utf8.count <= 65_536,
              let data = receiptJSON.data(using: .utf8),
              let receipt = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else {
            throw ControlPlaneAgentAdapterError.invalidToolResult
        }
        guard let persisted = receipt["evidence_persisted"] as? Bool else {
            return false
        }
        guard persisted == !evidenceReference.isEmpty else {
            throw ControlPlaneAgentAdapterError.invalidToolResult
        }
        return !persisted
    }

    public func cancel(
        runID: String,
        callID: String
    ) async -> AgentToolCancellationReceipt {
        var workerRequest = Melix_Worker_V1_CancelAgentToolRequest()
        workerRequest.runID = runID
        workerRequest.callID = callID
        workerRequest.cancellationID = "agent-cancel-\(UUID().uuidString)"
        workerRequest.sessionID = context.sessionID
        workerRequest.branchID = context.branchID
        workerRequest.actorID = context.actorID
        do {
            let response = try await worker.cancelAgentTool(request: workerRequest)
            guard response.runID == workerRequest.runID,
                  response.callID == workerRequest.callID,
                  response.cancellationID == workerRequest.cancellationID,
                  let disposition = Self.disposition(response.disposition),
                  Self.deprecatedSideEffectProjectionIsConsistent(response)
            else {
                return Self.unavailableCancellation(runID: runID, callID: callID)
            }
            return AgentToolCancellationReceipt(
                runID: runID,
                callID: callID,
                disposition: disposition,
                sideEffectState: Self.sideEffectState(
                    response.sideEffectState
                )
            )
        } catch {
            return Self.unavailableCancellation(runID: runID, callID: callID)
        }
    }

    public func cancelRun(
        runID: String
    ) async -> AgentRunToolCancellationReceipt {
        var workerRequest = Melix_Worker_V1_CancelAgentRunToolsRequest()
        workerRequest.runID = runID
        workerRequest.cancellationID = "agent-run-tools-cancel-\(UUID().uuidString)"
        workerRequest.sessionID = context.sessionID
        workerRequest.branchID = context.branchID
        workerRequest.actorID = context.actorID
        do {
            let response = try await worker.cancelAgentRunTools(
                request: workerRequest
            )
            guard response.runID == workerRequest.runID,
                  response.cancellationID == workerRequest.cancellationID,
                  let disposition = Self.disposition(response.disposition),
                  let computerDisposition = Self.disposition(
                    response.computerUseDisposition
                  )
            else {
                return Self.unavailableRunCancellation(runID: runID)
            }
            let callReceipts: [AgentToolCancellationReceipt] =
                response.calls.compactMap { callResponse in
                guard callResponse.runID == runID,
                      !callResponse.callID.isEmpty,
                      let callDisposition = Self.disposition(
                        callResponse.disposition
                      ),
                      Self.deprecatedSideEffectProjectionIsConsistent(
                        callResponse
                      )
                else {
                    return nil
                }
                return AgentToolCancellationReceipt(
                    runID: runID,
                    callID: callResponse.callID,
                    disposition: callDisposition,
                    sideEffectState: Self.sideEffectState(
                        callResponse.sideEffectState
                    )
                )
                }
            guard callReceipts.count == response.calls.count else {
                return Self.unavailableRunCancellation(runID: runID)
            }
            return AgentRunToolCancellationReceipt(
                runID: runID,
                disposition: disposition,
                sideEffectState: Self.sideEffectState(
                    response.sideEffectState
                ),
                callReceipts: callReceipts,
                computerUseDisposition: computerDisposition
            )
        } catch {
            return Self.unavailableRunCancellation(runID: runID)
        }
    }

    private static func disposition(
        _ disposition: Melix_Worker_V1_ToolCancellationDisposition
    ) -> AgentCancellationDisposition? {
        switch disposition {
        case .toolCancellationAccepted:
            return .accepted
        case .toolCancellationAlreadyTerminal:
            return .alreadyTerminal
        case .toolCancellationTooLate:
            return .tooLate
        case .toolCancellationNotFound:
            return .notFound
        case .toolCancellationScopeMismatch:
            return .scopeMismatch
        case .unspecified, .UNRECOGNIZED:
            return nil
        }
    }

    private static func deprecatedSideEffectProjectionIsConsistent(
        _ response: Melix_Worker_V1_CancelAgentToolResponse
    ) -> Bool {
        switch response.sideEffectState {
        case .toolSideEffectCommitted:
            return response.sideEffectCommitted
        case .toolSideEffectNone:
            return !response.sideEffectCommitted
        case .toolSideEffectUnknown, .unspecified, .UNRECOGNIZED:
            return !response.sideEffectCommitted
        }
    }

    private static func unavailableCancellation(
        runID: String,
        callID: String
    ) -> AgentToolCancellationReceipt {
        AgentToolCancellationReceipt(
            runID: runID,
            callID: callID,
            disposition: .unavailable,
            sideEffectState: .unknown
        )
    }

    private static func unavailableRunCancellation(
        runID: String
    ) -> AgentRunToolCancellationReceipt {
        AgentRunToolCancellationReceipt(
            runID: runID,
            disposition: .unavailable,
            sideEffectState: .unknown,
            computerUseDisposition: .unavailable
        )
    }

    private static func sideEffectState(
        _ state: Melix_Worker_V1_ToolSideEffectState
    ) -> AgentToolSideEffectState {
        switch state {
        case .toolSideEffectNone:
            return .none
        case .toolSideEffectCommitted:
            return .committed
        case .toolSideEffectUnknown, .unspecified, .UNRECOGNIZED:
            return .unknown
        }
    }
}

public struct AgentRuntimeToolCatalogLoader: Sendable {
    private let worker: any AgentToolRuntimeWorkerClientProtocol
    private let sourceConfigs: [Melix_Worker_V1_AgentToolSourceConfig]

    public init(
        worker: any AgentToolRuntimeWorkerClientProtocol,
        sourceConfigs: [Melix_Worker_V1_AgentToolSourceConfig]
    ) {
        self.worker = worker
        self.sourceConfigs = sourceConfigs
    }

    public func load(
        sessionID: String,
        branchID: String,
        actorID: String,
        deadlineUnixMs: Int64,
        leaseTtlMs: UInt32,
        refreshSources: Bool = true
    ) async throws -> AgentRuntimeToolCatalog {
        var request = Melix_Worker_V1_ListAgentToolsRequest()
        request.id.requestID = "agent-catalog-\(UUID().uuidString)"
        request.id.sessionID = sessionID
        request.id.branchID = branchID
        request.ownerActorID = actorID
        request.sources = sourceConfigs
        request.refreshSources = refreshSources
        request.deadlineUnixMs = deadlineUnixMs
        request.leaseTtlMs = leaseTtlMs
        do {
            return try AgentRuntimeToolCatalog(
                receipt: try await worker.listAgentTools(request: request)
            )
        } catch let error as ControlPlaneAgentAdapterError {
            throw error
        } catch {
            throw ControlPlaneAgentAdapterError.unavailableWorker
        }
    }

    public func release(
        sessionID: String,
        branchID: String,
        actorID: String,
        deadlineUnixMs: Int64
    ) async throws {
        var request = Melix_Worker_V1_ListAgentToolsRequest()
        request.id.requestID = "agent-catalog-release-\(UUID().uuidString)"
        request.id.sessionID = sessionID
        request.id.branchID = branchID
        request.ownerActorID = actorID
        request.releaseSources = true
        request.deadlineUnixMs = deadlineUnixMs
        request.leaseTtlMs = 1
        _ = try await worker.listAgentTools(request: request)
    }
}
