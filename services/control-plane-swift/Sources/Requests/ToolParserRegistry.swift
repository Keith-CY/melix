import Foundation
import MelixControlPlaneProtocol

public enum ToolParserMode: String, Codable, Sendable, Equatable {
    case text
    case json
    case qwen
    case gemma
    case minimax
    case glm
    case mistral
    case xml
}

public enum ToolParserKind: String, Codable, Sendable, Equatable {
    case plainText = "plain_text"
    case structuredOutput = "structured_output"
    case toolCall = "tool_call"
}

public enum ToolParserSelectorSurface: String, Codable, Sendable, Equatable {
    case api
    case desktop
    case cli
}

public enum ToolParserRequestContextMode: String, Codable, Sendable, Equatable, Hashable {
    case structuredJSON = "structured_json"
    case toolParser = "tool_parser"
    case reasoning
    case plain
}

public struct ToolParserAuditReceipt: Codable, Sendable, Equatable {
    public let parserID: String
    public let parserKind: ToolParserKind
    public let acceptedWireFormats: [String]
    public let selectorSurface: ToolParserSelectorSurface
    public let selectorSource: String
    public let requestContextMode: ToolParserRequestContextMode
    public let exemptionReason: String

    enum CodingKeys: String, CodingKey {
        case parserID = "parser_id"
        case parserKind = "parser_kind"
        case acceptedWireFormats = "accepted_wire_formats"
        case selectorSurface = "selector_surface"
        case selectorSource = "selector_source"
        case requestContextMode = "request_context_mode"
        case exemptionReason = "exemption_reason"
    }

    public init(
        parserID: String,
        parserKind: ToolParserKind,
        acceptedWireFormats: [String],
        selectorSurface: ToolParserSelectorSurface,
        selectorSource: String,
        requestContextMode: ToolParserRequestContextMode,
        exemptionReason: String = ""
    ) {
        self.parserID = parserID
        self.parserKind = parserKind
        self.acceptedWireFormats = acceptedWireFormats
        self.selectorSurface = selectorSurface
        self.selectorSource = selectorSource
        self.requestContextMode = requestContextMode
        self.exemptionReason = exemptionReason
    }
}

public enum ToolParserConfigurationError: Error, Equatable {
    case unsupportedMode(String)
    case invalidNamespace(String)
    case namespacesRequireStructuredParser(String)

    public var operatorMessage: String {
        switch self {
        case let .unsupportedMode(mode):
            return "Unsupported tool parser mode: \(mode)."
        case let .invalidNamespace(namespace):
            return "Invalid tool parser namespace: \(namespace)."
        case let .namespacesRequireStructuredParser(mode):
            return "Tool parser namespaces require a structured parser mode, got \(mode)."
        }
    }
}

public struct ToolParserSelection: Sendable, Equatable {
    public let mode: ToolParserMode
    public let namespaces: [String]
    public let source: String
    public let fallbackMode: ToolParserMode?
    public let mcpSourceIDs: [String]

    public init(
        mode: ToolParserMode,
        namespaces: [String] = [],
        source: String,
        fallbackMode: ToolParserMode? = nil,
        mcpSourceIDs: [String] = []
    ) {
        self.mode = mode
        self.namespaces = namespaces
        self.source = source
        self.fallbackMode = fallbackMode
        self.mcpSourceIDs = mcpSourceIDs
    }

    public var isExplicit: Bool {
        source != "default" || mode != .text || !namespaces.isEmpty || fallbackMode != nil || !mcpSourceIDs.isEmpty
    }

    init?(executionExt: [String: String]) {
        guard
            let rawMode = executionExt["melix.tool_parser.mode"],
            let mode = ToolParserRegistry().mode(for: rawMode)
        else {
            return nil
        }

        let namespaces = executionExt["melix.tool_parser.namespaces"]?
            .split(separator: ",")
            .map { String($0) } ?? []
        let fallbackMode = executionExt["melix.tool_parser.fallback_mode"]
            .flatMap { ToolParserRegistry().mode(for: $0) }
        let mcpSourceIDs = executionExt["melix.mcp.source_ids"]?
            .split(separator: ",")
            .map { String($0) } ?? []

        self.init(
            mode: mode,
            namespaces: namespaces,
            source: executionExt["melix.tool_parser.source"] ?? "request",
            fallbackMode: fallbackMode,
            mcpSourceIDs: mcpSourceIDs
        )
    }

