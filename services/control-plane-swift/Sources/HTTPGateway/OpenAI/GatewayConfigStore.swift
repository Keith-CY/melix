import Foundation
import MelixControlPlaneProtocol

public enum GatewayConfigValidationError: Error, Equatable, Sendable {
    case missingServerSessionID
    case missingHost
    case invalidPort
    case missingDefaultModelID
    case missingServedModelIDs
    case defaultModelNotServed
    case duplicateServedModelID
    case invalidRateLimit
    case invalidTimeout

    public var code: String {
        switch self {
        case .missingServerSessionID:
            return "missing_server_session_id"
        case .missingHost:
            return "missing_host"
        case .invalidPort:
            return "invalid_port"
        case .missingDefaultModelID:
            return "missing_default_model_id"
        case .missingServedModelIDs:
            return "missing_served_model_ids"
        case .defaultModelNotServed:
            return "default_model_not_served"
        case .duplicateServedModelID:
            return "duplicate_served_model_id"
        case .invalidRateLimit:
            return "invalid_rate_limit"
        case .invalidTimeout:
            return "invalid_timeout"
        }
    }

    public var message: String {
        switch self {
        case .missingServerSessionID:
            return "Gateway config requires a server session identifier."
        case .missingHost:
            return "Gateway config requires a non-empty host."
        case .invalidPort:
            return "Gateway config requires a TCP port between 1 and 65535."
        case .missingDefaultModelID:
            return "Gateway config requires a default model identifier."
        case .missingServedModelIDs:
            return "Gateway config requires at least one served model identifier."
        case .defaultModelNotServed:
            return "Gateway config default model must be included in the served model roster."
        case .duplicateServedModelID:
            return "Gateway config served model identifiers must be unique."
        case .invalidRateLimit:
            return "Gateway config requires a positive rate limit."
        case .invalidTimeout:
            return "Gateway config requires a positive timeout."
        }
    }
}

public struct GatewayRuntimeBinding: Equatable, Sendable {
    public let activeServerSessionID: String
    public let host: String
    public let port: UInt32

    public init(
        activeServerSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        host: String,
        port: UInt32
    ) {
        self.activeServerSessionID = activeServerSessionID
        self.host = host
        self.port = port
    }
}

private struct GatewayConfigDefaults: Equatable, Sendable {
    let host: String
    let port: UInt32
    let rateLimitPerMinute: UInt32
    let timeoutSeconds: UInt32
    let modelIdleTimeoutSeconds: UInt32
    let source: Melix_Controlplane_V1_GatewayConfigSource
}

private struct PersistedGatewayListenerRecord: Codable, Equatable, Sendable {
    let serverSessionID: String
    let host: String
    let port: UInt32
    let defaultModelID: String
    let servedModelIDs: [String]
    let rateLimitPerMinute: UInt32
    let timeoutSeconds: UInt32
    let modelIdleTimeoutSeconds: UInt32
    let sourceRawValue: Int
    let updatedAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case serverSessionID = "server_session_id"
        case host
        case port
        case defaultModelID = "default_model_id"
        case servedModelIDs = "served_model_ids"
        case rateLimitPerMinute = "rate_limit_per_minute"
        case timeoutSeconds = "timeout_seconds"
        case modelIdleTimeoutSeconds = "model_idle_timeout_seconds"
        case sourceRawValue = "source"
        case updatedAtUnixMS = "updated_at_unix_ms"
    }

    init(
        serverSessionID: String,
        host: String,
        port: UInt32,
        defaultModelID: String,
        servedModelIDs: [String],
        rateLimitPerMinute: UInt32,
        timeoutSeconds: UInt32,
        modelIdleTimeoutSeconds: UInt32,
        sourceRawValue: Int,
        updatedAtUnixMS: Int64
    ) {
        self.serverSessionID = serverSessionID
        self.host = host
        self.port = port
        self.defaultModelID = defaultModelID
        self.servedModelIDs = servedModelIDs
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
        self.sourceRawValue = sourceRawValue
        self.updatedAtUnixMS = updatedAtUnixMS
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaultModelID = try container.decodeIfPresent(String.self, forKey: .defaultModelID) ?? ""
        let servedModelIDs = try container.decodeIfPresent([String].self, forKey: .servedModelIDs)
            ?? (defaultModelID.isEmpty ? [] : [defaultModelID])
        self.init(
            serverSessionID: try container.decode(String.self, forKey: .serverSessionID),
            host: try container.decode(String.self, forKey: .host),
            port: try container.decode(UInt32.self, forKey: .port),
            defaultModelID: defaultModelID,
            servedModelIDs: servedModelIDs,
            rateLimitPerMinute: try container.decode(UInt32.self, forKey: .rateLimitPerMinute),
            timeoutSeconds: try container.decode(UInt32.self, forKey: .timeoutSeconds),
            modelIdleTimeoutSeconds: try container.decodeIfPresent(
                UInt32.self,
                forKey: .modelIdleTimeoutSeconds
            ) ?? 0,
            sourceRawValue: try container.decode(Int.self, forKey: .sourceRawValue),
            updatedAtUnixMS: try container.decode(Int64.self, forKey: .updatedAtUnixMS)
        )
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(serverSessionID, forKey: .serverSessionID)
        try container.encode(host, forKey: .host)
        try container.encode(port, forKey: .port)
        try container.encode(defaultModelID, forKey: .defaultModelID)
        try container.encode(servedModelIDs, forKey: .servedModelIDs)
        try container.encode(rateLimitPerMinute, forKey: .rateLimitPerMinute)
        try container.encode(timeoutSeconds, forKey: .timeoutSeconds)
        try container.encode(modelIdleTimeoutSeconds, forKey: .modelIdleTimeoutSeconds)
        try container.encode(sourceRawValue, forKey: .sourceRawValue)
        try container.encode(updatedAtUnixMS, forKey: .updatedAtUnixMS)
    }

    var source: Melix_Controlplane_V1_GatewayConfigSource {
        Melix_Controlplane_V1_GatewayConfigSource(rawValue: sourceRawValue) ?? .operatorOverride
    }
}

