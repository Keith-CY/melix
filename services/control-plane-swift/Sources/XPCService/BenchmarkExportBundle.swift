import Foundation

public enum ControlPlaneBenchmarkExportError: Error, LocalizedError, Equatable, Sendable {
    case invalidJSON(String)

    public var errorDescription: String? {
        switch self {
        case .invalidJSON(let message):
            return message
        }
    }
}

public struct ControlPlaneBenchmarkSuiteMetadata: Codable, Equatable, Sendable {
    public let title: String?
    public let sourceKind: String?
    public let datasetURI: String?
    public let datasetPath: String?
    public let datasetName: String?
    public let datasetRevision: String?
    public let datasetSplit: String?
    public let materializedPackagePath: String?
    public let cacheKey: String?
    public let cacheHit: Bool?
    public let sampleSize: Int?
    public let batchFactor: Int?

    enum CodingKeys: String, CodingKey {
        case title
        case sourceKind = "source_kind"
        case datasetURI = "dataset_uri"
        case datasetPath = "dataset_path"
        case datasetName = "dataset_name"
        case datasetRevision = "dataset_revision"
        case datasetSplit = "dataset_split"
        case materializedPackagePath = "materialized_package_path"
        case cacheKey = "cache_key"
        case cacheHit = "cache_hit"
        case sampleSize = "sample_size"
        case batchFactor = "batch_factor"
    }
}

public struct ControlPlaneBenchmarkMetricRecord: Codable, Equatable, Sendable {
    public let name: String
    public let value: Double
    public let unit: String
}

public struct ControlPlaneBenchmarkResultRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let suite: String
    public let metrics: [ControlPlaneBenchmarkMetricRecord]
    public let reportPath: String
    public let reportMarkdown: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case suite
        case metrics
        case reportPath = "report_path"
        case reportMarkdown = "report_markdown"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        suite = try container.decodeIfPresent(String.self, forKey: .suite) ?? ""
        metrics = try container.decodeIfPresent([ControlPlaneBenchmarkMetricRecord].self, forKey: .metrics) ?? []
        reportPath = try container.decodeIfPresent(String.self, forKey: .reportPath) ?? ""
        reportMarkdown = try container.decodeIfPresent(String.self, forKey: .reportMarkdown) ?? ""
    }
}

public struct ControlPlaneBenchmarkJobRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suites: [String]
    public let parameters: [String: String]
    public let status: String
    public let outputDir: String
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
    public let suiteMetadata: [String: ControlPlaneBenchmarkSuiteMetadata]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case modelID = "model_id"
        case taskKind = "task_kind"
        case sourceRepo = "source_repo"
        case suites
        case parameters
        case status
        case outputDir = "output_dir"
        case createdAtUnixMS = "created_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
        case suiteMetadata = "suite_metadata"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        modelID = try container.decodeIfPresent(String.self, forKey: .modelID) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        sourceRepo = try container.decodeIfPresent(String.self, forKey: .sourceRepo) ?? ""
        suites = try container.decodeIfPresent([String].self, forKey: .suites) ?? []
        parameters = try container.decodeIfPresent([String: String].self, forKey: .parameters) ?? [:]
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        outputDir = try container.decodeIfPresent(String.self, forKey: .outputDir) ?? ""
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
        updatedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .updatedAtUnixMS) ?? 0
        suiteMetadata = try container.decodeIfPresent([String: ControlPlaneBenchmarkSuiteMetadata].self, forKey: .suiteMetadata) ?? [:]
    }
}

public struct ControlPlaneBenchmarkHistoryEntry: Codable, Equatable, Sendable {
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let suiteTitle: String
    public let datasetRepo: String
    public let datasetConfig: String
    public let datasetSplit: String
    public let sampleSize: Int?
    public let batchFactor: Int?
    public let status: String
    public let metricCount: Int
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
    public let reportPath: String
}

public struct ControlPlaneBenchmarkCSVRow: Codable, Equatable, Sendable {
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let datasetRepo: String
    public let datasetConfig: String
    public let datasetSplit: String
    public let sampleSize: Int?
    public let batchFactor: Int?
    public let metricName: String
    public let metricValue: Double
    public let unit: String
    public let createdAtUnixMS: Int64
}

public struct ControlPlaneBenchmarkMatrixJobRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteIDs: [String]
    public let benchmarkMode: String
    public let status: String
    public let outputDir: String
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
    public let parameters: [String: String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case modelID = "model_id"
        case taskKind = "task_kind"
        case sourceRepo = "source_repo"
        case suiteIDs = "suite_ids"
        case benchmarkMode = "benchmark_mode"
        case status
        case outputDir = "output_dir"
        case createdAtUnixMS = "created_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
        case parameters
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        modelID = try container.decodeIfPresent(String.self, forKey: .modelID) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        sourceRepo = try container.decodeIfPresent(String.self, forKey: .sourceRepo) ?? ""
        suiteIDs = try container.decodeIfPresent([String].self, forKey: .suiteIDs) ?? []
        benchmarkMode = try container.decodeIfPresent(String.self, forKey: .benchmarkMode) ?? ""
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        outputDir = try container.decodeIfPresent(String.self, forKey: .outputDir) ?? ""
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
        updatedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .updatedAtUnixMS) ?? 0
        parameters = try container.decodeIfPresent([String: String].self, forKey: .parameters) ?? [:]
    }
}

public struct ControlPlaneBenchmarkMatrixSummaryCSVRow: Codable, Equatable, Sendable {
    public let jobID: String
    public let taskKind: String
    public let sourceRepo: String
    public let modelID: String
    public let suiteID: String
    public let contextLength: Int
    public let generationLength: Int
    public let batchSize: Int
    public let cacheProfile: String
    public let reasoningMode: String
    public let structuredOutputMode: String
    public let concurrencyLevel: Int
    public let repeats: Int
    public let requests: Int
    public let durationSeconds: Int
    public let ttftMeanMS: Double
    public let ttftStdMS: Double
    public let requestLatencyMeanMS: Double
    public let requestLatencyStdMS: Double
    public let prefillTokensPerSecondMean: Double
    public let decodeTokensPerSecondMean: Double
    public let throughputRequestsPerSecond: Double
    public let throughputTokensPerSecond: Double
    public let successRate: Double
    public let peakMemoryBytesMax: UInt64
    public let queueWaitMeanMS: Double
    public let queueWaitP95MS: Double
    public let cellWallMS: Double
    public let completedCount: Int
    public let failedCount: Int
    public let ttftP50MS: Double
    public let ttftP95MS: Double
    public let requestLatencyP50MS: Double
    public let requestLatencyP95MS: Double
    public let createdAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case taskKind = "task_kind"
        case sourceRepo = "source_repo"
        case modelID = "model_id"
        case suiteID = "suite_id"
        case contextLength = "context_length"
        case generationLength = "generation_length"
        case batchSize = "batch_size"
        case cacheProfile = "cache_profile"
        case reasoningMode = "reasoning_mode"
        case structuredOutputMode = "structured_output_mode"
        case concurrencyLevel = "concurrency_level"
        case repeats
        case requests
        case durationSeconds = "duration_seconds"
        case ttftMeanMS = "ttft_mean_ms"
        case ttftStdMS = "ttft_std_ms"
        case requestLatencyMeanMS = "request_latency_mean_ms"
        case requestLatencyStdMS = "request_latency_std_ms"
        case prefillTokensPerSecondMean = "prefill_tokens_per_second_mean"
        case decodeTokensPerSecondMean = "decode_tokens_per_second_mean"
        case throughputRequestsPerSecond = "throughput_requests_per_second"
        case throughputTokensPerSecond = "throughput_tokens_per_second"
        case successRate = "success_rate"
        case peakMemoryBytesMax = "peak_memory_bytes_max"
        case queueWaitMeanMS = "queue_wait_mean_ms"
        case queueWaitP95MS = "queue_wait_p95_ms"
        case cellWallMS = "cell_wall_ms"
        case completedCount = "completed_count"
        case failedCount = "failed_count"
        case ttftP50MS = "ttft_p50_ms"
        case ttftP95MS = "ttft_p95_ms"
        case requestLatencyP50MS = "request_latency_p50_ms"
        case requestLatencyP95MS = "request_latency_p95_ms"
        case createdAtUnixMS = "created_at_unix_ms"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        sourceRepo = try container.decodeIfPresent(String.self, forKey: .sourceRepo) ?? ""
        modelID = try container.decodeIfPresent(String.self, forKey: .modelID) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        contextLength = try container.decodeIfPresent(Int.self, forKey: .contextLength) ?? 0
        generationLength = try container.decodeIfPresent(Int.self, forKey: .generationLength) ?? 0
        batchSize = try container.decodeIfPresent(Int.self, forKey: .batchSize) ?? 0
        cacheProfile = try container.decodeIfPresent(String.self, forKey: .cacheProfile) ?? ""
        reasoningMode = try container.decodeIfPresent(String.self, forKey: .reasoningMode) ?? ""
        structuredOutputMode = try container.decodeIfPresent(String.self, forKey: .structuredOutputMode) ?? ""
        concurrencyLevel = try container.decodeIfPresent(Int.self, forKey: .concurrencyLevel) ?? 0
        repeats = try container.decodeIfPresent(Int.self, forKey: .repeats) ?? 0
        requests = try container.decodeIfPresent(Int.self, forKey: .requests) ?? 0
        durationSeconds = try container.decodeIfPresent(Int.self, forKey: .durationSeconds) ?? 0
        ttftMeanMS = try container.decodeIfPresent(Double.self, forKey: .ttftMeanMS) ?? 0
        ttftStdMS = try container.decodeIfPresent(Double.self, forKey: .ttftStdMS) ?? 0
        requestLatencyMeanMS = try container.decodeIfPresent(Double.self, forKey: .requestLatencyMeanMS) ?? 0
        requestLatencyStdMS = try container.decodeIfPresent(Double.self, forKey: .requestLatencyStdMS) ?? 0
        prefillTokensPerSecondMean = try container.decodeIfPresent(Double.self, forKey: .prefillTokensPerSecondMean) ?? 0
        decodeTokensPerSecondMean = try container.decodeIfPresent(Double.self, forKey: .decodeTokensPerSecondMean) ?? 0
        throughputRequestsPerSecond = try container.decodeIfPresent(Double.self, forKey: .throughputRequestsPerSecond) ?? 0
        throughputTokensPerSecond = try container.decodeIfPresent(Double.self, forKey: .throughputTokensPerSecond) ?? 0
        successRate = try container.decodeIfPresent(Double.self, forKey: .successRate) ?? 0
        peakMemoryBytesMax = try container.decodeIfPresent(UInt64.self, forKey: .peakMemoryBytesMax) ?? 0
        queueWaitMeanMS = try container.decodeIfPresent(Double.self, forKey: .queueWaitMeanMS) ?? 0
        queueWaitP95MS = try container.decodeIfPresent(Double.self, forKey: .queueWaitP95MS) ?? 0
        cellWallMS = try container.decodeIfPresent(Double.self, forKey: .cellWallMS) ?? 0
        completedCount = try container.decodeIfPresent(Int.self, forKey: .completedCount) ?? 0
        failedCount = try container.decodeIfPresent(Int.self, forKey: .failedCount) ?? 0
        ttftP50MS = try container.decodeIfPresent(Double.self, forKey: .ttftP50MS) ?? 0
        ttftP95MS = try container.decodeIfPresent(Double.self, forKey: .ttftP95MS) ?? 0
        requestLatencyP50MS = try container.decodeIfPresent(Double.self, forKey: .requestLatencyP50MS) ?? 0
        requestLatencyP95MS = try container.decodeIfPresent(Double.self, forKey: .requestLatencyP95MS) ?? 0
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
    }
}

