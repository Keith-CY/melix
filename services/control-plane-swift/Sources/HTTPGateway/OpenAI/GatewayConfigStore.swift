import Foundation
import MelixControlPlaneProtocol

public enum GatewayConfigValidationError: Error, Equatable, Sendable {
    case missingServerSessionID
    case missingHost
    case invalidPort
    case missingServedModelID
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
        case .missingServedModelID:
            return "missing_served_model_id"
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
        case .missingServedModelID:
            return "Gateway config requires a served model identifier."
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
    let source: Melix_Controlplane_V1_GatewayConfigSource
}

private struct PersistedGatewayListenerRecord: Codable, Equatable, Sendable {
    let serverSessionID: String
    let host: String
    let port: UInt32
    let servedModelID: String
    let rateLimitPerMinute: UInt32
    let timeoutSeconds: UInt32
    let sourceRawValue: Int
    let updatedAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case serverSessionID = "server_session_id"
        case host
        case port
        case servedModelID = "served_model_id"
        case rateLimitPerMinute = "rate_limit_per_minute"
        case timeoutSeconds = "timeout_seconds"
        case sourceRawValue = "source"
        case updatedAtUnixMS = "updated_at_unix_ms"
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

        let servedModelID = Self.trimmed(command.servedModelID)
        guard !servedModelID.isEmpty else {
            throw GatewayConfigValidationError.missingServedModelID
        }
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
            servedModelID: servedModelID,
            rateLimitPerMinute: command.rateLimitPerMinute,
            timeoutSeconds: command.timeoutSeconds,
            sourceRawValue: Melix_Controlplane_V1_GatewayConfigSource.operatorOverride.rawValue,
            updatedAtUnixMS: nowUnixMS()
        )
        recordsByServerSessionID[serverSessionID] = record
        try writeRecords()
    }

    public func summary(
        serverSessionIDs: [String],
        runtimeBinding: GatewayRuntimeBinding,
        fallbackServedModelID: String
    ) -> Melix_Controlplane_V1_GatewayConfigSummary {
        var summary = Melix_Controlplane_V1_GatewayConfigSummary()
        let resolvedFallbackModelID = Self.trimmed(fallbackServedModelID)

        let allServerSessionIDs = Set(
            serverSessionIDs.map(Self.trimmed).filter { !$0.isEmpty }
            + recordsByServerSessionID.keys
            + [runtimeBinding.activeServerSessionID]
        )

        summary.listeners = allServerSessionIDs.sorted().map { serverSessionID in
            let record = recordsByServerSessionID[serverSessionID]
            let requestedHost = record?.host ?? defaults.host
            let requestedPort = record?.port ?? defaults.port
            let servedModelID = record?.servedModelID ?? resolvedFallbackModelID
            let rateLimitPerMinute = record?.rateLimitPerMinute ?? defaults.rateLimitPerMinute
            let timeoutSeconds = record?.timeoutSeconds ?? defaults.timeoutSeconds
            let isActiveBinding = serverSessionID == runtimeBinding.activeServerSessionID

            var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
            listener.serverSessionID = serverSessionID
            listener.requestedHost = requestedHost
            listener.requestedPort = requestedPort
            listener.effectiveHost = isActiveBinding ? runtimeBinding.host : requestedHost
            listener.effectivePort = isActiveBinding ? runtimeBinding.port : requestedPort
            listener.servedModelID = servedModelID
            listener.rateLimitPerMinute = rateLimitPerMinute
            listener.timeoutSeconds = timeoutSeconds
            listener.source = record?.source ?? defaults.source
            listener.activeBinding = isActiveBinding
            listener.requiresRestart = isActiveBinding
                && (requestedHost != runtimeBinding.host || requestedPort != runtimeBinding.port)
            listener.updatedAtUnixMs = record?.updatedAtUnixMS ?? 0
            return listener
        }
        return summary
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
        let builtInHost = MelixGatewayDefaults.host
        let builtInPort: UInt32 = UInt32(MelixGatewayDefaults.port)
        let builtInRateLimit: UInt32 = 120
        let builtInTimeout: UInt32 = 120

        let envHost = trimmed(environment["MELIX_HTTP_HOST"])
        let envPort = UInt32(trimmed(environment["MELIX_HTTP_PORT"])) ?? 0
        let envRateLimit = UInt32(trimmed(environment["MELIX_GATEWAY_RATE_LIMIT_PER_MINUTE"])) ?? 0
        let envTimeout = UInt32(trimmed(environment["MELIX_GATEWAY_TIMEOUT_SECONDS"])) ?? 0

        let usesEnvironmentDefaults = !envHost.isEmpty || envPort > 0 || envRateLimit > 0 || envTimeout > 0

        return GatewayConfigDefaults(
            host: envHost.isEmpty ? builtInHost : envHost,
            port: envPort > 0 ? envPort : builtInPort,
            rateLimitPerMinute: envRateLimit > 0 ? envRateLimit : builtInRateLimit,
            timeoutSeconds: envTimeout > 0 ? envTimeout : builtInTimeout,
            source: usesEnvironmentDefaults ? .environmentDefaults : .builtInDefaults
        )
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