private struct GatewayConfigDocument: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let listeners: [PersistedGatewayListenerRecord]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case listeners
    }
}

public actor GatewayConfigStore {
    private let storeURL: URL
    private let fileManager: FileManager
    private let nowUnixMS: @Sendable () -> Int64
    private let defaults: GatewayConfigDefaults
    private var recordsByServerSessionID: [String: PersistedGatewayListenerRecord]

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        nowUnixMS: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.fileManager = fileManager
        self.nowUnixMS = nowUnixMS
        self.storeURL = Self.resolveStoreURL(environment: environment)
        self.defaults = Self.resolveDefaults(environment: environment)
        self.recordsByServerSessionID = Self.loadRecords(from: storeURL, fileManager: fileManager)
    }

    public init(
        storeURL: URL,
        defaults: [String: String],
        fileManager: FileManager = .default,
        nowUnixMS: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.fileManager = fileManager
        self.nowUnixMS = nowUnixMS
        self.storeURL = storeURL
        self.defaults = Self.resolveDefaults(environment: defaults)
        self.recordsByServerSessionID = Self.loadRecords(from: storeURL, fileManager: fileManager)
    }

    public func bootstrapBinding(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> GatewayRuntimeBinding {
        let resolvedServerSessionID = Self.trimmed(serverSessionID).isEmpty
            ? ServerSessionRuntimeStore.defaultServerSessionID
            : Self.trimmed(serverSessionID)
        let record = recordsByServerSessionID[resolvedServerSessionID]
        return GatewayRuntimeBinding(
            activeServerSessionID: resolvedServerSessionID,
            host: record?.host ?? defaults.host,
            port: record?.port ?? defaults.port
        )
    }

    public func storePath() -> String {
        storeURL.path
    }

    func apply(
        command: Melix_Controlplane_V1_ApplyGatewayConfig
    ) throws {
        let serverSessionID = Self.trimmed(command.serverSessionID)
        guard !serverSessionID.isEmpty else {
            throw GatewayConfigValidationError.missingServerSessionID
        }

        let host = Self.trimmed(command.host)
        guard !host.isEmpty else {
            throw GatewayConfigValidationError.missingHost
        }
        guard command.port > 0, command.port <= UInt32(UInt16.max) else {
            throw GatewayConfigValidationError.invalidPort
        }

        let defaultModelID = Self.trimmed(command.defaultModelID)
        guard !defaultModelID.isEmpty else {
            throw GatewayConfigValidationError.missingDefaultModelID
        }
        let servedModelIDs = try Self.normalizedServedModelIDs(
            command.servedModelIds,
            defaultModelID: defaultModelID
        )
        guard command.rateLimitPerMinute > 0 else {
            throw GatewayConfigValidationError.invalidRateLimit
        }
        guard command.timeoutSeconds > 0 else {
            throw GatewayConfigValidationError.invalidTimeout
        }

        let record = PersistedGatewayListenerRecord(
            serverSessionID: serverSessionID,
            host: host,
            port: command.port,
            defaultModelID: defaultModelID,
            servedModelIDs: servedModelIDs,
            rateLimitPerMinute: command.rateLimitPerMinute,
            timeoutSeconds: command.timeoutSeconds,
            modelIdleTimeoutSeconds: command.modelIdleTimeoutSeconds,
            sourceRawValue: Melix_Controlplane_V1_GatewayConfigSource.operatorOverride.rawValue,
            updatedAtUnixMS: nowUnixMS()
        )
        recordsByServerSessionID[serverSessionID] = record
        try writeRecords()
    }

    public func summary(
        serverSessionIDs: [String],
        runtimeBinding: GatewayRuntimeBinding,
        fallbackDefaultModelID: String
    ) -> Melix_Controlplane_V1_GatewayConfigSummary {
        var summary = Melix_Controlplane_V1_GatewayConfigSummary()
        let resolvedFallbackModelID = Self.trimmed(fallbackDefaultModelID)

        let allServerSessionIDs = Set(
            serverSessionIDs.map(Self.trimmed).filter { !$0.isEmpty }
            + recordsByServerSessionID.keys
            + [runtimeBinding.activeServerSessionID]
        )

        summary.listeners = allServerSessionIDs.sorted().map { serverSessionID in
            let record = recordsByServerSessionID[serverSessionID]
            let requestedHost = record?.host ?? defaults.host
            let requestedPort = record?.port ?? defaults.port
            let defaultModelID = record?.defaultModelID ?? resolvedFallbackModelID
            let servedModelIDs = record?.servedModelIDs ?? (defaultModelID.isEmpty ? [] : [defaultModelID])
            let rateLimitPerMinute = record?.rateLimitPerMinute ?? defaults.rateLimitPerMinute
            let timeoutSeconds = record?.timeoutSeconds ?? defaults.timeoutSeconds
            let modelIdleTimeoutSeconds = record?.modelIdleTimeoutSeconds ?? defaults.modelIdleTimeoutSeconds
            let isActiveBinding = serverSessionID == runtimeBinding.activeServerSessionID

            var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
            listener.serverSessionID = serverSessionID
            listener.requestedHost = requestedHost
            listener.requestedPort = requestedPort
            listener.effectiveHost = isActiveBinding ? runtimeBinding.host : requestedHost
            listener.effectivePort = isActiveBinding ? runtimeBinding.port : requestedPort
            listener.defaultModelID = defaultModelID
            listener.servedModelIds = servedModelIDs
            listener.rateLimitPerMinute = rateLimitPerMinute
            listener.timeoutSeconds = timeoutSeconds
            listener.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
            listener.source = record?.source ?? defaults.source
            listener.activeBinding = isActiveBinding
            listener.requiresRestart = isActiveBinding
                && (requestedHost != runtimeBinding.host || requestedPort != runtimeBinding.port)
            listener.updatedAtUnixMs = record?.updatedAtUnixMS ?? 0
            return listener
        }
        return summary
    }

    public func activeModelRoster(
        runtimeBinding: GatewayRuntimeBinding,
        fallbackDefaultModelID: String,
        fallbackServedModelIDs: [String]
    ) -> (defaultModelID: String, servedModelIDs: [String], modelIdleTimeoutSeconds: UInt32, explicit: Bool) {
        let record = recordsByServerSessionID[runtimeBinding.activeServerSessionID]
        let defaultModelID = record?.defaultModelID ?? Self.trimmed(fallbackDefaultModelID)
        let servedModelIDs = record?.servedModelIDs
            ?? Self.normalizedFallbackServedModelIDs(fallbackServedModelIDs, defaultModelID: defaultModelID)
        return (
            defaultModelID: defaultModelID,
            servedModelIDs: servedModelIDs,
            modelIdleTimeoutSeconds: record?.modelIdleTimeoutSeconds ?? defaults.modelIdleTimeoutSeconds,
            explicit: record != nil
        )
    }

    public func activeModelRosterIfConfigured(
        runtimeBinding: GatewayRuntimeBinding
    ) -> (defaultModelID: String, servedModelIDs: [String], modelIdleTimeoutSeconds: UInt32)? {
        guard let record = recordsByServerSessionID[runtimeBinding.activeServerSessionID] else {
            return nil
        }
        return (
            defaultModelID: record.defaultModelID,
            servedModelIDs: record.servedModelIDs,
            modelIdleTimeoutSeconds: record.modelIdleTimeoutSeconds
        )
    }

    private func writeRecords() throws {
        let document = GatewayConfigDocument(
            schemaVersion: 1,
            listeners: recordsByServerSessionID.values.sorted { lhs, rhs in
                lhs.serverSessionID < rhs.serverSessionID
            }
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(document)
        try fileManager.createDirectory(
            at: storeURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: storeURL, options: .atomic)
    }

    private static func loadRecords(
        from storeURL: URL,
        fileManager: FileManager
    ) -> [String: PersistedGatewayListenerRecord] {
        guard fileManager.fileExists(atPath: storeURL.path) else {
            return [:]
        }
        guard
            let data = try? Data(contentsOf: storeURL),
            let document = try? JSONDecoder().decode(GatewayConfigDocument.self, from: data)
        else {
            return [:]
        }
        return Dictionary(uniqueKeysWithValues: document.listeners.map { ($0.serverSessionID, $0) })
    }

    private static func resolveDefaults(environment: [String: String]) -> GatewayConfigDefaults {
        let builtInHost = "127.0.0.1"
        let builtInPort: UInt32 = 11_434
        let builtInRateLimit: UInt32 = 120
        let builtInTimeout: UInt32 = 120
        let builtInModelIdleTimeout: UInt32 = 600

        let envHost = trimmed(environment["MELIX_HTTP_HOST"])
        let envPort = UInt32(trimmed(environment["MELIX_HTTP_PORT"])) ?? 0
        let envRateLimit = UInt32(trimmed(environment["MELIX_GATEWAY_RATE_LIMIT_PER_MINUTE"])) ?? 0
        let envTimeout = UInt32(trimmed(environment["MELIX_GATEWAY_TIMEOUT_SECONDS"])) ?? 0
        let envModelIdleTimeout = UInt32(trimmed(environment["MELIX_MODEL_IDLE_TIMEOUT_SECONDS"])) ?? 0

        let usesEnvironmentDefaults = !envHost.isEmpty
            || envPort > 0
            || envRateLimit > 0
            || envTimeout > 0
            || envModelIdleTimeout > 0

        return GatewayConfigDefaults(
            host: envHost.isEmpty ? builtInHost : envHost,
            port: envPort > 0 ? envPort : builtInPort,
            rateLimitPerMinute: envRateLimit > 0 ? envRateLimit : builtInRateLimit,
            timeoutSeconds: envTimeout > 0 ? envTimeout : builtInTimeout,
            modelIdleTimeoutSeconds: envModelIdleTimeout > 0 ? envModelIdleTimeout : builtInModelIdleTimeout,
            source: usesEnvironmentDefaults ? .environmentDefaults : .builtInDefaults
        )
    }

    private static func normalizedServedModelIDs(
        _ rawModelIDs: [String],
        defaultModelID: String
    ) throws -> [String] {
        var orderedIDs = rawModelIDs.map(trimmed).filter { !$0.isEmpty }
        if orderedIDs.isEmpty {
            orderedIDs = [defaultModelID]
        }
        guard !orderedIDs.isEmpty else {
            throw GatewayConfigValidationError.missingServedModelIDs
        }
        var seen: Set<String> = []
        for modelID in orderedIDs {
            guard seen.insert(modelID).inserted else {
                throw GatewayConfigValidationError.duplicateServedModelID
            }
        }
        guard seen.contains(defaultModelID) else {
            throw GatewayConfigValidationError.defaultModelNotServed
        }
        return orderedIDs
    }

    private static func normalizedFallbackServedModelIDs(
        _ rawModelIDs: [String],
        defaultModelID: String
    ) -> [String] {
        var orderedIDs: [String] = []
        var seen: Set<String> = []
        for modelID in rawModelIDs.map(trimmed).filter({ !$0.isEmpty }) {
            guard seen.insert(modelID).inserted else {
                continue
            }
            orderedIDs.append(modelID)
        }
        if !defaultModelID.isEmpty, !seen.contains(defaultModelID) {
            orderedIDs.insert(defaultModelID, at: 0)
        }
        return orderedIDs
    }

    private static func resolveStoreURL(environment: [String: String]) -> URL {
        let configuredPath = trimmed(environment["MELIX_GATEWAY_CONFIG_STORE_PATH"])
        if !configuredPath.isEmpty {
            return URL(fileURLWithPath: configuredPath)
        }
        return MelixPathLayout(environment: environment).gatewayConfigStoreURL
    }

    private static func trimmed(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
