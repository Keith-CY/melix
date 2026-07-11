import Foundation

public struct TextCompatibilityPolicyReceipt: Codable, Sendable, Equatable {
    public let compatSurface: String
    public let streamMode: String
    public let reasoningMode: String
    public let reasoningSource: String
    public let reasoningEffort: String
    public let toolParserMode: String
    public let toolParserSource: String
    public let requestedParser: String
    public let resolvedParser: String
    public let parserFallbackMode: String
    public let parserRefusalReason: String
    public let toolNamespaces: [String]
    public let toolChoiceRequested: String
    public let toolChoiceResolved: String
    public let structuredOutputMode: String
    public let outputModalities: [String]
    public let effectiveConfigHash: String

    enum CodingKeys: String, CodingKey {
        case compatSurface = "compat_surface"
        case streamMode = "stream_mode"
        case reasoningMode = "reasoning_mode"
        case reasoningSource = "reasoning_source"
        case reasoningEffort = "reasoning_effort"
        case toolParserMode = "tool_parser_mode"
        case toolParserSource = "tool_parser_source"
        case requestedParser = "requested_parser"
        case resolvedParser = "resolved_parser"
        case parserFallbackMode = "parser_fallback_mode"
        case parserRefusalReason = "parser_refusal_reason"
        case toolNamespaces = "tool_namespaces"
        case toolChoiceRequested = "tool_choice_requested"
        case toolChoiceResolved = "tool_choice_resolved"
        case structuredOutputMode = "structured_output_mode"
        case outputModalities = "output_modalities"
        case effectiveConfigHash = "effective_config_hash"
    }

    public init(
        compatSurface: String,
        streamMode: String,
        reasoningMode: String,
        reasoningSource: String,
        reasoningEffort: String,
        toolParserMode: String,
        toolParserSource: String,
        requestedParser: String,
        resolvedParser: String,
        parserFallbackMode: String,
        parserRefusalReason: String,
        toolNamespaces: [String],
        toolChoiceRequested: String,
        toolChoiceResolved: String,
        structuredOutputMode: String,
        outputModalities: [String],
        effectiveConfigHash: String
    ) {
        self.compatSurface = compatSurface
        self.streamMode = streamMode
        self.reasoningMode = reasoningMode
        self.reasoningSource = reasoningSource
        self.reasoningEffort = reasoningEffort
        self.toolParserMode = toolParserMode
        self.toolParserSource = toolParserSource
        self.requestedParser = requestedParser
        self.resolvedParser = resolvedParser
        self.parserFallbackMode = parserFallbackMode
        self.parserRefusalReason = parserRefusalReason
        self.toolNamespaces = toolNamespaces
        self.toolChoiceRequested = toolChoiceRequested
        self.toolChoiceResolved = toolChoiceResolved
        self.structuredOutputMode = structuredOutputMode
        self.outputModalities = outputModalities
        self.effectiveConfigHash = effectiveConfigHash
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        compatSurface = try container.decode(String.self, forKey: .compatSurface)
        streamMode = try container.decode(String.self, forKey: .streamMode)
        reasoningMode = try container.decode(String.self, forKey: .reasoningMode)
        reasoningSource = try container.decode(String.self, forKey: .reasoningSource)
        reasoningEffort = try container.decode(String.self, forKey: .reasoningEffort)
        toolParserMode = try container.decode(String.self, forKey: .toolParserMode)
        toolParserSource = try container.decode(String.self, forKey: .toolParserSource)
        requestedParser = try container.decodeIfPresent(String.self, forKey: .requestedParser) ?? "none"
        resolvedParser = try container.decodeIfPresent(String.self, forKey: .resolvedParser) ?? "none"
        parserFallbackMode = try container.decodeIfPresent(String.self, forKey: .parserFallbackMode) ?? ""
        parserRefusalReason = try container.decodeIfPresent(String.self, forKey: .parserRefusalReason) ?? ""
        toolNamespaces = try container.decode([String].self, forKey: .toolNamespaces)
        toolChoiceRequested = try container.decode(String.self, forKey: .toolChoiceRequested)
        toolChoiceResolved = try container.decode(String.self, forKey: .toolChoiceResolved)
        structuredOutputMode = try container.decode(String.self, forKey: .structuredOutputMode)
        outputModalities = try container.decode([String].self, forKey: .outputModalities)
        effectiveConfigHash = try container.decode(String.self, forKey: .effectiveConfigHash)
    }

    public init(shapedRequest: ShapedTextRequest) {
        let fields = Self.hashFields(shapedRequest: shapedRequest)
        let effectiveConfigHash = cacheScopeHash(Self.canonicalJSONString(fields))
        self.init(
            compatSurface: fields["compat_surface"] as? String ?? "",
            streamMode: fields["stream_mode"] as? String ?? "",
            reasoningMode: fields["reasoning_mode"] as? String ?? "",
            reasoningSource: fields["reasoning_source"] as? String ?? "",
            reasoningEffort: fields["reasoning_effort"] as? String ?? "",
            toolParserMode: fields["tool_parser_mode"] as? String ?? "",
            toolParserSource: fields["tool_parser_source"] as? String ?? "",
            requestedParser: fields["requested_parser"] as? String ?? "",
            resolvedParser: fields["resolved_parser"] as? String ?? "",
            parserFallbackMode: fields["parser_fallback_mode"] as? String ?? "",
            parserRefusalReason: fields["parser_refusal_reason"] as? String ?? "",
            toolNamespaces: fields["tool_namespaces"] as? [String] ?? [],
            toolChoiceRequested: fields["tool_choice_requested"] as? String ?? "",
            toolChoiceResolved: fields["tool_choice_resolved"] as? String ?? "",
            structuredOutputMode: fields["structured_output_mode"] as? String ?? "",
            outputModalities: fields["output_modalities"] as? [String] ?? ["text"],
            effectiveConfigHash: effectiveConfigHash
        )
    }

