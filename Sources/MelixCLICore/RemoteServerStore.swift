import Foundation

public enum RemoteServerProviderPreset: String, Codable, CaseIterable, Sendable, Identifiable {
    case kimi
    case gemini
    case deepseek
    case glm
    case custom

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .kimi:
            return "Kimi"
        case .gemini:
            return "Gemini"
        case .deepseek:
            return "DeepSeek"
        case .glm:
            return "GLM"
        case .custom:
            return "Custom"
        }
    }

    public var providerKind: String {
        switch self {
        case .gemini:
            return "gemini-generative-language"
        case .kimi, .deepseek, .glm, .custom:
            return "openai-compatible"
        }
    }

    public var fixedBaseURL: String? {
        switch self {
        case .kimi:
            return "https://api.kimi.com/coding/v1"
        case .gemini:
            return "https://generativelanguage.googleapis.com/v1beta"
        case .deepseek:
            return "https://api.deepseek.com/v1"
        case .glm:
            return "https://open.bigmodel.cn/api/paas/v4"
        case .custom:
            return nil
        }
    }

    public var isBaseURLEditable: Bool {
        self == .custom
    }

    public static func normalized(_ value: String) -> RemoteServerProviderPreset? {
        switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "kimi":
            return .kimi
        case "gemini":
            return .gemini
        case "deepseek":
            return .deepseek
        case "glm":
            return .glm
        case "custom", "sub2api", "openai-compatible":
            return .custom
        default:
            return nil
        }
    }
}

public enum RemoteServerToolSupportMode: String, Codable, CaseIterable, Sendable, Identifiable {
    case auto
    case forceOn = "force_on"
    case forceOff = "force_off"

    public var id: String {
        rawValue
    }

    public static func normalized(_ value: String) -> RemoteServerToolSupportMode? {
        switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "auto":
            return .auto
        case "force-on", "force_on":
            return .forceOn
        case "force-off", "force_off":
            return .forceOff
        default:
            return nil
        }
    }

    public var commandValue: String {
        switch self {
        case .auto:
            return "auto"
        case .forceOn:
            return "force-on"
        case .forceOff:
            return "force-off"
        }
    }
}

public struct RemoteServer: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let title: String
    public let providerPreset: RemoteServerProviderPreset
    public let providerKind: String
    public let baseURL: String
    public let defaultModelID: String
    public let timeoutSeconds: UInt32
    public let rateLimitPerMinute: UInt32
    public let toolSupportMode: RemoteServerToolSupportMode
    public let credentialRef: String
    public let apiKeyHint: String
    public let healthStatus: String
    public let createdAt: Date
    public let updatedAt: Date

    public init(
        id: String,
        title: String,
        providerPreset: RemoteServerProviderPreset = .custom,
        providerKind: String,
        baseURL: String,
        defaultModelID: String,
        timeoutSeconds: UInt32 = 60,
        rateLimitPerMinute: UInt32 = 0,
        toolSupportMode: RemoteServerToolSupportMode = .auto,
        credentialRef: String,
        apiKeyHint: String = "",
        healthStatus: String = "unknown",
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.providerPreset = providerPreset
        self.providerKind = providerKind
        self.baseURL = baseURL
        self.defaultModelID = defaultModelID
        self.timeoutSeconds = timeoutSeconds
        self.rateLimitPerMinute = rateLimitPerMinute
        self.toolSupportMode = toolSupportMode
        self.credentialRef = credentialRef
        self.apiKeyHint = apiKeyHint
        self.healthStatus = healthStatus
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case providerPreset = "provider_preset"
        case providerKind = "provider_kind"
        case baseURL = "base_url"
        case defaultModelID = "default_model_id"
        case timeoutSeconds = "timeout_seconds"
        case rateLimitPerMinute = "rate_limit_per_minute"
        case toolSupportMode = "tool_support_mode"
        case credentialRef = "credential_ref"
        case apiKeyHint = "api_key_hint"
        case healthStatus = "health_status"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        let decodedProviderKind = try container.decode(String.self, forKey: .providerKind)
        let decodedBaseURL = try container.decode(String.self, forKey: .baseURL)
        if let rawPreset = try container.decodeIfPresent(String.self, forKey: .providerPreset),
           let decodedPreset = RemoteServerProviderPreset.normalized(rawPreset)
        {
            providerPreset = decodedPreset
        } else {
            providerPreset = .custom
        }
        providerKind = decodedProviderKind
        baseURL = decodedBaseURL
        defaultModelID = try container.decode(String.self, forKey: .defaultModelID)
        timeoutSeconds = try container.decode(UInt32.self, forKey: .timeoutSeconds)
        rateLimitPerMinute = try container.decode(UInt32.self, forKey: .rateLimitPerMinute)
        if let rawToolSupportMode = try container.decodeIfPresent(String.self, forKey: .toolSupportMode),
           let decodedToolSupportMode = RemoteServerToolSupportMode.normalized(rawToolSupportMode)
        {
            toolSupportMode = decodedToolSupportMode
        } else {
            toolSupportMode = .auto
        }
        credentialRef = try container.decode(String.self, forKey: .credentialRef)
        apiKeyHint = try container.decodeIfPresent(String.self, forKey: .apiKeyHint) ?? ""
        healthStatus = try container.decodeIfPresent(String.self, forKey: .healthStatus) ?? "unknown"
        createdAt = try container.decode(Date.self, forKey: .createdAt)
        updatedAt = try container.decode(Date.self, forKey: .updatedAt)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(title, forKey: .title)
        try container.encode(providerPreset, forKey: .providerPreset)
        try container.encode(providerKind, forKey: .providerKind)
        try container.encode(baseURL, forKey: .baseURL)
        try container.encode(defaultModelID, forKey: .defaultModelID)
        try container.encode(timeoutSeconds, forKey: .timeoutSeconds)
        try container.encode(rateLimitPerMinute, forKey: .rateLimitPerMinute)
        try container.encode(toolSupportMode, forKey: .toolSupportMode)
        try container.encode(credentialRef, forKey: .credentialRef)
        try container.encode(apiKeyHint, forKey: .apiKeyHint)
        try container.encode(healthStatus, forKey: .healthStatus)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encode(updatedAt, forKey: .updatedAt)
    }
}

