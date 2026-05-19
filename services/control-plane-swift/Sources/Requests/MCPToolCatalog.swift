import Foundation
import MelixControlPlaneProtocol

public struct MCPToolCatalog: Sendable, Equatable {
    public enum DiscoverySource: String, Sendable, Equatable {
        case none
        case environment
        case melixHome
        case explicit
    }

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

    public struct PolicyReceipt: Sendable, Equatable {
        public let requestedPolicy: String
        public let effectivePolicy: String
        public let operatorOverrideSource: String
        public let refusedNamespaces: [String]

        public static let `default` = PolicyReceipt(
            requestedPolicy: "default_block_high_risk",
            effectivePolicy: "block_high_risk",
            operatorOverrideSource: "",
            refusedNamespaces: []
        )
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
    public let discoverySource: DiscoverySource
    public let defaultParserMode: ToolParserMode
    public let sources: [Source]
    public let policyReceipt: PolicyReceipt

    public static let empty = MCPToolCatalog()

    public init(
        configPath: String = "",
        discoverySource: DiscoverySource = .none,
        defaultParserMode: ToolParserMode = .json,
        sources: [Source] = [],
        policyReceipt: PolicyReceipt = .default
    ) {
        self.configPath = configPath.trimmingCharacters(in: .whitespacesAndNewlines)
        self.discoverySource = self.configPath.isEmpty
            ? .none
            : (discoverySource == .none ? .explicit : discoverySource)
        self.defaultParserMode = defaultParserMode
        self.policyReceipt = policyReceipt
        let refused = Set(policyReceipt.refusedNamespaces)
        self.sources = sources.compactMap { source in
            let namespaces = source.namespaces.filter { !refused.contains($0) }
            guard !source.sourceID.isEmpty && !namespaces.isEmpty else {
                return nil
            }
            return Source(
                sourceID: source.sourceID,
                enabled: source.enabled,
                namespaces: namespaces
            )
        }.sorted { $0.sourceID < $1.sourceID }
    }

    public static func load(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> MCPToolCatalog {
        if
            let configPath = environment["MELIX_MCP_CONFIG_PATH"]?.trimmingCharacters(in: .whitespacesAndNewlines),
            !configPath.isEmpty
        {
            return load(configPath: configPath, discoverySource: .environment, environment: environment)
        }

        let melixHomeConfig = MelixPathLayout(environment: environment)
            .configDirectoryURL
            .appendingPathComponent("mcp-tools.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: melixHomeConfig.path) else {
            return .empty
        }
        return load(configPath: melixHomeConfig.path, discoverySource: .melixHome, environment: environment)
    }

    public static func load(
        configPath: String,
        discoverySource: DiscoverySource = .explicit,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> MCPToolCatalog {
        let trimmedPath = configPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard
            !trimmedPath.isEmpty,
            let data = try? Data(contentsOf: URL(fileURLWithPath: trimmedPath)),
            let payload = try? JSONDecoder().decode(FilePayload.self, from: data)
        else {
            return MCPToolCatalog(configPath: trimmedPath, discoverySource: discoverySource)
        }

        let registry = ToolParserRegistry()
        let defaultMode = payload.defaultParserMode
            .flatMap { registry.mode(for: $0) } ?? .json
        let policyReceipt = Self.policyReceipt(
            for: payload.sources,
            environment: environment
        )
        return MCPToolCatalog(
            configPath: trimmedPath,
            discoverySource: discoverySource,
            defaultParserMode: defaultMode,
            sources: payload.sources,
            policyReceipt: policyReceipt
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

    public var refusedNamespaceCount: UInt32 {
        UInt32(policyReceipt.refusedNamespaces.count)
    }

    func summary() -> Melix_Controlplane_V1_MCPToolCatalogSummary {
        var summary = Melix_Controlplane_V1_MCPToolCatalogSummary()
        summary.configPath = configPath
        summary.defaultParserMode = defaultParserMode.rawValue
        summary.enabledSourceCount = enabledSourceCount
        summary.resolvedToolCount = resolvedToolCount
        summary.requestedPolicy = policyReceipt.requestedPolicy
        summary.effectivePolicy = policyReceipt.effectivePolicy
        summary.operatorOverrideSource = policyReceipt.operatorOverrideSource
        summary.refusedNamespaces = policyReceipt.refusedNamespaces
        summary.sources = [discoveryReceiptSource()] + sources.map { source in
            var item = Melix_Controlplane_V1_MCPToolSourceSummary()
            item.sourceID = source.sourceID
            item.enabled = source.enabled
            item.namespaces = source.namespaces
            item.toolCount = UInt32(source.namespaces.count)
            item.policyState = "allowed"
            return item
        }
        return summary
    }

    private func discoveryReceiptSource() -> Melix_Controlplane_V1_MCPToolSourceSummary {
        var item = Melix_Controlplane_V1_MCPToolSourceSummary()
        item.sourceID = "config-discovery"
        item.enabled = !configPath.isEmpty
        item.namespaces = [discoverySource.rawValue]
        item.toolCount = 0
        item.policyState = configPath.isEmpty ? "not_configured" : "explicit_or_melix_home_only"
        return item
    }

    private static func policyReceipt(
        for sources: [Source],
        environment: [String: String]
    ) -> PolicyReceipt {
        let allowlistedNamespaces = Set(namespaceList(environment["MELIX_MCP_HIGH_RISK_ALLOWLIST"]))
        let allowlistEnabled = !allowlistedNamespaces.isEmpty
        let requestedPolicy = allowlistEnabled ? "operator_allowlist" : "default_block_high_risk"
        let refused = sources
            .filter(\.enabled)
            .flatMap(\.namespaces)
            .filter { isHighRiskNamespace($0) && !allowlistedNamespaces.contains($0) }
        let deduplicatedRefusals = deduplicate(refused).sorted()
        return PolicyReceipt(
            requestedPolicy: requestedPolicy,
            effectivePolicy: deduplicatedRefusals.isEmpty ? "allow_configured" : "block_high_risk",
            operatorOverrideSource: allowlistEnabled ? "MELIX_MCP_HIGH_RISK_ALLOWLIST" : "",
            refusedNamespaces: deduplicatedRefusals
        )
    }

    private static func namespaceList(_ rawValue: String?) -> [String] {
        (rawValue ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func deduplicate(_ values: [String]) -> [String] {
        var seen = Set<String>()
        var output: [String] = []
        for value in values where seen.insert(value).inserted {
            output.append(value)
        }
        return output
    }

    private static func isHighRiskNamespace(_ namespace: String) -> Bool {
        let normalized = namespace.lowercased()
        return highRiskMarkers.contains { normalized.contains($0) }
    }

    private static let highRiskMarkers = [
        "shell",
        "exec",
        "execute",
        "terminal",
        "process",
        "subprocess",
        "eval",
        "filesystem.write",
        "fs.write",
        "file.write",
        "network.upload",
        "upload",
    ]
}
