import Foundation
import MelixControlPlaneProtocol

public struct OCRExecutionPolicy: Sendable, Equatable {
    public let promptProfileID: String
    public let promptTemplate: String
    public let autoPrompt: String
    public let stopSequences: [String]
    public let samplingProfileID: String
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?

    public init?(
        modelSettings: Melix_Controlplane_V1_ModelSettings
    ) {
        let promptProfileID = modelSettings.ext["ocr_prompt_profile_id"]?.nilIfEmpty
        let promptTemplate = modelSettings.ext["ocr_prompt_template"]?.nilIfEmpty
        let autoPrompt = modelSettings.ext["ocr_auto_prompt"]?.nilIfEmpty
        let stopSequences = Self.parseList(modelSettings.ext["ocr_stop_sequences"])
        let samplingProfileID = modelSettings.ext["ocr_sampling_profile_id"]?.nilIfEmpty
        let temperature = Self.parseDouble(modelSettings.ext["ocr_default_temperature"])
        let topP = Self.parseDouble(modelSettings.ext["ocr_default_top_p"])
        let maxTokens = Self.parseUInt32(modelSettings.ext["ocr_default_max_tokens"])

        guard promptProfileID != nil
            || promptTemplate != nil
            || autoPrompt != nil
            || samplingProfileID != nil
            || !stopSequences.isEmpty
            || temperature != nil
            || topP != nil
            || maxTokens != nil
        else {
            return nil
        }

        self.promptProfileID = promptProfileID ?? "ocr-default"
        self.promptTemplate = promptTemplate ?? "{prompt}"
        self.autoPrompt = autoPrompt ?? "Extract the text from the image exactly as written."
        self.stopSequences = stopSequences
        self.samplingProfileID = samplingProfileID ?? "ocr-default"
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
    }

    private static func parseList(_ rawValue: String?) -> [String] {
        guard let rawValue else {
            return []
        }
        return rawValue
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func parseDouble(_ rawValue: String?) -> Double? {
        guard let rawValue = rawValue?.nilIfEmpty else {
            return nil
        }
        return Double(rawValue)
    }

    private static func parseUInt32(_ rawValue: String?) -> UInt32? {
        guard let rawValue = rawValue?.nilIfEmpty else {
            return nil
        }
        return UInt32(rawValue)
    }
}

public struct ResolvedOCRExecutionPolicy: Sendable, Equatable {
    public let promptProfileID: String
    public let promptTemplate: String
    public let autoPrompt: String
    public let promptSource: String
    public let samplingProfileID: String
    public let samplingSource: String
    public let stopSequences: [String]
}

public struct TextRequestShaper: Sendable {
    private struct PresetDefaults: Sendable {
        let temperature: Double?
        let topP: Double?
        let maxTokens: UInt32?
        let saveBoundarySnapshot: Bool?
        let cachePolicy: String?
        let thinking: MelixMessagesThinkingConfig?
    }

    private struct WorkflowDefaults: Sendable {
        let lane: String
        let priority: Int32
        let latencySensitive: Bool
        let latencyClass: String
        let admissionPolicy: String
        let cachePolicy: String?
        let saveBoundarySnapshot: Bool?
    }

    private struct ResolvedThinking: Sendable {
        let config: MelixMessagesThinkingConfig?
        let mode: String
        let source: String
    }

    private let presets: [String: PresetDefaults]
    private let workflows: [TextWorkflowKind: WorkflowDefaults]
    private let modelThinkingPolicies: [String: MelixMessagesThinkingConfig]
    private let toolParserRegistry: ToolParserRegistry
    private let chatTemplatePolicyRegistry: ChatTemplatePolicyRegistry

