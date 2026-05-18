import Foundation

public enum RuntimeBatchRunValidationSeverity: String, Equatable, Sendable {
    case info
    case warning
    case error
}

public struct RuntimeBatchRunValidationMessageState: Identifiable, Equatable, Sendable {
    public let id: String
    public let severity: RuntimeBatchRunValidationSeverity
    public let field: String
    public let message: String

    public init(id: String, severity: RuntimeBatchRunValidationSeverity, field: String, message: String) {
        self.id = id
        self.severity = severity
        self.field = field
        self.message = message
    }
}

public struct RuntimeBatchRunModelInputState: Identifiable, Equatable, Sendable {
    public let id: String
    public let index: String
    public let repoID: String
    public let sourceLine: Int

    public init(index: String, repoID: String, sourceLine: Int) {
        self.id = "\(index):\(repoID)"
        self.index = index
        self.repoID = repoID
        self.sourceLine = sourceLine
    }
}

public struct RuntimeBatchRunConfigEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let value: String
    public let sourceLine: Int

    public init(key: String, value: String, sourceLine: Int) {
        self.id = "\(sourceLine):\(key)"
        self.key = key
        self.value = value
        self.sourceLine = sourceLine
    }
}

public struct RuntimeBatchRunPreflightCheckState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let status: String
    public let detail: String
    public let actionable: String
    public let category: String
    public let metadata: [String: String]

    public init(
        name: String,
        status: String,
        detail: String,
        actionable: String,
        category: String,
        metadata: [String: String]
    ) {
        self.id = "\(category):\(name)"
        self.name = name
        self.status = status
        self.detail = detail
        self.actionable = actionable
        self.category = category
        self.metadata = metadata
    }

    public var isReady: Bool {
        status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "ready"
    }

    public var isBlocking: Bool {
        isReady == false
    }

    public var blockingReasonText: String {
        let action = actionable.trimmingCharacters(in: .whitespacesAndNewlines)
        if action.isEmpty == false {
            return action
        }
        return detail.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

public struct RuntimeBatchRunPreflightCategoryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let category: String
    public let checks: [RuntimeBatchRunPreflightCheckState]

    public var readyCount: Int {
        checks.filter(\.isReady).count
    }

    public var blockerCount: Int {
        checks.filter(\.isBlocking).count
    }

    public var readinessText: String {
        "\(readyCount)/\(checks.count) ready • \(blockerCount) blocker\(blockerCount == 1 ? "" : "s")"
    }

    public var blockingReasonTexts: [String] {
        checks
            .filter(\.isBlocking)
            .map(\.blockingReasonText)
            .filter { $0.isEmpty == false }
    }

    public init(category: String, checks: [RuntimeBatchRunPreflightCheckState]) {
        let normalizedCategory = RuntimeBatchRunPreflightCategoryState.normalizedCategory(category)
        self.id = normalizedCategory
        self.category = normalizedCategory
        self.checks = checks
    }

    static func normalizedCategory(_ category: String) -> String {
        let trimmed = category.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "uncategorized" : trimmed
    }
}

public struct RuntimeBatchRunSummaryRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let detail: String

    public init(id: String, title: String, detail: String) {
        self.id = id
        self.title = title
        self.detail = detail
    }
}

public struct RuntimeBatchRunStatusSummaryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let runID: String
    public let status: String
    public let totalModels: Int
    public let succeededModels: Int
    public let partialSuccessModels: Int
    public let failedModels: Int
    public let runningModels: Int
    public let plannedModels: Int
    public let tempRoot: String
    public let outputRoot: String
    public let manifestPath: String

    public var statusTitle: String {
        "Batch \(status.isEmpty ? "unknown" : status)"
    }

    public var countsText: String {
        "\(succeededModels) succeeded, \(partialSuccessModels) partial, \(failedModels) failed, \(runningModels) running, \(plannedModels) planned / \(totalModels) total"
    }

    public init(
        runID: String,
        status: String,
        totalModels: Int,
        succeededModels: Int,
        partialSuccessModels: Int,
        failedModels: Int,
        runningModels: Int,
        plannedModels: Int,
        tempRoot: String,
        outputRoot: String,
        manifestPath: String
    ) {
        self.id = "\(runID):\(manifestPath)"
        self.runID = runID
        self.status = status
        self.totalModels = totalModels
        self.succeededModels = succeededModels
        self.partialSuccessModels = partialSuccessModels
        self.failedModels = failedModels
        self.runningModels = runningModels
        self.plannedModels = plannedModels
        self.tempRoot = tempRoot
        self.outputRoot = outputRoot
        self.manifestPath = manifestPath
    }
}

public struct RuntimeBatchRunManifestStatusRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let modelIndex: String
    public let repoID: String
    public let status: String
    public let benchmarkJobID: String
    public let evaluationJobID: String
    public let failureCategory: String
    public let recoverability: String
    public let durationSeconds: Double

    public var failureAttribution: String {
        [failureCategory, recoverability]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.isEmpty == false }
            .joined(separator: " • ")
    }

    public var durationText: String {
        durationSeconds > 0 ? String(format: "%.2f s", durationSeconds) : ""
    }

    public init(
        modelIndex: String,
        repoID: String,
        status: String,
        benchmarkJobID: String,
        evaluationJobID: String,
        failureCategory: String,
        recoverability: String,
        durationSeconds: Double
    ) {
        self.id = "\(modelIndex):\(repoID)"
        self.modelIndex = modelIndex
        self.repoID = repoID
        self.status = status
        self.benchmarkJobID = benchmarkJobID
        self.evaluationJobID = evaluationJobID
        self.failureCategory = failureCategory
        self.recoverability = recoverability
        self.durationSeconds = durationSeconds
    }
}

struct RuntimeBatchRunStatusSnapshotState: Equatable, Sendable {
    let summary: RuntimeBatchRunStatusSummaryState
    let rows: [RuntimeBatchRunManifestStatusRowState]
}

public struct RuntimeBatchRunReportState: Identifiable, Equatable, Sendable {
    public let id: String
    public let runID: String
    public let preflightStatus: String
    public let blockerCount: Int
    public let modelCount: Int
    public let modelListPath: String
    public let configPath: String
    public let outputRoot: String
    public let tempRoot: String
    public let preflightReportPath: String
    public let checks: [RuntimeBatchRunPreflightCheckState]
    public let effectiveConfigRows: [RuntimeBatchRunSummaryRowState]
    public let isolationSummaryRows: [RuntimeBatchRunSummaryRowState]
    public let statusSummary: RuntimeBatchRunStatusSummaryState?
    public let manifestStatusRows: [RuntimeBatchRunManifestStatusRowState]

    public var statusTitle: String {
        "Preflight \(preflightStatus.isEmpty ? "unknown" : preflightStatus)"
    }

    public var preflightReadinessCategories: [RuntimeBatchRunPreflightCategoryState] {
        let groupedChecks = Dictionary(grouping: checks) { check in
            RuntimeBatchRunPreflightCategoryState.normalizedCategory(check.category)
        }
        return groupedChecks.keys.sorted().map { category in
            RuntimeBatchRunPreflightCategoryState(
                category: category,
                checks: groupedChecks[category, default: []]
            )
        }
    }

    public var incompleteManifestRowCount: Int {
        manifestStatusRows.filter { $0.status != "succeeded" }.count
    }

    public func canResume(missingOnly: Bool) -> Bool {
        if missingOnly == false {
            return true
        }
        return manifestStatusRows.isEmpty || incompleteManifestRowCount > 0
    }

    public func resumeSummaryText(missingOnly: Bool) -> String {
        if missingOnly {
            guard manifestStatusRows.isEmpty == false else {
                return "Manifest status has not loaded; resume will resolve the latest manifest."
            }
            let count = incompleteManifestRowCount
            if count == 0 {
                return "All manifest rows are complete."
            }
            return "\(count) incomplete row\(count == 1 ? "" : "s") available for missing-only resume."
        }

        let count = manifestStatusRows.isEmpty ? modelCount : manifestStatusRows.count
        return "Resume will rerun all \(count) manifest row\(count == 1 ? "" : "s")."
    }

