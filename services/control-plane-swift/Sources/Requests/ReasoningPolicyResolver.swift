import Foundation
import OSLog

public struct ResolvedReasoningPolicy: Sendable, Equatable {
    public let config: MelixMessagesThinkingConfig?
    public let mode: String
    public let modeSource: String
    public let effort: String?
    public let autoDetectModelFamily: String?
    public let continuityRehydrated: Bool

    public init(
        config: MelixMessagesThinkingConfig?,
        mode: String,
        modeSource: String,
        effort: String? = nil,
        autoDetectModelFamily: String? = nil,
        continuityRehydrated: Bool = false
    ) {
        self.config = config
        self.mode = mode
        self.modeSource = modeSource
        self.effort = Self.normalized(effort)
        self.autoDetectModelFamily = Self.normalized(autoDetectModelFamily)
        self.continuityRehydrated = continuityRehydrated
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed.lowercased()
    }
}

public struct ReasoningPolicyResolver: Sendable {
    private let logger = Logger(
        subsystem: "Melix.ControlPlane",
        category: "ReasoningPolicyResolver"
    )

    public init() {}

    public func resolve(
        modelID: String,
        explicitEnableThinking: Bool?,
        explicitEffort: String?,
        templatePolicy: ResolvedChatTemplatePolicy?,
        messagesThinking: MelixMessagesThinkingConfig?,
        preset: MelixMessagesThinkingConfig?,
        modelDefault: MelixMessagesThinkingConfig?,
        suppressForStructuredOutput: Bool = false
    ) -> ResolvedReasoningPolicy {
        let fallback = preset ?? modelDefault
        let normalizedEffort = normalizedString(explicitEffort)

        if let explicitEnableThinking {
            return resolvedFromEnableThinking(
                explicitEnableThinking,
                source: "request",
                effort: normalizedEffort,
                fallback: fallback
            )
        }

        if let templateEnableThinking = boolValue(templatePolicy?.effectiveValues["enable_thinking"]) {
            return resolvedFromEnableThinking(
                templateEnableThinking,
                source: "template",
                effort: normalizedEffort ?? stringValue(templatePolicy?.effectiveValues["reasoning_effort"]),
                fallback: fallback
            )
        }

        if let messagesThinking {
            return resolvedFromThinkingConfig(
                messagesThinking,
                source: "request",
                effort: normalizedEffort,
                fallback: fallback
            )
        }

        if let preset {
            return resolvedFromThinkingConfig(
                preset,
                source: "preset",
                effort: normalizedEffort,
                fallback: preset
            )
        }

        if let modelDefault {
            return resolvedFromThinkingConfig(
                modelDefault,
                source: "model",
                effort: normalizedEffort,
                fallback: modelDefault
            )
        }

        if let family = autoDetectedFamily(modelID: modelID) {
            return ResolvedReasoningPolicy(
                config: .init(type: "adaptive"),
                mode: "adaptive",
                modeSource: "family_auto_detect",
                effort: normalizedEffort,
                autoDetectModelFamily: family,
                continuityRehydrated: false
            )
        }

        if suppressForStructuredOutput {
            return ResolvedReasoningPolicy(
                config: .init(type: "disabled"),
                mode: "off",
                modeSource: "structured_output_suppression",
                effort: normalizedEffort,
                continuityRehydrated: false
            )
        }

        return ResolvedReasoningPolicy(
            config: nil,
            mode: "off",
            modeSource: "none",
            effort: normalizedEffort,
            continuityRehydrated: false
        )
    }

    private func resolvedFromEnableThinking(
        _ enabled: Bool,
        source: String,
        effort: String?,
        fallback: MelixMessagesThinkingConfig?
    ) -> ResolvedReasoningPolicy {
        guard enabled else {
            return ResolvedReasoningPolicy(
                config: .init(type: "disabled"),
                mode: "off",
                modeSource: source,
                effort: effort,
                continuityRehydrated: false
            )
        }

        let config = MelixMessagesThinkingConfig(
            type: "enabled",
            budgetTokens: fallback?.budgetTokens
        )
        return ResolvedReasoningPolicy(
            config: config,
            mode: config.reasoningMode,
            modeSource: source,
            effort: effort,
            continuityRehydrated: false
        )
    }

    private func resolvedFromThinkingConfig(
        _ requested: MelixMessagesThinkingConfig,
        source: String,
        effort: String?,
        fallback: MelixMessagesThinkingConfig?
    ) -> ResolvedReasoningPolicy {
        let normalizedType = requested.normalizedType
        if normalizedType == "disabled" {
            return ResolvedReasoningPolicy(
                config: .init(type: "disabled"),
                mode: "off",
                modeSource: source,
                effort: effort,
                continuityRehydrated: false
            )
        }

        let resolved = MelixMessagesThinkingConfig(
            type: normalizedType,
            budgetTokens: requested.budgetTokens ?? fallback?.budgetTokens
        )
        return ResolvedReasoningPolicy(
            config: resolved,
            mode: resolved.reasoningMode,
            modeSource: source,
            effort: effort,
            continuityRehydrated: false
        )
    }

    private func boolValue(_ value: StructuredJSONValue?) -> Bool? {
        guard case let .bool(enabled)? = value else {
            return nil
        }
        return enabled
    }

    private func stringValue(_ value: StructuredJSONValue?) -> String? {
        guard case let .string(value)? = value else {
            return nil
        }
        return normalizedString(value)
    }

    private func normalizedString(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed.lowercased()
    }

    private func autoDetectedFamily(modelID: String) -> String? {
        let normalized = modelID.lowercased()
        if normalized.contains("qwen") {
            return "qwen"
        }
        if normalized.contains("deepseek") {
            return "deepseek"
        }
        if normalized.contains("gpt-oss") {
            return "gpt-oss"
        }
        logger.warning(
            "No reasoning auto-detect family matched modelID=\(modelID, privacy: .public)"
        )
        return nil
    }
}