    public init(
        presets: [String: (
            temperature: Double?,
            topP: Double?,
            maxTokens: UInt32?,
            saveBoundarySnapshot: Bool?,
            cachePolicy: String?,
            thinking: MelixMessagesThinkingConfig?
        )] = [
            "deep_reasoning": (
                0.2,
                0.95,
                512,
                true,
                "reasoning-deep",
                .init(type: "enabled", budgetTokens: 512)
            ),
            "concise": (0.4, 1.0, 128, nil, nil, .init(type: "disabled")),
        ],
        workflows: [TextWorkflowKind: (lane: String, priority: Int32, latencySensitive: Bool, latencyClass: String, admissionPolicy: String, cachePolicy: String?, saveBoundarySnapshot: Bool?)] = [
            .interactive: (
                lane: "text.decode.interactive",
                priority: 100,
                latencySensitive: true,
                latencyClass: "interactive",
                admissionPolicy: "workflow.interactive",
                cachePolicy: nil,
                saveBoundarySnapshot: nil
            ),
            .toolFollowup: (
                lane: "text.prefill.hot",
                priority: 120,
                latencySensitive: true,
                latencyClass: "interactive",
                admissionPolicy: "workflow.tool_followup",
                cachePolicy: "session-hot",
                saveBoundarySnapshot: true
            ),
            .backgroundAnalysis: (
                lane: "text.prefill.background",
                priority: 40,
                latencySensitive: false,
                latencyClass: "background",
                admissionPolicy: "workflow.background_analysis",
                cachePolicy: "background-prefill",
                saveBoundarySnapshot: false
            ),
        ],
        modelThinkingPolicies: [String: MelixMessagesThinkingConfig] = [
            "melix-dev-text": .init(type: "adaptive", budgetTokens: 192),
        ],
        toolParserRegistry: ToolParserRegistry = ToolParserRegistry(),
        chatTemplatePolicyRegistry: ChatTemplatePolicyRegistry = ChatTemplatePolicyRegistry()
    ) {
        self.presets = presets.mapValues { value in
            PresetDefaults(
                temperature: value.temperature,
                topP: value.topP,
                maxTokens: value.maxTokens,
                saveBoundarySnapshot: value.saveBoundarySnapshot,
                cachePolicy: value.cachePolicy,
                thinking: value.thinking
            )
        }
        self.workflows = workflows.mapValues { value in
            WorkflowDefaults(
                lane: value.lane,
                priority: value.priority,
                latencySensitive: value.latencySensitive,
                latencyClass: value.latencyClass,
                admissionPolicy: value.admissionPolicy,
                cachePolicy: value.cachePolicy,
                saveBoundarySnapshot: value.saveBoundarySnapshot
            )
        }
        self.modelThinkingPolicies = modelThinkingPolicies
        self.toolParserRegistry = toolParserRegistry
        self.chatTemplatePolicyRegistry = chatTemplatePolicyRegistry
    }

    public func shape(
        _ request: NormalizedTextRequest,
        modelToolParser: ToolParserSelection? = nil,
        modelChatTemplatePolicy: ModelChatTemplatePolicy? = nil,
        modelOCRPolicy: OCRExecutionPolicy? = nil
    ) -> ShapedTextRequest {
        let preset = request.presetID.flatMap { presets[$0] }
        let workflowKind = request.workflow ?? .interactive
        let workflow = workflows[workflowKind] ?? workflows[.interactive]!
        let resolvedSessionID = request.sessionID?.nilIfEmpty
        let resolvedBranchID = request.branchID?.nilIfEmpty ?? (resolvedSessionID == nil ? nil : "branch-main")
        let resolvedOCRPolicy = resolveOCRPolicy(
            request: request,
            modelPolicy: modelOCRPolicy
        )

        let temperature = request.temperature
            ?? preset?.temperature
            ?? modelOCRPolicy?.temperature
            ?? 0.7
        let topP = request.topP
            ?? preset?.topP
            ?? modelOCRPolicy?.topP
            ?? 1.0
        let maxTokens = request.maxTokens
            ?? preset?.maxTokens
            ?? modelOCRPolicy?.maxTokens
            ?? 256
        let saveBoundarySnapshot = request.saveBoundarySnapshot
            ?? preset?.saveBoundarySnapshot
            ?? workflow.saveBoundarySnapshot
            ?? (resolvedSessionID != nil)
        let cachePolicy = workflow.cachePolicy
            ?? preset?.cachePolicy
            ?? (resolvedSessionID == nil ? nil : "session-reuse")
        let resolvedThinking = resolveThinking(
            requested: request.thinking,
            preset: preset?.thinking,
            modelPolicy: modelThinkingPolicies[request.model]
        )
        let resolvedToolParser = toolParserRegistry.resolve(
            requested: request.toolParser,
            modelDefault: modelToolParser
        )
        let resolvedChatTemplate = chatTemplatePolicyRegistry.resolve(
            requested: request.chatTemplate,
            modelPolicy: modelChatTemplatePolicy
        )
        let partialMode = resolvePartialMode(
            messages: request.messages,
            chatTemplate: resolvedChatTemplate
        )

        return ShapedTextRequest(
            endpoint: request.endpoint,
            model: request.model,
            messages: request.messages,
            stream: request.stream,
            includeUsage: request.includeUsage,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            sessionID: resolvedSessionID,
            branchID: resolvedBranchID,
            parentRequestID: request.parentRequestID?.nilIfEmpty,
            restoreSnapshotID: request.restoreSnapshotID?.nilIfEmpty,
            saveBoundarySnapshot: saveBoundarySnapshot,
            presetID: request.presetID?.nilIfEmpty,
            workflow: request.workflow,
            workflowRunID: request.workflowRunID?.nilIfEmpty,
            workflowNodeID: request.workflowNodeID?.nilIfEmpty,
            latencyClass: workflow.latencyClass,
            lane: workflow.lane,
            priority: workflow.priority,
            latencySensitive: workflow.latencySensitive,
            admissionPolicy: workflow.admissionPolicy,
            cachePolicy: cachePolicy,
            stopSequences: resolvedOCRPolicy?.stopSequences ?? request.stopSequences,
            userID: request.userID?.nilIfEmpty,
            thinking: resolvedThinking.config,
            reasoningMode: resolvedThinking.mode,
            reasoningSource: resolvedThinking.source,
            structuredOutput: request.structuredOutput,
            toolParser: resolvedToolParser,
            chatTemplate: resolvedChatTemplate,
            ocrPolicy: resolvedOCRPolicy,
            partialMode: partialMode.mode,
            assistantPrefill: partialMode.assistantPrefill
        )
    }

