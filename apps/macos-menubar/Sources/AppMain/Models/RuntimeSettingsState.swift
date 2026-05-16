import Foundation

public enum RuntimeSettingValidationState: String, Equatable, Sendable {
    case notValidated = "not_validated"
    case valid
    case invalid

    public var displayTitle: String {
        switch self {
        case .notValidated:
            return "Not validated"
        case .valid:
            return "Valid"
        case .invalid:
            return "Invalid"
        }
    }
}

public struct RuntimeSettingRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let currentValueText: String
    public let source: String
    public let sourceDetail: String
    public let validationState: RuntimeSettingValidationState
    public let validationMessage: String

    public init(
        key: String,
        currentValueText: String,
        source: String,
        sourceDetail: String,
        validationState: RuntimeSettingValidationState = .notValidated,
        validationMessage: String = ""
    ) {
        self.id = key
        self.key = key
        self.currentValueText = currentValueText
        self.source = source
        self.sourceDetail = sourceDetail
        self.validationState = validationState
        self.validationMessage = validationMessage
    }
}

public struct RuntimeSettingSourceState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let path: String

    public init(key: String, path: String) {
        self.id = key
        self.key = key
        self.path = path
    }
}

public struct RuntimeSettingMetricState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let valueText: String

    public init(name: String, valueText: String) {
        self.id = name
        self.name = name
        self.valueText = valueText
    }
}

public struct RuntimeSettingsSnapshotState: Equatable, Sendable {
    public static let empty = RuntimeSettingsSnapshotState(schemaVersion: "", rows: [], sources: [], metrics: [])

    public let schemaVersion: String
    public let rows: [RuntimeSettingRowState]
    public let sources: [RuntimeSettingSourceState]
    public let metrics: [RuntimeSettingMetricState]

    public init(
        schemaVersion: String,
        rows: [RuntimeSettingRowState],
        sources: [RuntimeSettingSourceState],
        metrics: [RuntimeSettingMetricState]
    ) {
        self.schemaVersion = schemaVersion
        self.rows = rows
        self.sources = sources
        self.metrics = metrics
    }
}

public enum RuntimeSettingsPayloadDecoder {
    public static func decodeShow(_ output: String) throws -> RuntimeSettingsSnapshotState {
        try decodeShow(Data(output.utf8))
    }

    public static func decodeShow(_ data: Data) throws -> RuntimeSettingsSnapshotState {
        let decoded = try JSONSerialization.jsonObject(with: data)
        guard let payload = decoded as? [String: Any] else {
            throw dataCorrupted("Settings show payload must be a JSON object.")
        }

        guard let settings = payload["settings"] as? [String: Any] else {
            throw dataCorrupted("Settings show payload is missing settings object.")
        }

        let rows = settings.keys.sorted().map { key in
            let setting = settings[key] as? [String: Any] ?? [:]
            return RuntimeSettingRowState(
                key: key,
                currentValueText: displayText(for: setting["value"] ?? NSNull()),
                source: stringText(for: setting["source"]),
                sourceDetail: stringText(for: setting["source_detail"])
            )
        }

        let sources = (payload["sources"] as? [String: Any] ?? [:]).keys.sorted().map { key in
            RuntimeSettingSourceState(key: key, path: stringText(for: (payload["sources"] as? [String: Any])?[key]))
        }

        let metrics = (payload["metrics"] as? [String: Any] ?? [:]).keys.sorted().map { key in
            RuntimeSettingMetricState(
                name: key,
                valueText: displayText(for: (payload["metrics"] as? [String: Any])?[key] ?? NSNull())
            )
        }

        return RuntimeSettingsSnapshotState(
            schemaVersion: stringText(for: payload["schema_version"]),
            rows: rows,
            sources: sources,
            metrics: metrics
        )
    }

    private static func stringText(for value: Any?) -> String {
        guard let value else {
            return ""
        }
        if value is NSNull {
            return ""
        }
        if let string = value as? String {
            return string
        }
        return displayText(for: value)
    }

    private static func displayText(for value: Any) -> String {
        if value is NSNull {
            return "null"
        }
        if let string = value as? String {
            return string
        }
        if let bool = value as? Bool {
            return bool ? "true" : "false"
        }
        if let number = value as? NSNumber {
            let doubleValue = number.doubleValue
            if doubleValue.isFinite, doubleValue.rounded(.towardZero) == doubleValue {
                return String(number.int64Value)
            }
            return String(doubleValue)
        }
        if JSONSerialization.isValidJSONObject(value),
           let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
           let string = String(data: data, encoding: .utf8)
        {
            return string
        }
        return String(describing: value)
    }

    private static func dataCorrupted(_ message: String) -> DecodingError {
        DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: message))
    }
}
