import Foundation

public enum RuntimeDiscoveryEndpoint: String, CaseIterable, Identifiable, Equatable, Sendable {
    case info
    case capabilities
    case instructions
    case schema
    case configMetadata

    public var id: String { rawValue }

    public var displayTitle: String {
        switch self {
        case .info:
            return "Info"
        case .capabilities:
            return "Capabilities"
        case .instructions:
            return "Instructions"
        case .schema:
            return "Schema"
        case .configMetadata:
            return "Config Metadata"
        }
    }
}

public struct RuntimeDiscoveryValueRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let value: String

    public init(key: String, value: String) {
        self.id = key
        self.key = key
        self.value = value
    }
}

public struct RuntimeDiscoveryLinkRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let url: String

    public init(key: String, url: String) {
        self.id = key
        self.key = key
        self.url = url
    }
}

public struct RuntimeDiscoveryInstructionAreaState: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let commands: [String]

    public init(id: String, title: String, commands: [String]) {
        self.id = id
        self.title = title
        self.commands = commands
    }

    public var commandsText: String {
        commands.joined(separator: ", ")
    }
}

public struct RuntimeDiscoverySchemaPathState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let path: String

    public init(key: String, path: String) {
        self.id = key
        self.key = key
        self.path = path
    }
}

public struct RuntimeDiscoveryConfigSettingState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let valueType: String
    public let defaultValueText: String
    public let environmentVariable: String
    public let summary: String

    public init(
        key: String,
        valueType: String,
        defaultValueText: String,
        environmentVariable: String,
        summary: String
    ) {
        self.id = key
        self.key = key
        self.valueType = valueType
        self.defaultValueText = defaultValueText
        self.environmentVariable = environmentVariable
        self.summary = summary
    }
}

public struct RuntimeDiscoveryModelState: Identifiable, Equatable, Sendable {
    public let id: String
    public let modelID: String
    public let kind: String
    public let supportedModalities: [String]
    public let supportedTasks: [String]
    public let capabilityReceiptText: String

    public init(
        modelID: String,
        kind: String,
        supportedModalities: [String],
        supportedTasks: [String],
        capabilityReceiptText: String
    ) {
        self.id = modelID
        self.modelID = modelID
        self.kind = kind
        self.supportedModalities = supportedModalities
        self.supportedTasks = supportedTasks
        self.capabilityReceiptText = capabilityReceiptText
    }

    public var supportedModalitiesText: String {
        supportedModalities.joined(separator: ", ")
    }

    public var supportedTasksText: String {
        supportedTasks.joined(separator: ", ")
    }
}

public struct RuntimeDiscoveryAliasState: Equatable, Sendable {
    public let query: String
    public let status: String
    public let suggestionsText: String

    public init(query: String, status: String, suggestionsText: String) {
        self.query = query
        self.status = status
        self.suggestionsText = suggestionsText
    }
}

public struct RuntimeDiscoveryPayloadState: Identifiable, Equatable, Sendable {
    public let id: String
    public let endpoint: RuntimeDiscoveryEndpoint
    public let schemaVersion: String
    public let valueRows: [RuntimeDiscoveryValueRowState]
    public let links: [RuntimeDiscoveryLinkRowState]
    public let instructionAreas: [RuntimeDiscoveryInstructionAreaState]
    public let schemaPaths: [RuntimeDiscoverySchemaPathState]
    public let configSettings: [RuntimeDiscoveryConfigSettingState]
    public let models: [RuntimeDiscoveryModelState]
    public let aliasDiscovery: RuntimeDiscoveryAliasState?

    public init(
        endpoint: RuntimeDiscoveryEndpoint,
        schemaVersion: String,
        valueRows: [RuntimeDiscoveryValueRowState],
        links: [RuntimeDiscoveryLinkRowState],
        instructionAreas: [RuntimeDiscoveryInstructionAreaState],
        schemaPaths: [RuntimeDiscoverySchemaPathState],
        configSettings: [RuntimeDiscoveryConfigSettingState],
        models: [RuntimeDiscoveryModelState],
        aliasDiscovery: RuntimeDiscoveryAliasState?
    ) {
        self.id = endpoint.rawValue
        self.endpoint = endpoint
        self.schemaVersion = schemaVersion
        self.valueRows = valueRows
        self.links = links
        self.instructionAreas = instructionAreas
        self.schemaPaths = schemaPaths
        self.configSettings = configSettings
        self.models = models
        self.aliasDiscovery = aliasDiscovery
    }
}

public struct RuntimeDiscoverySnapshotState: Equatable, Sendable {
    public static let empty = RuntimeDiscoverySnapshotState(payloads: [])

    public let payloads: [RuntimeDiscoveryPayloadState]

    public init(payloads: [RuntimeDiscoveryPayloadState]) {
        self.payloads = payloads
    }

    public func payload(for endpoint: RuntimeDiscoveryEndpoint) -> RuntimeDiscoveryPayloadState? {
        payloads.first { $0.endpoint == endpoint }
    }
}

public enum RuntimeDiscoveryPayloadDecoder {
    public static func decodeSnapshot(
        _ entries: [(RuntimeDiscoveryEndpoint, String)]
    ) throws -> RuntimeDiscoverySnapshotState {
        RuntimeDiscoverySnapshotState(
            payloads: try entries.map { endpoint, output in
                try decodePayload(endpoint: endpoint, output)
            }
        )
    }

