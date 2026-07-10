import Foundation

public struct TextEffectivePolicyReceipt: Sendable, Equatable {
    public static let schemaVersion = "melix.text_effective_policy_receipt.v1"

    public let model: String
    public let endpoint: String
    public let temperature: Double
    public let temperatureSource: String
    public let topP: Double
    public let topPSource: String
    public let maxTokens: UInt32
    public let maxTokensSource: String
    public let seed: UInt32?
    public let seedSource: String
    public let stopSource: String
    public let chatTemplateSource: String
    public let chatTemplateEffectiveKwargsHash: String
    public let chatTemplateRequestOverrideApplied: Bool
    public let chatTemplateForcedOverrideApplied: Bool
    public let chatTemplateForcedKeys: [String]
    public let reasoningMode: String
    public let reasoningSource: String
    public let reasoningEffort: String
    public let effectiveConfigHash: String

    public init(shapedRequest: ShapedTextRequest) {
        let seedSource = shapedRequest.seed == nil ? "none" : "request"
        let chatTemplate = shapedRequest.chatTemplate
        let fields = Self.hashFields(
            model: shapedRequest.model,
            endpoint: shapedRequest.endpoint.rawValue,
            temperature: shapedRequest.temperature,
            temperatureSource: shapedRequest.temperatureSource,
            topP: shapedRequest.topP,
            topPSource: shapedRequest.topPSource,
            maxTokens: shapedRequest.maxTokens,
            maxTokensSource: shapedRequest.maxTokensSource,
            seed: shapedRequest.seed,
            seedSource: seedSource,
            stopSource: shapedRequest.stopSource,
            chatTemplateSource: chatTemplate?.source ?? "none",
            chatTemplateEffectiveKwargsHash: cacheScopeHash(chatTemplate?.effectiveJSONString),
            chatTemplateRequestOverrideApplied: chatTemplate?.requestValues.isEmpty == false,
            chatTemplateForcedOverrideApplied: chatTemplate?.forcedValues.isEmpty == false,
            chatTemplateForcedKeys: chatTemplate?.forcedKeys ?? [],
            reasoningMode: shapedRequest.reasoningMode,
            reasoningSource: shapedRequest.reasoningSource,
            reasoningEffort: shapedRequest.reasoningEffort ?? ""
        )
        let effectiveConfigHash = cacheScopeHash(Self.canonicalJSONString(fields))

        self.model = shapedRequest.model
        self.endpoint = shapedRequest.endpoint.rawValue
        self.temperature = shapedRequest.temperature
        self.temperatureSource = shapedRequest.temperatureSource
        self.topP = shapedRequest.topP
        self.topPSource = shapedRequest.topPSource
        self.maxTokens = shapedRequest.maxTokens
        self.maxTokensSource = shapedRequest.maxTokensSource
        self.seed = shapedRequest.seed
        self.seedSource = seedSource
        self.stopSource = shapedRequest.stopSource
        self.chatTemplateSource = chatTemplate?.source ?? "none"
        self.chatTemplateEffectiveKwargsHash = cacheScopeHash(chatTemplate?.effectiveJSONString)
        self.chatTemplateRequestOverrideApplied = chatTemplate?.requestValues.isEmpty == false
        self.chatTemplateForcedOverrideApplied = chatTemplate?.forcedValues.isEmpty == false
        self.chatTemplateForcedKeys = chatTemplate?.forcedKeys ?? []
        self.reasoningMode = shapedRequest.reasoningMode
        self.reasoningSource = shapedRequest.reasoningSource
        self.reasoningEffort = shapedRequest.reasoningEffort ?? ""
        self.effectiveConfigHash = effectiveConfigHash
    }

    public var jsonString: String {
        Self.canonicalJSONString(dictionary)
    }

    public var extFields: [String: String] {
        [
            "melix.effective_policy.receipt_schema": Self.schemaVersion,
            "melix.effective_policy.effective_config_hash": effectiveConfigHash,
            "melix.effective_policy.sampling.temperature_source": temperatureSource,
            "melix.effective_policy.sampling.top_p_source": topPSource,
            "melix.effective_policy.sampling.max_tokens_source": maxTokensSource,
            "melix.effective_policy.sampling.seed_source": seedSource,
            "melix.effective_policy.chat_template.source": chatTemplateSource,
            "melix.effective_policy.chat_template.request_override_applied": chatTemplateRequestOverrideApplied ? "true" : "false",
            "melix.effective_policy.chat_template.forced_override_applied": chatTemplateForcedOverrideApplied ? "true" : "false",
            "melix.effective_policy.reasoning.mode": reasoningMode,
            "melix.effective_policy.reasoning.source": reasoningSource,
            "melix.effective_policy.receipt_json": jsonString,
        ]
    }

    private var dictionary: [String: Any] {
        var fields = Self.hashFields(
            model: model,
            endpoint: endpoint,
            temperature: temperature,
            temperatureSource: temperatureSource,
            topP: topP,
            topPSource: topPSource,
            maxTokens: maxTokens,
            maxTokensSource: maxTokensSource,
            seed: seed,
            seedSource: seedSource,
            stopSource: stopSource,
            chatTemplateSource: chatTemplateSource,
            chatTemplateEffectiveKwargsHash: chatTemplateEffectiveKwargsHash,
            chatTemplateRequestOverrideApplied: chatTemplateRequestOverrideApplied,
            chatTemplateForcedOverrideApplied: chatTemplateForcedOverrideApplied,
            chatTemplateForcedKeys: chatTemplateForcedKeys,
            reasoningMode: reasoningMode,
            reasoningSource: reasoningSource,
            reasoningEffort: reasoningEffort
        )
        fields["effective_config_hash"] = effectiveConfigHash
        return fields
    }

    private static func hashFields(
        model: String,
        endpoint: String,
        temperature: Double,
        temperatureSource: String,
        topP: Double,
        topPSource: String,
        maxTokens: UInt32,
        maxTokensSource: String,
        seed: UInt32?,
        seedSource: String,
        stopSource: String,
        chatTemplateSource: String,
        chatTemplateEffectiveKwargsHash: String,
        chatTemplateRequestOverrideApplied: Bool,
        chatTemplateForcedOverrideApplied: Bool,
        chatTemplateForcedKeys: [String],
        reasoningMode: String,
        reasoningSource: String,
        reasoningEffort: String
    ) -> [String: Any] {
        [
            "schema_version": Self.schemaVersion,
            "model": model,
            "endpoint": endpoint,
            "sampling": [
                "temperature": temperature,
                "temperature_source": temperatureSource,
                "top_p": topP,
                "top_p_source": topPSource,
                "max_tokens": Int(maxTokens),
                "max_tokens_source": maxTokensSource,
                "seed": seed.map { Int($0) } as Any? ?? NSNull(),
                "seed_source": seedSource,
                "stop_source": stopSource,
            ] as [String: Any],
            "chat_template": [
                "source": chatTemplateSource,
                "effective_kwargs_hash": chatTemplateEffectiveKwargsHash,
                "request_override_applied": chatTemplateRequestOverrideApplied,
                "forced_override_applied": chatTemplateForcedOverrideApplied,
                "forced_keys": chatTemplateForcedKeys,
            ] as [String: Any],
            "reasoning": [
                "mode": reasoningMode,
                "source": reasoningSource,
                "effort": reasoningEffort,
            ],
        ]
    }

    private static func canonicalJSONString(_ object: [String: Any]) -> String {
        let data = (try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])) ?? Data()
        return String(data: data, encoding: .utf8) ?? "{}"
    }
}
