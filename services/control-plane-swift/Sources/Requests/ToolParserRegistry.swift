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

    public init(
        mode: ToolParserMode,
        namespaces: [String] = [],
        source: String,
        fallbackMode: ToolParserMode? = nil
    ) {
        self.mode = mode
        self.namespaces = namespaces
        self.source = source
        self.fallbackMode = fallbackMode
    }

    public var isExplicit: Bool {
        source != "default" || mode != .text || !namespaces.isEmpty || fallbackMode != nil
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

        self.init(
            mode: mode,
            namespaces: namespaces,
            source: executionExt["melix.tool_parser.source"] ?? "request",
            fallbackMode: fallbackMode
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
    }

    private let descriptors: [Descriptor] = [
        .init(mode: .text, aliases: ["text", "plain"]),
        .init(mode: .json, aliases: ["json", "json_object"]),
        .init(mode: .qwen, aliases: ["qwen"]),
        .init(mode: .gemma, aliases: ["gemma"]),
        .init(mode: .minimax, aliases: ["minimax"]),
        .init(mode: .glm, aliases: ["glm"]),
        .init(mode: .mistral, aliases: ["mistral"]),
        .init(mode: .xml, aliases: ["xml"]),
    ]

    public init() {}

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
}
