import Foundation

public struct ProviderPrimaryAPIKeyRecord: Codable, Equatable, Sendable {
    public var providerID: String
    public var keyID: String
    public var primaryKey: String
    public var updatedAt: Date

    public init(
        providerID: String,
        keyID: String,
        primaryKey: String,
        updatedAt: Date
    ) {
        self.providerID = providerID
        self.keyID = keyID
        self.primaryKey = primaryKey
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case providerID = "provider_id"
        case keyID = "key_id"
        case primaryKey = "primary_key"
        case updatedAt = "updated_at"
    }
}

private struct ProviderAPIKeyStoreDocument: Codable, Equatable, Sendable {
    var schemaVersion: Int
    var sessions: [ProviderPrimaryAPIKeyRecord]

    init(
        schemaVersion: Int = 1,
        sessions: [ProviderPrimaryAPIKeyRecord] = []
    ) {
        self.schemaVersion = schemaVersion
        self.sessions = sessions
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessions
    }
}

public protocol ProviderAPIKeyStoring: Sendable {
    func loadPrimaryKey(providerID: String) throws -> ProviderPrimaryAPIKeyRecord?
    @discardableResult
    func savePrimaryKey(
        providerID: String,
        primaryKey: String,
        keyID: String
    ) throws -> ProviderPrimaryAPIKeyRecord
}

public struct NullProviderAPIKeyStore: ProviderAPIKeyStoring {
    public init() {}

    public func loadPrimaryKey(providerID: String) throws -> ProviderPrimaryAPIKeyRecord? {
        _ = providerID
        return nil
    }

    public func savePrimaryKey(
        providerID: String,
        primaryKey: String,
        keyID: String
    ) throws -> ProviderPrimaryAPIKeyRecord {
        ProviderPrimaryAPIKeyRecord(
            providerID: providerID,
            keyID: keyID,
            primaryKey: primaryKey,
            updatedAt: Date()
        )
    }
}

public struct ProviderAPIKeyStore: ProviderAPIKeyStoring {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func loadPrimaryKey(providerID: String) throws -> ProviderPrimaryAPIKeyRecord? {
        let document = try loadDocument()
        return document.sessions.first(where: { $0.providerID == providerID })
    }

    @discardableResult
    public func savePrimaryKey(
        providerID: String,
        primaryKey: String,
        keyID: String = "primary"
    ) throws -> ProviderPrimaryAPIKeyRecord {
        var document = try loadDocument()
        let record = ProviderPrimaryAPIKeyRecord(
            providerID: providerID,
            keyID: keyID,
            primaryKey: primaryKey,
            updatedAt: Date()
        )
        if let index = document.sessions.firstIndex(where: { $0.providerID == providerID }) {
            document.sessions[index] = record
        } else {
            document.sessions.append(record)
            document.sessions.sort { $0.providerID < $1.providerID }
        }
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.providerAPIKeysFileURL)
        return record
    }

    private func loadDocument() throws -> ProviderAPIKeyStoreDocument {
        let fileManager = FileManager.default
        let fileURL = melixHome.providerAPIKeysFileURL
        guard fileManager.fileExists(atPath: fileURL.path) else {
            return ProviderAPIKeyStoreDocument()
        }
        let data = try Data(contentsOf: fileURL)
        return try Self.decoder.decode(ProviderAPIKeyStoreDocument.self, from: data)
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}
