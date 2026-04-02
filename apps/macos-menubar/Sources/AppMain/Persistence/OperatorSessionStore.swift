import Foundation

public struct OperatorSessionState: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var selectedSurface: DesktopSurface
    public var selectedServerSessionID: String
    public var serverSessions: [DesktopServerSessionState]

    public init(
        schemaVersion: Int = 1,
        selectedSurface: DesktopSurface,
        selectedServerSessionID: String,
        serverSessions: [DesktopServerSessionState]
    ) {
        self.schemaVersion = schemaVersion
        self.selectedSurface = selectedSurface
        self.selectedServerSessionID = selectedServerSessionID
        self.serverSessions = serverSessions
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case selectedSurface = "selected_surface"
        case selectedServerSessionID = "selected_server_session_id"
        case serverSessions = "server_sessions"
    }
}

public protocol OperatorSessionStoring: Sendable {
    func load() throws -> OperatorSessionState?
    func save(_ state: OperatorSessionState) throws
}

public struct NullOperatorSessionStore: OperatorSessionStoring {
    public init() {}

    public func load() throws -> OperatorSessionState? {
        nil
    }

    public func save(_ state: OperatorSessionState) throws {
        _ = state
    }
}

public struct OperatorSessionStore: OperatorSessionStoring {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func load() throws -> OperatorSessionState? {
        let fileManager = FileManager.default
        let fileURL = melixHome.operatorSessionFileURL
        guard fileManager.fileExists(atPath: fileURL.path) else {
            return nil
        }
        let data = try Data(contentsOf: fileURL)
        return try Self.decoder.decode(OperatorSessionState.self, from: data)
    }

    public func save(_ state: OperatorSessionState) throws {
        let data = try Self.encoder.encode(state)
        try melixHome.writeAtomically(data, to: melixHome.operatorSessionFileURL)
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