    public init(
        runID: String,
        preflightStatus: String,
        blockerCount: Int,
        modelCount: Int,
        modelListPath: String,
        configPath: String,
        outputRoot: String,
        tempRoot: String,
        preflightReportPath: String,
        checks: [RuntimeBatchRunPreflightCheckState],
        effectiveConfigRows: [RuntimeBatchRunSummaryRowState] = [],
        isolationSummaryRows: [RuntimeBatchRunSummaryRowState] = [],
        statusSummary: RuntimeBatchRunStatusSummaryState? = nil,
        manifestStatusRows: [RuntimeBatchRunManifestStatusRowState] = []
    ) {
        self.id = "\(runID.isEmpty ? "batch-run" : runID):\(preflightReportPath)"
        self.runID = runID
        self.preflightStatus = preflightStatus
        self.blockerCount = blockerCount
        self.modelCount = modelCount
        self.modelListPath = modelListPath
        self.configPath = configPath
        self.outputRoot = outputRoot
        self.tempRoot = tempRoot
        self.preflightReportPath = preflightReportPath
        self.checks = checks
        self.effectiveConfigRows = effectiveConfigRows
        self.isolationSummaryRows = isolationSummaryRows
        self.statusSummary = statusSummary
        self.manifestStatusRows = manifestStatusRows
    }

    func applyingStatusSnapshot(_ snapshot: RuntimeBatchRunStatusSnapshotState) -> RuntimeBatchRunReportState {
        RuntimeBatchRunReportState(
            runID: runID,
            preflightStatus: preflightStatus,
            blockerCount: blockerCount,
            modelCount: max(modelCount, snapshot.summary.totalModels),
            modelListPath: modelListPath,
            configPath: configPath,
            outputRoot: outputRoot.isEmpty ? snapshot.summary.outputRoot : outputRoot,
            tempRoot: tempRoot.isEmpty ? snapshot.summary.tempRoot : tempRoot,
            preflightReportPath: preflightReportPath,
            checks: checks,
            effectiveConfigRows: effectiveConfigRows,
            isolationSummaryRows: isolationSummaryRows,
            statusSummary: snapshot.summary,
            manifestStatusRows: snapshot.rows
        )
    }
}

enum RuntimeBatchRunReportDecoder {
    static func decodePreflightOutput(_ output: String) throws -> RuntimeBatchRunReportState {
        let data = Data(output.utf8)
        let decoder = JSONDecoder()
        let payload = try decoder.decode(RuntimeBatchRunDryRunPayload.self, from: data)
        return payload.reportState()
    }

    static func decodeStatusOutput(_ output: String) throws -> RuntimeBatchRunStatusSnapshotState {
        let data = Data(output.utf8)
        let decoder = JSONDecoder()
        let payload = try decoder.decode(RuntimeBatchRunStatusPayload.self, from: data)
        return payload.snapshot()
    }
}