    init?(modelSettings: Melix_Controlplane_V1_ModelSettings) {
        let registry = ToolParserRegistry()
        guard
            let rawMode = modelSettings.ext["tool_parser_mode"],
            let mode = registry.mode(for: rawMode)
        else {
            return nil
        }
        let namespaces = (modelSettings.ext["tool_parser_namespaces"] ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let fallbackMode = modelSettings.ext["tool_parser_xml_fallback"] == "true" ? ToolParserMode.xml : nil
        self.init(mode: mode, namespaces: namespaces, source: "model", fallbackMode: fallbackMode)
    }
}

public struct ToolParserRequestConfiguration: Codable, Sendable, Equatable {
    public let mode: ToolParserMode
    public let namespaces: [String]
    public let xmlFallback: Bool

    enum CodingKeys: String, CodingKey {
        case mode
        case namespaces
        case xmlFallback = "xml_fallback"
    }

    public init(
        mode: ToolParserMode,
        namespaces: [String] = [],
        xmlFallback: Bool = false
    ) {
        self.mode = mode
        self.namespaces = namespaces
        self.xmlFallback = xmlFallback
    }

    public init(from decoder: Decoder) throws {
        let singleValue = try decoder.singleValueContainer()
        if let rawMode = try? singleValue.decode(String.self) {
            let registry = ToolParserRegistry()
            guard let mode = registry.mode(for: rawMode) else {
                throw ToolParserConfigurationError.unsupportedMode(rawMode)
            }
            self.init(mode: mode)
            return
        }

        let container = try decoder.container(keyedBy: CodingKeys.self)
        let rawMode = try container.decode(String.self, forKey: .mode)
        let registry = ToolParserRegistry()
        guard let mode = registry.mode(for: rawMode) else {
            throw ToolParserConfigurationError.unsupportedMode(rawMode)
        }
        let namespaces = try container.decodeIfPresent([String].self, forKey: .namespaces) ?? []
        let xmlFallback = try container.decodeIfPresent(Bool.self, forKey: .xmlFallback) ?? false
        self.init(mode: mode, namespaces: namespaces, xmlFallback: xmlFallback)
    }

    public func resolvedSelection() throws -> ToolParserSelection {
        let registry = ToolParserRegistry()
        return try registry.selection(
            requestedMode: mode,
            requestedNamespaces: namespaces,
            source: "request",
            xmlFallback: xmlFallback
        )
    }
}

public struct ToolParserRegistry: Sendable {
    private struct Descriptor: Sendable {
        let mode: ToolParserMode
        let aliases: Set<String>
        let parserKind: ToolParserKind
        let acceptedWireFormats: [String]
        let requestContextModes: [ToolParserRequestContextMode]
    }

    private let descriptors: [Descriptor] = [
        .init(
            mode: .text,
            aliases: ["text", "plain"],
            parserKind: .plainText,
            acceptedWireFormats: ["raw_text"],
            requestContextModes: [.plain]
        ),
        .init(
            mode: .json,
            aliases: ["json", "json_object"],
            parserKind: .structuredOutput,
            acceptedWireFormats: ["json_object"],
            requestContextModes: [.structuredJSON]
        ),
        .init(
            mode: .qwen,
            aliases: ["qwen"],
            parserKind: .toolCall,
            acceptedWireFormats: ["qwen_xml_tool_call"],
            requestContextModes: [.toolParser, .reasoning]
        ),
        .init(
            mode: .gemma,
            aliases: ["gemma"],
            parserKind: .toolCall,
            acceptedWireFormats: ["gemma_tool_call"],
            requestContextModes: [.toolParser]
        ),
        .init(
            mode: .minimax,
            aliases: ["minimax"],
            parserKind: .toolCall,
            acceptedWireFormats: ["minimax_tool_call"],
            requestContextModes: [.toolParser]
        ),
        .init(
            mode: .glm,
            aliases: ["glm"],
            parserKind: .toolCall,
            acceptedWireFormats: ["glm_tool_call"],
            requestContextModes: [.toolParser]
        ),
        .init(
            mode: .mistral,
            aliases: ["mistral"],
            parserKind: .toolCall,
            acceptedWireFormats: ["mistral_tool_call"],
            requestContextModes: [.toolParser]
        ),
        .init(
            mode: .xml,
            aliases: ["xml"],
            parserKind: .toolCall,
            acceptedWireFormats: ["xml_tool_call"],
            requestContextModes: [.toolParser]
        ),
    ]

