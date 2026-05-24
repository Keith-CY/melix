import Foundation

public struct TextCompatibilityPolicyReceipt: Codable, Sendable, Equatable {
    public let compatSurface: String
    public let streamMode: String
    public let reasoningMode: String
    public let reasoningSource: String
    public let reasoningEffort: String
    public let toolParserMode: String
    public let toolParserSource: String
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
        self.toolNamespaces = toolNamespaces
        self.toolChoiceRequested = toolChoiceRequested
        self.toolChoiceResolved = toolChoiceResolved
        self.structuredOutputMode = structuredOutputMode
        self.outputModalities = outputModalities
        self.effectiveConfigHash = effectiveConfigHash
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
        return [
            "compat_surface": compatSurface(for: shapedRequest.endpoint),
            "stream_mode": shapedRequest.stream ? "stream" : "non_stream",
            "reasoning_mode": shapedRequest.reasoningMode,
            "reasoning_source": shapedRequest.reasoningSource,
            "reasoning_effort": shapedRequest.reasoningEffort ?? "",
            "tool_parser_mode": shapedRequest.toolParser?.mode.rawValue ?? "none",
            "tool_parser_source": shapedRequest.toolParser?.source ?? "none",
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