private struct RuntimeBatchRunDryRunPayload: Decodable {
    let runID: String
    let modelList: String
    let configPath: String
    let outputRoot: String
    let tempRoot: String
    let melixHome: String?
    let runtimeDir: String?
    let httpPort: RuntimeBatchRunStringValue?
    let serviceInstanceName: String?
    let selectedModelCount: Int
    let totalModelCount: Int?
    let continueOnFailure: Bool?
    let restartStackPerModel: Bool?
    let preflightReport: String
    let benchmark: RuntimeBatchRunBenchmarkPayload?
    let evaluation: RuntimeBatchRunEvaluationPayload?
    let isolationPolicy: RuntimeBatchRunIsolationPolicyPayload?
    let preflightResult: RuntimeBatchRunPreflightPayload?

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case modelList = "model_list"
        case configPath = "config_path"
        case outputRoot = "output_root"
        case tempRoot = "temp_root"
        case melixHome = "melix_home"
        case runtimeDir = "runtime_dir"
        case httpPort = "http_port"
        case serviceInstanceName = "service_instance_name"
        case selectedModelCount = "selected_model_count"
        case totalModelCount = "total_model_count"
        case continueOnFailure = "continue_on_failure"
        case restartStackPerModel = "restart_stack_per_model"
        case preflightReport = "preflight_report"
        case benchmark
        case evaluation
        case isolationPolicy = "isolation_policy"
        case preflightResult = "preflight_result"
    }

    func reportState() -> RuntimeBatchRunReportState {
        RuntimeBatchRunReportState(
            runID: preflightResult?.runID.isEmpty == false ? preflightResult?.runID ?? runID : runID,
            preflightStatus: preflightResult?.status ?? "unknown",
            blockerCount: preflightResult?.blockerCount ?? 0,
            modelCount: preflightResult?.modelCount ?? selectedModelCount,
            modelListPath: modelList,
            configPath: configPath,
            outputRoot: outputRoot,
            tempRoot: tempRoot,
            preflightReportPath: preflightReport,
            checks: preflightResult?.checks.map(\.state) ?? [],
            effectiveConfigRows: effectiveConfigRows(),
            isolationSummaryRows: isolationSummaryRows()
        )
    }

    private func effectiveConfigRows() -> [RuntimeBatchRunSummaryRowState] {
        let totalModels = totalModelCount ?? preflightResult?.modelCount ?? selectedModelCount
        let modelDetail = totalModels == selectedModelCount
            ? "\(selectedModelCount)"
            : "\(selectedModelCount)/\(totalModels)"

        return [
            row(id: "run-id", title: "Run ID", detail: runID),
            row(id: "models", title: "Models", detail: modelDetail),
            row(id: "output-root", title: "Output Root", detail: outputRoot),
            row(id: "temp-root", title: "Temp Root", detail: tempRoot),
            row(id: "melix-home", title: "MELIX_HOME", detail: melixHome),
            row(id: "runtime-dir", title: "Runtime Dir", detail: runtimeDir),
            row(id: "http-port", title: "HTTP Port", detail: httpPort?.value),
            row(id: "service-instance", title: "Service Instance", detail: serviceInstanceName),
            row(id: "continue-on-failure", title: "Continue On Failure", detail: enabledText(continueOnFailure)),
            row(id: "benchmark", title: "Benchmark", detail: benchmark?.summaryText),
            row(id: "evaluation", title: "Evaluation", detail: evaluation?.summaryText),
        ].compactMap { $0 }
    }

    private func isolationSummaryRows() -> [RuntimeBatchRunSummaryRowState] {
        [
            row(
                id: "best-effort-unload-previous-model",
                title: "Best-effort Unload Previous Model",
                detail: enabledText(isolationPolicy?.bestEffortUnloadPreviousModel)
            ),
            row(
                id: "best-effort-unload-after-model",
                title: "Best-effort Unload After Model",
                detail: enabledText(isolationPolicy?.bestEffortUnloadAfterModel)
            ),
            row(
                id: "restart-stack-per-model",
                title: "Restart Stack Per Model",
                detail: enabledText(isolationPolicy?.restartStackPerModel ?? restartStackPerModel)
            ),
            row(
                id: "force-clean-stack-after-runtime-failure",
                title: "Force Clean After Runtime Failure",
                detail: enabledText(isolationPolicy?.forceCleanStackAfterRuntimeFailure)
            ),
            row(
                id: "cleanup-failures-preserve-artifacts",
                title: "Cleanup Failures Preserve Artifacts",
                detail: enabledText(isolationPolicy?.cleanupFailuresPreserveArtifacts)
            ),
        ].compactMap { $0 }
    }

    private func row(id: String, title: String, detail: String?) -> RuntimeBatchRunSummaryRowState? {
        guard let detail = detail?.trimmingCharacters(in: .whitespacesAndNewlines), detail.isEmpty == false else {
            return nil
        }
        return RuntimeBatchRunSummaryRowState(id: id, title: title, detail: detail)
    }

    private func enabledText(_ value: Bool?) -> String? {
        guard let value else {
            return nil
        }
        return value ? "enabled" : "disabled"
    }
}

