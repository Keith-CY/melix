import Foundation

public struct TextEffectivePolicyReceipt: Sendable, Equatable, Encodable {
    public static let schemaVersion = "melix.text_effective_policy_receipt.v1"

    public let model: String
    public let endpoint: String
    public let temperature: Double
    public let temperatureSource: String
    public let topP: Double
    public let topPSource: String
    public let maxTokens: UInt32
    public let maxTokensSource: String
    public let samplingPolicyLookupStatus: String
    public let samplingPolicyCanonicalModel: String
    public let samplingPolicyMatchedAlias: String
    public let samplingPolicySourceURL: String
    public let samplingRequestOverrideApplied: Bool
    public let recommendedSamplingRequired: Bool
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
        let fields = HashPayload(
            model: shapedRequest.model,
            endpoint: shapedRequest.endpoint.rawValue,
            temperature: shapedRequest.temperature,
            temperatureSource: shapedRequest.temperatureSource,
            topP: shapedRequest.topP,
            topPSource: shapedRequest.topPSource,
            maxTokens: shapedRequest.maxTokens,
            maxTokensSource: shapedRequest.maxTokensSource,
            samplingPolicyLookupStatus: shapedRequest.samplingPolicyLookupStatus,
            samplingPolicyCanonicalModel: shapedRequest.samplingPolicyCanonicalModel,
            samplingPolicyMatchedAlias: shapedRequest.samplingPolicyMatchedAlias,
            samplingPolicySourceURL: shapedRequest.samplingPolicySourceURL,
            samplingRequestOverrideApplied: shapedRequest.samplingRequestOverrideApplied,
            recommendedSamplingRequired: shapedRequest.recommendedSamplingRequired,
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
        self.samplingPolicyLookupStatus = shapedRequest.samplingPolicyLookupStatus
        self.samplingPolicyCanonicalModel = shapedRequest.samplingPolicyCanonicalModel
        self.samplingPolicyMatchedAlias = shapedRequest.samplingPolicyMatchedAlias
        self.samplingPolicySourceURL = shapedRequest.samplingPolicySourceURL
        self.samplingRequestOverrideApplied = shapedRequest.samplingRequestOverrideApplied
        self.recommendedSamplingRequired = shapedRequest.recommendedSamplingRequired
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
        Self.canonicalJSONString(self)
    }

    public var extFields: [String: String] {
        [
            "melix.effective_policy.receipt_schema": Self.schemaVersion,
            "melix.effective_policy.effective_config_hash": effectiveConfigHash,
            "melix.effective_policy.sampling.temperature_source": temperatureSource,
            "melix.effective_policy.sampling.top_p_source": topPSource,
            "melix.effective_policy.sampling.max_tokens_source": maxTokensSource,
            "melix.effective_policy.sampling.policy_lookup_status": samplingPolicyLookupStatus,
            "melix.effective_policy.sampling.policy_canonical_model": samplingPolicyCanonicalModel,
            "melix.effective_policy.sampling.policy_matched_alias": samplingPolicyMatchedAlias,
            "melix.effective_policy.sampling.policy_source_url": samplingPolicySourceURL,
            "melix.effective_policy.sampling.request_override_applied": samplingRequestOverrideApplied ? "true" : "false",
            "melix.effective_policy.sampling.recommended_sampling_required": recommendedSamplingRequired ? "true" : "false",
            "melix.effective_policy.sampling.seed_source": seedSource,
            "melix.effective_policy.chat_template.source": chatTemplateSource,
            "melix.effective_policy.chat_template.request_override_applied": chatTemplateRequestOverrideApplied ? "true" : "false",
            "melix.effective_policy.chat_template.forced_override_applied": chatTemplateForcedOverrideApplied ? "true" : "false",
            "melix.effective_policy.reasoning.mode": reasoningMode,
            "melix.effective_policy.reasoning.source": reasoningSource,
            "melix.effective_policy.receipt_json": jsonString,
        ]
    }

    private struct HashPayload: Encodable {
        let model: String
        let endpoint: String
        let temperature: Double
        let temperatureSource: String
        let topP: Double
        let topPSource: String
        let maxTokens: UInt32
        let maxTokensSource: String
        let samplingPolicyLookupStatus: String
        let samplingPolicyCanonicalModel: String
        let samplingPolicyMatchedAlias: String
        let samplingPolicySourceURL: String
        let samplingRequestOverrideApplied: Bool
        let recommendedSamplingRequired: Bool
        let seed: UInt32?
        let seedSource: String
        let stopSource: String
        let chatTemplateSource: String
        let chatTemplateEffectiveKwargsHash: String
        let chatTemplateRequestOverrideApplied: Bool
        let chatTemplateForcedOverrideApplied: Bool
        let chatTemplateForcedKeys: [String]
        let reasoningMode: String
        let reasoningSource: String
        let reasoningEffort: String

        func encode(to encoder: Encoder) throws {
            try TextEffectivePolicyReceipt.encodePayload(
                to: encoder,
                model: model,
                endpoint: endpoint,
                temperature: temperature,
                temperatureSource: temperatureSource,
                topP: topP,
                topPSource: topPSource,
                maxTokens: maxTokens,
                maxTokensSource: maxTokensSource,
                samplingPolicyLookupStatus: samplingPolicyLookupStatus,
                samplingPolicyCanonicalModel: samplingPolicyCanonicalModel,
                samplingPolicyMatchedAlias: samplingPolicyMatchedAlias,
                samplingPolicySourceURL: samplingPolicySourceURL,
                samplingRequestOverrideApplied: samplingRequestOverrideApplied,
                recommendedSamplingRequired: recommendedSamplingRequired,
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
        }
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case model
        case endpoint
        case sampling
        case chatTemplate = "chat_template"
        case reasoning
        case effectiveConfigHash = "effective_config_hash"
    }