public struct RemoteServerMutation: Equatable, Sendable {
    public let id: String
    public let title: String
    public let providerPreset: RemoteServerProviderPreset
    public let providerKind: String
    public let baseURL: String
    public let defaultModelID: String
    public let timeoutSeconds: UInt32
    public let rateLimitPerMinute: UInt32
    public let toolSupportMode: RemoteServerToolSupportMode
    public let apiKey: String

    public init(
        id: String,
        title: String,
        providerPreset: RemoteServerProviderPreset = .custom,
        providerKind: String,
        baseURL: String,
        defaultModelID: String,
        timeoutSeconds: UInt32 = 60,
        rateLimitPerMinute: UInt32 = 0,
        toolSupportMode: RemoteServerToolSupportMode = .auto,
        apiKey: String = ""
    ) {
        self.id = id
        self.title = title
        self.providerPreset = providerPreset
        self.providerKind = providerKind
        self.baseURL = baseURL
        self.defaultModelID = defaultModelID
        self.timeoutSeconds = timeoutSeconds
        self.rateLimitPerMinute = rateLimitPerMinute
        self.toolSupportMode = toolSupportMode
        self.apiKey = apiKey
    }
}

public struct RemoteServerAPIKeyRecord: Codable, Equatable, Sendable {
    public let remoteServerID: String
    public let apiKey: String
    public let updatedAt: Date

    public init(remoteServerID: String, apiKey: String, updatedAt: Date = Date()) {
        self.remoteServerID = remoteServerID
        self.apiKey = apiKey
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case remoteServerID = "remote_server_id"
        case apiKey = "api_key"
        case updatedAt = "updated_at"
    }
}