    public var jsonString: String {
        Self.canonicalJSONString(dictionary)
    }

    public var extFields: [String: String] {
        [
            "melix.compat.compat_surface": compatSurface,
            "melix.compat.stream_mode": streamMode,
            "melix.compat.reasoning_mode": reasoningMode,
            "melix.compat.reasoning_source": reasoningSource,
            "melix.compat.reasoning_effort": reasoningEffort,
            "melix.compat.tool_parser_mode": toolParserMode,
            "melix.compat.tool_parser_source": toolParserSource,
            "melix.compat.requested_parser": requestedParser,
            "melix.compat.resolved_parser": resolvedParser,
            "melix.compat.parser_fallback_mode": parserFallbackMode,
            "melix.compat.parser_refusal_reason": parserRefusalReason,
            "melix.compat.tool_namespaces": toolNamespaces.joined(separator: ","),
            "melix.compat.tool_choice_requested": toolChoiceRequested,
            "melix.compat.tool_choice_resolved": toolChoiceResolved,
            "melix.compat.structured_output_mode": structuredOutputMode,
            "melix.compat.output_modalities": outputModalities.joined(separator: ","),
            "melix.compat.effective_config_hash": effectiveConfigHash,
            "melix.compat.policy_receipt_json": jsonString,
        ]
    }

    private var dictionary: [String: Any] {
        [
            "compat_surface": compatSurface,
            "stream_mode": streamMode,
            "reasoning_mode": reasoningMode,
            "reasoning_source": reasoningSource,
            "reasoning_effort": reasoningEffort,
            "tool_parser_mode": toolParserMode,
            "tool_parser_source": toolParserSource,
            "requested_parser": requestedParser,
            "resolved_parser": resolvedParser,
            "parser_fallback_mode": parserFallbackMode,
            "parser_refusal_reason": parserRefusalReason,
            "tool_namespaces": toolNamespaces,
            "tool_choice_requested": toolChoiceRequested,
            "tool_choice_resolved": toolChoiceResolved,
            "structured_output_mode": structuredOutputMode,
            "output_modalities": outputModalities,
            "effective_config_hash": effectiveConfigHash,
        ]
    }

    private static func hashFields(shapedRequest: ShapedTextRequest) -> [String: Any] {
        let toolChoiceRequested = shapedRequest.toolChoice ?? ""
        let requestedParser = if let toolParser = shapedRequest.toolParser,
                                 toolParser.source == "request" {
            toolParser.mode.rawValue
        } else {
            "none"
        }
        return [
            "compat_surface": compatSurface(for: shapedRequest.endpoint),
            "stream_mode": shapedRequest.stream ? "stream" : "non_stream",
            "reasoning_mode": shapedRequest.reasoningMode,
            "reasoning_source": shapedRequest.reasoningSource,
            "reasoning_effort": shapedRequest.reasoningEffort ?? "",
            "tool_parser_mode": shapedRequest.toolParser?.mode.rawValue ?? "none",
            "tool_parser_source": shapedRequest.toolParser?.source ?? "none",
            "requested_parser": requestedParser,
            "resolved_parser": shapedRequest.toolParser?.mode.rawValue ?? "none",
            "parser_fallback_mode": shapedRequest.toolParser?.fallbackMode?.rawValue ?? "",
            "parser_refusal_reason": shapedRequest.toolParserSuppressedReason ?? "",
            "tool_namespaces": shapedRequest.toolParser?.namespaces ?? [],
            "tool_choice_requested": toolChoiceRequested,
            "tool_choice_resolved": resolvedToolChoice(requested: toolChoiceRequested, hasTools: !shapedRequest.tools.isEmpty),
            "structured_output_mode": shapedRequest.structuredOutput?.mode.rawValue ?? "text",
            "output_modalities": ["text"],
        ]
    }

    private static func compatSurface(for endpoint: TextEndpointKind) -> String {
        switch endpoint {
        case .chatCompletions:
            return "openai.chat.completions"
        case .completions:
            return "openai.completions"
        case .responses:
            return "openai.responses"
        case .messages:
            return "melix.messages"
        }
    }

    private static func resolvedToolChoice(requested: String, hasTools: Bool) -> String {
        if !requested.isEmpty {
            return requested
        }
        return hasTools ? "auto" : "none"
    }

    private static func canonicalJSONString(_ object: [String: Any]) -> String {
        let data = (try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])) ?? Data()
        return String(data: data, encoding: .utf8) ?? "{}"
    }
}
