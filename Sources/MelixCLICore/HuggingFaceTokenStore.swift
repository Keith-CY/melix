import Foundation

public struct HuggingFaceTokenRecord: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var token: String
    public var maskedHint: String
    public var updatedAt: Date

    public init(
        schemaVersion: Int = 1,
        token: String,
        maskedHint: String? = nil,
        updatedAt: Date = Date()
    ) {
        self.schemaVersion = max(schemaVersion, 1)
        self.token = token
        self.maskedHint = maskedHint ?? Self.maskedHint(for: token)
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case token
        case maskedHint = "masked_hint"
        case updatedAt = "updated_at"
    }

    public static func maskedHint(for token: String) -> String {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return ""
        }
        if trimmed.count <= 8 {
            return "saved"
        }
        return "\(trimmed.prefix(4))...\(trimmed.suffix(4))"
    }
}

public protocol HuggingFaceTokenStoring: Sendable {
    func loadToken() throws -> HuggingFaceTokenRecord?
    @discardableResult
    func saveToken(_ token: String) throws -> HuggingFaceTokenRecord
}

public struct NullHuggingFaceTokenStore: HuggingFaceTokenStoring {
    public init() {}

    public func loadToken() throws -> HuggingFaceTokenRecord? {
        nil
    }

    public func saveToken(_ token: String) throws -> HuggingFaceTokenRecord {
        HuggingFaceTokenRecord(token: token)
    }
}

public struct HuggingFaceTokenStore: HuggingFaceTokenStoring {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func loadToken() throws -> HuggingFaceTokenRecord? {
        let fileURL = melixHome.huggingFaceTokenFileURL
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return nil
        }
        let data = try Data(contentsOf: fileURL)
        return try Self.decoder.decode(HuggingFaceTokenRecord.self, from: data)
    }

    @discardableResult
    public func saveToken(_ token: String) throws -> HuggingFaceTokenRecord {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        let record = HuggingFaceTokenRecord(token: trimmed)
        let data = try Self.encoder.encode(record)
        try melixHome.writeAtomically(data, to: melixHome.huggingFaceTokenFileURL)
        return record
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