public struct ControlPlaneBenchmarkMatrixRequestCSVRow: Codable, Equatable, Sendable {
    public let jobID: String
    public let cellID: String
    public let taskKind: String
    public let suiteID: String
    public let contextLength: Int
    public let generationLength: Int
    public let batchSize: Int
    public let cacheProfile: String
    public let reasoningMode: String
    public let structuredOutputMode: String
    public let concurrencyLevel: Int
    public let repeatIndex: Int
    public let requestIndex: Int
    public let ttftMS: Double
    public let requestLatencyMS: Double
    public let prefillTokensPerSecond: Double
    public let decodeTokensPerSecond: Double
    public let queueWaitMS: Double
    public let peakMemoryBytes: UInt64
    public let status: String
    public let errorCode: String
    public let datasetMaterializeMS: Double
    public let promptRenderMS: Double
    public let warmupMS: Double
    public let prefillMS: Double
    public let decodeMS: Double
    public let tokensIn: Int
    public let tokensOut: Int
    public let firstTokenIndex: Int
    public let cacheHit: Bool
    public let runtimeKind: String
    public let errorStage: String
    public let speculativeAcceptanceRate: Double
    public let speculativeRollbackRate: Double
    public let speculativeAcceptedTokens: Int
    public let speculativeRejectedTokens: Int
    public let speculativeFallbackCount: Int
    public let speculativeNumDraftTokens: Int
    public let speculativeDraftModelConfigured: Bool
    public let speculativeDraftProposeMS: Double
    public let speculativeTargetVerifyMS: Double
    public let dflashEnabled: Bool
    public let dflashBlockSize: Int
    public let dflashRollbackCount: Int
    public let dflashTargetHiddenLayers: Int
    public let createdAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case cellID = "cell_id"
        case taskKind = "task_kind"
        case suiteID = "suite_id"
        case contextLength = "context_length"
        case generationLength = "generation_length"
        case batchSize = "batch_size"
        case cacheProfile = "cache_profile"
        case reasoningMode = "reasoning_mode"
        case structuredOutputMode = "structured_output_mode"
        case concurrencyLevel = "concurrency_level"
        case repeatIndex = "repeat_index"
        case requestIndex = "request_index"
        case ttftMS = "ttft_ms"
        case requestLatencyMS = "request_latency_ms"
        case prefillTokensPerSecond = "prefill_tokens_per_second"
        case decodeTokensPerSecond = "decode_tokens_per_second"
        case queueWaitMS = "queue_wait_ms"
        case peakMemoryBytes = "peak_memory_bytes"
        case status
        case errorCode = "error_code"
        case datasetMaterializeMS = "dataset_materialize_ms"
        case promptRenderMS = "prompt_render_ms"
        case warmupMS = "warmup_ms"
        case prefillMS = "prefill_ms"
        case decodeMS = "decode_ms"
        case tokensIn = "tokens_in"
        case tokensOut = "tokens_out"
        case firstTokenIndex = "first_token_index"
        case cacheHit = "cache_hit"
        case runtimeKind = "runtime_kind"
        case errorStage = "error_stage"
        case speculativeAcceptanceRate = "speculative_acceptance_rate"
        case speculativeRollbackRate = "speculative_rollback_rate"
        case speculativeAcceptedTokens = "speculative_accepted_tokens"
        case speculativeRejectedTokens = "speculative_rejected_tokens"
        case speculativeFallbackCount = "speculative_fallback_count"
        case speculativeNumDraftTokens = "speculative_num_draft_tokens"
        case speculativeDraftModelConfigured = "speculative_draft_model_configured"
        case speculativeDraftProposeMS = "speculative_draft_propose_ms"
        case speculativeTargetVerifyMS = "speculative_target_verify_ms"
        case dflashEnabled = "dflash_enabled"
        case dflashBlockSize = "dflash_block_size"
        case dflashRollbackCount = "dflash_rollback_count"
        case dflashTargetHiddenLayers = "dflash_target_hidden_layers"
        case createdAtUnixMS = "created_at_unix_ms"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        cellID = try container.decodeIfPresent(String.self, forKey: .cellID) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        contextLength = try container.decodeIfPresent(Int.self, forKey: .contextLength) ?? 0
        generationLength = try container.decodeIfPresent(Int.self, forKey: .generationLength) ?? 0
        batchSize = try container.decodeIfPresent(Int.self, forKey: .batchSize) ?? 0
        cacheProfile = try container.decodeIfPresent(String.self, forKey: .cacheProfile) ?? ""
        reasoningMode = try container.decodeIfPresent(String.self, forKey: .reasoningMode) ?? ""
        structuredOutputMode = try container.decodeIfPresent(String.self, forKey: .structuredOutputMode) ?? ""
        concurrencyLevel = try container.decodeIfPresent(Int.self, forKey: .concurrencyLevel) ?? 0
        repeatIndex = try container.decodeIfPresent(Int.self, forKey: .repeatIndex) ?? 0
        requestIndex = try container.decodeIfPresent(Int.self, forKey: .requestIndex) ?? 0
        ttftMS = try container.decodeIfPresent(Double.self, forKey: .ttftMS) ?? 0
        requestLatencyMS = try container.decodeIfPresent(Double.self, forKey: .requestLatencyMS) ?? 0
        prefillTokensPerSecond = try container.decodeIfPresent(Double.self, forKey: .prefillTokensPerSecond) ?? 0
        decodeTokensPerSecond = try container.decodeIfPresent(Double.self, forKey: .decodeTokensPerSecond) ?? 0
        queueWaitMS = try container.decodeIfPresent(Double.self, forKey: .queueWaitMS) ?? 0
        peakMemoryBytes = try container.decodeIfPresent(UInt64.self, forKey: .peakMemoryBytes) ?? 0
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        errorCode = try container.decodeIfPresent(String.self, forKey: .errorCode) ?? ""
        datasetMaterializeMS = try container.decodeIfPresent(Double.self, forKey: .datasetMaterializeMS) ?? 0
        promptRenderMS = try container.decodeIfPresent(Double.self, forKey: .promptRenderMS) ?? 0
        warmupMS = try container.decodeIfPresent(Double.self, forKey: .warmupMS) ?? 0
        prefillMS = try container.decodeIfPresent(Double.self, forKey: .prefillMS) ?? 0
        decodeMS = try container.decodeIfPresent(Double.self, forKey: .decodeMS) ?? 0
        tokensIn = try container.decodeIfPresent(Int.self, forKey: .tokensIn) ?? 0
        tokensOut = try container.decodeIfPresent(Int.self, forKey: .tokensOut) ?? 0
        firstTokenIndex = try container.decodeIfPresent(Int.self, forKey: .firstTokenIndex) ?? 0
        cacheHit = try container.decodeIfPresent(Bool.self, forKey: .cacheHit) ?? false
        runtimeKind = try container.decodeIfPresent(String.self, forKey: .runtimeKind) ?? ""
        errorStage = try container.decodeIfPresent(String.self, forKey: .errorStage) ?? ""
        speculativeAcceptanceRate = try container.decodeIfPresent(Double.self, forKey: .speculativeAcceptanceRate) ?? 0
        speculativeRollbackRate = try container.decodeIfPresent(Double.self, forKey: .speculativeRollbackRate) ?? 0
        speculativeAcceptedTokens = try container.decodeIfPresent(Int.self, forKey: .speculativeAcceptedTokens) ?? 0
        speculativeRejectedTokens = try container.decodeIfPresent(Int.self, forKey: .speculativeRejectedTokens) ?? 0
        speculativeFallbackCount = try container.decodeIfPresent(Int.self, forKey: .speculativeFallbackCount) ?? 0
        speculativeNumDraftTokens = try container.decodeIfPresent(Int.self, forKey: .speculativeNumDraftTokens) ?? 0
        speculativeDraftModelConfigured = try container.decodeIfPresent(Bool.self, forKey: .speculativeDraftModelConfigured) ?? false
        speculativeDraftProposeMS = try container.decodeIfPresent(Double.self, forKey: .speculativeDraftProposeMS) ?? 0
        speculativeTargetVerifyMS = try container.decodeIfPresent(Double.self, forKey: .speculativeTargetVerifyMS) ?? 0
        dflashEnabled = try container.decodeIfPresent(Bool.self, forKey: .dflashEnabled) ?? false
        dflashBlockSize = try container.decodeIfPresent(Int.self, forKey: .dflashBlockSize) ?? 0
        dflashRollbackCount = try container.decodeIfPresent(Int.self, forKey: .dflashRollbackCount) ?? 0
        dflashTargetHiddenLayers = try container.decodeIfPresent(Int.self, forKey: .dflashTargetHiddenLayers) ?? 0
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
    }
}

public struct ControlPlaneBenchmarkMatrixHistoryEntry: Codable, Equatable, Sendable {
    public let benchmarkMode: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let contextLength: Int
    public let generationLength: Int
    public let batchSize: Int
    public let cacheProfile: String
    public let reasoningMode: String
    public let structuredOutputMode: String
    public let concurrencyLevel: Int
    public let repeats: Int
    public let requests: Int
    public let durationSeconds: Int
    public let status: String
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
}

public struct ControlPlaneEvaluationJobRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let scoringMode: String
    public let parameters: [String: String]
    public let status: String
    public let outputDir: String
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case modelID = "model_id"
        case taskKind = "task_kind"
        case sourceRepo = "source_repo"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleSize = "sample_size"
        case scoringMode = "scoring_mode"
        case parameters
        case status
        case outputDir = "output_dir"
        case createdAtUnixMS = "created_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        modelID = try container.decodeIfPresent(String.self, forKey: .modelID) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        sourceRepo = try container.decodeIfPresent(String.self, forKey: .sourceRepo) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleSize = try container.decodeIfPresent(Int.self, forKey: .sampleSize) ?? 0
        scoringMode = try container.decodeIfPresent(String.self, forKey: .scoringMode) ?? ""
        parameters = try container.decodeIfPresent([String: String].self, forKey: .parameters) ?? [:]
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        outputDir = try container.decodeIfPresent(String.self, forKey: .outputDir) ?? ""
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
        updatedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .updatedAtUnixMS) ?? 0
    }
}

public struct ControlPlaneEvaluationResultRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let primaryScoreName: String
    public let primaryScoreValue: Double
    public let extractionSuccessCount: Int
    public let validationSuccessCount: Int
    public let scoredSampleCount: Int
    public let failureCount: Int
    public let durationSeconds: Double
    public let metrics: [ControlPlaneBenchmarkMetricRecord]
    public let reportPath: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleSize = "sample_size"
        case primaryScoreName = "primary_score_name"
        case primaryScoreValue = "primary_score_value"
        case extractionSuccessCount = "extraction_success_count"
        case validationSuccessCount = "validation_success_count"
        case scoredSampleCount = "scored_sample_count"
        case failureCount = "failure_count"
        case durationSeconds = "duration_seconds"
        case metrics
        case reportPath = "report_path"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleSize = try container.decodeIfPresent(Int.self, forKey: .sampleSize) ?? 0
        primaryScoreName = try container.decodeIfPresent(String.self, forKey: .primaryScoreName) ?? ""
        primaryScoreValue = try container.decodeIfPresent(Double.self, forKey: .primaryScoreValue) ?? 0
        extractionSuccessCount = try container.decodeIfPresent(Int.self, forKey: .extractionSuccessCount) ?? 0
        validationSuccessCount = try container.decodeIfPresent(Int.self, forKey: .validationSuccessCount) ?? 0
        scoredSampleCount = try container.decodeIfPresent(Int.self, forKey: .scoredSampleCount) ?? 0
        failureCount = try container.decodeIfPresent(Int.self, forKey: .failureCount) ?? 0
        durationSeconds = try container.decodeIfPresent(Double.self, forKey: .durationSeconds) ?? 0
        metrics = try container.decodeIfPresent([ControlPlaneBenchmarkMetricRecord].self, forKey: .metrics) ?? []
        reportPath = try container.decodeIfPresent(String.self, forKey: .reportPath) ?? ""
    }
}

public struct ControlPlaneEvaluationSampleRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let suiteID: String
    public let datasetID: String
    public let sampleID: String
    public let system: String
    public let inputText: String
    public let target: String
    public let rawResponse: String
    public let extractedResult: String
    public let typedScore: Double
    public let timeS: Double
    public let extractionStatus: String
    public let validationStatus: String
    public let failureReason: String
    public let taskKind: String
    public let inputModalities: [String]
    public let mediaReferences: [String]
    public let codeLanguage: String
    public let codeEntryPoint: String
    public let codeCompileStatus: String
    public let codeRuntimeStatus: String
    public let codeTimeoutStatus: String
    public let codeTestStatus: String
    public let codeTestsPassed: Int
    public let codeTestsTotal: Int
    public let codeFailureDetail: String
    public let categoryLabel: String
    public let subjectLabel: String
    public let parseStatus: String
    public let sampleRenderMS: Double
    public let inferenceMS: Double
    public let extractionMS: Double
    public let validationMS: Double
    public let scoringMS: Double
    public let rawResponseChars: Int
    public let extractedResultChars: Int
    public let failureStage: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleID = "sample_id"
        case system
        case inputText = "input_text"
        case target
        case rawResponse = "raw_response"
        case extractedResult = "extracted_result"
        case typedScore = "typed_score"
        case timeS = "time_s"
        case extractionStatus = "extraction_status"
        case validationStatus = "validation_status"
        case failureReason = "failure_reason"
        case taskKind = "task_kind"
        case inputModalities = "input_modalities"
        case mediaReferences = "media_references"
        case codeLanguage = "code_language"
        case codeEntryPoint = "code_entry_point"
        case codeCompileStatus = "code_compile_status"
        case codeRuntimeStatus = "code_runtime_status"
        case codeTimeoutStatus = "code_timeout_status"
        case codeTestStatus = "code_test_status"
        case codeTestsPassed = "code_tests_passed"
        case codeTestsTotal = "code_tests_total"
        case codeFailureDetail = "code_failure_detail"
        case categoryLabel = "category_label"
        case subjectLabel = "subject_label"
        case question
        case expected
        case predicted
        case correct
        case parseStatus = "parse_status"
        case sampleRenderMS = "sample_render_ms"
        case inferenceMS = "inference_ms"
        case extractionMS = "extraction_ms"
        case validationMS = "validation_ms"
        case scoringMS = "scoring_ms"
        case rawResponseChars = "raw_response_chars"
        case extractedResultChars = "extracted_result_chars"
        case failureStage = "failure_stage"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleID = try container.decodeIfPresent(String.self, forKey: .sampleID) ?? ""
        system = try container.decodeIfPresent(String.self, forKey: .system) ?? ""
        inputText = try container.decodeIfPresent(String.self, forKey: .inputText)
            ?? (try container.decodeIfPresent(String.self, forKey: .question) ?? "")
        target = try container.decodeIfPresent(String.self, forKey: .target)
            ?? (try container.decodeIfPresent(String.self, forKey: .expected) ?? "")
        rawResponse = try container.decodeIfPresent(String.self, forKey: .rawResponse) ?? ""
        extractedResult = try container.decodeIfPresent(String.self, forKey: .extractedResult)
            ?? (try container.decodeIfPresent(String.self, forKey: .predicted) ?? "")
        if let typedScore = try container.decodeIfPresent(Double.self, forKey: .typedScore) {
            self.typedScore = typedScore
        } else {
            self.typedScore = (try container.decodeIfPresent(Bool.self, forKey: .correct) ?? false) ? 1.0 : 0.0
        }
        timeS = try container.decodeIfPresent(Double.self, forKey: .timeS) ?? 0
        parseStatus = try container.decodeIfPresent(String.self, forKey: .parseStatus) ?? ""
        extractionStatus = try container.decodeIfPresent(String.self, forKey: .extractionStatus)
            ?? ((parseStatus.isEmpty && extractedResult.isEmpty) ? "" : "extracted")
        if let validationStatus = try container.decodeIfPresent(String.self, forKey: .validationStatus) {
            self.validationStatus = validationStatus
        } else if container.contains(.correct) || extractedResult.isEmpty == false {
            self.validationStatus = "validated"
        } else {
            self.validationStatus = ""
        }
        failureReason = try container.decodeIfPresent(String.self, forKey: .failureReason) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        inputModalities = try container.decodeIfPresent([String].self, forKey: .inputModalities) ?? []
        mediaReferences = try container.decodeIfPresent([String].self, forKey: .mediaReferences) ?? []
        codeLanguage = try container.decodeIfPresent(String.self, forKey: .codeLanguage) ?? ""
        codeEntryPoint = try container.decodeIfPresent(String.self, forKey: .codeEntryPoint) ?? ""
        codeCompileStatus = try container.decodeIfPresent(String.self, forKey: .codeCompileStatus) ?? ""
        codeRuntimeStatus = try container.decodeIfPresent(String.self, forKey: .codeRuntimeStatus) ?? ""
        codeTimeoutStatus = try container.decodeIfPresent(String.self, forKey: .codeTimeoutStatus) ?? ""
        codeTestStatus = try container.decodeIfPresent(String.self, forKey: .codeTestStatus) ?? ""
        codeTestsPassed = try container.decodeIfPresent(Int.self, forKey: .codeTestsPassed) ?? 0
        codeTestsTotal = try container.decodeIfPresent(Int.self, forKey: .codeTestsTotal) ?? 0
        codeFailureDetail = try container.decodeIfPresent(String.self, forKey: .codeFailureDetail) ?? ""
        categoryLabel = try container.decodeIfPresent(String.self, forKey: .categoryLabel) ?? ""
        subjectLabel = try container.decodeIfPresent(String.self, forKey: .subjectLabel) ?? ""
        sampleRenderMS = try container.decodeIfPresent(Double.self, forKey: .sampleRenderMS) ?? 0
        inferenceMS = try container.decodeIfPresent(Double.self, forKey: .inferenceMS) ?? 0
        extractionMS = try container.decodeIfPresent(Double.self, forKey: .extractionMS) ?? 0
        validationMS = try container.decodeIfPresent(Double.self, forKey: .validationMS) ?? 0
        scoringMS = try container.decodeIfPresent(Double.self, forKey: .scoringMS) ?? 0
        rawResponseChars = try container.decodeIfPresent(Int.self, forKey: .rawResponseChars) ?? rawResponse.count
        extractedResultChars = try container.decodeIfPresent(Int.self, forKey: .extractedResultChars) ?? extractedResult.count
        failureStage = try container.decodeIfPresent(String.self, forKey: .failureStage) ?? ""
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(jobID, forKey: .jobID)
        try container.encode(suiteID, forKey: .suiteID)
        try container.encode(datasetID, forKey: .datasetID)
        try container.encode(sampleID, forKey: .sampleID)
        try container.encode(system, forKey: .system)
        try container.encode(inputText, forKey: .inputText)
        try container.encode(target, forKey: .target)
        try container.encode(rawResponse, forKey: .rawResponse)
        try container.encode(extractedResult, forKey: .extractedResult)
        try container.encode(typedScore, forKey: .typedScore)
        try container.encode(timeS, forKey: .timeS)
        try container.encode(extractionStatus, forKey: .extractionStatus)
        try container.encode(validationStatus, forKey: .validationStatus)
        try container.encode(failureReason, forKey: .failureReason)
        try container.encode(taskKind, forKey: .taskKind)
        try container.encode(inputModalities, forKey: .inputModalities)
        try container.encode(mediaReferences, forKey: .mediaReferences)
        try container.encode(codeLanguage, forKey: .codeLanguage)
        try container.encode(codeEntryPoint, forKey: .codeEntryPoint)
        try container.encode(codeCompileStatus, forKey: .codeCompileStatus)
        try container.encode(codeRuntimeStatus, forKey: .codeRuntimeStatus)
        try container.encode(codeTimeoutStatus, forKey: .codeTimeoutStatus)
        try container.encode(codeTestStatus, forKey: .codeTestStatus)
        try container.encode(codeTestsPassed, forKey: .codeTestsPassed)
        try container.encode(codeTestsTotal, forKey: .codeTestsTotal)
        try container.encode(codeFailureDetail, forKey: .codeFailureDetail)
        if categoryLabel.isEmpty == false {
            try container.encode(categoryLabel, forKey: .categoryLabel)
        }
        if subjectLabel.isEmpty == false {
            try container.encode(subjectLabel, forKey: .subjectLabel)
        }
        try container.encode(sampleRenderMS, forKey: .sampleRenderMS)
        try container.encode(inferenceMS, forKey: .inferenceMS)
        try container.encode(extractionMS, forKey: .extractionMS)
        try container.encode(validationMS, forKey: .validationMS)
        try container.encode(scoringMS, forKey: .scoringMS)
        try container.encode(rawResponseChars, forKey: .rawResponseChars)
        try container.encode(extractedResultChars, forKey: .extractedResultChars)
        try container.encode(failureStage, forKey: .failureStage)
    }
}

