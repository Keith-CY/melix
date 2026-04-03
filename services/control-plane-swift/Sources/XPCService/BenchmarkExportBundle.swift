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
    public let metrics: [ControlPlaneBenchmarkMetricRecord]
    public let reportPath: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleSize = "sample_size"
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
    public let question: String
    public let expected: String
    public let predicted: String
    public let rawResponse: String
    public let correct: Bool
    public let timeS: Double
    public let parseStatus: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case suiteID = "suite_id"
        case datasetID = "dataset_id"
        case sampleID = "sample_id"
        case question
        case expected
        case predicted
        case rawResponse = "raw_response"
        case correct
        case timeS = "time_s"
        case parseStatus = "parse_status"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        jobID = try container.decodeIfPresent(String.self, forKey: .jobID) ?? ""
        suiteID = try container.decodeIfPresent(String.self, forKey: .suiteID) ?? ""
        datasetID = try container.decodeIfPresent(String.self, forKey: .datasetID) ?? ""
        sampleID = try container.decodeIfPresent(String.self, forKey: .sampleID) ?? ""
        question = try container.decodeIfPresent(String.self, forKey: .question) ?? ""
        expected = try container.decodeIfPresent(String.self, forKey: .expected) ?? ""
        predicted = try container.decodeIfPresent(String.self, forKey: .predicted) ?? ""
        rawResponse = try container.decodeIfPresent(String.self, forKey: .rawResponse) ?? ""
        correct = try container.decodeIfPresent(Bool.self, forKey: .correct) ?? false
        timeS = try container.decodeIfPresent(Double.self, forKey: .timeS) ?? 0
        parseStatus = try container.decodeIfPresent(String.self, forKey: .parseStatus) ?? ""
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
    public let scoringMode: String
    public let metricName: String
    public let metricValue: Double
    public let unit: String
    public let createdAtUnixMS: Int64
}

public struct ControlPlaneBenchmarkExportBundle: Codable, Equatable, Sendable {
    public let exportSchemaVersion: String
    public let exportedAtUnixMS: Int64
    public let benchmarkJobs: [ControlPlaneBenchmarkJobRecord]
    public let benchmarkResults: [ControlPlaneBenchmarkResultRecord]
    public let evaluationJobs: [ControlPlaneEvaluationJobRecord]
    public let evaluationResults: [ControlPlaneEvaluationResultRecord]
    public let evaluationSamples: [ControlPlaneEvaluationSampleRecord]

    enum CodingKeys: String, CodingKey {
        case exportSchemaVersion = "export_schema_version"
        case exportedAtUnixMS = "exported_at_unix_ms"
        case benchmarkJobs = "benchmark_jobs"
        case benchmarkResults = "benchmark_results"
        case evaluationJobs = "evaluation_jobs"
        case evaluationResults = "evaluation_results"
        case evaluationSamples = "evaluation_samples"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        exportSchemaVersion = try container.decodeIfPresent(String.self, forKey: .exportSchemaVersion) ?? ""
        exportedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .exportedAtUnixMS) ?? 0
        benchmarkJobs = try container.decodeIfPresent([ControlPlaneBenchmarkJobRecord].self, forKey: .benchmarkJobs) ?? []
        benchmarkResults = try container.decodeIfPresent([ControlPlaneBenchmarkResultRecord].self, forKey: .benchmarkResults) ?? []
        evaluationJobs = try container.decodeIfPresent([ControlPlaneEvaluationJobRecord].self, forKey: .evaluationJobs) ?? []
        evaluationResults = try container.decodeIfPresent([ControlPlaneEvaluationResultRecord].self, forKey: .evaluationResults) ?? []
        evaluationSamples = try container.decodeIfPresent([ControlPlaneEvaluationSampleRecord].self, forKey: .evaluationSamples) ?? []
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
        let resultsByJob = Dictionary(grouping: evaluationResults, by: \.jobID)
        return evaluationJobs
            .filter { jobID == nil || $0.jobID == jobID }
            .sorted {
                if $0.createdAtUnixMS == $1.createdAtUnixMS {
                    return $0.jobID < $1.jobID
                }
                return $0.createdAtUnixMS < $1.createdAtUnixMS
            }
            .flatMap { job in
                let result = resultsByJob[job.jobID]?.first
                return (result?.metrics ?? []).sorted { $0.name < $1.name }.map { metric in
                    ControlPlaneEvaluationSummaryCSVRow(
                        jobID: job.jobID,
                        modelID: job.modelID,
                        taskKind: normalizedEvaluationTaskKind(for: job),
                        sourceRepo: normalizedEvaluationSourceRepo(for: job),
                        suiteID: job.suiteID,
                        datasetID: job.datasetID,
                        sampleSize: job.sampleSize,
                        scoringMode: job.scoringMode,
                        metricName: metric.name,
                        metricValue: metric.value,
                        unit: metric.unit,
                        createdAtUnixMS: job.createdAtUnixMS
                    )
                }
            }
    }

    public func evaluationSummaryCSV(jobID: String? = nil) -> String {
        let rows = evaluationSummaryCSVRows(jobID: jobID)
        let header = "job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,scoring_mode,metric_name,metric_value,unit,created_at_unix_ms"
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
                row.scoringMode,
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
        let header = "id,correct,expected,predicted,question,raw_response,time_s,parse_status"
        guard rows.isEmpty == false else {
            return header + "\n"
        }
        let body = rows.map { row in
            [
                row.sampleID,
                row.correct ? "true" : "false",
                row.expected,
                row.predicted,
                row.question,
                row.rawResponse,
                String(row.timeS),
                row.parseStatus,
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
}
