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

public struct RuntimeDiscoveryMediaRouteReceiptState: Equatable, Sendable {
    public let mediaRoute: String
    public let mediaPartsCount: Int
    public let mediaTurnCount: Int
    public let cacheHitCount: Int
    public let cacheMissCount: Int
    public let unsupportedReason: String

    public init(
        mediaRoute: String,
        mediaPartsCount: Int,
        mediaTurnCount: Int,
        cacheHitCount: Int,
        cacheMissCount: Int,
        unsupportedReason: String
    ) {
        self.mediaRoute = mediaRoute
        self.mediaPartsCount = mediaPartsCount
        self.mediaTurnCount = mediaTurnCount
        self.cacheHitCount = cacheHitCount
        self.cacheMissCount = cacheMissCount
        self.unsupportedReason = unsupportedReason
    }
}

public struct RuntimeDiscoveryModelState: Identifiable, Equatable, Sendable {
    public let id: String
    public let modelID: String
    public let kind: String
    public let supportedModalities: [String]
    public let supportedTasks: [String]
    public let mediaRouteReceipt: RuntimeDiscoveryMediaRouteReceiptState?
    public let capabilityReceiptText: String

    public init(
        modelID: String,
        kind: String,
        supportedModalities: [String],
        supportedTasks: [String],
        mediaRouteReceipt: RuntimeDiscoveryMediaRouteReceiptState? = nil,
        capabilityReceiptText: String
    ) {
        self.id = modelID
        self.modelID = modelID
        self.kind = kind
        self.supportedModalities = supportedModalities
        self.supportedTasks = supportedTasks
        self.mediaRouteReceipt = mediaRouteReceipt
        self.capabilityReceiptText = capabilityReceiptText
    }

    public var supportedModalitiesText: String {
        supportedModalities.joined(separator: ", ")
    }

    public var supportedTasksText: String {
        supportedTasks.joined(separator: ", ")
    }
}

public struct RuntimeDiscoveryAliasSuggestionState: Identifiable, Equatable, Sendable {
    public let id: String
    public let modelID: String
    public let family: String
    public let aliases: [String]
    public let quantization: String

    public init(modelID: String, family: String, aliases: [String], quantization: String) {
        self.id = [modelID, aliases.joined(separator: ",")].filter { $0.isEmpty == false }.joined(separator: "|")
        self.modelID = modelID
        self.family = family
        self.aliases = aliases
        self.quantization = quantization
    }

    public var aliasesText: String {
        aliases.joined(separator: ", ")
    }

    public var displayText: String {
        [
            modelID,
            family.isEmpty ? "" : "family: \(family)",
            quantization.isEmpty ? "" : "quantization: \(quantization)",
            aliasesText.isEmpty ? "" : "aliases: \(aliasesText)",
        ]
        .filter { $0.isEmpty == false }
        .joined(separator: " | ")
    }
}

public struct RuntimeDiscoveryAliasState: Equatable, Sendable {
    public let query: String
    public let status: String
    public let suggestions: [RuntimeDiscoveryAliasSuggestionState]
    public let suggestionsText: String

    public init(
        query: String,
        status: String,
        suggestions: [RuntimeDiscoveryAliasSuggestionState] = [],
        suggestionsText: String = ""
    ) {
        self.query = query
        self.status = status
        self.suggestions = suggestions
        self.suggestionsText = suggestionsText.isEmpty
            ? suggestions.map(\.displayText).joined(separator: " | ")
            : suggestionsText
    }

    public var statusDisplayTitle: String {
        switch status {
        case "suggested":
            return "Suggestions available"
        case "no_match":
            return "No match"
        case "valid_full_model_id":
            return "Full model ID"
        case "local_path_passthrough":
            return "Local path"
        case "not_requested":
            return "Not requested"
        default:
            return status
        }
    }

    public var emptyStateMessage: String {
        guard suggestions.isEmpty else {
            return ""
        }
        switch status {
        case "no_match" where query.isEmpty == false:
            return "No model alias matches \(query)."
        case "not_requested":
            return "Enter a model alias query to see suggestions."
        case "valid_full_model_id":
            return "Query is already a full model ID."
        case "local_path_passthrough":
            return "Query is treated as a local model path."
        default:
            return ""
        }
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
                mediaRouteReceipt: mediaRouteReceipt(from: model["media_route_receipt"]),
                capabilityReceiptText: displayText(for: model["capability_receipt"] ?? NSNull())
            )
        }
    }

    private static func mediaRouteReceipt(from value: Any?) -> RuntimeDiscoveryMediaRouteReceiptState? {
        guard let object = value as? [String: Any] else {
            return nil
        }
        return RuntimeDiscoveryMediaRouteReceiptState(
            mediaRoute: stringText(for: object["media_route"]),
            mediaPartsCount: nonNegativeInt(for: object["media_parts_count"]),
            mediaTurnCount: nonNegativeInt(for: object["media_turn_count"]),
            cacheHitCount: nonNegativeInt(for: object["cache_hit_count"]),
            cacheMissCount: nonNegativeInt(for: object["cache_miss_count"]),
            unsupportedReason: stringText(for: object["unsupported_reason"])
        )
    }

    private static func aliasDiscovery(from value: Any?) -> RuntimeDiscoveryAliasState? {
        guard let object = value as? [String: Any] else {
            return nil
        }
        let suggestions = aliasSuggestions(from: object["suggestions"])
        return RuntimeDiscoveryAliasState(
            query: stringText(for: object["query"]),
            status: stringText(for: object["status"]),
            suggestions: suggestions,
            suggestionsText: suggestions.map(\.displayText).joined(separator: " | ")
        )
    }

    private static func aliasSuggestions(from value: Any?) -> [RuntimeDiscoveryAliasSuggestionState] {
        (value as? [[String: Any]] ?? []).map { suggestion in
            RuntimeDiscoveryAliasSuggestionState(
                modelID: stringText(for: suggestion["model_id"]),
                family: stringText(for: suggestion["family"]),
                aliases: stringArray(for: suggestion["aliases"]),
                quantization: stringText(for: suggestion["quantization"])
            )
        }
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

    private static func nonNegativeInt(for value: Any?) -> Int {
        if let int = value as? Int {
            return max(0, int)
        }
        if let number = value as? NSNumber {
            return max(0, number.intValue)
        }
        if let string = value as? String, let int = Int(string) {
            return max(0, int)
        }
        return 0
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
