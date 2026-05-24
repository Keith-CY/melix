import Foundation

public struct RuntimeDatasetVersionReceiptState: Equatable, Sendable {
    public let schemaVersion: String
    public let status: String
    public let datasetID: String
    public let versionID: String
    public let createdAt: String
    public let workspaceProjectID: String
    public let trainCount: Int
    public let validationCount: Int
    public let failedCount: Int
    public let qualitySummaryPath: String
    public let packageManifestPath: String
    public let samplesPath: String
    public let validationSamplesPath: String
    public let failedSegmentsPath: String
    public let metrics: [String: Double]
}

public struct RuntimeDatasetRetryReceiptState: Equatable, Sendable {
    public let schemaVersion: String
    public let baseVersionID: String
    public let retryVersionID: String
    public let inputFailedSegmentCount: Int
    public let retrySuccessCount: Int
    public let retryFailedCount: Int
    public let reusedSuccessfulSampleCount: Int
    public let rewrittenSuccessfulSampleCount: Int
    public let failedRetrySuccessRate: Double
    public let datasetVersionPath: String
    public let metrics: [String: Double]
}

public struct RuntimeDatasetVersionListState: Equatable, Sendable {
    public let schemaVersion: String
    public let workspaceManifestPath: String
    public let datasetID: String
    public let versions: [RuntimeDatasetVersionRowState]
    public let metrics: [String: Double]
}

public struct RuntimeDatasetVersionRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let datasetID: String
    public let versionID: String
    public let createdAt: String
    public let status: String
    public let trainCount: Int
    public let validationCount: Int
    public let failedCount: Int
    public let qualitySummaryPath: String
    public let datasetVersionPath: String
}

public struct RuntimeDatasetQualitySummaryState: Equatable, Sendable {
    public let schemaVersion: String
    public let datasetID: String
    public let versionID: String
    public let score: Double
    public let grade: String
    public let successRate: Double
    public let failedCount: Int
    public let trainCount: Int
    public let validationCount: Int
    public let piiMaskCount: Int
    public let dedupRatio: Double
    public let meanOutputLength: Double
    public let p95OutputLength: Double
    public let policyID: String
    public let reviewNotes: [String]
    public let blockingReasons: [String]
    public let metrics: [String: Double]
}

public enum RuntimeDatasetVersionReceiptDecoder {
    public static func decode(_ output: String) throws -> RuntimeDatasetVersionReceiptState {
        let payload = try JSONDecoder().decode(RuntimeDatasetVersionReceiptPayload.self, from: Data(output.utf8))
        return payload.state()
    }
}

public enum RuntimeDatasetRetryReceiptDecoder {
    public static func decode(_ output: String) throws -> RuntimeDatasetRetryReceiptState {
        let payload = try JSONDecoder().decode(RuntimeDatasetRetryReceiptPayload.self, from: Data(output.utf8))
        return payload.state()
    }
}

public enum RuntimeDatasetVersionListDecoder {
    public static func decode(_ output: String) throws -> RuntimeDatasetVersionListState {
        let payload = try JSONDecoder().decode(RuntimeDatasetVersionListPayload.self, from: Data(output.utf8))
        return payload.state()
    }
}

public enum RuntimeDatasetQualitySummaryDecoder {
    public static func decode(_ output: String) throws -> RuntimeDatasetQualitySummaryState {
        let payload = try JSONDecoder().decode(RuntimeDatasetQualitySummaryPayload.self, from: Data(output.utf8))
        return payload.state()
    }
}

private struct RuntimeDatasetVersionReceiptPayload: Decodable {
    let schemaVersion: String
    let status: String
    let datasetID: String
    let versionID: String
    let createdAt: String
    let workspaceProjectID: String
    let trainCount: Int
    let validationCount: Int
    let failedCount: Int
    let qualitySummaryPath: String
    let packageManifestPath: String
    let samplesPath: String
    let validationSamplesPath: String
    let failedSegmentsPath: String
    let metrics: [String: Double]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case datasetID = "dataset_id"
        case versionID = "version_id"
        case createdAt = "created_at"
        case workspaceProjectID = "workspace_project_id"
        case trainCount = "train_count"
        case validationCount = "validation_count"
        case failedCount = "failed_count"
        case qualitySummaryPath = "quality_summary_path"
        case packageManifestPath = "package_manifest_path"
        case samplesPath = "samples_path"
        case validationSamplesPath = "validation_samples_path"
        case failedSegmentsPath = "failed_segments_path"
        case metrics
    }

    func state() -> RuntimeDatasetVersionReceiptState {
        .init(
            schemaVersion: schemaVersion,
            status: status,
            datasetID: datasetID,
            versionID: versionID,
            createdAt: createdAt,
            workspaceProjectID: workspaceProjectID,
            trainCount: trainCount,
            validationCount: validationCount,
            failedCount: failedCount,
            qualitySummaryPath: qualitySummaryPath,
            packageManifestPath: packageManifestPath,
            samplesPath: samplesPath,
            validationSamplesPath: validationSamplesPath,
            failedSegmentsPath: failedSegmentsPath,
            metrics: metrics
        )
    }
}