private struct RuntimeBatchRunPreflightPayload: Decodable {
    let runID: String
    let status: String
    let blockerCount: Int
    let modelCount: Int
    let checks: [RuntimeBatchRunPreflightCheckPayload]

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case status
        case blockerCount = "blocker_count"
        case modelCount = "model_count"
        case checks
    }
}

private struct RuntimeBatchRunPreflightCheckPayload: Decodable {
    let name: String
    let status: String
    let detail: String
    let actionable: String
    let category: String
    let metadata: [String: String]

    var state: RuntimeBatchRunPreflightCheckState {
        RuntimeBatchRunPreflightCheckState(
            name: name,
            status: status,
            detail: detail,
            actionable: actionable,
            category: category,
            metadata: metadata
        )
    }
}

private struct RuntimeBatchRunStatusPayload: Decodable {
    let runID: String
    let status: String
    let totalModels: Int
    let succeededModels: Int
    let partialSuccessModels: Int
    let failedModels: Int
    let runningModels: Int
    let plannedModels: Int
    let tempRoot: String
    let outputRoot: String
    let manifestPath: String
    let models: [RuntimeBatchRunStatusModelPayload]

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case status
        case totalModels = "total_models"
        case succeededModels = "succeeded_models"
        case partialSuccessModels = "partial_success_models"
        case failedModels = "failed_models"
        case runningModels = "running_models"
        case plannedModels = "planned_models"
        case tempRoot = "temp_root"
        case outputRoot = "output_root"
        case manifestPath = "manifest_path"
        case models
    }

    func snapshot() -> RuntimeBatchRunStatusSnapshotState {
        RuntimeBatchRunStatusSnapshotState(
            summary: RuntimeBatchRunStatusSummaryState(
                runID: runID,
                status: status,
                totalModels: totalModels,
                succeededModels: succeededModels,
                partialSuccessModels: partialSuccessModels,
                failedModels: failedModels,
                runningModels: runningModels,
                plannedModels: plannedModels,
                tempRoot: tempRoot,
                outputRoot: outputRoot,
                manifestPath: manifestPath
            ),
            rows: models.map(\.state)
        )
    }
}

private struct RuntimeBatchRunStatusModelPayload: Decodable {
    let modelIndex: String
    let repoID: String
    let status: String
    let benchmarkJobID: String
    let evaluationJobID: String
    let failureCategory: String
    let recoverability: String
    let durationSeconds: Double

    enum CodingKeys: String, CodingKey {
        case modelIndex = "model_index"
        case repoID = "repo_id"
        case status
        case benchmarkJobID = "benchmark_job_id"
        case evaluationJobID = "evaluation_job_id"
        case failureCategory = "failure_category"
        case recoverability
        case durationSeconds = "duration_seconds"
    }

    var state: RuntimeBatchRunManifestStatusRowState {
        RuntimeBatchRunManifestStatusRowState(
            modelIndex: modelIndex,
            repoID: repoID,
            status: status,
            benchmarkJobID: benchmarkJobID,
            evaluationJobID: evaluationJobID,
            failureCategory: failureCategory,
            recoverability: recoverability,
            durationSeconds: durationSeconds
        )
    }
}

private struct RuntimeBatchRunStringValue: Decodable {
    let value: String

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let stringValue = try? container.decode(String.self) {
            value = stringValue
        } else if let intValue = try? container.decode(Int.self) {
            value = String(intValue)
        } else if let boolValue = try? container.decode(Bool.self) {
            value = boolValue ? "true" : "false"
        } else {
            value = ""
        }
    }
}

private struct RuntimeBatchRunBenchmarkPayload: Decodable {
    let suite: String?
    let contextLength: Int?
    let generationLength: Int?
    let batchSize: Int?
    let repeats: Int?
    let sampleSize: Int?
    let batchFactor: Int?

    enum CodingKeys: String, CodingKey {
        case suite
        case contextLength = "context_length"
        case generationLength = "generation_length"
        case batchSize = "batch_size"
        case repeats
        case sampleSize = "sample_size"
        case batchFactor = "batch_factor"
    }

