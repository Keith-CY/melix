import CryptoKit
import Foundation

func cacheScopeHash(_ value: String?) -> String {
    guard let value, !value.isEmpty else {
        return ""
    }
    return SHA256.hash(data: Data(value.utf8))
        .map { String(format: "%02x", $0) }
        .joined()
}
