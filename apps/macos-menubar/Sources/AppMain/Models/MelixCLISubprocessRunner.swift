import Foundation
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum MelixCLIProcessLaunchError: Error, Equatable, CustomStringConvertible {
    case launchFailed(String)
    case processFailed(exitStatus: Int32, stderr: String, stdout: String)
    case invalidOutput(String)
    case missingFallback(String)

    public var description: String {
        switch self {
        case .launchFailed(let message):
            return "melix subprocess launch failed: \(message)"
        case .processFailed(_, let stderr, let stdout):
            let message = stderr.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? stdout.trimmingCharacters(in: .whitespacesAndNewlines)
                : stderr.trimmingCharacters(in: .whitespacesAndNewlines)
            return "melix subprocess failed: \(message)"
        case .invalidOutput(let message):
            return "melix subprocess returned invalid output: \(message)"
        case .missingFallback(let operation):
            return "melix subprocess runner has no fallback for \(operation)"
        }
    }
}

public struct MelixCLISubprocessRunner: MelixOperatorCommandRunning, Sendable {
    private let environment: [String: String]
    private let launcher: any MelixCLIProcessLaunching
    private let fallbackRunner: (any MelixOperatorCommandRunning)?

    public init(
        environment: [String: String],
        launcher: any MelixCLIProcessLaunching = FoundationMelixCLIProcessLauncher(),
        fallbackRunner: (any MelixOperatorCommandRunning)? = nil
    ) {
        self.environment = environment
        self.launcher = launcher
        self.fallbackRunner = fallbackRunner
    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        try await fallback("run").run(command)
    }