    var summaryText: String {
        [
            suite,
            contextLength.map { "ctx \($0)" },
            generationLength.map { "gen \($0)" },
            batchSize.map { "batch \($0)" },
            repeats.map { "repeats \($0)" },
            sampleSize.map { "sample \($0)" },
            batchFactor.map { "batch factor \($0)" },
        ].compactMap { $0 }.joined(separator: " • ")
    }
}

private struct RuntimeBatchRunEvaluationPayload: Decodable {
    let suite: String?
    let datasetID: String?
    let scoringMode: String?
    let sampleSize: Int?
    let batchFactor: Int?

    enum CodingKeys: String, CodingKey {
        case suite
        case datasetID = "dataset_id"
        case scoringMode = "scoring_mode"
        case sampleSize = "sample_size"
        case batchFactor = "batch_factor"
    }

    var summaryText: String {
        [
            suite,
            datasetID.map { "dataset \($0)" },
            scoringMode.map { "scoring \($0)" },
            sampleSize.map { "sample \($0)" },
            batchFactor.map { "batch factor \($0)" },
        ].compactMap { $0 }.joined(separator: " • ")
    }
}

private struct RuntimeBatchRunIsolationPolicyPayload: Decodable {
    let bestEffortUnloadPreviousModel: Bool?
    let bestEffortUnloadAfterModel: Bool?
    let restartStackPerModel: Bool?
    let forceCleanStackAfterRuntimeFailure: Bool?
    let cleanupFailuresPreserveArtifacts: Bool?

    enum CodingKeys: String, CodingKey {
        case bestEffortUnloadPreviousModel = "best_effort_unload_previous_model"
        case bestEffortUnloadAfterModel = "best_effort_unload_after_model"
        case restartStackPerModel = "restart_stack_per_model"
        case forceCleanStackAfterRuntimeFailure = "force_clean_stack_after_runtime_failure"
        case cleanupFailuresPreserveArtifacts = "cleanup_failures_preserve_artifacts"
    }
}

enum RuntimeBatchRunSetupParser {
    private static let supportedConfigKeys: Set<String> = [
        "bench_batch_factor",
        "bench_batch_size",
        "bench_context_length",
        "bench_generation_length",
        "bench_repeats",
        "bench_sample_size",
        "bench_suite",
        "continue_on_failure",
        "eval_batch_factor",
        "eval_dataset_id",
        "eval_sample_size",
        "eval_scoring_mode",
        "eval_suite",
        "judge_model",
        "judge_remote_server_id",
        "max_models",
        "melix_cli",
        "melix_home",
        "model_list",
        "output_root",
        "preflight",
        "restart_stack_per_model",
        "runtime_dir",
        "run_id",
        "service_instance_name",
        "start_index",
        "temp_root",
        "http_port",
    ]
    private static let secretKeySubstrings = ["api_key", "token", "secret", "password"]