    public static func decodePayload(
        endpoint: RuntimeDiscoveryEndpoint,
        _ output: String
    ) throws -> RuntimeDiscoveryPayloadState {
        try decodePayload(endpoint: endpoint, Data(output.utf8))
    }

    public static func decodePayload(
        endpoint: RuntimeDiscoveryEndpoint,
        _ data: Data
    ) throws -> RuntimeDiscoveryPayloadState {
        let decoded = try JSONSerialization.jsonObject(with: data)
        guard let payload = decoded as? [String: Any] else {
            throw dataCorrupted("Discovery payload must be a JSON object.")
        }

        let schemaVersion = stringText(for: payload["schema_version"])
        let valueRows = valueRows(from: payload)
        return RuntimeDiscoveryPayloadState(
            endpoint: endpoint,
            schemaVersion: schemaVersion,
            valueRows: valueRows,
            links: linkRows(from: payload["links"]),
            instructionAreas: instructionAreas(from: payload["areas"]),
            schemaPaths: schemaPaths(from: payload["schemas"]) + schemaPaths(from: (payload["schema"] as? [String: Any])?["schemas"]),
            configSettings: configSettings(from: payload["settings"]),
            models: models(from: payload["models"]),
            aliasDiscovery: aliasDiscovery(from: payload["model_alias_discovery"])
        )
    }

    private static func valueRows(from payload: [String: Any]) -> [RuntimeDiscoveryValueRowState] {
        var rows: [RuntimeDiscoveryValueRowState] = []
        for key in ["version", "features", "supported_tasks"] {
            if let value = payload[key] {
                rows.append(RuntimeDiscoveryValueRowState(key: key, value: displayText(for: value)))
            }
        }
        rows.append(contentsOf: nestedValueRows(prefix: "local_paths", value: payload["local_paths"]))
        rows.append(contentsOf: nestedValueRows(prefix: "update", value: payload["update"]))
        rows.append(contentsOf: nestedValueRows(prefix: "metrics", value: payload["metrics"]))
        return rows
    }

    private static func nestedValueRows(prefix: String, value: Any?) -> [RuntimeDiscoveryValueRowState] {
        guard let object = value as? [String: Any] else {
            return []
        }
        return object.keys.sorted().map { key in
            RuntimeDiscoveryValueRowState(key: "\(prefix).\(key)", value: displayText(for: object[key] ?? NSNull()))
        }
    }

    private static func linkRows(from value: Any?) -> [RuntimeDiscoveryLinkRowState] {
        guard let object = value as? [String: Any] else {
            return []
        }
        return object.keys.sorted().map { key in
            RuntimeDiscoveryLinkRowState(key: key, url: stringText(for: object[key]))
        }
    }

    private static func instructionAreas(from value: Any?) -> [RuntimeDiscoveryInstructionAreaState] {
        (value as? [[String: Any]] ?? []).map { area in
            RuntimeDiscoveryInstructionAreaState(
                id: stringText(for: area["id"]),
                title: stringText(for: area["title"]),
                commands: stringArray(for: area["commands"])
            )
        }
    }

    private static func schemaPaths(from value: Any?) -> [RuntimeDiscoverySchemaPathState] {
        (value as? [[String: Any]] ?? [])
            .map { schema in
                RuntimeDiscoverySchemaPathState(
                    key: stringText(for: schema["id"]),
                    path: stringText(for: schema["path"])
                )
            }
            .sorted { $0.key < $1.key }
    }

    private static func configSettings(from value: Any?) -> [RuntimeDiscoveryConfigSettingState] {
        (value as? [[String: Any]] ?? [])
            .map { setting in
                RuntimeDiscoveryConfigSettingState(
                    key: stringText(for: setting["key"]),
                    valueType: stringText(for: setting["type"]),
                    defaultValueText: displayText(for: setting["default"] ?? NSNull()),
                    environmentVariable: stringText(for: setting["environment_variable"]),
                    summary: stringText(for: setting["summary"])
                )
            }
            .sorted { $0.key < $1.key }
    }

    private static func models(from value: Any?) -> [RuntimeDiscoveryModelState] {
        (value as? [[String: Any]] ?? []).map { model in
            RuntimeDiscoveryModelState(
                modelID: stringText(for: model["model_id"]),
                kind: stringText(for: model["kind"]),
                supportedModalities: stringArray(for: model["supported_modalities"]),
                supportedTasks: stringArray(for: model["supported_tasks"]),
                capabilityReceiptText: displayText(for: model["capability_receipt"] ?? NSNull())
            )
        }
    }

    private static func aliasDiscovery(from value: Any?) -> RuntimeDiscoveryAliasState? {
        guard let object = value as? [String: Any] else {
            return nil
        }
        let suggestions = (object["suggestions"] as? [[String: Any]] ?? [])
            .map { suggestion in
                [
                    stringText(for: suggestion["model_id"]),
                    stringText(for: suggestion["family"]),
                    stringText(for: suggestion["quantization"]),
                    stringArray(for: suggestion["aliases"]).joined(separator: ", "),
                ]
                .filter { $0.isEmpty == false }
                .joined(separator: " ")
            }
        return RuntimeDiscoveryAliasState(
            query: stringText(for: object["query"]),
            status: stringText(for: object["status"]),
            suggestionsText: suggestions.joined(separator: " | ")
        )
    }

    private static func stringArray(for value: Any?) -> [String] {
        (value as? [Any] ?? []).map { stringText(for: $0) }.filter { $0.isEmpty == false }
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
        if let values = value as? [Any] {
            return values.map { displayText(for: $0) }.joined(separator: ", ")
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