public struct ControlPlaneEvaluationHistoryEntry: Codable, Equatable, Sendable {
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let scoringMode: String
    public let status: String
    public let metricCount: Int
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
    public let reportPath: String
}

public struct ControlPlaneEvaluationSummaryCSVRow: Codable, Equatable, Sendable {
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let primaryScoreName: String
    public let primaryScoreValue: Double
    public let extractionSuccessCount: Int
    public let validationSuccessCount: Int
    public let scoredSampleCount: Int
    public let failureCount: Int
    public let effectThreshold: Double?
    public let verdict: String
    public let bootstrapLowerBound: Double?
    public let bootstrapUpperBound: Double?
    public let analyticalLowerBound: Double?
    public let analyticalUpperBound: Double?
    public let durationSeconds: Double
    public let createdAtUnixMS: Int64

    public init(
        jobID: String,
        modelID: String,
        taskKind: String,
        sourceRepo: String,
        suiteID: String,
        datasetID: String,
        sampleSize: Int,
        primaryScoreName: String,
        primaryScoreValue: Double,
        extractionSuccessCount: Int,
        validationSuccessCount: Int,
        scoredSampleCount: Int,
        failureCount: Int,
        effectThreshold: Double? = nil,
        verdict: String = "",
        bootstrapLowerBound: Double? = nil,
        bootstrapUpperBound: Double? = nil,
        analyticalLowerBound: Double? = nil,
        analyticalUpperBound: Double? = nil,
        durationSeconds: Double,
        createdAtUnixMS: Int64
    ) {
        self.jobID = jobID
        self.modelID = modelID
        self.taskKind = taskKind
        self.sourceRepo = sourceRepo
        self.suiteID = suiteID
        self.datasetID = datasetID
        self.sampleSize = sampleSize
        self.primaryScoreName = primaryScoreName
        self.primaryScoreValue = primaryScoreValue
        self.extractionSuccessCount = extractionSuccessCount
        self.validationSuccessCount = validationSuccessCount
        self.scoredSampleCount = scoredSampleCount
        self.failureCount = failureCount
        self.effectThreshold = effectThreshold
        self.verdict = verdict
        self.bootstrapLowerBound = bootstrapLowerBound
        self.bootstrapUpperBound = bootstrapUpperBound
        self.analyticalLowerBound = analyticalLowerBound
        self.analyticalUpperBound = analyticalUpperBound
        self.durationSeconds = durationSeconds
        self.createdAtUnixMS = createdAtUnixMS
    }

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case modelID = "model_id"
        case taskKind = "task_kind"
        case sourceRepo = "source_repo"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleSize = "sample_size"
        case primaryScoreName = "primary_score_name"
        case primaryScoreValue = "primary_score_value"
        case extractionSuccessCount = "extraction_success_count"
        case validationSuccessCount = "validation_success_count"
        case scoredSampleCount = "scored_sample_count"
        case failureCount = "failure_count"
        case effectThreshold = "effect_threshold"
        case verdict
        case bootstrapLowerBound = "bootstrap_lower_bound"
        case bootstrapUpperBound = "bootstrap_upper_bound"
        case analyticalLowerBound = "analytical_lower_bound"
        case analyticalUpperBound = "analytical_upper_bound"
        case durationSeconds = "duration_seconds"
        case createdAtUnixMS = "created_at_unix_ms"
        case scoreName = "score_name"
        case scoreValue = "score_value"
        case correctCount = "correct_count"
        case incorrectCount = "incorrect_count"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        modelID = try container.decodeIfPresent(String.self, forKey: .modelID) ?? ""
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        sourceRepo = try container.decodeIfPresent(String.self, forKey: .sourceRepo) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleSize = try container.decodeIfPresent(Int.self, forKey: .sampleSize) ?? 0
        primaryScoreName = try container.decodeIfPresent(String.self, forKey: .primaryScoreName)
            ?? (try container.decodeIfPresent(String.self, forKey: .scoreName) ?? "")
        primaryScoreValue = try container.decodeIfPresent(Double.self, forKey: .primaryScoreValue)
            ?? (try container.decodeIfPresent(Double.self, forKey: .scoreValue) ?? 0)
        let legacyCorrectCount = try container.decodeIfPresent(Int.self, forKey: .correctCount) ?? 0
        let legacyIncorrectCount = try container.decodeIfPresent(Int.self, forKey: .incorrectCount) ?? 0
        let legacySampleCount = max(legacyCorrectCount + legacyIncorrectCount, 0)
        extractionSuccessCount = try container.decodeIfPresent(Int.self, forKey: .extractionSuccessCount)
            ?? legacySampleCount
        validationSuccessCount = try container.decodeIfPresent(Int.self, forKey: .validationSuccessCount)
            ?? legacySampleCount
        scoredSampleCount = try container.decodeIfPresent(Int.self, forKey: .scoredSampleCount)
            ?? legacySampleCount
        failureCount = try container.decodeIfPresent(Int.self, forKey: .failureCount) ?? 0
        effectThreshold = try container.decodeFlexibleDoubleIfPresent(forKey: .effectThreshold)
        verdict = try container.decodeIfPresent(String.self, forKey: .verdict) ?? ""
        bootstrapLowerBound = try container.decodeFlexibleDoubleIfPresent(forKey: .bootstrapLowerBound)
        bootstrapUpperBound = try container.decodeFlexibleDoubleIfPresent(forKey: .bootstrapUpperBound)
        analyticalLowerBound = try container.decodeFlexibleDoubleIfPresent(forKey: .analyticalLowerBound)
        analyticalUpperBound = try container.decodeFlexibleDoubleIfPresent(forKey: .analyticalUpperBound)
        durationSeconds = try container.decodeIfPresent(Double.self, forKey: .durationSeconds) ?? 0
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(jobID, forKey: .jobID)
        try container.encode(modelID, forKey: .modelID)
        try container.encode(taskKind, forKey: .taskKind)
        try container.encode(sourceRepo, forKey: .sourceRepo)
        try container.encode(suiteID, forKey: .suiteID)
        try container.encode(datasetID, forKey: .datasetID)
        try container.encode(sampleSize, forKey: .sampleSize)
        try container.encode(primaryScoreName, forKey: .primaryScoreName)
        try container.encode(primaryScoreValue, forKey: .primaryScoreValue)
        try container.encode(extractionSuccessCount, forKey: .extractionSuccessCount)
        try container.encode(validationSuccessCount, forKey: .validationSuccessCount)
        try container.encode(scoredSampleCount, forKey: .scoredSampleCount)
        try container.encode(failureCount, forKey: .failureCount)
        try container.encodeIfPresent(effectThreshold, forKey: .effectThreshold)
        if verdict.isEmpty == false {
            try container.encode(verdict, forKey: .verdict)
        }
        try container.encodeIfPresent(bootstrapLowerBound, forKey: .bootstrapLowerBound)
        try container.encodeIfPresent(bootstrapUpperBound, forKey: .bootstrapUpperBound)
        try container.encodeIfPresent(analyticalLowerBound, forKey: .analyticalLowerBound)
        try container.encodeIfPresent(analyticalUpperBound, forKey: .analyticalUpperBound)
        try container.encode(durationSeconds, forKey: .durationSeconds)
        try container.encode(createdAtUnixMS, forKey: .createdAtUnixMS)
    }
}

public struct ControlPlaneEvaluationCompareJobRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let baseModelID: String
    public let targetModelIDs: [String]
    public let taskKind: String
    public let sourceRepo: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let scoringMode: String
    public let parameters: [String: String]
    public let status: String
    public let outputDir: String
    public let createdAtUnixMS: Int64
    public let updatedAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case baseModelID = "base_model_id"
        case targetModelIDs = "target_model_ids"
        case taskKind = "task_kind"
        case sourceRepo = "source_repo"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleSize = "sample_size"
        case scoringMode = "scoring_mode"
        case parameters
        case status
        case outputDir = "output_dir"
        case createdAtUnixMS = "created_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        baseModelID = try container.decodeIfPresent(String.self, forKey: .baseModelID) ?? ""
        targetModelIDs = try container.decodeIfPresent([String].self, forKey: .targetModelIDs) ?? []
        taskKind = try container.decodeIfPresent(String.self, forKey: .taskKind) ?? ""
        sourceRepo = try container.decodeIfPresent(String.self, forKey: .sourceRepo) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleSize = try container.decodeIfPresent(Int.self, forKey: .sampleSize) ?? 0
        scoringMode = try container.decodeIfPresent(String.self, forKey: .scoringMode) ?? ""
        parameters = try container.decodeIfPresent([String: String].self, forKey: .parameters) ?? [:]
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        outputDir = try container.decodeIfPresent(String.self, forKey: .outputDir) ?? ""
        createdAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .createdAtUnixMS) ?? 0
        updatedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .updatedAtUnixMS) ?? 0
    }
}

public struct ControlPlaneEvaluationCompareSummaryRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let baseModelID: String
    public let targetModelID: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let scoringMode: String
    public let winCount: Int
    public let lossCount: Int
    public let tieCount: Int
    public let regressionCount: Int
    public let baseAccuracy: Double
    public let targetAccuracy: Double
    public let deltaAccuracy: Double
    public let durationSeconds: Double
    public let metrics: [ControlPlaneBenchmarkMetricRecord]
    public let reportPath: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case baseModelID = "base_model_id"
        case targetModelID = "target_model_id"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleSize = "sample_size"
        case scoringMode = "scoring_mode"
        case winCount = "win_count"
        case lossCount = "loss_count"
        case tieCount = "tie_count"
        case regressionCount = "regression_count"
        case baseAccuracy = "base_accuracy"
        case targetAccuracy = "target_accuracy"
        case deltaAccuracy = "delta_accuracy"
        case durationSeconds = "duration_seconds"
        case metrics
        case reportPath = "report_path"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        baseModelID = try container.decodeIfPresent(String.self, forKey: .baseModelID) ?? ""
        targetModelID = try container.decodeIfPresent(String.self, forKey: .targetModelID) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleSize = try container.decodeIfPresent(Int.self, forKey: .sampleSize) ?? 0
        scoringMode = try container.decodeIfPresent(String.self, forKey: .scoringMode) ?? ""
        winCount = try container.decodeIfPresent(Int.self, forKey: .winCount) ?? 0
        lossCount = try container.decodeIfPresent(Int.self, forKey: .lossCount) ?? 0
        tieCount = try container.decodeIfPresent(Int.self, forKey: .tieCount) ?? 0
        regressionCount = try container.decodeIfPresent(Int.self, forKey: .regressionCount) ?? 0
        baseAccuracy = try container.decodeIfPresent(Double.self, forKey: .baseAccuracy) ?? 0
        targetAccuracy = try container.decodeIfPresent(Double.self, forKey: .targetAccuracy) ?? 0
        deltaAccuracy = try container.decodeIfPresent(Double.self, forKey: .deltaAccuracy) ?? 0
        durationSeconds = try container.decodeIfPresent(Double.self, forKey: .durationSeconds) ?? 0
        metrics = try container.decodeIfPresent([ControlPlaneBenchmarkMetricRecord].self, forKey: .metrics) ?? []
        reportPath = try container.decodeIfPresent(String.self, forKey: .reportPath) ?? ""
    }
}

public struct ControlPlaneEvaluationCompareSampleRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let suiteID: String
    public let datasetID: String
    public let sampleID: String
    public let targetModelID: String
    public let inputText: String
    public let target: String
    public let baseExtractedResult: String
    public let targetExtractedResult: String
    public let baseRawResponse: String
    public let targetRawResponse: String
    public let baseTypedScore: Double
    public let targetTypedScore: Double
    public let outcome: String
    public let regressionKind: String
    public let baseTimeS: Double
    public let targetTimeS: Double
    public let baseExtractionStatus: String
    public let targetExtractionStatus: String
    public let baseValidationStatus: String
    public let targetValidationStatus: String
    public let baseFailureReason: String
    public let targetFailureReason: String
    public let baseParseStatus: String
    public let targetParseStatus: String
    public let codeLanguage: String
    public let codeEntryPoint: String
    public let baseCodeCompileStatus: String
    public let targetCodeCompileStatus: String
    public let baseCodeRuntimeStatus: String
    public let targetCodeRuntimeStatus: String
    public let baseCodeTimeoutStatus: String
    public let targetCodeTimeoutStatus: String
    public let baseCodeTestStatus: String
    public let targetCodeTestStatus: String
    public let baseCodeTestsPassed: Int
    public let targetCodeTestsPassed: Int
    public let baseCodeTestsTotal: Int
    public let targetCodeTestsTotal: Int
    public let baseCodeFailureDetail: String
    public let targetCodeFailureDetail: String
    public let categoryLabel: String
    public let subjectLabel: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleID = "sample_id"
        case targetModelID = "target_model_id"
        case inputText = "input_text"
        case target
        case baseExtractedResult = "base_extracted_result"
        case targetExtractedResult = "target_extracted_result"
        case question
        case expected
        case basePredicted = "base_predicted"
        case targetPredicted = "target_predicted"
        case baseRawResponse = "base_raw_response"
        case targetRawResponse = "target_raw_response"
        case baseTypedScore = "base_typed_score"
        case targetTypedScore = "target_typed_score"
        case baseCorrect = "base_correct"
        case targetCorrect = "target_correct"
        case outcome
        case regressionKind = "regression_kind"
        case regression
        case baseTimeS = "base_time_s"
        case targetTimeS = "target_time_s"
        case baseExtractionStatus = "base_extraction_status"
        case targetExtractionStatus = "target_extraction_status"
        case baseValidationStatus = "base_validation_status"
        case targetValidationStatus = "target_validation_status"
        case baseFailureReason = "base_failure_reason"
        case targetFailureReason = "target_failure_reason"
        case baseParseStatus = "base_parse_status"
        case targetParseStatus = "target_parse_status"
        case codeLanguage = "code_language"
        case codeEntryPoint = "code_entry_point"
        case baseCodeCompileStatus = "base_code_compile_status"
        case targetCodeCompileStatus = "target_code_compile_status"
        case baseCodeRuntimeStatus = "base_code_runtime_status"
        case targetCodeRuntimeStatus = "target_code_runtime_status"
        case baseCodeTimeoutStatus = "base_code_timeout_status"
        case targetCodeTimeoutStatus = "target_code_timeout_status"
        case baseCodeTestStatus = "base_code_test_status"
        case targetCodeTestStatus = "target_code_test_status"
        case baseCodeTestsPassed = "base_code_tests_passed"
        case targetCodeTestsPassed = "target_code_tests_passed"
        case baseCodeTestsTotal = "base_code_tests_total"
        case targetCodeTestsTotal = "target_code_tests_total"
        case baseCodeFailureDetail = "base_code_failure_detail"
        case targetCodeFailureDetail = "target_code_failure_detail"
        case categoryLabel = "category_label"
        case subjectLabel = "subject_label"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleID = try container.decodeIfPresent(String.self, forKey: .sampleID) ?? ""
        targetModelID = try container.decodeIfPresent(String.self, forKey: .targetModelID) ?? ""
        inputText = try container.decodeIfPresent(String.self, forKey: .inputText)
            ?? (try container.decodeIfPresent(String.self, forKey: .question) ?? "")
        target = try container.decodeIfPresent(String.self, forKey: .target)
            ?? (try container.decodeIfPresent(String.self, forKey: .expected) ?? "")
        baseExtractedResult = try container.decodeIfPresent(String.self, forKey: .baseExtractedResult)
            ?? (try container.decodeIfPresent(String.self, forKey: .basePredicted) ?? "")
        targetExtractedResult = try container.decodeIfPresent(String.self, forKey: .targetExtractedResult)
            ?? (try container.decodeIfPresent(String.self, forKey: .targetPredicted) ?? "")
        baseRawResponse = try container.decodeIfPresent(String.self, forKey: .baseRawResponse) ?? ""
        targetRawResponse = try container.decodeIfPresent(String.self, forKey: .targetRawResponse) ?? ""
        if let baseTypedScore = try container.decodeIfPresent(Double.self, forKey: .baseTypedScore) {
            self.baseTypedScore = baseTypedScore
        } else {
            self.baseTypedScore = (try container.decodeIfPresent(Bool.self, forKey: .baseCorrect) ?? false) ? 1.0 : 0.0
        }
        if let targetTypedScore = try container.decodeIfPresent(Double.self, forKey: .targetTypedScore) {
            self.targetTypedScore = targetTypedScore
        } else {
            self.targetTypedScore = (try container.decodeIfPresent(Bool.self, forKey: .targetCorrect) ?? false) ? 1.0 : 0.0
        }
        outcome = try container.decodeIfPresent(String.self, forKey: .outcome) ?? ""
        if let regressionKind = try container.decodeIfPresent(String.self, forKey: .regressionKind) {
            self.regressionKind = regressionKind
        } else {
            self.regressionKind = (try container.decodeIfPresent(Bool.self, forKey: .regression) ?? false) ? "score_regression" : ""
        }
        baseTimeS = try container.decodeIfPresent(Double.self, forKey: .baseTimeS) ?? 0
        targetTimeS = try container.decodeIfPresent(Double.self, forKey: .targetTimeS) ?? 0
        baseExtractionStatus = try container.decodeIfPresent(String.self, forKey: .baseExtractionStatus)
            ?? ((try container.decodeIfPresent(String.self, forKey: .baseParseStatus) ?? "").isEmpty ? "" : "extracted")
        targetExtractionStatus = try container.decodeIfPresent(String.self, forKey: .targetExtractionStatus)
            ?? ((try container.decodeIfPresent(String.self, forKey: .targetParseStatus) ?? "").isEmpty ? "" : "extracted")
        if let baseValidationStatus = try container.decodeIfPresent(String.self, forKey: .baseValidationStatus) {
            self.baseValidationStatus = baseValidationStatus
        } else if container.contains(.baseCorrect) || baseExtractedResult.isEmpty == false {
            self.baseValidationStatus = "validated"
        } else {
            self.baseValidationStatus = ""
        }
        if let targetValidationStatus = try container.decodeIfPresent(String.self, forKey: .targetValidationStatus) {
            self.targetValidationStatus = targetValidationStatus
        } else if container.contains(.targetCorrect) || targetExtractedResult.isEmpty == false {
            self.targetValidationStatus = "validated"
        } else {
            self.targetValidationStatus = ""
        }
        baseFailureReason = try container.decodeIfPresent(String.self, forKey: .baseFailureReason) ?? ""
        targetFailureReason = try container.decodeIfPresent(String.self, forKey: .targetFailureReason) ?? ""
        baseParseStatus = try container.decodeIfPresent(String.self, forKey: .baseParseStatus) ?? ""
        targetParseStatus = try container.decodeIfPresent(String.self, forKey: .targetParseStatus) ?? ""
        codeLanguage = try container.decodeIfPresent(String.self, forKey: .codeLanguage) ?? ""
        codeEntryPoint = try container.decodeIfPresent(String.self, forKey: .codeEntryPoint) ?? ""
        baseCodeCompileStatus = try container.decodeIfPresent(String.self, forKey: .baseCodeCompileStatus) ?? ""
        targetCodeCompileStatus = try container.decodeIfPresent(String.self, forKey: .targetCodeCompileStatus) ?? ""
        baseCodeRuntimeStatus = try container.decodeIfPresent(String.self, forKey: .baseCodeRuntimeStatus) ?? ""
        targetCodeRuntimeStatus = try container.decodeIfPresent(String.self, forKey: .targetCodeRuntimeStatus) ?? ""
        baseCodeTimeoutStatus = try container.decodeIfPresent(String.self, forKey: .baseCodeTimeoutStatus) ?? ""
        targetCodeTimeoutStatus = try container.decodeIfPresent(String.self, forKey: .targetCodeTimeoutStatus) ?? ""
        baseCodeTestStatus = try container.decodeIfPresent(String.self, forKey: .baseCodeTestStatus) ?? ""
        targetCodeTestStatus = try container.decodeIfPresent(String.self, forKey: .targetCodeTestStatus) ?? ""
        baseCodeTestsPassed = try container.decodeIfPresent(Int.self, forKey: .baseCodeTestsPassed) ?? 0
        targetCodeTestsPassed = try container.decodeIfPresent(Int.self, forKey: .targetCodeTestsPassed) ?? 0
        baseCodeTestsTotal = try container.decodeIfPresent(Int.self, forKey: .baseCodeTestsTotal) ?? 0
        targetCodeTestsTotal = try container.decodeIfPresent(Int.self, forKey: .targetCodeTestsTotal) ?? 0
        baseCodeFailureDetail = try container.decodeIfPresent(String.self, forKey: .baseCodeFailureDetail) ?? ""
        targetCodeFailureDetail = try container.decodeIfPresent(String.self, forKey: .targetCodeFailureDetail) ?? ""
        categoryLabel = try container.decodeIfPresent(String.self, forKey: .categoryLabel) ?? ""
        subjectLabel = try container.decodeIfPresent(String.self, forKey: .subjectLabel) ?? ""
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(jobID, forKey: .jobID)
        try container.encode(suiteID, forKey: .suiteID)
        try container.encode(datasetID, forKey: .datasetID)
        try container.encode(sampleID, forKey: .sampleID)
        try container.encode(targetModelID, forKey: .targetModelID)
        try container.encode(inputText, forKey: .inputText)
        try container.encode(target, forKey: .target)
        try container.encode(baseExtractedResult, forKey: .baseExtractedResult)
        try container.encode(targetExtractedResult, forKey: .targetExtractedResult)
        try container.encode(baseRawResponse, forKey: .baseRawResponse)
        try container.encode(targetRawResponse, forKey: .targetRawResponse)
        try container.encode(baseTypedScore, forKey: .baseTypedScore)
        try container.encode(targetTypedScore, forKey: .targetTypedScore)
        try container.encode(outcome, forKey: .outcome)
        try container.encode(regressionKind, forKey: .regressionKind)
        try container.encode(baseTimeS, forKey: .baseTimeS)
        try container.encode(targetTimeS, forKey: .targetTimeS)
        try container.encode(baseExtractionStatus, forKey: .baseExtractionStatus)
        try container.encode(targetExtractionStatus, forKey: .targetExtractionStatus)
        try container.encode(baseValidationStatus, forKey: .baseValidationStatus)
        try container.encode(targetValidationStatus, forKey: .targetValidationStatus)
        try container.encode(baseFailureReason, forKey: .baseFailureReason)
        try container.encode(targetFailureReason, forKey: .targetFailureReason)
        try container.encode(baseParseStatus, forKey: .baseParseStatus)
        try container.encode(targetParseStatus, forKey: .targetParseStatus)
        try container.encode(codeLanguage, forKey: .codeLanguage)
        try container.encode(codeEntryPoint, forKey: .codeEntryPoint)
        try container.encode(baseCodeCompileStatus, forKey: .baseCodeCompileStatus)
        try container.encode(targetCodeCompileStatus, forKey: .targetCodeCompileStatus)
        try container.encode(baseCodeRuntimeStatus, forKey: .baseCodeRuntimeStatus)
        try container.encode(targetCodeRuntimeStatus, forKey: .targetCodeRuntimeStatus)
        try container.encode(baseCodeTimeoutStatus, forKey: .baseCodeTimeoutStatus)
        try container.encode(targetCodeTimeoutStatus, forKey: .targetCodeTimeoutStatus)
        try container.encode(baseCodeTestStatus, forKey: .baseCodeTestStatus)
        try container.encode(targetCodeTestStatus, forKey: .targetCodeTestStatus)
        try container.encode(baseCodeTestsPassed, forKey: .baseCodeTestsPassed)
        try container.encode(targetCodeTestsPassed, forKey: .targetCodeTestsPassed)
        try container.encode(baseCodeTestsTotal, forKey: .baseCodeTestsTotal)
        try container.encode(targetCodeTestsTotal, forKey: .targetCodeTestsTotal)
        try container.encode(baseCodeFailureDetail, forKey: .baseCodeFailureDetail)
        try container.encode(targetCodeFailureDetail, forKey: .targetCodeFailureDetail)
        if categoryLabel.isEmpty == false {
            try container.encode(categoryLabel, forKey: .categoryLabel)
        }
        if subjectLabel.isEmpty == false {
            try container.encode(subjectLabel, forKey: .subjectLabel)
        }
    }
}