    static func modelInputs(from text: String) -> [RuntimeBatchRunModelInputState] {
        var inputs: [RuntimeBatchRunModelInputState] = []
        var autoIndex = 1
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.isEmpty == false, line.hasPrefix("#") == false else {
                continue
            }

            let index: String
            let repoID: String
            if let separator = line.firstIndex(of: "|") {
                index = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
                repoID = line[line.index(after: separator)...].trimmingCharacters(in: .whitespacesAndNewlines)
            } else {
                index = String(format: "%02d", autoIndex)
                repoID = line
            }

            if index.isEmpty == false, repoID.isEmpty == false {
                inputs.append(RuntimeBatchRunModelInputState(index: index, repoID: repoID, sourceLine: lineNumber))
            }
            autoIndex += 1
        }
        return inputs
    }

    static func configEntries(from text: String) -> [RuntimeBatchRunConfigEntryState] {
        var entries: [RuntimeBatchRunConfigEntryState] = []
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            guard let parsed = parsedConfigLine(rawLine, lineNumber: lineNumber) else {
                continue
            }
            guard supportedConfigKeys.contains(parsed.key), embedsRawSecret(parsed.key) == false else {
                continue
            }
            entries.append(RuntimeBatchRunConfigEntryState(key: parsed.key, value: parsed.value, sourceLine: lineNumber))
        }
        return entries
    }

    static func validationMessages(modelsText: String, configText: String) -> [RuntimeBatchRunValidationMessageState] {
        var messages: [RuntimeBatchRunValidationMessageState] = []
        let modelInputs = modelInputs(from: modelsText)
        if modelInputs.isEmpty {
            messages.append(
                RuntimeBatchRunValidationMessageState(
                    id: "models-empty",
                    severity: .error,
                    field: "Model List",
                    message: "Add at least one model repository."
                )
            )
        }

        messages.append(contentsOf: modelValidationMessages(from: modelsText))
        messages.append(contentsOf: configValidationMessages(from: configText))
        return messages
    }

    static func canRequestPreflight(modelsText: String, configText: String) -> Bool {
        validationMessages(modelsText: modelsText, configText: configText).contains { $0.severity == .error } == false
    }

    static func summaryText(modelsText: String, configText: String) -> String {
        let modelCount = modelInputs(from: modelsText).count
        let configCount = configEntries(from: configText).count
        return "\(modelCount) \(modelCount == 1 ? "model" : "models") • \(configCount) config values"
    }

    private static func modelValidationMessages(from text: String) -> [RuntimeBatchRunValidationMessageState] {
        var messages: [RuntimeBatchRunValidationMessageState] = []
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.isEmpty == false, line.hasPrefix("#") == false else {
                continue
            }
            if let separator = line.firstIndex(of: "|") {
                let index = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
                let repoID = line[line.index(after: separator)...].trimmingCharacters(in: .whitespacesAndNewlines)
                if index.isEmpty || repoID.isEmpty {
                    messages.append(
                        RuntimeBatchRunValidationMessageState(
                            id: "models-line-\(lineNumber)",
                            severity: .error,
                            field: "Model List",
                            message: "Invalid model list line \(lineNumber); expected index | repo-id."
                        )
                    )
                }
            }
        }
        return messages
    }

    private static func configValidationMessages(from text: String) -> [RuntimeBatchRunValidationMessageState] {
        var messages: [RuntimeBatchRunValidationMessageState] = []
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            var line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.isEmpty == false, line.hasPrefix("#") == false else {
                continue
            }
            if let comment = line.firstIndex(of: "#") {
                line = line[..<comment].trimmingCharacters(in: .whitespacesAndNewlines)
            }
            guard let separator = line.firstIndex(of: ":") else {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-line-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Invalid batch config line \(lineNumber); expected key: value."
                    )
                )
                continue
            }
            let key = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
            if key.isEmpty {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-line-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Invalid batch config line \(lineNumber); key is empty."
                    )
                )
                continue
            }
            let keyString = String(key)
            if embedsRawSecret(keyString) {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-secret-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Unsupported batch config key '\(keyString)' at line \(lineNumber); use stored credential ids instead of raw secrets."
                    )
                )
            } else if supportedConfigKeys.contains(keyString) == false {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-unsupported-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Unsupported batch config key '\(keyString)' at line \(lineNumber)."
                    )
                )
            }
        }
        return messages
    }

    private static func parsedConfigLine(
        _ rawLine: Substring,
        lineNumber: Int
    ) -> (key: String, value: String, sourceLine: Int)? {
        var line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard line.isEmpty == false, line.hasPrefix("#") == false else {
            return nil
        }
        if let comment = line.firstIndex(of: "#") {
            line = line[..<comment].trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard let separator = line.firstIndex(of: ":") else {
            return nil
        }
        let key = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
        let value = line[line.index(after: separator)...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        guard key.isEmpty == false else {
            return nil
        }
        return (String(key), value, lineNumber)
    }

    private static func embedsRawSecret(_ key: String) -> Bool {
        let lowered = key.lowercased()
        return secretKeySubstrings.contains { lowered.contains($0) }
    }
}