    private func resolveOCRPolicy(
        request: NormalizedTextRequest,
        modelPolicy: OCRExecutionPolicy?
    ) -> ResolvedOCRExecutionPolicy? {
        guard let modelPolicy else {
            return nil
        }

        let hasExplicitSamplingOverride = request.temperature != nil
            || request.topP != nil
            || request.maxTokens != nil
            || !request.stopSequences.isEmpty
        let hasExplicitPrompt = request.messages.contains { message in
            message.parts.contains { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        }

        return ResolvedOCRExecutionPolicy(
            promptProfileID: modelPolicy.promptProfileID,
            promptTemplate: modelPolicy.promptTemplate,
            autoPrompt: modelPolicy.autoPrompt,
            promptSource: hasExplicitPrompt ? "request" : "model_auto_prompt",
            samplingProfileID: modelPolicy.samplingProfileID,
            samplingSource: hasExplicitSamplingOverride ? "request" : "model",
            stopSequences: request.stopSequences.isEmpty ? modelPolicy.stopSequences : request.stopSequences
        )
    }

    private func resolvePartialMode(
        messages: [NormalizedTextMessage],
        chatTemplate: ResolvedChatTemplatePolicy?
    ) -> (mode: String?, assistantPrefill: AssistantPrefillSelection?) {
        guard chatTemplate?.continueFinalMessageEnabled == true else {
            return (nil, nil)
        }

        let mode = "continue_final_message"
        guard let lastMessageIndex = messages.indices.last,
              messages[lastMessageIndex].role == "assistant"
        else {
            return (mode, nil)
        }

        return (
            mode,
            AssistantPrefillSelection(
                messageIndex: lastMessageIndex,
                messageName: messages[lastMessageIndex].name?.nilIfEmpty
            )
        )
    }

    private func resolveThinking(
        requested: MelixMessagesThinkingConfig?,
        preset: MelixMessagesThinkingConfig?,
        modelPolicy: MelixMessagesThinkingConfig?
    ) -> ResolvedThinking {
        let fallback = preset ?? modelPolicy

        if let requested {
            let normalizedType = requested.normalizedType
            if normalizedType == "disabled" {
                return ResolvedThinking(
                    config: .init(type: "disabled"),
                    mode: "off",
                    source: "request"
                )
            }

            let resolved = MelixMessagesThinkingConfig(
                type: normalizedType,
                budgetTokens: requested.budgetTokens ?? fallback?.budgetTokens
            )
            return ResolvedThinking(
                config: resolved,
                mode: resolved.reasoningMode,
                source: "request"
            )
        }

        if let preset {
            let resolved = MelixMessagesThinkingConfig(
                type: preset.normalizedType,
                budgetTokens: preset.budgetTokens
            )
            return ResolvedThinking(
                config: resolved.normalizedType == "disabled" ? .init(type: "disabled") : resolved,
                mode: resolved.reasoningMode,
                source: "preset"
            )
        }

        if let modelPolicy {
            let resolved = MelixMessagesThinkingConfig(
                type: modelPolicy.normalizedType,
                budgetTokens: modelPolicy.budgetTokens
            )
            return ResolvedThinking(
                config: resolved.normalizedType == "disabled" ? .init(type: "disabled") : resolved,
                mode: resolved.reasoningMode,
                source: "model"
            )
        }

        return ResolvedThinking(
            config: nil,
            mode: "off",
            source: "none"
        )
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