public struct ControlPlaneBenchmarkExportBundle: Codable, Equatable, Sendable {
    public let exportSchemaVersion: String
    public let exportedAtUnixMS: Int64
    public let benchmarkJobs: [ControlPlaneBenchmarkJobRecord]
    public let benchmarkResults: [ControlPlaneBenchmarkResultRecord]
    public let benchmarkMatrixJobs: [ControlPlaneBenchmarkMatrixJobRecord]
    public let benchmarkMatrixSummaryRows: [ControlPlaneBenchmarkMatrixSummaryCSVRow]
    public let benchmarkMatrixRequestRecords: [ControlPlaneBenchmarkMatrixRequestCSVRow]
    public let evaluationJobs: [ControlPlaneEvaluationJobRecord]
    public let evaluationResults: [ControlPlaneEvaluationResultRecord]
    public let evaluationSummaryRows: [ControlPlaneEvaluationSummaryCSVRow]
    public let evaluationSamples: [ControlPlaneEvaluationSampleRecord]
    public let evaluationCompareJobs: [ControlPlaneEvaluationCompareJobRecord]
    public let evaluationCompareSummaryRecords: [ControlPlaneEvaluationCompareSummaryRecord]
    public let evaluationCompareSampleRecords: [ControlPlaneEvaluationCompareSampleRecord]

