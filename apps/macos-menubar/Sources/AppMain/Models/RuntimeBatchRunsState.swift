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

    public var statusTitle: String {
        "Preflight \(preflightStatus.isEmpty ? "unknown" : preflightStatus)"
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
        isolationSummaryRows: [RuntimeBatchRunSummaryRowState] = []
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
    }
}

enum RuntimeBatchRunReportDecoder {
    static func decodePreflightOutput(_ output: String) throws -> RuntimeBatchRunReportState {
        let data = Data(output.utf8)
        let decoder = JSONDecoder()
        let payload = try decoder.decode(RuntimeBatchRunDryRunPayload.self, from: data)
        return payload.reportState()
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
