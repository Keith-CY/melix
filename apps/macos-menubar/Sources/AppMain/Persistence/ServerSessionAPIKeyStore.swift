import Foundation

public struct ServerSessionPrimaryAPIKeyRecord: Codable, Equatable, Sendable {
    public var serverSessionID: String
    public var keyID: String
    public var primaryKey: String
    public var updatedAt: Date

    public init(
        serverSessionID: String,
        keyID: String,
        primaryKey: String,
        updatedAt: Date
    ) {
        self.serverSessionID = serverSessionID
        self.keyID = keyID
        self.primaryKey = primaryKey
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case serverSessionID = "server_session_id"
        case keyID = "key_id"
        case primaryKey = "primary_key"
        case updatedAt = "updated_at"
    }
}

private struct ServerSessionAPIKeyStoreDocument: Codable, Equatable, Sendable {
    var schemaVersion: Int
    var sessions: [ServerSessionPrimaryAPIKeyRecord]

    init(
        schemaVersion: Int = 1,
        sessions: [ServerSessionPrimaryAPIKeyRecord] = []
    ) {
        self.schemaVersion = schemaVersion
        self.sessions = sessions
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessions
    }
}

public protocol ServerSessionAPIKeyStoring: Sendable {
    func loadPrimaryKey(serverSessionID: String) throws -> ServerSessionPrimaryAPIKeyRecord?
    @discardableResult
    func savePrimaryKey(
        serverSessionID: String,
        primaryKey: String,
        keyID: String
    ) throws -> ServerSessionPrimaryAPIKeyRecord
}

public struct NullServerSessionAPIKeyStore: ServerSessionAPIKeyStoring {
    public init() {}

    public func loadPrimaryKey(serverSessionID: String) throws -> ServerSessionPrimaryAPIKeyRecord? {
        _ = serverSessionID
        return nil
    }

    public func savePrimaryKey(
        serverSessionID: String,
        primaryKey: String,
        keyID: String
    ) throws -> ServerSessionPrimaryAPIKeyRecord {
        ServerSessionPrimaryAPIKeyRecord(
            serverSessionID: serverSessionID,
            keyID: keyID,
            primaryKey: primaryKey,
            updatedAt: Date()
        )
    }
}

public struct ServerSessionAPIKeyStore: ServerSessionAPIKeyStoring {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func loadPrimaryKey(serverSessionID: String) throws -> ServerSessionPrimaryAPIKeyRecord? {
        let document = try loadDocument()
        return document.sessions.first(where: { $0.serverSessionID == serverSessionID })
    }

    @discardableResult
    public func savePrimaryKey(
        serverSessionID: String,
        primaryKey: String,
        keyID: String = "primary"
    ) throws -> ServerSessionPrimaryAPIKeyRecord {
        var document = try loadDocument()
        let record = ServerSessionPrimaryAPIKeyRecord(
            serverSessionID: serverSessionID,
            keyID: keyID,
            primaryKey: primaryKey,
            updatedAt: Date()
        )
        if let index = document.sessions.firstIndex(where: { $0.serverSessionID == serverSessionID }) {
            document.sessions[index] = record
        } else {
            document.sessions.append(record)
            document.sessions.sort { $0.serverSessionID < $1.serverSessionID }
        }
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.serverSessionAPIKeysFileURL)
        return record
    }

    private func loadDocument() throws -> ServerSessionAPIKeyStoreDocument {
        let fileManager = FileManager.default
        let fileURL = melixHome.serverSessionAPIKeysFileURL
        guard fileManager.fileExists(atPath: fileURL.path) else {
            return ServerSessionAPIKeyStoreDocument()
        }
        let data = try Data(contentsOf: fileURL)
        return try Self.decoder.decode(ServerSessionAPIKeyStoreDocument.self, from: data)
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