    private enum SamplingCodingKeys: String, CodingKey {
        case temperature
        case temperatureSource = "temperature_source"
        case topP = "top_p"
        case topPSource = "top_p_source"
        case maxTokens = "max_tokens"
        case maxTokensSource = "max_tokens_source"
        case policyLookupStatus = "policy_lookup_status"
        case policyCanonicalModel = "policy_canonical_model"
        case policyMatchedAlias = "policy_matched_alias"
        case policySourceURL = "policy_source_url"
        case requestOverrideApplied = "request_override_applied"
        case recommendedSamplingRequired = "recommended_sampling_required"
        case seed
        case seedSource = "seed_source"
        case stopSource = "stop_source"
    }

    private enum ChatTemplateCodingKeys: String, CodingKey {
        case source
        case effectiveKwargsHash = "effective_kwargs_hash"
        case requestOverrideApplied = "request_override_applied"
        case forcedOverrideApplied = "forced_override_applied"
        case forcedKeys = "forced_keys"
    }

    private enum ReasoningCodingKeys: String, CodingKey {
        case mode
        case source
        case effort
    }

    public func encode(to encoder: Encoder) throws {
        try Self.encodePayload(
            to: encoder,
            model: model,
            endpoint: endpoint,
            temperature: temperature,
            temperatureSource: temperatureSource,
            topP: topP,
            topPSource: topPSource,
            maxTokens: maxTokens,
            maxTokensSource: maxTokensSource,
            samplingPolicyLookupStatus: samplingPolicyLookupStatus,
            samplingPolicyCanonicalModel: samplingPolicyCanonicalModel,
            samplingPolicyMatchedAlias: samplingPolicyMatchedAlias,
            samplingPolicySourceURL: samplingPolicySourceURL,
            samplingRequestOverrideApplied: samplingRequestOverrideApplied,
            recommendedSamplingRequired: recommendedSamplingRequired,
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
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(effectiveConfigHash, forKey: .effectiveConfigHash)
    }

    private static func encodePayload(
        to encoder: Encoder,
        model: String,
        endpoint: String,
        temperature: Double,
        temperatureSource: String,
        topP: Double,
        topPSource: String,
        maxTokens: UInt32,
        maxTokensSource: String,
        samplingPolicyLookupStatus: String,
        samplingPolicyCanonicalModel: String,
        samplingPolicyMatchedAlias: String,
        samplingPolicySourceURL: String,
        samplingRequestOverrideApplied: Bool,
        recommendedSamplingRequired: Bool,
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
    ) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(Self.schemaVersion, forKey: .schemaVersion)
        try container.encode(model, forKey: .model)
        try container.encode(endpoint, forKey: .endpoint)

        var samplingContainer = container.nestedContainer(keyedBy: SamplingCodingKeys.self, forKey: .sampling)
        try samplingContainer.encode(temperature, forKey: .temperature)
        try samplingContainer.encode(temperatureSource, forKey: .temperatureSource)
        try samplingContainer.encode(topP, forKey: .topP)
        try samplingContainer.encode(topPSource, forKey: .topPSource)
        try samplingContainer.encode(Int(maxTokens), forKey: .maxTokens)
        try samplingContainer.encode(maxTokensSource, forKey: .maxTokensSource)
        try samplingContainer.encode(samplingPolicyLookupStatus, forKey: .policyLookupStatus)
        try samplingContainer.encode(samplingPolicyCanonicalModel, forKey: .policyCanonicalModel)
        try samplingContainer.encode(samplingPolicyMatchedAlias, forKey: .policyMatchedAlias)
        try samplingContainer.encode(samplingPolicySourceURL, forKey: .policySourceURL)
        try samplingContainer.encode(samplingRequestOverrideApplied, forKey: .requestOverrideApplied)
        try samplingContainer.encode(recommendedSamplingRequired, forKey: .recommendedSamplingRequired)
        try samplingContainer.encode(seed.map { Int($0) }, forKey: .seed)
        try samplingContainer.encode(seedSource, forKey: .seedSource)
        try samplingContainer.encode(stopSource, forKey: .stopSource)

        var chatTemplateContainer = container.nestedContainer(keyedBy: ChatTemplateCodingKeys.self, forKey: .chatTemplate)
        try chatTemplateContainer.encode(chatTemplateSource, forKey: .source)
        try chatTemplateContainer.encode(chatTemplateEffectiveKwargsHash, forKey: .effectiveKwargsHash)
        try chatTemplateContainer.encode(chatTemplateRequestOverrideApplied, forKey: .requestOverrideApplied)
        try chatTemplateContainer.encode(chatTemplateForcedOverrideApplied, forKey: .forcedOverrideApplied)
        try chatTemplateContainer.encode(chatTemplateForcedKeys, forKey: .forcedKeys)

        var reasoningContainer = container.nestedContainer(keyedBy: ReasoningCodingKeys.self, forKey: .reasoning)
        try reasoningContainer.encode(reasoningMode, forKey: .mode)
        try reasoningContainer.encode(reasoningSource, forKey: .source)
        try reasoningContainer.encode(reasoningEffort, forKey: .effort)
    }

    private static func canonicalJSONString<T: Encodable>(_ object: T) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        do {
            let data = try encoder.encode(object)
            guard let json = String(data: data, encoding: .utf8) else {
                preconditionFailure("Text effective policy receipt encoded non-UTF-8 JSON")
            }
            return json
        } catch {
            preconditionFailure("Text effective policy receipt JSON encoding failed: \(error)")
        }
    }
}
