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

public struct RuntimeSyntheticDatasetErrorState: Identifiable, Equatable, Sendable {
    public let source: String
    public let title: String
    public let detail: String
    public let recoveryHint: String

    public init(source: String, title: String, detail: String, recoveryHint: String) {
        self.source = source
        self.title = title
        self.detail = detail
        self.recoveryHint = recoveryHint
    }

    public var id: String {
        "\(source)|\(title)|\(detail)"
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

public struct RuntimeSyntheticDatasetPreviewFieldState: Identifiable, Equatable, Sendable {
    public let name: String
    public let valueText: String

    public init(name: String, valueText: String) {
        self.name = name
        self.valueText = valueText
    }

    public var id: String {
        name
    }
}

public struct RuntimeSyntheticDatasetPreviewRowState: Identifiable, Equatable, Sendable {
    public let index: Int
    public let fields: [RuntimeSyntheticDatasetPreviewFieldState]

    public init(index: Int, fields: [RuntimeSyntheticDatasetPreviewFieldState]) {
        self.index = index
        self.fields = fields
    }

    public var id: String {
        "preview-row-\(index)"
    }

    public var summaryText: String {
        fields.map { "\($0.name)=\($0.valueText)" }.joined(separator: " | ")
    }
}

public struct RuntimeSyntheticDatasetArtifactRowState: Identifiable, Equatable, Sendable {
    public let name: String
    public let path: String

    public init(name: String, path: String) {
        self.name = name
        self.path = path
    }

    public var id: String {
        "\(name)|\(path)"
    }
}

public struct RuntimeSyntheticDatasetManifestRowState: Identifiable, Equatable, Sendable {
    public let name: String
    public let valueText: String

    public init(name: String, valueText: String) {
        self.name = name
        self.valueText = valueText
    }

    public var id: String {
        name
    }
}

public struct RuntimeSyntheticDatasetPreviewState: Equatable, Sendable {
    public let schemaVersion: String
    public let datasetID: String
    public let datasetName: String
    public let outputKind: String
    public let outputFormat: String
    public let rowCount: Int
    public let sampleCount: Int
    public let previewCount: Int
    public let previewOnly: Bool
    public let previewRows: [RuntimeSyntheticDatasetPreviewRowState]
    public let artifactRows: [RuntimeSyntheticDatasetArtifactRowState]

    public init(
        schemaVersion: String,
        datasetID: String,
        datasetName: String,
        outputKind: String,
        outputFormat: String,
        rowCount: Int,
        sampleCount: Int,
        previewCount: Int,
        previewOnly: Bool,
        previewRows: [RuntimeSyntheticDatasetPreviewRowState],
        artifactRows: [RuntimeSyntheticDatasetArtifactRowState]
    ) {
        self.schemaVersion = schemaVersion
        self.datasetID = datasetID
        self.datasetName = datasetName
        self.outputKind = outputKind
        self.outputFormat = outputFormat
        self.rowCount = rowCount
        self.sampleCount = sampleCount
        self.previewCount = previewCount
        self.previewOnly = previewOnly
        self.previewRows = previewRows
        self.artifactRows = artifactRows
    }

    public var summaryText: String {
        let label = datasetID.isEmpty ? datasetName : datasetID
        let rowLabel = sampleCount == 1 ? "row" : "rows"
        return "\(label) preview contains \(sampleCount) \(rowLabel)."
    }
}

public struct RuntimeSyntheticDatasetCreateResultState: Equatable, Sendable {
    public let schemaVersion: String
    public let datasetID: String
    public let datasetName: String
    public let outputKind: String
    public let outputFormat: String
    public let rowCount: Int
    public let sampleCount: Int
    public let previewOnly: Bool
    public let manifestRows: [RuntimeSyntheticDatasetManifestRowState]
    public let artifactRows: [RuntimeSyntheticDatasetArtifactRowState]

    public init(
        schemaVersion: String,
        datasetID: String,
        datasetName: String,
        outputKind: String,
        outputFormat: String,
        rowCount: Int,
        sampleCount: Int,
        previewOnly: Bool,
        manifestRows: [RuntimeSyntheticDatasetManifestRowState],
        artifactRows: [RuntimeSyntheticDatasetArtifactRowState]
    ) {
        self.schemaVersion = schemaVersion
        self.datasetID = datasetID
        self.datasetName = datasetName
        self.outputKind = outputKind
        self.outputFormat = outputFormat
        self.rowCount = rowCount
        self.sampleCount = sampleCount
        self.previewOnly = previewOnly
        self.manifestRows = manifestRows
        self.artifactRows = artifactRows
    }

    public var summaryText: String {
        let label = datasetID.isEmpty ? datasetName : datasetID
        let rowLabel = rowCount == 1 ? "row" : "rows"
        return "\(label) package contains \(rowCount) \(rowLabel)."
    }
}

public enum RuntimeSyntheticDatasetPayloadDecoder {
    public static func decodePreview(_ output: String) throws -> RuntimeSyntheticDatasetPreviewState {
        try decodePreview(Data(output.utf8))
    }

    public static func decodePreview(_ data: Data) throws -> RuntimeSyntheticDatasetPreviewState {
        let payload = try jsonObject(from: data, message: "Synthetic dataset preview payload must be a JSON object.")
        let previewRows = (payload["preview_samples"] as? [[String: Any]] ?? []).enumerated().map { index, row in
            RuntimeSyntheticDatasetPreviewRowState(
                index: index + 1,
                fields: row.keys.sorted().map { key in
                    RuntimeSyntheticDatasetPreviewFieldState(
                        name: key,
                        valueText: displayText(for: row[key] ?? NSNull())
                    )
                }
            )
        }
        return RuntimeSyntheticDatasetPreviewState(
            schemaVersion: stringText(for: payload["schema_version"]),
            datasetID: stringText(for: payload["dataset_id"]),
            datasetName: stringText(for: payload["dataset_name"]),
            outputKind: stringText(for: payload["output_kind"]),
            outputFormat: stringText(for: payload["output_format"]),
            rowCount: intValue(for: payload["row_count"], fallback: previewRows.count),
            sampleCount: intValue(for: payload["sample_count"], fallback: previewRows.count),
            previewCount: intValue(for: payload["preview_count"], fallback: previewRows.count),
            previewOnly: boolValue(for: payload["preview_only"]),
            previewRows: previewRows,
            artifactRows: artifactRows(from: payload)
        )
    }

    public static func decodeCreate(_ output: String) throws -> RuntimeSyntheticDatasetCreateResultState {
        try decodeCreate(Data(output.utf8))
    }

    public static func decodeCreate(_ data: Data) throws -> RuntimeSyntheticDatasetCreateResultState {
        let payload = try jsonObject(from: data, message: "Synthetic dataset create payload must be a JSON object.")
        let rowCount = intValue(for: payload["row_count"], fallback: 0)
        return RuntimeSyntheticDatasetCreateResultState(
            schemaVersion: stringText(for: payload["schema_version"]),
            datasetID: stringText(for: payload["dataset_id"]),
            datasetName: stringText(for: payload["dataset_name"]),
            outputKind: stringText(for: payload["output_kind"]),
            outputFormat: stringText(for: payload["output_format"]),
            rowCount: rowCount,
            sampleCount: intValue(for: payload["sample_count"], fallback: rowCount),
            previewOnly: boolValue(for: payload["preview_only"]),
            manifestRows: manifestRows(from: payload),
            artifactRows: artifactRows(from: payload)
        )
    }

    private static func manifestRows(from payload: [String: Any]) -> [RuntimeSyntheticDatasetManifestRowState] {
        payload.keys.sorted().compactMap { key in
            guard isManifestScalarKey(key),
                  let value = payload[key],
                  isScalarManifestValue(value)
            else {
                return nil
            }
            return RuntimeSyntheticDatasetManifestRowState(name: key, valueText: displayText(for: value))
        }
    }

    private static func artifactRows(from payload: [String: Any]) -> [RuntimeSyntheticDatasetArtifactRowState] {
        var rows: [RuntimeSyntheticDatasetArtifactRowState] = []
        appendPathRows(from: payload, into: &rows)
        let dataDesigner = payload["datadesigner"] as? [String: Any] ?? [:]
        for key in ["artifact_path", "config_path", "generated_jsonl_path"] {
            if let path = nonEmptyString(dataDesigner[key]) {
                rows.append(.init(name: key, path: path))
            }
        }
        let package = payload["package"] as? [String: Any] ?? [:]
        appendPathRows(from: package, prefix: "package.", into: &rows)
        return rows.sorted { lhs, rhs in
            if lhs.name == rhs.name {
                return lhs.path < rhs.path
            }
            return lhs.name < rhs.name
        }
    }

    private static func appendPathRows(
        from payload: [String: Any],
        prefix: String = "",
        into rows: inout [RuntimeSyntheticDatasetArtifactRowState]
    ) {
        for key in payload.keys.sorted() where isArtifactPathKey(key) {
            if let path = nonEmptyString(payload[key]) {
                rows.append(.init(name: "\(prefix)\(key)", path: path))
            }
        }
    }

    private static func isManifestScalarKey(_ key: String) -> Bool {
        guard isArtifactPathKey(key) == false else {
            return false
        }
        return key != "datadesigner" && key != "package" && key != "preview_samples"
    }

    private static func isArtifactPathKey(_ key: String) -> Bool {
        key == "path" || key.hasSuffix("_path")
    }

    private static func isScalarManifestValue(_ value: Any) -> Bool {
        value is String || value is NSNumber || value is Bool
    }

    private static func jsonObject(from data: Data, message: String) throws -> [String: Any] {
        let decoded = try JSONSerialization.jsonObject(with: data)
        guard let payload = decoded as? [String: Any] else {
            throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: message))
        }
        return payload
    }

    private static func nonEmptyString(_ value: Any?) -> String? {
        let text = stringText(for: value)
        return text.isEmpty ? nil : text
    }

    private static func stringText(for value: Any?) -> String {
        guard let value, value is NSNull == false else {
            return ""
        }
        if let string = value as? String {
            return string
        }
        return displayText(for: value)
    }

    private static func intValue(for value: Any?, fallback: Int) -> Int {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let string = value as? String, let int = Int(string) {
            return int
        }
        return fallback
    }

    private static func boolValue(for value: Any?) -> Bool {
        if let bool = value as? Bool {
            return bool
        }
        if let number = value as? NSNumber {
            return number.boolValue
        }
        if let string = value as? String {
            return ["true", "1", "yes"].contains(string.lowercased())
        }
        return false
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
}
