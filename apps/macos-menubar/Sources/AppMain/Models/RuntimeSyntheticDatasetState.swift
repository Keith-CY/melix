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

public struct RuntimeSyntheticDatasetColumnState: Identifiable, Equatable, Sendable {
    public let name: String
    public let type: String
    public let payload: String

    public init(name: String, type: String, payload: String) {
        self.name = name
        self.type = type
        self.payload = payload
    }

    public var id: String {
        commandArgument
    }

    public var commandArgument: String {
        "\(name):\(type):\(payload)"
    }
}