    public init() {}

    public func supportedModes() -> [ToolParserMode] {
        descriptors.map(\.mode)
    }

    public func auditReceipts() -> [ToolParserAuditReceipt] {
        descriptors.flatMap { descriptor in
            descriptor.requestContextModes.map { requestContextMode in
                ToolParserAuditReceipt(
                    parserID: descriptor.mode.rawValue,
                    parserKind: descriptor.parserKind,
                    acceptedWireFormats: acceptedWireFormats(
                        for: descriptor,
                        requestContextMode: requestContextMode
                    ),
                    selectorSurface: .api,
                    selectorSource: "request.tool_parser",
                    requestContextMode: requestContextMode
                )
            }
        }
    }

    public func selectorAuditReceipts() -> [ToolParserAuditReceipt] {
        descriptors.flatMap { descriptor in
            descriptor.requestContextModes.flatMap { requestContextMode in
                let acceptedWireFormats = acceptedWireFormats(
                    for: descriptor,
                    requestContextMode: requestContextMode
                )
                return [
                    ToolParserAuditReceipt(
                        parserID: descriptor.mode.rawValue,
                        parserKind: descriptor.parserKind,
                        acceptedWireFormats: acceptedWireFormats,
                        selectorSurface: .api,
                        selectorSource: "request.tool_parser",
                        requestContextMode: requestContextMode
                    ),
                    ToolParserAuditReceipt(
                        parserID: descriptor.mode.rawValue,
                        parserKind: descriptor.parserKind,
                        acceptedWireFormats: acceptedWireFormats,
                        selectorSurface: .desktop,
                        selectorSource: "tooling_settings.builtin_tool_parser_modes",
                        requestContextMode: requestContextMode
                    ),
                    ToolParserAuditReceipt(
                        parserID: descriptor.mode.rawValue,
                        parserKind: descriptor.parserKind,
                        acceptedWireFormats: acceptedWireFormats,
                        selectorSurface: .cli,
                        selectorSource: "none",
                        requestContextMode: requestContextMode,
                        exemptionReason: Self.cliSelectorExemptionReason
                    ),
                ]
            }
        }
    }

    public func requestContextFixtures() -> [ToolParserAuditReceipt] {
        [
            receipt(mode: .json, requestContextMode: .structuredJSON),
            receipt(mode: .qwen, requestContextMode: .toolParser),
            receipt(mode: .qwen, requestContextMode: .reasoning),
            receipt(mode: .text, requestContextMode: .plain),
        ]
    }

    func mode(for rawMode: String) -> ToolParserMode? {
        let normalized = rawMode.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return descriptors.first(where: { $0.aliases.contains(normalized) })?.mode
    }

    func resolve(
        requested: ToolParserSelection?,
        modelDefault: ToolParserSelection?
    ) -> ToolParserSelection? {
        if let requested {
            return requested
        }
        if let modelDefault {
            return modelDefault
        }
        return nil
    }