    public func performModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String = "",
        weightQuant: String = "",
        kvQuant: String = "",
        ext: [String: String] = [:]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await fallback("performModelOperation").performModelOperation(
            modelID: modelID,
            operation: operation,
            outputDir: outputDir,
            quantProfileID: quantProfileID,
            weightQuant: weightQuant,
            kvQuant: kvQuant,
            ext: ext
        )
    }

    public func inspectModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        try await fallback("inspectModel").inspectModel(modelID: modelID)
    }

    public func loadModel(
        modelID: String,
        memoryBudgetBytes: UInt64 = 0
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await fallback("loadModel").loadModel(modelID: modelID, memoryBudgetBytes: memoryBudgetBytes)
    }

    public func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await fallback("unloadModel").unloadModel(modelID: modelID)
    }

    public func searchHubModels(
        query: String,
        pageSize: UInt32 = 10,
        cursor: String = "",
        mlxOnly: Bool = true
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        try await fallback("searchHubModels").searchHubModels(
            query: query,
            pageSize: pageSize,
            cursor: cursor,
            mlxOnly: mlxOnly
        )
    }

    public func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        try await fallback("getHubModelCard").getHubModelCard(repoID: repoID)
    }

    public func downloadHubModel(
        repoID: String,
        revision: String = "main"
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await fallback("downloadHubModel").downloadHubModel(repoID: repoID, revision: revision)
    }

    public func applyConfiguredServerSessionGatewayConfig(
        serverSessionID: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await fallback("applyConfiguredServerSessionGatewayConfig")
            .applyConfiguredServerSessionGatewayConfig(serverSessionID: serverSessionID)
    }

    public func applyConfiguredServerSessionServingDefaults(
        serverSessionID: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await fallback("applyConfiguredServerSessionServingDefaults")
            .applyConfiguredServerSessionServingDefaults(serverSessionID: serverSessionID)
    }

    public func runBenchmark(_ options: BenchRunOptions) async throws -> ControlPlaneBenchResult {
        let stdout = try await runJSONCommand(arguments: benchmarkArguments(for: options))
        let payload = try decodeObject(stdout)
        let metrics = (payload["metrics"] as? [String: NSNumber])?.reduce(into: [String: Double]()) { partialResult, entry in
            partialResult[entry.key] = entry.value.doubleValue
        } ?? (payload["metrics"] as? [String: Double]) ?? [:]
        guard let reportPath = payload["report_path"] as? String,
              let reportMarkdown = payload["report_markdown"] as? String
        else {
            throw MelixCLIProcessLaunchError.invalidOutput("benchmark payload is missing report fields")
        }
        return ControlPlaneBenchResult(
            reportPath: reportPath,
            reportMarkdown: reportMarkdown,
            metrics: metrics
        )
    }

    public func runBenchmarkMatrix(_ options: BenchMatrixRunOptions) async throws -> ControlPlaneBenchMatrixResult {
        let stdout = try await runJSONCommand(arguments: benchmarkMatrixArguments(for: options))
        let payload = try decodeObject(stdout)
        guard let jobPayload = payload["job"] as? [String: Any],
              let rowsPayload = payload["summary_rows"] as? [[String: Any]]
        else {
            throw MelixCLIProcessLaunchError.invalidOutput("benchmark matrix payload is missing job or summary_rows")
        }

        var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
        job.schemaVersion = string(jobPayload["schema_version"])
        job.jobID = string(jobPayload["job_id"])
        job.modelID = string(jobPayload["model_id"])
        job.taskKind = string(jobPayload["task_kind"])
        job.sourceRepo = string(jobPayload["source_repo"])
        job.suiteIds = strings(jobPayload["suite_ids"])
        job.benchmarkMode = string(jobPayload["benchmark_mode"])
        job.status = string(jobPayload["status"])
        job.outputDir = string(jobPayload["output_dir"])
        job.createdAtUnixMs = int64(jobPayload["created_at_unix_ms"])
        job.updatedAtUnixMs = int64(jobPayload["updated_at_unix_ms"])

        let rows = rowsPayload.map { payload in
            var row = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
            row.jobID = string(payload["job_id"])
            row.taskKind = string(payload["task_kind"])
            row.sourceRepo = string(payload["source_repo"])
            row.modelID = string(payload["model_id"])
            row.suiteID = string(payload["suite_id"])
            row.contextLength = uint32(payload["context_length"])
            row.generationLength = uint32(payload["generation_length"])
            row.batchSize = uint32(payload["batch_size"])
            row.cacheProfile = string(payload["cache_profile"])
            row.reasoningMode = string(payload["reasoning_mode"])
            row.structuredOutputMode = string(payload["structured_output_mode"])
            row.concurrencyLevel = uint32(payload["concurrency_level"])
            row.repeats = uint32(payload["repeats"])
            row.requests = uint32(payload["requests"])
            row.durationSeconds = uint32(payload["duration_seconds"])
            row.ttftMeanMs = double(payload["ttft_mean_ms"])
            row.ttftStdMs = double(payload["ttft_std_ms"])
            row.requestLatencyMeanMs = double(payload["request_latency_mean_ms"])
            row.requestLatencyStdMs = double(payload["request_latency_std_ms"])
            row.prefillTokensPerSecondMean = double(payload["prefill_tokens_per_second_mean"])
            row.decodeTokensPerSecondMean = double(payload["decode_tokens_per_second_mean"])
            row.throughputRequestsPerSecond = double(payload["throughput_requests_per_second"])
            row.throughputTokensPerSecond = double(payload["throughput_tokens_per_second"])
            row.successRate = double(payload["success_rate"])
            row.peakMemoryBytesMax = uint64(payload["peak_memory_bytes_max"])
            row.queueWaitMeanMs = double(payload["queue_wait_mean_ms"])
            row.queueWaitP95Ms = double(payload["queue_wait_p95_ms"])
            row.createdAtUnixMs = int64(payload["created_at_unix_ms"])
            return row
        }

        return ControlPlaneBenchMatrixResult(job: job, summaryRows: rows)
    }

    public func runEvaluations(_ options: EvalRunOptions) async throws -> [ControlPlaneEvaluationResult] {
        let stdout = try await runJSONCommand(arguments: evaluationArguments(for: options))
        let payloads = try decodeArray(stdout)
        return payloads.map { payload in
            var job = Melix_Controlplane_V1_EvaluationJobSummary()
            let jobPayload = payload["job"] as? [String: Any] ?? [:]
            job.schemaVersion = string(jobPayload["schema_version"])
            job.jobID = string(jobPayload["job_id"])
            job.modelID = string(jobPayload["model_id"])
            job.taskKind = string(jobPayload["task_kind"])
            job.sourceRepo = string(jobPayload["source_repo"])
            job.suiteID = string(jobPayload["suite_id"])
            job.datasetID = string(jobPayload["dataset_id"])
            job.sampleSize = uint32(jobPayload["sample_size"])
            job.scoringMode = string(jobPayload["scoring_mode"])
            job.parameters = dictionary(jobPayload["parameters"])
            job.status = string(jobPayload["status"])
            job.outputDir = string(jobPayload["output_dir"])
            job.createdAtUnixMs = int64(jobPayload["created_at_unix_ms"])
            job.updatedAtUnixMs = int64(jobPayload["updated_at_unix_ms"])

            let resultsPayload = payload["results"] as? [[String: Any]] ?? []
            let results = resultsPayload.map { resultPayload in
                var record = Melix_Controlplane_V1_EvaluationResultSummary()
                record.schemaVersion = string(resultPayload["schema_version"])
                record.jobID = string(resultPayload["job_id"])
                record.suiteID = string(resultPayload["suite_id"])
                record.datasetID = string(resultPayload["dataset_id"])
                record.sampleSize = uint32(resultPayload["sample_size"])
                record.reportPath = string(resultPayload["report_path"])
                let metrics = resultPayload["metrics"] as? [[String: Any]] ?? []
                record.metrics = metrics.map { metricPayload in
                    var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
                    metric.name = string(metricPayload["name"])
                    metric.value = double(metricPayload["value"])
                    metric.unit = string(metricPayload["unit"])
                    return metric
                }
                return record
            }
            return ControlPlaneEvaluationResult(job: job, results: results)
        }
    }

    public func fetchBenchmarkExportBundle(outputDir: String = "") async throws -> ControlPlaneBenchmarkExportBundle {
        let bundlePayload = try await makeBenchmarkExportBundlePayload(outputDir: outputDir)
        let data = try JSONSerialization.data(withJSONObject: bundlePayload, options: [.sortedKeys])
        return try ControlPlaneBenchmarkExportBundle.decode(json: String(decoding: data, as: UTF8.self))
    }

    var resolvedExecutablePathForTesting: String {
        resolveExecutablePath()
    }

    private func fallback(_ operation: String) throws -> any MelixOperatorCommandRunning {
        guard let fallbackRunner else {
            throw MelixCLIProcessLaunchError.missingFallback(operation)
        }
        return fallbackRunner
    }

    private func runJSONCommand(arguments: [String]) async throws -> String {
        let executable = resolveExecutablePath()
        do {
            let result = try await launcher.run(
                executable: executable,
                arguments: arguments,
                environment: environment
            )
            guard result.exitStatus == 0 else {
                throw MelixCLIProcessLaunchError.processFailed(
                    exitStatus: result.exitStatus,
                    stderr: result.stderr,
                    stdout: result.stdout
                )
            }
            return result.stdout
        } catch let error as MelixCLIProcessLaunchError {
            throw error
        } catch {
            throw MelixCLIProcessLaunchError.launchFailed(error.localizedDescription)
        }
    }

    private func runDecodableCommand<T: Decodable>(
        arguments: [String],
        as type: T.Type
    ) async throws -> T {
        let stdout = try await runJSONCommand(arguments: arguments)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let data = stdout.data(using: .utf8) else {
            throw MelixCLIProcessLaunchError.invalidOutput("expected UTF-8 JSON output")
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw MelixCLIProcessLaunchError.invalidOutput("could not decode JSON output: \(error)")
        }
    }

    private func makeBenchmarkExportBundlePayload(outputDir: String) async throws -> [String: Any] {
        let exportDirectory = resolvedSyntheticExportDirectory(outputDir: outputDir)
        try FileManager.default.createDirectory(at: exportDirectory, withIntermediateDirectories: true)

        let benchmarkHistory: [ControlPlaneBenchmarkHistoryEntry] = try await runDecodableCommand(
            arguments: ["bench", "list", "--json"],
            as: [ControlPlaneBenchmarkHistoryEntry].self
        )
        let benchmarkCSVRowsByJob = try await loadBenchmarkCSVRowsByJob(
            benchmarkHistory: benchmarkHistory,
            exportDirectory: exportDirectory
        )

        let benchmarkMatrixHistory: [ControlPlaneBenchmarkMatrixHistoryEntry] = try await runDecodableCommand(
            arguments: ["bench", "matrix", "list", "--json"],
            as: [ControlPlaneBenchmarkMatrixHistoryEntry].self
        )
        let benchmarkMatrixSummaryRowsByJob = try await loadBenchmarkMatrixRowsByJob(
            benchmarkMatrixHistory: benchmarkMatrixHistory,
            exportDirectory: exportDirectory,
            exportKind: .summary
        )
        let benchmarkMatrixRequestRowsByJob = try await loadBenchmarkMatrixRowsByJob(
            benchmarkMatrixHistory: benchmarkMatrixHistory,
            exportDirectory: exportDirectory,
            exportKind: .requests
        )

        let evaluationHistory: [ControlPlaneEvaluationHistoryEntry] = try await runDecodableCommand(
            arguments: ["eval", "list", "--json"],
            as: [ControlPlaneEvaluationHistoryEntry].self
        )
        let evaluationSummaryRowsByJob = try await loadEvaluationSummaryRowsByJob(
            evaluationHistory: evaluationHistory,
            exportDirectory: exportDirectory
        )
        let evaluationSamplesByJob = try await loadEvaluationSamplesByJob(
            evaluationHistory: evaluationHistory,
            exportDirectory: exportDirectory
        )

        let benchmarkPayload = makeBenchmarkPayload(
            history: benchmarkHistory,
            csvRowsByJob: benchmarkCSVRowsByJob
        )
        let benchmarkMatrixPayload = makeBenchmarkMatrixPayload(
            history: benchmarkMatrixHistory,
            summaryRowsByJob: benchmarkMatrixSummaryRowsByJob,
            requestRowsByJob: benchmarkMatrixRequestRowsByJob
        )
        let evaluationPayload = makeEvaluationPayload(
            history: evaluationHistory,
            summaryRowsByJob: evaluationSummaryRowsByJob,
            samplesByJob: evaluationSamplesByJob
        )

        return [
            "export_schema_version": "melix.benchmark_export.v1",
            "exported_at_unix_ms": Int64(Date().timeIntervalSince1970 * 1_000),
            "benchmark_jobs": benchmarkPayload.jobs,
            "benchmark_results": benchmarkPayload.results,
            "benchmark_matrix_jobs": benchmarkMatrixPayload.jobs,
            "benchmark_matrix_summary_rows": benchmarkMatrixPayload.summaryRows,
            "benchmark_matrix_request_rows": benchmarkMatrixPayload.requestRows,
            "evaluation_jobs": evaluationPayload.jobs,
            "evaluation_results": evaluationPayload.results,
            "evaluation_summary_rows": evaluationPayload.summaryRows,
            "evaluation_samples": evaluationPayload.samples,
        ]
    }

    private func loadBenchmarkCSVRowsByJob(
        benchmarkHistory: [ControlPlaneBenchmarkHistoryEntry],
        exportDirectory: URL
    ) async throws -> [String: [[String: Any]]] {
        var rowsByJob: [String: [[String: Any]]] = [:]
        for jobID in orderedJobIDs(benchmarkHistory.map(\.jobID), entries: benchmarkHistory.map(\.createdAtUnixMS)) {
            let outputURL = exportDirectory.appendingPathComponent("bench-\(jobID).csv")
            _ = try await runJSONCommand(
                arguments: [
                    "bench",
                    "export-csv",
                    "--job-id", jobID,
                    "--output", outputURL.path,
                    "--json",
                ]
            )
            let contents = try String(contentsOf: outputURL, encoding: .utf8)
            rowsByJob[jobID] = try parseBenchmarkCSVRows(contents)
        }
        return rowsByJob
    }

    private func loadBenchmarkMatrixRowsByJob(
        benchmarkMatrixHistory: [ControlPlaneBenchmarkMatrixHistoryEntry],
        exportDirectory: URL,
        exportKind: BenchmarkMatrixExportKind
    ) async throws -> [String: [[String: Any]]] {
        var rowsByJob: [String: [[String: Any]]] = [:]
        for jobID in orderedJobIDs(benchmarkMatrixHistory.map(\.jobID), entries: benchmarkMatrixHistory.map(\.createdAtUnixMS)) {
            let outputURL = exportDirectory.appendingPathComponent(exportKind.fileNamePrefix + "-\(jobID).csv")
            _ = try await runJSONCommand(arguments: exportKind.arguments(jobID: jobID, outputPath: outputURL.path))
            let contents = try String(contentsOf: outputURL, encoding: .utf8)
            switch exportKind {
            case .summary:
                rowsByJob[jobID] = try parseBenchmarkMatrixSummaryRows(contents)
            case .requests:
                rowsByJob[jobID] = try parseBenchmarkMatrixRequestRows(contents)
            }
        }
        return rowsByJob
    }

    private func loadEvaluationSummaryRowsByJob(
        evaluationHistory: [ControlPlaneEvaluationHistoryEntry],
        exportDirectory: URL
    ) async throws -> [String: [[String: Any]]] {
        var rowsByJob: [String: [[String: Any]]] = [:]
        for jobID in orderedJobIDs(evaluationHistory.map(\.jobID), entries: evaluationHistory.map(\.createdAtUnixMS)) {
            let outputURL = exportDirectory.appendingPathComponent("eval-summary-\(jobID).csv")
            _ = try await runJSONCommand(
                arguments: [
                    "eval",
                    "export-summary-csv",
                    "--job-id", jobID,
                    "--output", outputURL.path,
                    "--json",
                ]
            )
            let contents = try String(contentsOf: outputURL, encoding: .utf8)
            rowsByJob[jobID] = try parseEvaluationSummaryRows(contents)
        }
        return rowsByJob
    }

    private func loadEvaluationSamplesByJob(
        evaluationHistory: [ControlPlaneEvaluationHistoryEntry],
        exportDirectory: URL
    ) async throws -> [String: [[String: Any]]] {
        var rowsByJob: [String: [[String: Any]]] = [:]
        for jobID in orderedJobIDs(evaluationHistory.map(\.jobID), entries: evaluationHistory.map(\.createdAtUnixMS)) {
            let outputURL = exportDirectory.appendingPathComponent("eval-samples-\(jobID).jsonl")
            _ = try await runJSONCommand(
                arguments: [
                    "eval",
                    "export-samples-jsonl",
                    "--job-id", jobID,
                    "--output", outputURL.path,
                    "--json",
                ]
            )
            let contents = try String(contentsOf: outputURL, encoding: .utf8)
            rowsByJob[jobID] = try parseJSONLRows(contents)
        }
        return rowsByJob
    }

    private func makeBenchmarkPayload(
        history: [ControlPlaneBenchmarkHistoryEntry],
        csvRowsByJob: [String: [[String: Any]]]
    ) -> (jobs: [[String: Any]], results: [[String: Any]]) {
        let historyByJob = Dictionary(grouping: history, by: \.jobID)
        let orderedJobIDs = orderedJobIDs(history.map(\.jobID), entries: history.map(\.createdAtUnixMS))
        var jobs: [[String: Any]] = []
        var results: [[String: Any]] = []

        for jobID in orderedJobIDs {
            guard let jobHistory = historyByJob[jobID], let first = jobHistory.first else {
                continue
            }
            let suites = orderedUnique(jobHistory.map(\.suiteID))
            let sampleSize = jobHistory.compactMap(\.sampleSize).first
            let batchFactor = jobHistory.compactMap(\.batchFactor).first
            let sourceRepo = jobHistory.map(\.sourceRepo).first(where: { $0.isEmpty == false }) ?? first.sourceRepo
            jobs.append([
                "schema_version": "melix.serving_benchmark_job.v1",
                "job_id": jobID,
                "model_id": first.modelID,
                "task_kind": first.taskKind,
                "source_repo": sourceRepo,
                "suites": suites,
                "parameters": benchmarkParameters(sampleSize: sampleSize, batchFactor: batchFactor),
                "status": first.status,
                "output_dir": benchmarkOutputDirectory(entries: jobHistory),
                "created_at_unix_ms": first.createdAtUnixMS,
                "updated_at_unix_ms": jobHistory.map(\.updatedAtUnixMS).max() ?? first.updatedAtUnixMS,
                "suite_metadata": Dictionary(uniqueKeysWithValues: jobHistory.map { entry in
                    (
                        entry.suiteID,
                        [
                            "title": entry.suiteTitle,
                            "dataset_path": entry.datasetRepo,
                            "dataset_name": entry.datasetConfig,
                            "dataset_split": entry.datasetSplit,
                            "sample_size": entry.sampleSize as Any,
                            "batch_factor": entry.batchFactor as Any,
                        ]
                    )
                }),
            ])

            let rowsBySuite = Dictionary(grouping: csvRowsByJob[jobID] ?? []) { row in
                string(row["suite_id"])
            }
            for entry in jobHistory {
                let metrics = (rowsBySuite[entry.suiteID] ?? []).sorted {
                    string($0["metric_name"]) < string($1["metric_name"])
                }
                .map { row in
                    [
                        "name": string(row["metric_name"]),
                        "value": double(row["metric_value"]),
                        "unit": string(row["unit"]),
                    ]
                }
                results.append([
                    "schema_version": "melix.serving_benchmark_result.v1",
                    "job_id": jobID,
                    "suite": entry.suiteID,
                    "metrics": metrics,
                    "report_path": entry.reportPath,
                    "report_markdown": "",
                ])
            }
        }

        return (jobs, results)
    }

    private func makeBenchmarkMatrixPayload(
        history: [ControlPlaneBenchmarkMatrixHistoryEntry],
        summaryRowsByJob: [String: [[String: Any]]],
        requestRowsByJob: [String: [[String: Any]]]
    ) -> (jobs: [[String: Any]], summaryRows: [[String: Any]], requestRows: [[String: Any]]) {
        let historyByJob = Dictionary(grouping: history, by: \.jobID)
        let orderedJobIDs = orderedJobIDs(history.map(\.jobID), entries: history.map(\.createdAtUnixMS))
        var jobs: [[String: Any]] = []

        for jobID in orderedJobIDs {
            guard let jobHistory = historyByJob[jobID], let first = jobHistory.first else {
                continue
            }
            jobs.append([
                "schema_version": "melix.benchmark_matrix_job.v1",
                "job_id": jobID,
                "model_id": first.modelID,
                "task_kind": first.taskKind,
                "source_repo": first.sourceRepo,
                "suite_ids": orderedUnique(jobHistory.map(\.suiteID)),
                "benchmark_mode": first.benchmarkMode,
                "status": first.status,
                "output_dir": "",
                "created_at_unix_ms": first.createdAtUnixMS,
                "updated_at_unix_ms": jobHistory.map(\.updatedAtUnixMS).max() ?? first.updatedAtUnixMS,
            ])
        }

        return (
            jobs,
            orderedJobIDs.flatMap { summaryRowsByJob[$0] ?? [] },
            orderedJobIDs.flatMap { requestRowsByJob[$0] ?? [] }
        )
    }

    private func makeEvaluationPayload(
        history: [ControlPlaneEvaluationHistoryEntry],
        summaryRowsByJob: [String: [[String: Any]]],
        samplesByJob: [String: [[String: Any]]]
    ) -> (jobs: [[String: Any]], results: [[String: Any]], summaryRows: [[String: Any]], samples: [[String: Any]]) {
        let historyByJob = Dictionary(grouping: history, by: \.jobID)
        let orderedJobIDs = orderedJobIDs(history.map(\.jobID), entries: history.map(\.createdAtUnixMS))
        var jobs: [[String: Any]] = []
        var results: [[String: Any]] = []

        for jobID in orderedJobIDs {
            guard let jobHistory = historyByJob[jobID], let first = jobHistory.first else {
                continue
            }
            let summaryRow = (summaryRowsByJob[jobID] ?? []).first
            jobs.append([
                "schema_version": "melix.evaluation_job.v1",
                "job_id": jobID,
                "model_id": first.modelID,
                "task_kind": first.taskKind,
                "source_repo": first.sourceRepo,
                "suite_id": first.suiteID,
                "dataset_id": first.datasetID,
                "sample_size": first.sampleSize,
                "scoring_mode": first.scoringMode,
                "parameters": [:] as [String: String],
                "status": first.status,
                "output_dir": parentDirectory(of: first.reportPath),
                "created_at_unix_ms": first.createdAtUnixMS,
                "updated_at_unix_ms": jobHistory.map(\.updatedAtUnixMS).max() ?? first.updatedAtUnixMS,
            ])
            let metrics: [[String: Any]]
            if let summaryRow {
                var rebuiltMetrics: [[String: Any]] = [[
                    "name": string(summaryRow["score_name"]),
                    "value": double(summaryRow["score_value"]),
                    "unit": "ratio",
                ]]
                let correctCount = int(summaryRow["correct_count"])
                if correctCount > 0 {
                    rebuiltMetrics.append([
                        "name": "eval.\(first.suiteID).correct_count",
                        "value": correctCount,
                        "unit": "count",
                    ])
                }
                let incorrectCount = int(summaryRow["incorrect_count"])
                if incorrectCount > 0 {
                    rebuiltMetrics.append([
                        "name": "eval.\(first.suiteID).incorrect_count",
                        "value": incorrectCount,
                        "unit": "count",
                    ])
                }
                let durationSeconds = int(summaryRow["duration_seconds"])
                if durationSeconds > 0 {
                    rebuiltMetrics.append([
                        "name": "eval.\(first.suiteID).duration_seconds",
                        "value": durationSeconds,
                        "unit": "seconds",
                    ])
                }
                while rebuiltMetrics.count < first.metricCount {
                    rebuiltMetrics.append([
                        "name": "eval.\(first.suiteID).synthetic_metric_\(rebuiltMetrics.count + 1)",
                        "value": 0,
                        "unit": "",
                    ])
                }
                metrics = rebuiltMetrics
            } else {
                metrics = []
            }
            results.append([
                "schema_version": "melix.evaluation_result.v1",
                "job_id": jobID,
                "suite_id": first.suiteID,
                "dataset_id": first.datasetID,
                "sample_size": first.sampleSize,
                "metrics": metrics,
                "report_path": first.reportPath,
            ])
        }

        return (
            jobs,
            results,
            orderedJobIDs.flatMap { summaryRowsByJob[$0] ?? [] },
            orderedJobIDs.flatMap { samplesByJob[$0] ?? [] }
        )
    }

    private func resolvedSyntheticExportDirectory(outputDir: String) -> URL {
        let basePath = outputDir.trimmingCharacters(in: .whitespacesAndNewlines)
        if basePath.isEmpty == false {
            return URL(fileURLWithPath: basePath, isDirectory: true).appendingPathComponent("cli-subprocess-bundle", isDirectory: true)
        }
        return FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-cli-subprocess-bundle", isDirectory: true)
    }

    private func orderedJobIDs(_ jobIDs: [String], entries: [Int64]) -> [String] {
        let paired = Array(zip(jobIDs, entries))
        let ordered = paired.sorted {
            if $0.1 == $1.1 {
                return $0.0 < $1.0
            }
            return $0.1 > $1.1
        }.map(\.0)
        return orderedUnique(ordered)
    }

    private func orderedUnique(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { value in
            seen.insert(value).inserted
        }
    }

    private func benchmarkParameters(sampleSize: Int?, batchFactor: Int?) -> [String: String] {
        var parameters: [String: String] = [:]
        if let sampleSize {
            parameters["sample_size"] = String(sampleSize)
        }
        if let batchFactor {
            parameters["batch_factor"] = String(batchFactor)
        }
        return parameters
    }

    private func benchmarkOutputDirectory(entries: [ControlPlaneBenchmarkHistoryEntry]) -> String {
        for entry in entries where entry.reportPath.isEmpty == false {
            return parentDirectory(of: entry.reportPath)
        }
        return ""
    }

    private func parentDirectory(of path: String) -> String {
        guard path.isEmpty == false else {
            return ""
        }
        return URL(fileURLWithPath: path).deletingLastPathComponent().path
    }

    private func resolveExecutablePath() -> String {
        if let explicit = environment["MELIX_CLI"], explicit.isEmpty == false {
            return explicit
        }
        if let explicit = environment["MELIX_CLI_EXECUTABLE"], explicit.isEmpty == false {
            return explicit
        }
        if let repoRoot = environment["MELIX_REPO_ROOT"], repoRoot.isEmpty == false {
            return MenuBarBootstrapEnvironment.inferCLIExecutablePath(repoRoot: repoRoot)
        }
        return "melix"
    }

    private func benchmarkArguments(for options: BenchRunOptions) -> [String] {
        var arguments = ["bench", "run"]
        appendTargetArguments(modelID: options.modelID, hfRepoID: options.hfRepoID, to: &arguments)
        appendRepeatedFlag("--suite", values: options.suites, to: &arguments)
        appendRepeatedFlag("--context-length", values: options.contextLengths.map(String.init), to: &arguments)
        if options.generationLength > 0 {
            arguments.append(contentsOf: ["--generation-length", String(options.generationLength)])
        }
        appendRepeatedFlag("--batch-size", values: options.batchSizes.map(String.init), to: &arguments)
        if options.repeats > 1 {
            arguments.append(contentsOf: ["--repeats", String(options.repeats)])
        }
        if !options.cacheProfile.isEmpty {
            arguments.append(contentsOf: ["--cache-profile", options.cacheProfile])
        }
        if !options.reasoningMode.isEmpty {
            arguments.append(contentsOf: ["--reasoning-mode", options.reasoningMode])
        }
        if !options.structuredOutputMode.isEmpty {
            arguments.append(contentsOf: ["--structured-output-mode", options.structuredOutputMode])
        }
        if let sampleSize = options.parameters["sample_size"], !sampleSize.isEmpty {
            arguments.append(contentsOf: ["--sample-size", sampleSize])
        }
        if let batchFactor = options.parameters["batch_factor"], !batchFactor.isEmpty {
            arguments.append(contentsOf: ["--batch-factor", batchFactor])
        }
        return arguments + ["--json"]
    }

    private func benchmarkMatrixArguments(for options: BenchMatrixRunOptions) -> [String] {
        var arguments = ["bench", "matrix", "run"]
        appendTargetArguments(modelID: options.modelID, hfRepoID: options.hfRepoID, to: &arguments)
        if !options.taskKind.isEmpty {
            arguments.append(contentsOf: ["--task-kind", options.taskKind])
        }
        appendRepeatedFlag("--suite", values: options.suites, to: &arguments)
        appendRepeatedFlag("--context-length", values: options.contextLengths.map(String.init), to: &arguments)
        appendRepeatedFlag("--generation-length", values: options.generationLengths.map(String.init), to: &arguments)
        appendRepeatedFlag("--batch-size", values: options.batchSizes.map(String.init), to: &arguments)
        appendRepeatedFlag("--cache-profile", values: options.cacheProfiles, to: &arguments)
        appendRepeatedFlag("--reasoning-mode", values: options.reasoningModes, to: &arguments)
        appendRepeatedFlag("--structured-output-mode", values: options.structuredOutputModes, to: &arguments)
        appendRepeatedFlag("--concurrency", values: options.concurrencyLevels.map(String.init), to: &arguments)
        if options.repeats > 1 {
            arguments.append(contentsOf: ["--repeats", String(options.repeats)])
        }
        if options.requests > 0 {
            arguments.append(contentsOf: ["--requests", String(options.requests)])
        }
        if options.durationSeconds > 0 {
            arguments.append(contentsOf: ["--duration-seconds", String(options.durationSeconds)])
        }
        if options.allowLargeMatrix {
            arguments.append("--allow-large-matrix")
        }
        return arguments + ["--json"]
    }

    private func evaluationArguments(for options: EvalRunOptions) -> [String] {
        var arguments = ["eval", "run"]
        appendTargetArguments(modelID: options.modelID, hfRepoID: options.hfRepoID, to: &arguments)
        appendRepeatedFlag("--suite", values: options.suites, to: &arguments)
        if !options.datasetID.isEmpty {
            arguments.append(contentsOf: ["--dataset-id", options.datasetID])
        }
        if options.sampleSize > 0 {
            arguments.append(contentsOf: ["--sample-size", String(options.sampleSize)])
        }
        if let batchFactor = options.parameters["batch_factor"], !batchFactor.isEmpty {
            arguments.append(contentsOf: ["--batch-factor", batchFactor])
        }
        if let datasetRoot = options.parameters["dataset_root"], !datasetRoot.isEmpty {
            arguments.append(contentsOf: ["--dataset-root", datasetRoot])
        }
        if let seed = options.parameters["seed"], !seed.isEmpty {
            arguments.append(contentsOf: ["--seed", seed])
        }
        if let fewShot = options.parameters["few_shot"], !fewShot.isEmpty {
            arguments.append(contentsOf: ["--few-shot", fewShot])
        }
        if let scoringMode = options.parameters["scoring_mode"], !scoringMode.isEmpty {
            arguments.append(contentsOf: ["--scoring-mode", scoringMode])
        }
        if let codeExecPolicy = options.parameters["code_exec_policy"], !codeExecPolicy.isEmpty {
            arguments.append(contentsOf: ["--code-exec-policy", codeExecPolicy])
        }
        return arguments + ["--json"]
    }

    private func appendTargetArguments(modelID: String, hfRepoID: String, to arguments: inout [String]) {
        if !modelID.isEmpty {
            arguments.append(contentsOf: ["--model-id", modelID])
        } else if !hfRepoID.isEmpty {
            arguments.append(contentsOf: ["--repo-id", hfRepoID])
        }
    }

    private func appendRepeatedFlag(_ flag: String, values: [String], to arguments: inout [String]) {
        for value in values {
            guard !value.isEmpty else {
                continue
            }
            arguments.append(contentsOf: [flag, value])
        }
    }

    private func decodeObject(_ stdout: String) throws -> [String: Any] {
        guard let data = stdout.data(using: .utf8),
              let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            throw MelixCLIProcessLaunchError.invalidOutput("expected JSON object")
        }
        return payload
    }

    private func decodeArray(_ stdout: String) throws -> [[String: Any]] {
        guard let data = stdout.data(using: .utf8),
              let payload = try JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else {
            throw MelixCLIProcessLaunchError.invalidOutput("expected JSON array")
        }
        return payload
    }

    private func string(_ value: Any?) -> String {
        value as? String ?? ""
    }

    private func strings(_ value: Any?) -> [String] {
        value as? [String] ?? []
    }

    private func dictionary(_ value: Any?) -> [String: String] {
        value as? [String: String] ?? [:]
    }

    private func uint32(_ value: Any?) -> UInt32 {
        if let value = value as? UInt32 {
            return value
        }
        if let value = value as? Int {
            return UInt32(value)
        }
        if let value = value as? NSNumber {
            return value.uint32Value
        }
        return 0
    }

    private func uint64(_ value: Any?) -> UInt64 {
        if let value = value as? UInt64 {
            return value
        }
        if let value = value as? Int {
            return UInt64(value)
        }
        if let value = value as? NSNumber {
            return value.uint64Value
        }
        return UInt64(string(value)) ?? 0
    }

    private func int64(_ value: Any?) -> Int64 {
        if let value = value as? Int64 {
            return value
        }
        if let value = value as? Int {
            return Int64(value)
        }
        if let value = value as? NSNumber {
            return value.int64Value
        }
        return Int64(string(value)) ?? 0
    }

    private func double(_ value: Any?) -> Double {
        if let value = value as? Double {
            return value
        }
        if let value = value as? NSNumber {
            return value.doubleValue
        }
        return Double(string(value)) ?? 0
    }

    private func parseBenchmarkCSVRows(_ contents: String) throws -> [[String: Any]] {
        try parseCSVRows(contents).map { row in
            [
                "job_id": string(row["job_id"]),
                "model_id": string(row["model_id"]),
                "task_kind": string(row["task_kind"]),
                "source_repo": string(row["source_repo"]),
                "suite_id": string(row["suite_id"]),
                "dataset_repo": string(row["dataset_repo"]),
                "dataset_config": string(row["dataset_config"]),
                "dataset_split": string(row["dataset_split"]),
                "sample_size": optionalInt(row["sample_size"]) as Any,
                "batch_factor": optionalInt(row["batch_factor"]) as Any,
                "metric_name": string(row["metric_name"]),
                "metric_value": double(row["metric_value"]),
                "unit": string(row["unit"]),
                "created_at_unix_ms": int64(row["created_at_unix_ms"]),
            ]
        }
    }

    private func parseBenchmarkMatrixSummaryRows(_ contents: String) throws -> [[String: Any]] {
        try parseCSVRows(contents).map { row in
            [
                "job_id": string(row["job_id"]),
                "task_kind": string(row["task_kind"]),
                "source_repo": string(row["source_repo"]),
                "model_id": string(row["model_id"]),
                "suite_id": string(row["suite_id"]),
                "context_length": int(row["context_length"]),
                "generation_length": int(row["generation_length"]),
                "batch_size": int(row["batch_size"]),
                "cache_profile": string(row["cache_profile"]),
                "reasoning_mode": string(row["reasoning_mode"]),
                "structured_output_mode": string(row["structured_output_mode"]),
                "concurrency_level": int(row["concurrency_level"]),
                "repeats": int(row["repeats"]),
                "requests": int(row["requests"]),
                "duration_seconds": int(row["duration_seconds"]),
                "ttft_mean_ms": double(row["ttft_mean_ms"]),
                "ttft_std_ms": double(row["ttft_std_ms"]),
                "request_latency_mean_ms": double(row["request_latency_mean_ms"]),
                "request_latency_std_ms": double(row["request_latency_std_ms"]),
                "prefill_tokens_per_second_mean": double(row["prefill_tokens_per_second_mean"]),
                "decode_tokens_per_second_mean": double(row["decode_tokens_per_second_mean"]),
                "throughput_requests_per_second": double(row["throughput_requests_per_second"]),
                "throughput_tokens_per_second": double(row["throughput_tokens_per_second"]),
                "success_rate": double(row["success_rate"]),
                "peak_memory_bytes_max": uint64(row["peak_memory_bytes_max"]),
                "queue_wait_mean_ms": double(row["queue_wait_mean_ms"]),
                "queue_wait_p95_ms": double(row["queue_wait_p95_ms"]),
                "created_at_unix_ms": int64(row["created_at_unix_ms"]),
            ]
        }
    }

    private func parseBenchmarkMatrixRequestRows(_ contents: String) throws -> [[String: Any]] {
        try parseCSVRows(contents).map { row in
            [
                "job_id": string(row["job_id"]),
                "cell_id": string(row["cell_id"]),
                "task_kind": string(row["task_kind"]),
                "suite_id": string(row["suite_id"]),
                "context_length": int(row["context_length"]),
                "generation_length": int(row["generation_length"]),
                "batch_size": int(row["batch_size"]),
                "cache_profile": string(row["cache_profile"]),
                "reasoning_mode": string(row["reasoning_mode"]),
                "structured_output_mode": string(row["structured_output_mode"]),
                "concurrency_level": int(row["concurrency_level"]),
                "repeat_index": int(row["repeat_index"]),
                "request_index": int(row["request_index"]),
                "ttft_ms": double(row["ttft_ms"]),
                "request_latency_ms": double(row["request_latency_ms"]),
                "prefill_tokens_per_second": double(row["prefill_tokens_per_second"]),
                "decode_tokens_per_second": double(row["decode_tokens_per_second"]),
                "queue_wait_ms": double(row["queue_wait_ms"]),
                "peak_memory_bytes": uint64(row["peak_memory_bytes"]),
                "status": string(row["status"]),
                "error_code": string(row["error_code"]),
                "created_at_unix_ms": int64(row["created_at_unix_ms"]),
            ]
        }
    }

    private func parseEvaluationSummaryRows(_ contents: String) throws -> [[String: Any]] {
        try parseCSVRows(contents).map { row in
            [
                "job_id": string(row["job_id"]),
                "model_id": string(row["model_id"]),
                "task_kind": string(row["task_kind"]),
                "source_repo": string(row["source_repo"]),
                "suite_id": string(row["suite_id"]),
                "dataset_id": string(row["dataset_id"]),
                "sample_size": int(row["sample_size"]),
                "score_name": string(row["score_name"]),
                "score_value": double(row["score_value"]),
                "correct_count": int(row["correct_count"]),
                "incorrect_count": int(row["incorrect_count"]),
                "duration_seconds": int(row["duration_seconds"]),
                "created_at_unix_ms": int64(row["created_at_unix_ms"]),
            ]
        }
    }

    private func parseJSONLRows(_ contents: String) throws -> [[String: Any]] {
        try contents
            .split(whereSeparator: \.isNewline)
            .filter { $0.isEmpty == false }
            .map { line in
                guard let data = String(line).data(using: .utf8),
                      let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                else {
                    throw MelixCLIProcessLaunchError.invalidOutput("expected JSON object line")
                }
                return payload
            }
    }

    private func parseCSVRows(_ contents: String) throws -> [[String: String]] {
        let rows = try parseCSVTable(contents)
        guard let header = rows.first else {
            return []
        }
        return try rows.dropFirst().compactMap { row in
            if row.allSatisfy(\.isEmpty) {
                return nil
            }
            guard row.count == header.count else {
                throw MelixCLIProcessLaunchError.invalidOutput("csv row does not match header width")
            }
            return Dictionary(uniqueKeysWithValues: zip(header, row))
        }
    }

    private func parseCSVTable(_ contents: String) throws -> [[String]] {
        var rows: [[String]] = []
        var row: [String] = []
        var field = ""
        var isQuoted = false
        var index = contents.startIndex

        while index < contents.endIndex {
            let character = contents[index]
            if isQuoted {
                if character == "\"" {
                    let nextIndex = contents.index(after: index)
                    if nextIndex < contents.endIndex, contents[nextIndex] == "\"" {
                        field.append("\"")
                        index = nextIndex
                    } else {
                        isQuoted = false
                    }
                } else {
                    field.append(character)
                }
            } else {
                switch character {
                case "\"":
                    isQuoted = true
                case ",":
                    row.append(field)
                    field = ""
                case "\n":
                    row.append(field)
                    rows.append(row)
                    row = []
                    field = ""
                case "\r":
                    break
                default:
                    field.append(character)
                }
            }
            index = contents.index(after: index)
        }

        if isQuoted {
            throw MelixCLIProcessLaunchError.invalidOutput("unterminated csv quote")
        }
        if field.isEmpty == false || row.isEmpty == false {
            row.append(field)
            rows.append(row)
        }
        return rows
    }

    private func optionalInt(_ value: Any?) -> Int? {
        let stringValue = string(value)
        guard stringValue.isEmpty == false else {
            return nil
        }
        return Int(stringValue)
    }

    private func int(_ value: Any?) -> Int {
        if let value = value as? Int {
            return value
        }
        if let value = value as? NSNumber {
            return value.intValue
        }
        return Int(string(value)) ?? 0
    }

}

private enum BenchmarkMatrixExportKind {
    case summary
    case requests

    var fileNamePrefix: String {
        switch self {
        case .summary:
            return "bench-matrix-summary"
        case .requests:
            return "bench-matrix-requests"
        }
    }

    func arguments(jobID: String, outputPath: String) -> [String] {
        switch self {
        case .summary:
            return [
                "bench",
                "matrix",
                "export-summary-csv",
                "--job-id", jobID,
                "--output", outputPath,
                "--json",
            ]
        case .requests:
            return [
                "bench",
                "matrix",
                "export-requests-csv",
                "--job-id", jobID,
                "--output", outputPath,
                "--json",
            ]
        }
    }

}
