import Foundation

public struct RuntimeSyntheticDatasetValidationMessageState: Identifiable, Equatable, Sendable {
    public let field: String
    public let message: String

    public init(field: String, message: String) {
        self.field = field
        self.message = message
    }

    public var id: String {
        "\(field):\(message)"
    }
}
