import Foundation
import MelixControlPlaneProtocol

public struct MCPToolCatalog: Sendable, Equatable {
    public struct Source: Sendable, Codable, Equatable {
        public let sourceID: String
        public let enabled: Bool
        public let namespaces: [String]

        enum CodingKeys: String, CodingKey {
            case sourceID = "source_id"
            case enabled
            case namespaces
        }

        public init(
            sourceID: String,
            enabled: Bool = true,
            namespaces: [String]
        ) {
            self.sourceID = Self.normalizeSourceID(sourceID)
            self.enabled = enabled
            self.namespaces = Self.normalizeNamespaces(namespaces)
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.init(
                sourceID: try container.decode(String.self, forKey: .sourceID),
                enabled: try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? true,
                namespaces: try container.decodeIfPresent([String].self, forKey: .namespaces) ?? []
            )
        }

        private static func normalizeSourceID(_ rawValue: String) -> String {
            rawValue
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
        }

        private static func normalizeNamespaces(_ namespaces: [String]) -> [String] {
            var normalized: [String] = []
            var seen = Set<String>()
            for namespace in namespaces {
                let trimmed = namespace.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmed.isEmpty else {
                    continue
                }
                if seen.insert(trimmed).inserted {
                    normalized.append(trimmed)
                }
            }
            return normalized
        }
    }

    private struct FilePayload: Decodable {
        let defaultParserMode: String?
        let sources: [Source]

        enum CodingKeys: String, CodingKey {
            case defaultParserMode = "default_parser_mode"
            case sources
        }
    }

    public let configPath: String
    public let defaultParserMode: ToolParserMode
    public let sources: [Source]

    public static let empty = MCPToolCatalog()

    public init(
        configPath: String = "",
        defaultParserMode: ToolParserMode = .json,
        sources: [Source] = []
    ) {
        self.configPath = configPath.trimmingCharacters(in: .whitespacesAndNewlines)
        self.defaultParserMode = defaultParserMode
        self.sources = sources
            .filter { !$0.sourceID.isEmpty && !$0.namespaces.isEmpty }
            .sorted { $0.sourceID < $1.sourceID }
    }

    public static func load(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> MCPToolCatalog {
        guard
            let configPath = environment["MELIX_MCP_CONFIG_PATH"]?.trimmingCharacters(in: .whitespacesAndNewlines),
            !configPath.isEmpty
        else {
            return .empty
        }

        return load(configPath: configPath)
    }

    public static func load(configPath: String) -> MCPToolCatalog {
        let trimmedPath = configPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard
            !trimmedPath.isEmpty,
            let data = try? Data(contentsOf: URL(fileURLWithPath: trimmedPath)),
            let payload = try? JSONDecoder().decode(FilePayload.self, from: data)
        else {
            return MCPToolCatalog(configPath: trimmedPath)
        }

        let registry = ToolParserRegistry()
        let defaultMode = payload.defaultParserMode
            .flatMap { registry.mode(for: $0) } ?? .json
        return MCPToolCatalog(
            configPath: trimmedPath,
            defaultParserMode: defaultMode,
            sources: payload.sources
        )
    }

    public var enabledSources: [Source] {
        sources.filter(\.enabled)
    }

    public var resolvedSourceIDs: [String] {
        enabledSources.map(\.sourceID)
    }

    public var resolvedNamespaces: [String] {
        var namespaces: [String] = []
        var seen = Set<String>()
        for source in enabledSources {
            for namespace in source.namespaces where seen.insert(namespace).inserted {
                namespaces.append(namespace)
            }
        }
        return namespaces
    }

    public var enabledSourceCount: UInt32 {
        UInt32(enabledSources.count)
    }

    public var resolvedToolCount: UInt32 {
        UInt32(resolvedNamespaces.count)
    }

    func summary() -> Melix_Controlplane_V1_MCPToolCatalogSummary {
        var summary = Melix_Controlplane_V1_MCPToolCatalogSummary()
        summary.configPath = configPath
        summary.defaultParserMode = defaultParserMode.rawValue
        summary.enabledSourceCount = enabledSourceCount
        summary.resolvedToolCount = resolvedToolCount
        summary.sources = sources.map { source in
            var item = Melix_Controlplane_V1_MCPToolSourceSummary()
            item.sourceID = source.sourceID
            item.enabled = source.enabled
            item.namespaces = source.namespaces
            item.toolCount = UInt32(source.namespaces.count)
            return item
        }
        return summary
    }
}
