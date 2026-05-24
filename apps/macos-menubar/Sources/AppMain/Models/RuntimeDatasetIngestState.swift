import Foundation

public struct RuntimeDatasetIngestReceiptState: Equatable, Sendable {
    public let schemaVersion: String
    public let status: String
    public let workspaceProjectID: String
    public let datasetPreparationID: String
    public let sourceInventory: [RuntimeDatasetIngestSourceState]
    public let operatorFailures: [RuntimeDatasetIngestFailureState]
    public let qualityControlSummary: [String: Double]
    public let metrics: [String: Double]

    public init(
        schemaVersion: String,
        status: String,
        workspaceProjectID: String,
        datasetPreparationID: String,
        sourceInventory: [RuntimeDatasetIngestSourceState],
        operatorFailures: [RuntimeDatasetIngestFailureState],
        qualityControlSummary: [String: Double],
        metrics: [String: Double]
    ) {
        self.schemaVersion = schemaVersion
        self.status = status
        self.workspaceProjectID = workspaceProjectID
        self.datasetPreparationID = datasetPreparationID
        self.sourceInventory = sourceInventory
        self.operatorFailures = operatorFailures
        self.qualityControlSummary = qualityControlSummary
        self.metrics = metrics
    }
}

public struct RuntimeDatasetIngestSourceState: Identifiable, Equatable, Sendable {
    public let id: String
    public let sourceKind: String
    public let recordCount: Int

    public init(id: String, sourceKind: String, recordCount: Int) {
        self.id = id
        self.sourceKind = sourceKind
        self.recordCount = recordCount
    }
}

public struct RuntimeDatasetIngestFailureState: Identifiable, Equatable, Sendable {
    public let id: String
    public let code: String
    public let detail: String
    public let recoveryHint: String

    public init(id: String, code: String, detail: String, recoveryHint: String) {
        self.id = id
        self.code = code
        self.detail = detail
        self.recoveryHint = recoveryHint
    }
}

public enum RuntimeDatasetIngestReceiptDecoder {
    public static func decode(_ output: String) throws -> RuntimeDatasetIngestReceiptState {
        try decode(Data(output.utf8))
    }

    public static func decode(_ data: Data) throws -> RuntimeDatasetIngestReceiptState {
        let payload = try JSONDecoder().decode(RuntimeDatasetIngestReceiptPayload.self, from: data)
        return payload.state()
    }
}

private struct RuntimeDatasetIngestReceiptPayload: Decodable {
    let schemaVersion: String
    let status: String
    let workspaceProjectID: String
    let datasetPreparationID: String
    let sourceInventory: [RuntimeDatasetIngestSourcePayload]
    let operatorFailures: [RuntimeDatasetIngestFailurePayload]
    let qualityControlSummary: [String: Double]
    let metrics: [String: Double]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case workspaceProjectID = "workspace_project_id"
        case datasetPreparationID = "dataset_preparation_id"
        case sourceInventory = "source_inventory"
        case operatorFailures = "operator_failures"
        case qualityControlSummary = "quality_control_summary"
        case metrics
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decode(String.self, forKey: .schemaVersion)
        status = try container.decode(String.self, forKey: .status)
        workspaceProjectID = try container.decode(String.self, forKey: .workspaceProjectID)
        datasetPreparationID = try container.decode(String.self, forKey: .datasetPreparationID)
        sourceInventory = try container.decode([RuntimeDatasetIngestSourcePayload].self, forKey: .sourceInventory)
        operatorFailures = try container.decodeIfPresent(
            [RuntimeDatasetIngestFailurePayload].self,
            forKey: .operatorFailures
        ) ?? []
        qualityControlSummary = try container.decode([String: Double].self, forKey: .qualityControlSummary)
        metrics = try container.decode([String: Double].self, forKey: .metrics)
    }

    func state() -> RuntimeDatasetIngestReceiptState {
        RuntimeDatasetIngestReceiptState(
            schemaVersion: schemaVersion,
            status: status,
            workspaceProjectID: workspaceProjectID,
            datasetPreparationID: datasetPreparationID,
            sourceInventory: sourceInventory.map { $0.state() },
            operatorFailures: operatorFailures.map { $0.state() },
            qualityControlSummary: qualityControlSummary,
            metrics: metrics
        )
    }
}

private struct RuntimeDatasetIngestSourcePayload: Decodable {
    let sourceID: String
    let sourceKind: String
    let recordCount: Int

    enum CodingKeys: String, CodingKey {
        case sourceID = "source_id"
        case sourceKind = "source_kind"
        case recordCount = "record_count"
    }

    func state() -> RuntimeDatasetIngestSourceState {
        RuntimeDatasetIngestSourceState(
            id: sourceID,
            sourceKind: sourceKind,
            recordCount: recordCount
        )
    }
}

private struct RuntimeDatasetIngestFailurePayload: Decodable {
    let id: String
    let code: String
    let detail: String
    let recoveryHint: String

    enum CodingKeys: String, CodingKey {
        case id
        case code
        case detail
        case recoveryHint = "recovery_hint"
    }

    func state() -> RuntimeDatasetIngestFailureState {
        RuntimeDatasetIngestFailureState(
            id: id,
            code: code,
            detail: detail,
            recoveryHint: recoveryHint
        )
    }
}