    func resolve(
        requested: ToolParserSelection?,
        modelDefault: ToolParserSelection?,
        mcpToolCatalog: MCPToolCatalog
    ) -> ToolParserSelection? {
        if let requested {
            return mergeMCPCatalog(mcpToolCatalog, into: requested)
        }
        if let modelDefault {
            return mergeMCPCatalog(mcpToolCatalog, into: modelDefault)
        }

        guard !mcpToolCatalog.resolvedNamespaces.isEmpty else {
            return nil
        }

        return ToolParserSelection(
            mode: mcpToolCatalog.defaultParserMode,
            namespaces: mcpToolCatalog.resolvedNamespaces,
            source: "mcp",
            mcpSourceIDs: mcpToolCatalog.resolvedSourceIDs
        )
    }

    func selection(
        requestedMode: ToolParserMode,
        requestedNamespaces: [String],
        source: String,
        xmlFallback: Bool
    ) throws -> ToolParserSelection {
        let namespaces = try sanitizeNamespaces(requestedNamespaces)
        if requestedMode == .text, !namespaces.isEmpty {
            throw ToolParserConfigurationError.namespacesRequireStructuredParser(requestedMode.rawValue)
        }
        return ToolParserSelection(
            mode: requestedMode,
            namespaces: namespaces,
            source: source,
            fallbackMode: xmlFallback && requestedMode != .xml ? .xml : nil
        )
    }

    private func sanitizeNamespaces(
        _ namespaces: [String]
    ) throws -> [String] {
        var sanitized: [String] = []
        var seen = Set<String>()
        for namespace in namespaces {
            let normalized = namespace.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !normalized.isEmpty else {
                continue
            }
            guard normalized.unicodeScalars.allSatisfy({ scalar in
                CharacterSet.alphanumerics.contains(scalar)
                    || scalar == "_"
                    || scalar == "-"
                    || scalar == "."
                    || scalar == ":"
            }) else {
                throw ToolParserConfigurationError.invalidNamespace(namespace)
            }
            if seen.insert(normalized).inserted {
                sanitized.append(normalized)
            }
        }
        return sanitized
    }

    private func mergeMCPCatalog(
        _ mcpToolCatalog: MCPToolCatalog,
        into base: ToolParserSelection
    ) -> ToolParserSelection {
        guard
            !mcpToolCatalog.resolvedNamespaces.isEmpty,
            base.mode != .text
        else {
            return base
        }

        var mergedNamespaces = base.namespaces
        var seenNamespaces = Set(base.namespaces)
        for namespace in mcpToolCatalog.resolvedNamespaces where seenNamespaces.insert(namespace).inserted {
            mergedNamespaces.append(namespace)
        }

        var mergedSourceIDs = base.mcpSourceIDs
        var seenSourceIDs = Set(base.mcpSourceIDs)
        for sourceID in mcpToolCatalog.resolvedSourceIDs where seenSourceIDs.insert(sourceID).inserted {
            mergedSourceIDs.append(sourceID)
        }

        return ToolParserSelection(
            mode: base.mode,
            namespaces: mergedNamespaces,
            source: base.source,
            fallbackMode: base.fallbackMode,
            mcpSourceIDs: mergedSourceIDs
        )
    }

    private static let cliSelectorExemptionReason = "CLI has no request-construction surface for tool parser selection; it reports remote model supported_parsers only."

    private func receipt(
        mode: ToolParserMode,
        requestContextMode: ToolParserRequestContextMode
    ) -> ToolParserAuditReceipt {
        let descriptor = descriptors.first(where: { $0.mode == mode })!
        return ToolParserAuditReceipt(
            parserID: descriptor.mode.rawValue,
            parserKind: descriptor.parserKind,
            acceptedWireFormats: acceptedWireFormats(for: descriptor, requestContextMode: requestContextMode),
            selectorSurface: .api,
            selectorSource: "request.tool_parser",
            requestContextMode: requestContextMode
        )
    }

    private func acceptedWireFormats(
        for descriptor: Descriptor,
        requestContextMode: ToolParserRequestContextMode
    ) -> [String] {
        if descriptor.mode == .qwen, requestContextMode == .reasoning {
            return descriptor.acceptedWireFormats + ["reasoning_channel_tags"]
        }
        return descriptor.acceptedWireFormats
    }
}
