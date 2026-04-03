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

public struct ControlPlaneBenchmarkExportBundle: Codable, Equatable, Sendable {
    public let exportSchemaVersion: String
    public let exportedAtUnixMS: Int64
    public let benchmarkJobs: [ControlPlaneBenchmarkJobRecord]
    public let benchmarkResults: [ControlPlaneBenchmarkResultRecord]

    enum CodingKeys: String, CodingKey {
        case exportSchemaVersion = "export_schema_version"
        case exportedAtUnixMS = "exported_at_unix_ms"
        case benchmarkJobs = "benchmark_jobs"
        case benchmarkResults = "benchmark_results"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        exportSchemaVersion = try container.decodeIfPresent(String.self, forKey: .exportSchemaVersion) ?? ""
        exportedAtUnixMS = try container.decodeIfPresent(Int64.self, forKey: .exportedAtUnixMS) ?? 0
        benchmarkJobs = try container.decodeIfPresent([ControlPlaneBenchmarkJobRecord].self, forKey: .benchmarkJobs) ?? []
        benchmarkResults = try container.decodeIfPresent([ControlPlaneBenchmarkResultRecord].self, forKey: .benchmarkResults) ?? []
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

    private static func parameterInt(_ rawValue: String?) -> Int? {
        guard let rawValue else {
            return nil
        }
        return Int(rawValue)
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
