import Darwin
import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public struct MCPToolCatalog: Sendable, Equatable {
    public enum DiscoverySource: String, Sendable, Equatable {
        case none
        case environment
        case melixHome
        case explicit
    }

    public enum ConfigurationState: String, Sendable, Equatable {
        case notConfigured = "not_configured"
        case loaded
        case unreadable = "config_unreadable"
        case invalid = "config_invalid"
    }

    public struct Source: Sendable, Codable, Equatable {
        public struct StdioTransport: Sendable, Codable, Equatable {
            public let command: String
            public let arguments: [String]
            public let workingDirectory: String
            public let environmentReferences: [String: String]

            enum CodingKeys: String, CodingKey {
                case command
                case arguments
                case workingDirectory = "working_directory"
                case environmentReferences = "environment_references"
            }

            public init(
                command: String,
                arguments: [String] = [],
                workingDirectory: String = "",
                environmentReferences: [String: String] = [:]
            ) {
                self.command = command.trimmingCharacters(in: .whitespacesAndNewlines)
                self.arguments = arguments
                self.workingDirectory = workingDirectory.trimmingCharacters(in: .whitespacesAndNewlines)
                self.environmentReferences = environmentReferences
            }
        }

        public struct StreamableHTTPTransport: Sendable, Codable, Equatable {
            public let url: String
            public let headers: [String: String]
            public let headerEnvironmentReferences: [String: String]

            enum CodingKeys: String, CodingKey {
                case url
                case headers
                case headerEnvironmentReferences = "header_environment_references"
            }

            public init(
                url: String,
                headers: [String: String] = [:],
                headerEnvironmentReferences: [String: String] = [:]
            ) {
                self.url = url.trimmingCharacters(in: .whitespacesAndNewlines)
                self.headers = headers
                self.headerEnvironmentReferences = headerEnvironmentReferences
            }
        }

        public enum Transport: Sendable, Codable, Equatable {
            case stdio(StdioTransport)
            case streamableHTTP(StreamableHTTPTransport)

            private enum CodingKeys: String, CodingKey {
                case kind
                case command
                case arguments
                case workingDirectory = "working_directory"
                case environmentReferences = "environment_references"
                case url
                case headers
                case headerEnvironmentReferences = "header_environment_references"
            }

            private enum Kind: String, Codable {
                case stdio
                case streamableHTTP = "streamable_http"
            }

            public init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                switch try container.decode(Kind.self, forKey: .kind) {
                case .stdio:
                    guard
                        !container.contains(.url),
                        !container.contains(.headers),
                        !container.contains(.headerEnvironmentReferences)
                    else {
                        throw DecodingError.dataCorruptedError(
                            forKey: .kind,
                            in: container,
                            debugDescription: "stdio transport contains HTTP-only fields"
                        )
                    }
                    self = .stdio(
                        StdioTransport(
                            command: try container.decode(String.self, forKey: .command),
                            arguments: try container.decodeIfPresentRejectingNull(
                                [String].self,
                                forKey: .arguments
                            ) ?? [],
                            workingDirectory: try container.decodeIfPresentRejectingNull(
                                String.self,
                                forKey: .workingDirectory
                            ) ?? "",
                            environmentReferences: try container.decodeIfPresentRejectingNull(
                                [String: String].self,
                                forKey: .environmentReferences
                            ) ?? [:]
                        )
                    )
                case .streamableHTTP:
                    guard
                        !container.contains(.command),
                        !container.contains(.arguments),
                        !container.contains(.workingDirectory),
                        !container.contains(.environmentReferences)
                    else {
                        throw DecodingError.dataCorruptedError(
                            forKey: .kind,
                            in: container,
                            debugDescription: "streamable_http transport contains stdio-only fields"
                        )
                    }
                    self = .streamableHTTP(
                        StreamableHTTPTransport(
                            url: try container.decode(String.self, forKey: .url),
                            headers: try container.decodeIfPresentRejectingNull(
                                [String: String].self,
                                forKey: .headers
                            ) ?? [:],
                            headerEnvironmentReferences: try container.decodeIfPresentRejectingNull(
                                [String: String].self,
                                forKey: .headerEnvironmentReferences
                            ) ?? [:]
                        )
                    )
                }
            }

            public func encode(to encoder: Encoder) throws {
                var container = encoder.container(keyedBy: CodingKeys.self)
                switch self {
                case .stdio(let transport):
                    try container.encode(Kind.stdio, forKey: .kind)
                    try container.encode(transport.command, forKey: .command)
                    try container.encode(transport.arguments, forKey: .arguments)
                    try container.encode(transport.workingDirectory, forKey: .workingDirectory)
                    try container.encode(transport.environmentReferences, forKey: .environmentReferences)
                case .streamableHTTP(let transport):
                    try container.encode(Kind.streamableHTTP, forKey: .kind)
                    try container.encode(transport.url, forKey: .url)
                    try container.encode(transport.headers, forKey: .headers)
                    try container.encode(
                        transport.headerEnvironmentReferences,
                        forKey: .headerEnvironmentReferences
                    )
                }
            }
        }

        public let sourceID: String
        public let enabled: Bool
        public let namespaces: [String]
        public let transport: Transport?
        public let requestTimeoutMs: UInt32
        public let connectTimeoutMs: UInt32
        public let maxResultBytes: UInt64
        public let redactionTerms: [String]
        public let configurationRevision: String

        enum CodingKeys: String, CodingKey {
            case sourceID = "source_id"
            case enabled
            case namespaces
            case transport
            case requestTimeoutMs = "request_timeout_ms"
            case connectTimeoutMs = "connect_timeout_ms"
            case maxResultBytes = "max_result_bytes"
            case redactionTerms = "redaction_terms"
            case configurationRevision = "configuration_revision"
        }

        public init(
            sourceID: String,
            enabled: Bool = true,
            namespaces: [String] = [],
            transport: Transport? = nil,
            requestTimeoutMs: UInt32 = 30_000,
            connectTimeoutMs: UInt32 = 15_000,
            maxResultBytes: UInt64 = 262_144,
            redactionTerms: [String] = [],
            configurationRevision: String = ""
        ) {
            self.sourceID = Self.normalizeSourceID(sourceID)
            self.enabled = enabled
            self.namespaces = Self.normalizeNamespaces(namespaces)
            self.transport = transport
            self.requestTimeoutMs = max(1, requestTimeoutMs)
            self.connectTimeoutMs = max(1, connectTimeoutMs)
            self.maxResultBytes = max(1_024, maxResultBytes)
            self.redactionTerms = redactionTerms.filter { !$0.isEmpty }
            self.configurationRevision = configurationRevision.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.init(
                sourceID: try container.decode(String.self, forKey: .sourceID),
                enabled: try container.decodeIfPresentRejectingNull(Bool.self, forKey: .enabled) ?? true,
                namespaces: try container.decodeIfPresentRejectingNull([String].self, forKey: .namespaces) ?? [],
                transport: try container.decodeIfPresentRejectingNull(Transport.self, forKey: .transport),
                requestTimeoutMs: try container.decodeIfPresentRejectingNull(
                    UInt32.self,
                    forKey: .requestTimeoutMs
                ) ?? 30_000,
                connectTimeoutMs: try container.decodeIfPresentRejectingNull(
                    UInt32.self,
                    forKey: .connectTimeoutMs
                ) ?? 15_000,
                maxResultBytes: try container.decodeIfPresentRejectingNull(
                    UInt64.self,
                    forKey: .maxResultBytes
                ) ?? 262_144,
                redactionTerms: try container.decodeIfPresentRejectingNull(
                    [String].self,
                    forKey: .redactionTerms
                ) ?? [],
                configurationRevision: try container.decodeIfPresentRejectingNull(
                    String.self,
                    forKey: .configurationRevision
                ) ?? ""
            )
        }

        public var hasLiveTransport: Bool {
            transport != nil
        }

        public func workerConfig() -> Melix_Worker_V1_AgentToolSourceConfig? {
            guard let transport else {
                return nil
            }
            var config = Melix_Worker_V1_AgentToolSourceConfig()
            config.sourceID = sourceID
            config.enabled = enabled
            config.requestTimeoutMs = requestTimeoutMs
            config.connectTimeoutMs = connectTimeoutMs
            config.maxResultBytes = maxResultBytes
            config.redactionTerms = redactionTerms
            config.configurationRevision = configurationRevision
            switch transport {
            case .stdio(let stdio):
                config.stdio.command = stdio.command
                config.stdio.arguments = stdio.arguments
                config.stdio.workingDirectory = stdio.workingDirectory
                config.stdio.environmentReferences = stdio.environmentReferences
            case .streamableHTTP(let http):
                config.streamableHTTP.url = http.url
                config.streamableHTTP.headers = http.headers
                config.streamableHTTP.headerEnvironmentReferences = http.headerEnvironmentReferences
            }
            return config
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

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            defaultParserMode = try container.decodeIfPresentRejectingNull(
                String.self,
                forKey: .defaultParserMode
            )
            sources = try container.decode([Source].self, forKey: .sources)
        }
    }

    private enum ConfigurationReadError: Error {
        case unreadable
        case invalid
    }

    public let configPath: String
    public let discoverySource: DiscoverySource
    public let configurationState: ConfigurationState
    public let defaultParserMode: ToolParserMode
    public let sources: [Source]
    public let policyReceipt: PolicyReceipt

    public static let empty = MCPToolCatalog()

    public static func configurationDataPassesPreflight(_ data: Data) -> Bool {
        configurationPayload(from: data) != nil
    }

    public init(
        configPath: String = "",
        discoverySource: DiscoverySource = .none,
        configurationState: ConfigurationState? = nil,
        defaultParserMode: ToolParserMode = .json,
        sources: [Source] = [],
        policyReceipt: PolicyReceipt = .default
    ) {
        self.configPath = configPath.trimmingCharacters(in: .whitespacesAndNewlines)
        self.discoverySource = self.configPath.isEmpty
            ? .none
            : (discoverySource == .none ? .explicit : discoverySource)
        self.configurationState = configurationState
            ?? (self.configPath.isEmpty ? .notConfigured : .loaded)
        self.defaultParserMode = defaultParserMode
        self.policyReceipt = policyReceipt
        let refused = Set(policyReceipt.refusedNamespaces)
        self.sources = sources.compactMap { source in
            let namespaces = source.namespaces.filter { !refused.contains($0) }
            guard
                !source.sourceID.isEmpty,
                !namespaces.isEmpty || source.hasLiveTransport
            else {
                return nil
            }
            return Source(
                sourceID: source.sourceID,
                enabled: source.enabled,
                namespaces: namespaces,
                transport: source.transport,
                requestTimeoutMs: source.requestTimeoutMs,
                connectTimeoutMs: source.connectTimeoutMs,
                maxResultBytes: source.maxResultBytes,
                redactionTerms: source.redactionTerms,
                configurationRevision: source.configurationRevision
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
        guard !trimmedPath.isEmpty else {
            return .empty
        }
        guard let resolvedPath = resolvedExplicitConfigPath(
            trimmedPath,
            environment: environment
        ) else {
            return MCPToolCatalog(
                configPath: trimmedPath,
                discoverySource: discoverySource,
                configurationState: .unreadable
            )
        }
        let data: Data
        do {
            data = try boundedConfigurationData(atPath: resolvedPath)
        } catch ConfigurationReadError.invalid {
            return MCPToolCatalog(
                configPath: resolvedPath,
                discoverySource: discoverySource,
                configurationState: .invalid
            )
        } catch {
            return MCPToolCatalog(
                configPath: resolvedPath,
                discoverySource: discoverySource,
                configurationState: .unreadable
            )
        }
        guard let payload = configurationPayload(from: data) else {
            return MCPToolCatalog(
                configPath: resolvedPath,
                discoverySource: discoverySource,
                configurationState: .invalid
            )
        }

        let registry = ToolParserRegistry()
        let defaultMode = payload.defaultParserMode
            .flatMap { registry.mode(for: $0) } ?? .json
        let policyReceipt = Self.policyReceipt(
            for: payload.sources,
            environment: environment
        )
        return MCPToolCatalog(
            configPath: resolvedPath,
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

    public var liveSourceConfigs: [Melix_Worker_V1_AgentToolSourceConfig] {
        sources.compactMap { $0.workerConfig() }
    }

    public var refusedNamespaceCount: UInt32 {
        UInt32(policyReceipt.refusedNamespaces.count)
    }

    public var configurationErrorCode: String? {
        switch configurationState {
        case .unreadable, .invalid:
            configurationState.rawValue
        case .notConfigured, .loaded:
            nil
        }
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
            item.policyState = source.hasLiveTransport
                ? "live_transport_configured"
                : "catalog_only"
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
        item.policyState = configurationState.rawValue
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

    private static func resolvedExplicitConfigPath(
        _ path: String,
        environment: [String: String]
    ) -> String? {
        guard path.utf8.count <= maximumExplicitConfigPathBytes,
              !path.contains("\0")
        else {
            return nil
        }

        let expandedPath: String
        if path == "~" || path.hasPrefix("~/") {
            let configuredHome = environment["HOME"]?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let homePath: String
            if let configuredHome,
               !configuredHome.isEmpty,
               (configuredHome as NSString).isAbsolutePath
            {
                homePath = configuredHome
            } else {
                homePath = FileManager.default.homeDirectoryForCurrentUser.path
            }
            expandedPath = path == "~"
                ? homePath
                : URL(fileURLWithPath: homePath, isDirectory: true)
                    .appendingPathComponent(String(path.dropFirst(2)), isDirectory: false)
                    .path
        } else {
            guard !path.hasPrefix("~"), (path as NSString).isAbsolutePath else {
                return nil
            }
            expandedPath = path
        }

        return URL(fileURLWithPath: expandedPath, isDirectory: false)
            .standardizedFileURL
            .path
    }

    /// Reads the active MCP configuration from the same descriptor that is
    /// classified and size-checked. The final path component cannot be a
    /// symlink, and non-regular files are opened non-blocking and rejected
    /// before any bytes are read.
    public static func boundedConfigurationData(atPath path: String) throws -> Data {
        try boundedConfigurationData(
            atPath: path,
            beforeOpeningResolvedURL: { _ in }
        )
    }

    static func boundedConfigurationData(
        atPath path: String,
        beforeOpeningResolvedURL: (URL) throws -> Void
    ) throws -> Data {
        let fileURL = URL(fileURLWithPath: path, isDirectory: false)
            .resolvingSymlinksInPath()
        do {
            try beforeOpeningResolvedURL(fileURL)
        } catch {
            throw ConfigurationReadError.unreadable
        }

        let descriptor = Darwin.open(
            fileURL.path,
            O_RDONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW
        )
        guard descriptor >= 0 else {
            throw ConfigurationReadError.unreadable
        }
        defer { _ = Darwin.close(descriptor) }

        var status = stat()
        guard Darwin.fstat(descriptor, &status) == 0 else {
            throw ConfigurationReadError.unreadable
        }
        guard
            (status.st_mode & S_IFMT) == S_IFREG,
            status.st_size >= 0,
            status.st_size <= off_t(maximumConfigurationBytes)
        else {
            throw ConfigurationReadError.invalid
        }

        do {
            let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
            let data = try handle.read(upToCount: maximumConfigurationBytes + 1) ?? Data()
            guard data.count <= maximumConfigurationBytes else {
                throw ConfigurationReadError.invalid
            }
            return data
        } catch let error as ConfigurationReadError {
            throw error
        } catch {
            throw ConfigurationReadError.unreadable
        }
    }

    private static func validatesConfigurationPayload(_ payload: FilePayload) -> Bool {
        guard payload.sources.count <= maximumConfigurationSources else {
            return false
        }

        var credentialSourceKeys = Set<String>()
        var sourceIDs = Set<String>()
        var credentialSourceKeyBytes = 0
        var referenceCount = 0
        var referenceTargetBytes = 0
        var httpHeaderCount = 0
        var httpHeaderNameBytes = 0

        for source in payload.sources {
            guard
                isValidSourceID(source.sourceID),
                sourceIDs.insert(source.sourceID).inserted
            else {
                return false
            }
            guard let transport = source.transport else {
                continue
            }

            let references: [String: String]
            switch transport {
            case .stdio(let stdio):
                guard
                    !stdio.command.isEmpty,
                    !stdio.command.contains("\0"),
                    stdio.workingDirectory.isEmpty || stdio.workingDirectory.hasPrefix("/")
                else {
                    return false
                }
                references = stdio.environmentReferences
                for childKey in references.keys where !isValidEnvironmentKey(childKey) {
                    return false
                }
            case .streamableHTTP(let http):
                guard isValidStreamableHTTPURL(http.url) else {
                    return false
                }
                for headerName in http.headers.keys where isCredentialHTTPHeaderName(headerName) {
                    return false
                }
                references = http.headerEnvironmentReferences
                let headerNames = Array(http.headers.keys) + Array(references.keys)
                var normalizedHeaderNames = Set<String>()
                for headerName in headerNames {
                    guard
                        isValidHTTPHeaderName(headerName),
                        normalizedHeaderNames.insert(headerName.lowercased()).inserted
                    else {
                        return false
                    }
                    httpHeaderCount += 1
                    httpHeaderNameBytes += headerName.utf8.count
                    if httpHeaderCount > 1 {
                        httpHeaderNameBytes += 1
                    }
                    guard
                        httpHeaderCount <= maximumCredentialReferences,
                        httpHeaderNameBytes <= maximumReferenceTargetListBytes
                    else {
                        return false
                    }
                }
            }

            for (targetName, sourceKey) in references {
                guard isValidEnvironmentKey(sourceKey) else {
                    return false
                }
                referenceCount += 1
                referenceTargetBytes += targetName.utf8.count
                if referenceCount > 1 {
                    referenceTargetBytes += 1
                }
                guard
                    referenceCount <= maximumCredentialReferences,
                    referenceTargetBytes <= maximumReferenceTargetListBytes
                else {
                    return false
                }

                if credentialSourceKeys.insert(sourceKey).inserted {
                    credentialSourceKeyBytes += sourceKey.utf8.count
                    if credentialSourceKeys.count > 1 {
                        credentialSourceKeyBytes += 1
                    }
                    guard
                        credentialSourceKeys.count <= maximumCredentialReferences,
                        credentialSourceKeyBytes <= maximumCredentialKeyListBytes
                    else {
                        return false
                    }
                }
            }
        }
        return true
    }

    private static func configurationPayload(from data: Data) -> FilePayload? {
        guard
            data.count <= maximumConfigurationBytes,
            JSONDuplicateKeyValidator.validates(data),
            let payload = try? JSONDecoder().decode(FilePayload.self, from: data),
            validatesConfigurationPayload(payload)
        else {
            return nil
        }
        return payload
    }

    private static func isValidSourceID(_ sourceID: String) -> Bool {
        let scalars = sourceID.unicodeScalars
        guard
            sourceID.utf8.count <= maximumSourceIDBytes,
            let first = scalars.first,
            isLowercaseASCII(first) || isDigitASCII(first)
        else {
            return false
        }
        return scalars.dropFirst().allSatisfy { scalar in
            isLowercaseASCII(scalar)
                || isDigitASCII(scalar)
                || scalar == "_"
                || scalar == "-"
        }
    }

    private static func isValidEnvironmentKey(_ key: String) -> Bool {
        let scalars = key.unicodeScalars
        guard
            key.utf8.count <= maximumCredentialKeyBytes,
            let first = scalars.first,
            isUppercaseASCII(first) || first == "_"
        else {
            return false
        }
        return scalars.dropFirst().allSatisfy { scalar in
            isUppercaseASCII(scalar) || isDigitASCII(scalar) || scalar == "_"
        }
    }

    private static func isValidHTTPHeaderName(_ name: String) -> Bool {
        let scalars = name.unicodeScalars
        guard
            name.utf8.count <= maximumReferenceTargetBytes,
            !scalars.isEmpty
        else {
            return false
        }
        return scalars.allSatisfy { scalar in
            isUppercaseASCII(scalar)
                || isLowercaseASCII(scalar)
                || isDigitASCII(scalar)
                || httpHeaderTokenPunctuation.contains(scalar)
        }
    }

    private static func isValidStreamableHTTPURL(_ value: String) -> Bool {
        guard
            !value.contains("#"),
            let components = URLComponents(string: value),
            let scheme = components.scheme?.lowercased(),
            ["http", "https"].contains(scheme),
            let encodedHost = components.host?.lowercased(),
            !encodedHost.isEmpty,
            components.user == nil,
            components.password == nil
        else {
            return false
        }
        let host = encodedHost.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        return scheme == "https" || loopbackHTTPHosts.contains(host)
    }

    private static func isCredentialHTTPHeaderName(_ name: String) -> Bool {
        let normalized = name.lowercased()
        return credentialHTTPHeaderMarkers.contains { normalized.contains($0) }
    }

    private static func isUppercaseASCII(_ scalar: UnicodeScalar) -> Bool {
        (65...90).contains(Int(scalar.value))
    }

    private static func isLowercaseASCII(_ scalar: UnicodeScalar) -> Bool {
        (97...122).contains(Int(scalar.value))
    }

    private static func isDigitASCII(_ scalar: UnicodeScalar) -> Bool {
        (48...57).contains(Int(scalar.value))
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

    private static let httpHeaderTokenPunctuation = Set("!#$%&'*+-.^_`|~".unicodeScalars)
    private static let maximumConfigurationBytes = 1_048_576
    private static let maximumConfigurationSources = 256
    private static let maximumCredentialReferences = 1_024
    private static let maximumCredentialKeyBytes = 255
    private static let maximumCredentialKeyListBytes = 32_768
    private static let maximumReferenceTargetBytes = 255
    private static let maximumReferenceTargetListBytes = 32_768
    private static let maximumSourceIDBytes = 64
    private static let loopbackHTTPHosts: Set<String> = ["127.0.0.1", "::1", "localhost"]
    private static let credentialHTTPHeaderMarkers = [
        "authorization",
        "cookie",
        "credential",
        "password",
        "privatekey",
        "private-key",
        "private_key",
        "secret",
        "signature",
        "token",
        "apikey",
        "api-key",
        "api_key",
    ]
    private static let maximumExplicitConfigPathBytes = 4_096
}

private extension KeyedDecodingContainer {
    func decodeIfPresentRejectingNull<T: Decodable>(
        _ type: T.Type,
        forKey key: Key
    ) throws -> T? {
        guard contains(key) else {
            return nil
        }
        guard try !decodeNil(forKey: key) else {
            throw DecodingError.dataCorruptedError(
                forKey: key,
                in: self,
                debugDescription: "explicit null is not valid for a known MCP configuration field"
            )
        }
        return try decode(type, forKey: key)
    }
}

private struct JSONDuplicateKeyValidator {
    private let bytes: [UInt8]
    private var index = 0
    private var remainingValueTokens = 16_384
    private var remainingObjectMembers = 8_192

    static func validates(_ data: Data) -> Bool {
        var parser = JSONDuplicateKeyValidator(bytes: Array(data))
        return parser.parseDocument()
    }

    private mutating func parseDocument() -> Bool {
        skipWhitespace()
        guard parseValue(depth: 1) else {
            return false
        }
        skipWhitespace()
        return index == bytes.count
    }

    private mutating func parseValue(depth: Int) -> Bool {
        skipWhitespace()
        guard
            depth <= 128,
            remainingValueTokens > 0,
            index < bytes.count
        else {
            return false
        }
        remainingValueTokens -= 1
        switch bytes[index] {
        case UInt8(ascii: "{"):
            return parseObject(depth: depth)
        case UInt8(ascii: "["):
            return parseArray(depth: depth)
        case UInt8(ascii: "\""):
            return parseStringToken() != nil
        default:
            return parsePrimitive()
        }
    }

    private mutating func parseObject(depth: Int) -> Bool {
        index += 1
        skipWhitespace()
        if consume(UInt8(ascii: "}")) {
            return true
        }

        var keys = Set<String>()
        while true {
            skipWhitespace()
            guard
                remainingObjectMembers > 0,
                let token = parseStringToken(),
                let key = try? JSONDecoder().decode(String.self, from: token),
                keys.insert(key).inserted
            else {
                return false
            }
            remainingObjectMembers -= 1
            skipWhitespace()
            guard consume(UInt8(ascii: ":")), parseValue(depth: depth + 1) else {
                return false
            }
            skipWhitespace()
            if consume(UInt8(ascii: "}")) {
                return true
            }
            guard consume(UInt8(ascii: ",")) else {
                return false
            }
        }
    }

    private mutating func parseArray(depth: Int) -> Bool {
        index += 1
        skipWhitespace()
        if consume(UInt8(ascii: "]")) {
            return true
        }

        while true {
            guard parseValue(depth: depth + 1) else {
                return false
            }
            skipWhitespace()
            if consume(UInt8(ascii: "]")) {
                return true
            }
            guard consume(UInt8(ascii: ",")) else {
                return false
            }
        }
    }

    private mutating func parseStringToken() -> Data? {
        guard index < bytes.count, bytes[index] == UInt8(ascii: "\"") else {
            return nil
        }
        let start = index
        index += 1
        while index < bytes.count {
            switch bytes[index] {
            case UInt8(ascii: "\""):
                index += 1
                return Data(bytes[start..<index])
            case UInt8(ascii: "\\"):
                index += 2
                if index > bytes.count {
                    return nil
                }
            default:
                index += 1
            }
        }
        return nil
    }

    private mutating func parsePrimitive() -> Bool {
        let start = index
        while index < bytes.count {
            switch bytes[index] {
            case UInt8(ascii: ","), UInt8(ascii: "]"), UInt8(ascii: "}"),
                 UInt8(ascii: " "), UInt8(ascii: "\t"), UInt8(ascii: "\n"),
                 UInt8(ascii: "\r"):
                return primitiveTokenIsLexicallyAllowed(start..<index)
            default:
                index += 1
            }
        }
        return primitiveTokenIsLexicallyAllowed(start..<index)
    }

    private func primitiveTokenIsLexicallyAllowed(_ range: Range<Int>) -> Bool {
        guard let first = range.first.map({ bytes[$0] }) else {
            return false
        }
        guard first == UInt8(ascii: "-") || (UInt8(ascii: "0")...UInt8(ascii: "9")).contains(first) else {
            return true
        }

        var cursor = range.lowerBound
        if bytes[cursor] == UInt8(ascii: "-") {
            cursor += 1
            guard cursor < range.upperBound else {
                return false
            }
        }
        if bytes[cursor] == UInt8(ascii: "0") {
            return cursor + 1 == range.upperBound
        }
        guard (UInt8(ascii: "1")...UInt8(ascii: "9")).contains(bytes[cursor]) else {
            return false
        }
        cursor += 1
        while cursor < range.upperBound {
            guard (UInt8(ascii: "0")...UInt8(ascii: "9")).contains(bytes[cursor]) else {
                return false
            }
            cursor += 1
        }
        return true
    }

    private mutating func skipWhitespace() {
        while index < bytes.count {
            switch bytes[index] {
            case UInt8(ascii: " "), UInt8(ascii: "\t"), UInt8(ascii: "\n"),
                 UInt8(ascii: "\r"):
                index += 1
            default:
                return
            }
        }
    }

    private mutating func consume(_ byte: UInt8) -> Bool {
        guard index < bytes.count, bytes[index] == byte else {
            return false
        }
        index += 1
        return true
    }
}