public struct RemoteServerStore: Sendable {
    private let melixHome: MelixHome
    private let apiKeyStore: RemoteServerAPIKeyStore

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
        self.apiKeyStore = RemoteServerAPIKeyStore(melixHome: melixHome)
    }

    public func list() throws -> [RemoteServer] {
        try loadDocument().servers.sorted { $0.id < $1.id }
    }

    public func loadAPIKey(remoteServerID: String) throws -> RemoteServerAPIKeyRecord? {
        try apiKeyStore.loadAPIKey(remoteServerID: remoteServerID)
    }

    public func get(id: String) throws -> RemoteServer? {
        let normalizedID = try Self.normalizedRequired(id, fieldName: "remote_server_id")
        return try list().first { $0.id == normalizedID }
    }

    @discardableResult
    public func save(_ mutation: RemoteServerMutation) throws -> RemoteServer {
        let normalizedID = try Self.normalizedRequired(mutation.id, fieldName: "remote_server_id")
        let normalizedTitle = try Self.normalizedRequired(mutation.title, fieldName: "title")
        let normalizedProvider = mutation.providerPreset.providerKind
        let normalizedBaseURL: String
        if let fixedBaseURL = mutation.providerPreset.fixedBaseURL {
            normalizedBaseURL = fixedBaseURL
        } else {
            normalizedBaseURL = try Self.normalizedBaseURL(mutation.baseURL)
        }
        let normalizedDefaultModel = try Self.normalizedRequired(mutation.defaultModelID, fieldName: "default_model_id")
        var document = try loadDocument()
        let existing = document.servers.first { $0.id == normalizedID }
        let now = Date()
        let trimmedAPIKey = mutation.apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let apiKeyHint: String
        if trimmedAPIKey.isEmpty == false {
            try apiKeyStore.saveAPIKey(trimmedAPIKey, remoteServerID: normalizedID)
            apiKeyHint = RemoteServerAPIKeyStore.maskedHint(for: trimmedAPIKey)
        } else {
            apiKeyHint = existing?.apiKeyHint ?? ""
        }

        let server = RemoteServer(
            id: normalizedID,
            title: normalizedTitle,
            providerPreset: mutation.providerPreset,
            providerKind: normalizedProvider,
            baseURL: normalizedBaseURL,
            defaultModelID: normalizedDefaultModel,
            timeoutSeconds: mutation.timeoutSeconds == 0 ? 60 : mutation.timeoutSeconds,
            rateLimitPerMinute: mutation.rateLimitPerMinute,
            toolSupportMode: mutation.toolSupportMode,
            credentialRef: Self.credentialRef(for: normalizedID),
            apiKeyHint: apiKeyHint,
            healthStatus: existing?.healthStatus ?? "unknown",
            createdAt: existing?.createdAt ?? now,
            updatedAt: now
        )

        document.servers.removeAll { $0.id == normalizedID }
        document.servers.append(server)
        document.servers.sort { $0.id < $1.id }
        try saveDocument(document)
        return server
    }

    public func remove(id: String) throws {
        let normalizedID = try Self.normalizedRequired(id, fieldName: "remote_server_id")
        var document = try loadDocument()
        document.servers.removeAll { $0.id == normalizedID }
        try saveDocument(document)
        try apiKeyStore.removeAPIKey(remoteServerID: normalizedID)
    }

    public static func credentialRef(for remoteServerID: String) -> String {
        "remote-server-api-key:\(remoteServerID)"
    }

    private func loadDocument() throws -> RemoteServerDocument {
        guard FileManager.default.fileExists(atPath: melixHome.remoteServersFileURL.path) else {
            return RemoteServerDocument()
        }
        let data = try Data(contentsOf: melixHome.remoteServersFileURL)
        return try Self.decoder.decode(RemoteServerDocument.self, from: data)
    }

    private func saveDocument(_ document: RemoteServerDocument) throws {
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.remoteServersFileURL)
    }

    private static func normalizedRequired(_ value: String, fieldName: String) throws -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.isEmpty == false else {
            throw MelixCLIError.missingRequired("\(fieldName) must not be empty.")
        }
        return normalized
    }

    private static func normalizedBaseURL(_ value: String) throws -> String {
        var normalized = try normalizedRequired(value, fieldName: "base_url")
        while normalized.hasSuffix("/") {
            normalized.removeLast()
        }
        return normalized
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}

public struct RemoteServerAPIKeyStore: Sendable {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func loadAPIKey(remoteServerID: String) throws -> RemoteServerAPIKeyRecord? {
        let normalizedID = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedID.isEmpty == false else {
            return nil
        }
        return try loadDocument().keys.first { $0.remoteServerID == normalizedID }
    }

    @discardableResult
    public func saveAPIKey(_ apiKey: String, remoteServerID: String) throws -> RemoteServerAPIKeyRecord {
        let normalizedID = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedID.isEmpty == false else {
            throw MelixCLIError.missingRequired("remote_server_id must not be empty.")
        }
        guard normalizedAPIKey.isEmpty == false else {
            throw MelixCLIError.missingRequired("api_key must not be empty.")
        }

        var document = try loadDocument()
        let record = RemoteServerAPIKeyRecord(remoteServerID: normalizedID, apiKey: normalizedAPIKey)
        document.keys.removeAll { $0.remoteServerID == normalizedID }
        document.keys.append(record)
        document.keys.sort { $0.remoteServerID < $1.remoteServerID }
        try saveDocument(document)
        return record
    }

    public func removeAPIKey(remoteServerID: String) throws {
        let normalizedID = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        var document = try loadDocument()
        document.keys.removeAll { $0.remoteServerID == normalizedID }
        try saveDocument(document)
    }

    public static func maskedHint(for apiKey: String) -> String {
        let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return ""
        }
        if trimmed.count <= 8 {
            return "saved"
        }
        return "\(trimmed.prefix(4))...\(trimmed.suffix(4))"
    }

    private func loadDocument() throws -> RemoteServerAPIKeyDocument {
        guard FileManager.default.fileExists(atPath: melixHome.remoteServerAPIKeysFileURL.path) else {
            return RemoteServerAPIKeyDocument()
        }
        let data = try Data(contentsOf: melixHome.remoteServerAPIKeysFileURL)
        return try Self.decoder.decode(RemoteServerAPIKeyDocument.self, from: data)
    }

    private func saveDocument(_ document: RemoteServerAPIKeyDocument) throws {
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.remoteServerAPIKeysFileURL)
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}

private struct RemoteServerDocument: Codable {
    var schemaVersion: Int
    var servers: [RemoteServer]

    init(schemaVersion: Int = 1, servers: [RemoteServer] = []) {
        self.schemaVersion = max(schemaVersion, 1)
        self.servers = servers
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case servers
    }
}

private struct RemoteServerAPIKeyDocument: Codable {
    var schemaVersion: Int
    var keys: [RemoteServerAPIKeyRecord]

    init(schemaVersion: Int = 1, keys: [RemoteServerAPIKeyRecord] = []) {
        self.schemaVersion = max(schemaVersion, 1)
        self.keys = keys
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case keys
    }
}
