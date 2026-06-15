import CryptoKit
import Foundation

enum PromptContextSourceIDRedactor {
    static func redactedSourceID(
        _ sourceID: String,
        prefix: String,
        allowColon: Bool = false
    ) -> String {
        let normalized = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else {
            return normalized
        }
        guard isPublicSourceID(normalized, allowColon: allowColon) else {
            return "\(prefix):\(sha256Hex(normalized).prefix(12))"
        }
        return normalized
    }

    private static func isPublicSourceID(_ sourceID: String, allowColon: Bool) -> Bool {
        guard sourceID.count <= 96 else {
            return false
        }
        return sourceID.allSatisfy { character in
            character.isASCII
                && (
                    character.isLetter
                        || character.isNumber
                        || character == "."
                        || character == "_"
                        || character == "-"
                        || (allowColon && character == ":")
                )
        }
    }

    private static func sha256Hex(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }
}