    enum CodingKeys: String, CodingKey {
        case exportSchemaVersion = "export_schema_version"
        case exportedAtUnixMS = "exported_at_unix_ms"
        case benchmarkJobs = "benchmark_jobs"
        case benchmarkResults = "benchmark_results"
        case benchmarkMatrixJobs = "benchmark_matrix_jobs"
        case benchmarkMatrixSummaryRows = "benchmark_matrix_summary_rows"
        case benchmarkMatrixRequestRecords = "benchmark_matrix_request_rows"
        case evaluationJobs = "evaluation_jobs"
        case evaluationResults = "evaluation_results"
        case evaluationSummaryRows = "evaluation_summary_rows"
        case evaluationSamples = "evaluation_samples"
        case evaluationCompareJobs = "evaluation_compare_jobs"
        case evaluationCompareSummaryRecords = "evaluation_compare_summary_rows"
        case evaluationCompareSampleRecords = "evaluation_compare_samples"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        exportSchemaVersion = try container.decodeIfPresent(String.self, forKey: .exportSchemaVersion) ?? ""
        exportedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .exportedAtUnixMS) ?? 0
        benchmarkJobs = try container.decodeIfPresent([ControlPlaneBenchmarkJobRecord].self, forKey: .benchmarkJobs) ?? []
        benchmarkResults = try container.decodeIfPresent([ControlPlaneBenchmarkResultRecord].self, forKey: .benchmarkResults) ?? []
        benchmarkMatrixJobs = try container.decodeIfPresent([ControlPlaneBenchmarkMatrixJobRecord].self, forKey: .benchmarkMatrixJobs) ?? []
        benchmarkMatrixSummaryRows = try container.decodeIfPresent([ControlPlaneBenchmarkMatrixSummaryCSVRow].self, forKey: .benchmarkMatrixSummaryRows) ?? []
        benchmarkMatrixRequestRecords = try container.decodeIfPresent([ControlPlaneBenchmarkMatrixRequestCSVRow].self, forKey: .benchmarkMatrixRequestRecords) ?? []
        evaluationJobs = try container.decodeIfPresent([ControlPlaneEvaluationJobRecord].self, forKey: .evaluationJobs) ?? []
        evaluationResults = try container.decodeIfPresent([ControlPlaneEvaluationResultRecord].self, forKey: .evaluationResults) ?? []
        evaluationSummaryRows = try container.decodeIfPresent([ControlPlaneEvaluationSummaryCSVRow].self, forKey: .evaluationSummaryRows) ?? []
        evaluationSamples = try container.decodeIfPresent([ControlPlaneEvaluationSampleRecord].self, forKey: .evaluationSamples) ?? []
        evaluationCompareJobs = try container.decodeIfPresent([ControlPlaneEvaluationCompareJobRecord].self, forKey: .evaluationCompareJobs) ?? []
        evaluationCompareSummaryRecords = try container.decodeIfPresent([ControlPlaneEvaluationCompareSummaryRecord].self, forKey: .evaluationCompareSummaryRecords) ?? []
        evaluationCompareSampleRecords = try container.decodeIfPresent([ControlPlaneEvaluationCompareSampleRecord].self, forKey: .evaluationCompareSampleRecords) ?? []
    }

    public static func decode(json: String) throws -> ControlPlaneBenchmarkExportBundle {
        do {
            return try JSONDecoder().decode(Self.self, from: Data(json.utf8))
        } catch {
            throw ControlPlaneBenchmarkExportError.invalidJSON(
                "Benchmark export bundle could not be decoded: \(error)"
            )
        }
    }

    public func benchmarkHistoryEntries() -> [ControlPlaneBenchmarkHistoryEntry] {
        let resultsByJob = Dictionary(grouping: benchmarkResults, by: \.jobID)
        return benchmarkJobs
            .sorted(by: Self.sortJobsNewestFirst)
            .flatMap { job -> [ControlPlaneBenchmarkHistoryEntry] in
                let jobResults = resultsByJob[job.jobID] ?? []
                let resultsBySuite = Dictionary(uniqueKeysWithValues: jobResults.map { ($0.suite, $0) })
                return orderedSuiteIDs(for: job, results: jobResults).map { suiteID in
                    let metadata = job.suiteMetadata[suiteID]
                    let result = resultsBySuite[suiteID]
                    return ControlPlaneBenchmarkHistoryEntry(
                        jobID: job.jobID,
                        modelID: job.modelID,
                        taskKind: normalizedTaskKind(for: job),
                        sourceRepo: normalizedSourceRepo(for: job, metadata: metadata),
                        suiteID: suiteID,
                        suiteTitle: metadata?.title ?? suiteID,
                        datasetRepo: metadata?.datasetPath ?? "",
                        datasetConfig: metadata?.datasetName ?? "",
                        datasetSplit: metadata?.datasetSplit ?? "",
                        sampleSize: metadata?.sampleSize ?? Self.parameterInt(job.parameters["sample_size"]),
                        batchFactor: metadata?.batchFactor ?? Self.parameterInt(job.parameters["batch_factor"]),
                        status: job.status,
                        metricCount: result?.metrics.count ?? 0,
                        createdAtUnixMS: job.createdAtUnixMS,
                        updatedAtUnixMS: job.updatedAtUnixMS,
                        reportPath: result?.reportPath ?? ""
                    )
                }
            }
    }

    public func benchmarkCSVRows(jobID: String? = nil) -> [ControlPlaneBenchmarkCSVRow] {
        let resultsByJob = Dictionary(grouping: benchmarkResults, by: \.jobID)
        return benchmarkJobs
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return $0.jobID < $1.jobID
                }
                return $0.createdAtUnixMS < $1.createdAtUnixMS
            }
            .flatMap { job -> [ControlPlaneBenchmarkCSVRow] in
                let jobResults = resultsByJob[job.jobID] ?? []
                let resultsBySuite = Dictionary(uniqueKeysWithValues: jobResults.map { ($0.suite, $0) })
                return orderedSuiteIDs(for: job, results: jobResults).flatMap { suiteID -> [ControlPlaneBenchmarkCSVRow] in
                    let metadata = job.suiteMetadata[suiteID]
                    let result = resultsBySuite[suiteID]
                    return (result?.metrics ?? []).sorted { $0.name < $1.name }.map { metric in
                        ControlPlaneBenchmarkCSVRow(
                            jobID: job.jobID,
                            modelID: job.modelID,
                            taskKind: normalizedTaskKind(for: job),
                            sourceRepo: normalizedSourceRepo(for: job, metadata: metadata),
                            suiteID: suiteID,
                            datasetRepo: metadata?.datasetPath ?? "",
                            datasetConfig: metadata?.datasetName ?? "",
                            datasetSplit: metadata?.datasetSplit ?? "",
                            sampleSize: metadata?.sampleSize ?? Self.parameterInt(job.parameters["sample_size"]),
                            batchFactor: metadata?.batchFactor ?? Self.parameterInt(job.parameters["batch_factor"]),
                            metricName: metric.name,
                            metricValue: metric.value,
                            unit: metric.unit,
                            createdAtUnixMS: job.createdAtUnixMS
                        )
                    }
                }
            }
    }

    public func benchmarkCSV(jobID: String? = nil) -> String {
        let rows = benchmarkCSVRows(jobID: jobID)
        let header = "job_id,model_id,task_kind,source_repo,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.jobID,
                row.modelID,
                row.taskKind,
                row.sourceRepo,
                row.suiteID,
                row.datasetRepo,
                row.datasetConfig,
                row.datasetSplit,
                row.sampleSize.map(String.init) ?? "",
                row.batchFactor.map(String.init) ?? "",
                row.metricName,
                String(row.metricValue),
                row.unit,
                String(row.createdAtUnixMS),
            ]
            .map(Self.csvField)
            .joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func benchmarkMatrixHistoryEntries() -> [ControlPlaneBenchmarkMatrixHistoryEntry] {
        let jobsByID = Dictionary(uniqueKeysWithValues: benchmarkMatrixJobs.map { ($0.jobID, $0) })
        return benchmarkMatrixSummaryRows
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return ($0.jobID, $0.suiteID, $0.contextLength, $0.batchSize) < ($1.jobID, $1.suiteID, $1.contextLength, $1.batchSize)
                }
                return $0.createdAtUnixMS > $1.createdAtUnixMS
            }
            .map { row in
                let job = jobsByID[row.jobID]
                return ControlPlaneBenchmarkMatrixHistoryEntry(
                    benchmarkMode: job?.benchmarkMode.isEmpty == false ? (job?.benchmarkMode ?? "") : "matrix",
                    jobID: row.jobID,
                    modelID: row.modelID,
                    taskKind: row.taskKind,
                    sourceRepo: row.sourceRepo,
                    suiteID: row.suiteID,
                    contextLength: row.contextLength,
                    generationLength: row.generationLength,
                    batchSize: row.batchSize,
                    cacheProfile: row.cacheProfile,
                    reasoningMode: row.reasoningMode,
                    structuredOutputMode: row.structuredOutputMode,
                    concurrencyLevel: row.concurrencyLevel,
                    repeats: row.repeats,
                    requests: row.requests,
                    durationSeconds: row.durationSeconds,
                    status: job?.status ?? "completed",
                    createdAtUnixMS: row.createdAtUnixMS,
                    updatedAtUnixMS: job?.updatedAtUnixMS ?? row.createdAtUnixMS
                )
            }
    }

    public func benchmarkMatrixSummaryCSVRows(jobID: String? = nil) -> [ControlPlaneBenchmarkMatrixSummaryCSVRow] {
        benchmarkMatrixSummaryRows
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return ($0.jobID, $0.suiteID, $0.contextLength, $0.batchSize) < ($1.jobID, $1.suiteID, $1.contextLength, $1.batchSize)
                }
                return $0.createdAtUnixMS < $1.createdAtUnixMS
            }
    }

    public func benchmarkMatrixSummaryCSV(jobID: String? = nil) -> String {
        let rows = benchmarkMatrixSummaryCSVRows(jobID: jobID)
        let header = "job_id,task_kind,source_repo,model_id,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeats,requests,duration_seconds,ttft_mean_ms,ttft_std_ms,request_latency_mean_ms,request_latency_std_ms,prefill_tokens_per_second_mean,decode_tokens_per_second_mean,throughput_requests_per_second,throughput_tokens_per_second,success_rate,peak_memory_bytes_max,queue_wait_mean_ms,queue_wait_p95_ms,cell_wall_ms,completed_count,failed_count,ttft_p50_ms,ttft_p95_ms,request_latency_p50_ms,request_latency_p95_ms,created_at_unix_ms"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.jobID,
                row.taskKind,
                row.sourceRepo,
                row.modelID,
                row.suiteID,
                String(row.contextLength),
                String(row.generationLength),
                String(row.batchSize),
                row.cacheProfile,
                row.reasoningMode,
                row.structuredOutputMode,
                String(row.concurrencyLevel),
                String(row.repeats),
                String(row.requests),
                String(row.durationSeconds),
                String(row.ttftMeanMS),
                String(row.ttftStdMS),
                String(row.requestLatencyMeanMS),
                String(row.requestLatencyStdMS),
                String(row.prefillTokensPerSecondMean),
                String(row.decodeTokensPerSecondMean),
                String(row.throughputRequestsPerSecond),
                String(row.throughputTokensPerSecond),
                String(row.successRate),
                String(row.peakMemoryBytesMax),
                String(row.queueWaitMeanMS),
                String(row.queueWaitP95MS),
                String(row.cellWallMS),
                String(row.completedCount),
                String(row.failedCount),
                String(row.ttftP50MS),
                String(row.ttftP95MS),
                String(row.requestLatencyP50MS),
                String(row.requestLatencyP95MS),
                String(row.createdAtUnixMS),
            ]
            .map(Self.csvField)
            .joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func benchmarkMatrixRequestRows(jobID: String? = nil) -> [ControlPlaneBenchmarkMatrixRequestCSVRow] {
        benchmarkMatrixRequestRecords
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return ($0.jobID, $0.cellID, $0.repeatIndex, $0.requestIndex) < ($1.jobID, $1.cellID, $1.repeatIndex, $1.requestIndex)
                }
                return $0.createdAtUnixMS < $1.createdAtUnixMS
            }
    }

    public func benchmarkMatrixRequestsCSV(jobID: String? = nil) -> String {
        let rows = benchmarkMatrixRequestRows(jobID: jobID)
        let header = "job_id,cell_id,task_kind,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeat_index,request_index,ttft_ms,request_latency_ms,prefill_tokens_per_second,decode_tokens_per_second,queue_wait_ms,peak_memory_bytes,status,error_code,dataset_materialize_ms,prompt_render_ms,warmup_ms,prefill_ms,decode_ms,tokens_in,tokens_out,first_token_index,cache_hit,runtime_kind,error_stage,speculative_acceptance_rate,speculative_rollback_rate,speculative_accepted_tokens,speculative_rejected_tokens,speculative_fallback_count,speculative_num_draft_tokens,speculative_draft_model_configured,speculative_draft_propose_ms,speculative_target_verify_ms,dflash_enabled,dflash_block_size,dflash_rollback_count,dflash_target_hidden_layers,created_at_unix_ms"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            let fields: [String] = [
                row.jobID,
                row.cellID,
                row.taskKind,
                row.suiteID,
                String(row.contextLength),
                String(row.generationLength),
                String(row.batchSize),
                row.cacheProfile,
                row.reasoningMode,
                row.structuredOutputMode,
                String(row.concurrencyLevel),
                String(row.repeatIndex),
                String(row.requestIndex),
                String(row.ttftMS),
                String(row.requestLatencyMS),
                String(row.prefillTokensPerSecond),
                String(row.decodeTokensPerSecond),
                String(row.queueWaitMS),
                String(row.peakMemoryBytes),
                row.status,
                row.errorCode,
                String(row.datasetMaterializeMS),
                String(row.promptRenderMS),
                String(row.warmupMS),
                String(row.prefillMS),
                String(row.decodeMS),
                String(row.tokensIn),
                String(row.tokensOut),
                String(row.firstTokenIndex),
                String(row.cacheHit),
                row.runtimeKind,
                row.errorStage,
                String(row.speculativeAcceptanceRate),
                String(row.speculativeRollbackRate),
                String(row.speculativeAcceptedTokens),
                String(row.speculativeRejectedTokens),
                String(row.speculativeFallbackCount),
                String(row.speculativeNumDraftTokens),
                String(row.speculativeDraftModelConfigured),
                String(row.speculativeDraftProposeMS),
                String(row.speculativeTargetVerifyMS),
                String(row.dflashEnabled),
                String(row.dflashBlockSize),
                String(row.dflashRollbackCount),
                String(row.dflashTargetHiddenLayers),
                String(row.createdAtUnixMS),
            ]
            return fields.map(Self.csvField).joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func evaluationHistoryEntries() -> [ControlPlaneEvaluationHistoryEntry] {
        let resultsByJob = Dictionary(grouping: evaluationResults, by: \.jobID)
        return evaluationJobs
            .sorted(by: Self.sortEvaluationJobsNewestFirst)
            .map { job in
                let result = resultsByJob[job.jobID]?.first
                return ControlPlaneEvaluationHistoryEntry(
                    jobID: job.jobID,
                    modelID: job.modelID,
                    taskKind: normalizedEvaluationTaskKind(for: job),
                    sourceRepo: normalizedEvaluationSourceRepo(for: job),
                    suiteID: job.suiteID,
                    datasetID: job.datasetID,
                    sampleSize: job.sampleSize,
                    scoringMode: job.scoringMode,
                    status: job.status,
                    metricCount: result?.metrics.count ?? 0,
                    createdAtUnixMS: job.createdAtUnixMS,
                    updatedAtUnixMS: job.updatedAtUnixMS,
                    reportPath: result?.reportPath ?? ""
                )
            }
    }

    public func evaluationSummaryCSVRows(jobID: String? = nil) -> [ControlPlaneEvaluationSummaryCSVRow] {
        let canonicalRows = evaluationSummaryRows
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return $0.jobID < $1.jobID
                }
                return $0.createdAtUnixMS < $1.createdAtUnixMS
            }
        if canonicalRows.isEmpty == false {
            return canonicalRows
        }

        let resultsByJob = Dictionary(grouping: evaluationResults, by: \.jobID)
        return evaluationJobs
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return $0.jobID < $1.jobID
                }
                return $0.createdAtUnixMS < $1.createdAtUnixMS
            }
            .compactMap { job in
                let result = resultsByJob[job.jobID]?.first
                return result.map { result in
                    ControlPlaneEvaluationSummaryCSVRow(
                        jobID: job.jobID,
                        modelID: job.modelID,
                        taskKind: normalizedEvaluationTaskKind(for: job),
                        sourceRepo: normalizedEvaluationSourceRepo(for: job),
                        suiteID: job.suiteID,
                        datasetID: job.datasetID,
                        sampleSize: job.sampleSize,
                        primaryScoreName: result.primaryScoreName.isEmpty ? (result.metrics.first?.name ?? "") : result.primaryScoreName,
                        primaryScoreValue: result.primaryScoreName.isEmpty ? (result.metrics.first?.value ?? 0) : result.primaryScoreValue,
                        extractionSuccessCount: result.extractionSuccessCount,
                        validationSuccessCount: result.validationSuccessCount,
                        scoredSampleCount: result.scoredSampleCount,
                        failureCount: result.failureCount,
                        durationSeconds: result.durationSeconds,
                        createdAtUnixMS: job.createdAtUnixMS
                    )
                }
            }
    }

    public func evaluationSummaryCSV(jobID: String? = nil) -> String {
        let rows = evaluationSummaryCSVRows(jobID: jobID)
        let header = "job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.jobID,
                row.modelID,
                row.taskKind,
                row.sourceRepo,
                row.suiteID,
                row.datasetID,
                String(row.sampleSize),
                row.primaryScoreName,
                String(row.primaryScoreValue),
                String(row.extractionSuccessCount),
                String(row.validationSuccessCount),
                String(row.scoredSampleCount),
                String(row.failureCount),
                Self.optionalCSVNumber(row.effectThreshold),
                row.verdict,
                Self.optionalCSVNumber(row.bootstrapLowerBound),
                Self.optionalCSVNumber(row.bootstrapUpperBound),
                Self.optionalCSVNumber(row.analyticalLowerBound),
                Self.optionalCSVNumber(row.analyticalUpperBound),
                String(row.durationSeconds),
                String(row.createdAtUnixMS),
            ]
            .map(Self.csvField)
            .joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func evaluationSampleRows(jobID: String? = nil) -> [ControlPlaneEvaluationSampleRecord] {
        evaluationSamples
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.jobID == $1.jobID {
                    return $0.sampleID < $1.sampleID
                }
                return $0.jobID < $1.jobID
            }
    }

    public func evaluationSamplesCSV(jobID: String? = nil) -> String {
        let rows = evaluationSampleRows(jobID: jobID)
        let header = "job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label,sample_render_ms,inference_ms,extraction_ms,validation_ms,scoring_ms,raw_response_chars,extracted_result_chars,failure_stage"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.jobID,
                row.suiteID,
                row.sampleID,
                row.taskKind,
                row.target,
                row.extractedResult,
                row.inputText,
                row.rawResponse,
                String(row.typedScore),
                String(row.timeS),
                row.extractionStatus,
                row.validationStatus,
                row.failureReason,
                row.inputModalities.joined(separator: ","),
                row.mediaReferences.joined(separator: ","),
                row.codeLanguage,
                row.codeEntryPoint,
                row.codeCompileStatus,
                row.codeRuntimeStatus,
                row.codeTimeoutStatus,
                row.codeTestStatus,
                String(row.codeTestsPassed),
                String(row.codeTestsTotal),
                row.codeFailureDetail,
                row.categoryLabel,
                row.subjectLabel,
                String(row.sampleRenderMS),
                String(row.inferenceMS),
                String(row.extractionMS),
                String(row.validationMS),
                String(row.scoringMS),
                String(row.rawResponseChars),
                String(row.extractedResultChars),
                row.failureStage,
            ]
            .map(Self.csvField)
            .joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func evaluationSamplesJSONL(jobID: String? = nil) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let rows = evaluationSampleRows(jobID: jobID)
        return try rows
            .map { sample in
                let data = try encoder.encode(sample)
                return String(decoding: data, as: UTF8.self)
            }
            .joined(separator: "\n")
            + (rows.isEmpty ? "" : "\n")
    }

    public func evaluationCompareSummaryRows(jobID: String? = nil) -> [ControlPlaneEvaluationCompareSummaryRecord] {
        evaluationCompareSummaryRecords
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.jobID == $1.jobID {
                    return $0.targetModelID < $1.targetModelID
                }
                return $0.jobID < $1.jobID
            }
    }

    public func evaluationCompareSummaryCSV(jobID: String? = nil) -> String {
        let rows = evaluationCompareSummaryRows(jobID: jobID)
        let header = "job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.jobID,
                row.baseModelID,
                row.targetModelID,
                row.suiteID,
                row.datasetID,
                String(row.sampleSize),
                String(row.winCount),
                String(row.lossCount),
                String(row.tieCount),
                String(row.regressionCount),
                String(row.baseAccuracy),
                String(row.targetAccuracy),
                String(row.deltaAccuracy),
                String(row.durationSeconds),
            ]
            .map(Self.csvField)
            .joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func evaluationCompareSampleRows(jobID: String? = nil) -> [ControlPlaneEvaluationCompareSampleRecord] {
        evaluationCompareSampleRecords
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.jobID == $1.jobID {
                    if $0.targetModelID == $1.targetModelID {
                        return $0.sampleID < $1.sampleID
                    }
                    return $0.targetModelID < $1.targetModelID
                }
                return $0.jobID < $1.jobID
            }
    }

    public func evaluationCompareSamplesCSV(jobID: String? = nil) -> String {
        let rows = evaluationCompareSampleRows(jobID: jobID)
        let header = "job_id,suite_id,dataset_id,sample_id,target_model_id,input_text,target,base_extracted_result,target_extracted_result,base_raw_response,target_raw_response,base_typed_score,target_typed_score,outcome,regression_kind,base_time_s,target_time_s,base_extraction_status,target_extraction_status,base_validation_status,target_validation_status,base_failure_reason,target_failure_reason,base_parse_status,target_parse_status,code_language,code_entry_point,base_code_compile_status,target_code_compile_status,base_code_runtime_status,target_code_runtime_status,base_code_timeout_status,target_code_timeout_status,base_code_test_status,target_code_test_status,base_code_tests_passed,target_code_tests_passed,base_code_tests_total,target_code_tests_total,base_code_failure_detail,target_code_failure_detail,category_label,subject_label"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.jobID,
                row.suiteID,
                row.datasetID,
                row.sampleID,
                row.targetModelID,
                row.inputText,
                row.target,
                row.baseExtractedResult,
                row.targetExtractedResult,
                row.baseRawResponse,
                row.targetRawResponse,
                String(row.baseTypedScore),
                String(row.targetTypedScore),
                row.outcome,
                row.regressionKind,
                String(row.baseTimeS),
                String(row.targetTimeS),
                row.baseExtractionStatus,
                row.targetExtractionStatus,
                row.baseValidationStatus,
                row.targetValidationStatus,
                row.baseFailureReason,
                row.targetFailureReason,
                row.baseParseStatus,
                row.targetParseStatus,
                row.codeLanguage,
                row.codeEntryPoint,
                row.baseCodeCompileStatus,
                row.targetCodeCompileStatus,
                row.baseCodeRuntimeStatus,
                row.targetCodeRuntimeStatus,
                row.baseCodeTimeoutStatus,
                row.targetCodeTimeoutStatus,
                row.baseCodeTestStatus,
                row.targetCodeTestStatus,
                String(row.baseCodeTestsPassed),
                String(row.targetCodeTestsPassed),
                String(row.baseCodeTestsTotal),
                String(row.targetCodeTestsTotal),
                row.baseCodeFailureDetail,
                row.targetCodeFailureDetail,
                row.categoryLabel,
                row.subjectLabel,
            ]
            .map(Self.csvField)
            .joined(separator: ",")
        }
        return ([header] + body).joined(separator: "\n") + "\n"
    }

    public func evaluationCompareSamplesJSONL(jobID: String? = nil) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let rows = evaluationCompareSampleRows(jobID: jobID)
        return try rows
            .map { sample in
                let data = try encoder.encode(sample)
                return String(decoding: data, as: UTF8.self)
            }
            .joined(separator: "\n")
            + (rows.isEmpty ? "" : "\n")
    }

    private static func parameterInt(_ rawValue: String?) -> Int? {
        guard let rawValue else {
            return nil
        }
        return Int(rawValue)
    }

    private func normalizedEvaluationTaskKind(for job: ControlPlaneEvaluationJobRecord) -> String {
        if !job.taskKind.isEmpty {
            return job.taskKind
        }
        if let parameterTaskKind = job.parameters["task_kind"], !parameterTaskKind.isEmpty {
            return parameterTaskKind
        }
        return "text-generation"
    }

    private func normalizedEvaluationSourceRepo(for job: ControlPlaneEvaluationJobRecord) -> String {
        if !job.sourceRepo.isEmpty {
            return job.sourceRepo
        }
        return job.parameters["source_repo"] ?? ""
    }

    private func normalizedTaskKind(for job: ControlPlaneBenchmarkJobRecord) -> String {
        if !job.taskKind.isEmpty {
            return job.taskKind
        }
        if let parameterTaskKind = job.parameters["task_kind"], !parameterTaskKind.isEmpty {
            return parameterTaskKind
        }
        return "text-generation"
    }

    private func normalizedSourceRepo(
        for job: ControlPlaneBenchmarkJobRecord,
        metadata: ControlPlaneBenchmarkSuiteMetadata?
    ) -> String {
        if !job.sourceRepo.isEmpty {
            return job.sourceRepo
        }
        return metadata?.datasetPath ?? ""
    }

    private static func sortJobsNewestFirst(
        lhs: ControlPlaneBenchmarkJobRecord,
        rhs: ControlPlaneBenchmarkJobRecord
    ) -> Bool {
        if lhs.createdAtUnixMS == rhs.createdAtUnixMS {
            return lhs.jobID > rhs.jobID
        }
        return lhs.createdAtUnixMS > rhs.createdAtUnixMS
    }

    private static func sortEvaluationJobsNewestFirst(
        lhs: ControlPlaneEvaluationJobRecord,
        rhs: ControlPlaneEvaluationJobRecord
    ) -> Bool {
        if lhs.createdAtUnixMS == rhs.createdAtUnixMS {
            return lhs.jobID > rhs.jobID
        }
        return lhs.createdAtUnixMS > rhs.createdAtUnixMS
    }

    private func orderedSuiteIDs(
        for job: ControlPlaneBenchmarkJobRecord,
        results: [ControlPlaneBenchmarkResultRecord]
    ) -> [String] {
        var suiteIDs = job.suites
        for suiteID in job.suiteMetadata.keys.sorted() where suiteIDs.contains(suiteID) == false {
            suiteIDs.append(suiteID)
        }
        for suiteID in results.map(\.suite).sorted() where suiteIDs.contains(suiteID) == false {
            suiteIDs.append(suiteID)
        }
        return suiteIDs
    }

    private static func csvField(_ value: String) -> String {
        let escaped = value.replacingOccurrences(of: "\"", with: "\"\"")
        if escaped.contains(",") || escaped.contains("\n") || escaped.contains("\"") {
            return "\"\(escaped)\""
        }
        return escaped
    }

    private static func optionalCSVNumber(_ value: Double?) -> String {
        guard let value else {
            return ""
        }
        return String(value)
    }
}

private extension KeyedDecodingContainer {
    func decodeFlexibleDoubleIfPresent(forKey key: Key) throws -> Double? {
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return value
        }
        guard let text = try decodeIfPresent(String.self, forKey: key) else {
            return nil
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return nil
        }
        return Double(trimmed)
    }
}