private struct RuntimeDatasetRetryReceiptPayload: Decodable {
    let schemaVersion: String
    let baseVersionID: String
    let retryVersionID: String
    let inputFailedSegmentCount: Int
    let retrySuccessCount: Int
    let retryFailedCount: Int
    let reusedSuccessfulSampleCount: Int
    let rewrittenSuccessfulSampleCount: Int
    let failedRetrySuccessRate: Double
    let datasetVersionPath: String
    let metrics: [String: Double]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case baseVersionID = "base_version_id"
        case retryVersionID = "retry_version_id"
        case inputFailedSegmentCount = "input_failed_segment_count"
        case retrySuccessCount = "retry_success_count"
        case retryFailedCount = "retry_failed_count"
        case reusedSuccessfulSampleCount = "reused_successful_sample_count"
        case rewrittenSuccessfulSampleCount = "rewritten_successful_sample_count"
        case failedRetrySuccessRate = "failed_retry_success_rate"
        case datasetVersionPath = "dataset_version_path"
        case metrics
    }

    func state() -> RuntimeDatasetRetryReceiptState {
        .init(
            schemaVersion: schemaVersion,
            baseVersionID: baseVersionID,
            retryVersionID: retryVersionID,
            inputFailedSegmentCount: inputFailedSegmentCount,
            retrySuccessCount: retrySuccessCount,
            retryFailedCount: retryFailedCount,
            reusedSuccessfulSampleCount: reusedSuccessfulSampleCount,
            rewrittenSuccessfulSampleCount: rewrittenSuccessfulSampleCount,
            failedRetrySuccessRate: failedRetrySuccessRate,
            datasetVersionPath: datasetVersionPath,
            metrics: metrics
        )
    }
}

private struct RuntimeDatasetVersionListPayload: Decodable {
    let schemaVersion: String
    let workspaceManifestPath: String
    let datasetID: String
    let versions: [RuntimeDatasetVersionRowPayload]
    let metrics: [String: Double]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case workspaceManifestPath = "workspace_manifest_path"
        case datasetID = "dataset_id"
        case versions
        case metrics
    }

    func state() -> RuntimeDatasetVersionListState {
        .init(
            schemaVersion: schemaVersion,
            workspaceManifestPath: workspaceManifestPath,
            datasetID: datasetID,
            versions: versions.map { $0.state() },
            metrics: metrics
        )
    }
}

private struct RuntimeDatasetVersionRowPayload: Decodable {
    let datasetID: String
    let versionID: String
    let createdAt: String
    let status: String
    let trainCount: Int
    let validationCount: Int
    let failedCount: Int
    let qualitySummaryPath: String
    let datasetVersionPath: String

    enum CodingKeys: String, CodingKey {
        case datasetID = "dataset_id"
        case versionID = "version_id"
        case createdAt = "created_at"
        case status
        case trainCount = "train_count"
        case validationCount = "validation_count"
        case failedCount = "failed_count"
        case qualitySummaryPath = "quality_summary_path"
        case datasetVersionPath = "dataset_version_path"
    }

    func state() -> RuntimeDatasetVersionRowState {
        .init(
            id: "\(datasetID):\(versionID)",
            datasetID: datasetID,
            versionID: versionID,
            createdAt: createdAt,
            status: status,
            trainCount: trainCount,
            validationCount: validationCount,
            failedCount: failedCount,
            qualitySummaryPath: qualitySummaryPath,
            datasetVersionPath: datasetVersionPath
        )
    }
}

private struct RuntimeDatasetQualitySummaryPayload: Decodable {
    let schemaVersion: String
    let datasetID: String
    let versionID: String
    let score: Double
    let grade: String
    let successRate: Double
    let failedCount: Int
    let trainCount: Int
    let validationCount: Int
    let piiMaskCount: Int
    let dedupRatio: Double
    let meanOutputLength: Double
    let p95OutputLength: Double
    let policyID: String
    let reviewNotes: [String]
    let blockingReasons: [String]
    let metrics: [String: Double]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case datasetID = "dataset_id"
        case versionID = "version_id"
        case score
        case grade
        case successRate = "success_rate"
        case failedCount = "failed_count"
        case trainCount = "train_count"
        case validationCount = "validation_count"
        case piiMaskCount = "pii_mask_count"
        case dedupRatio = "dedup_ratio"
        case meanOutputLength = "mean_output_length"
        case p95OutputLength = "p95_output_length"
        case policyID = "policy_id"
        case reviewNotes = "review_notes"
        case blockingReasons = "blocking_reasons"
        case metrics
    }

    func state() -> RuntimeDatasetQualitySummaryState {
        .init(
            schemaVersion: schemaVersion,
            datasetID: datasetID,
            versionID: versionID,
            score: score,
            grade: grade,
            successRate: successRate,
            failedCount: failedCount,
            trainCount: trainCount,
            validationCount: validationCount,
            piiMaskCount: piiMaskCount,
            dedupRatio: dedupRatio,
            meanOutputLength: meanOutputLength,
            p95OutputLength: p95OutputLength,
            policyID: policyID,
            reviewNotes: reviewNotes,
            blockingReasons: blockingReasons,
            metrics: metrics
        )
    }
}
