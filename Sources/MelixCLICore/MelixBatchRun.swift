import Foundation

public struct BatchRunOptions: Equatable, Sendable {
    public let modelListPath: String
    public let configPath: String
    public let runID: String
    public let outputRoot: String
    public let tempRoot: String
    public let startIndex: Int
    public let maxModels: Int
    public let judgeRemoteServerID: String
    public let judgeModelID: String
    public let benchSuite: String
    public let benchContextLength: UInt32
    public let benchGenerationLength: UInt32
    public let benchBatchSize: UInt32
    public let benchRepeats: UInt32
    public let benchSampleSize: UInt32
    public let benchBatchFactor: UInt32
    public let evalSuite: String
    public let evalDatasetID: String
    public let evalScoringMode: String
    public let evalSampleSize: UInt32
    public let evalBatchFactor: UInt32
    public let continueOnFailure: Bool
    public let restartStackPerModel: Bool
    public let preflight: Bool
    public let dryRun: Bool
    public let json: Bool
    public let explicitOptions: Set<String>

    public init(
        modelListPath: String,
        configPath: String = "",
        runID: String = "",
        outputRoot: String = "",
        tempRoot: String = "",
        startIndex: Int = 1,
        maxModels: Int = 0,
        judgeRemoteServerID: String = "",
        judgeModelID: String = "",
        benchSuite: String = "",
        benchContextLength: UInt32 = 0,
        benchGenerationLength: UInt32 = 0,
        benchBatchSize: UInt32 = 0,
        benchRepeats: UInt32 = 0,
        benchSampleSize: UInt32 = 0,
        benchBatchFactor: UInt32 = 0,
        evalSuite: String = "",
        evalDatasetID: String = "",
        evalScoringMode: String = "",
        evalSampleSize: UInt32 = 0,
        evalBatchFactor: UInt32 = 0,
        continueOnFailure: Bool = true,
        restartStackPerModel: Bool = true,
        preflight: Bool = false,
        dryRun: Bool = false,
        json: Bool = false,
        explicitOptions: Set<String> = []
    ) {
        self.modelListPath = modelListPath
        self.configPath = configPath
        self.runID = runID
        self.outputRoot = outputRoot
        self.tempRoot = tempRoot
        self.startIndex = startIndex
        self.maxModels = maxModels
        self.judgeRemoteServerID = judgeRemoteServerID
        self.judgeModelID = judgeModelID
        self.benchSuite = benchSuite
        self.benchContextLength = benchContextLength
        self.benchGenerationLength = benchGenerationLength
        self.benchBatchSize = benchBatchSize
        self.benchRepeats = benchRepeats
        self.benchSampleSize = benchSampleSize
        self.benchBatchFactor = benchBatchFactor
        self.evalSuite = evalSuite
        self.evalDatasetID = evalDatasetID
        self.evalScoringMode = evalScoringMode
        self.evalSampleSize = evalSampleSize
        self.evalBatchFactor = evalBatchFactor
        self.continueOnFailure = continueOnFailure
        self.restartStackPerModel = restartStackPerModel
        self.preflight = preflight
        self.dryRun = dryRun
        self.json = json
        self.explicitOptions = explicitOptions
    }
}

struct BatchRunModelEntry: Equatable {
    let index: String
    let repoID: String
    let sourceLine: Int
}

struct BatchRunEffectiveConfig: Equatable {
    let repoRoot: String
    let runID: String
    let modelListPath: String
    let configPath: String
    let outputRoot: String
    let tempRoot: String
    let melixHome: String
    let runtimeDir: String
    let httpPort: String
    let serviceInstanceName: String
    let cliPath: String
    let startIndex: Int
    let maxModels: Int
    let judgeRemoteServerID: String
    let judgeModelID: String
    let benchSuite: String
    let benchContextLength: UInt32
    let benchGenerationLength: UInt32
    let benchBatchSize: UInt32
    let benchRepeats: UInt32
    let benchSampleSize: UInt32
    let benchBatchFactor: UInt32
    let evalSuite: String
    let evalDatasetID: String
    let evalScoringMode: String
    let evalSampleSize: UInt32
    let evalBatchFactor: UInt32
    let continueOnFailure: Bool
    let restartStackPerModel: Bool
    let preflight: Bool
    let dryRun: Bool
    let isSubsetRun: Bool
}

struct BatchRunPlan: Equatable {
    let config: BatchRunEffectiveConfig
    let models: [BatchRunModelEntry]
    let selectedModels: [BatchRunModelEntry]
    let manifestPath: String
    let effectiveConfigPath: String
    let preflightReportPath: String
}

struct BatchRunPreflightCheck: Equatable {
    let name: String
    let status: String
    let detail: String
    let actionable: String

    var isBlocking: Bool {
        status == "blocked"
    }

    func payload() -> [String: Any] {
        [
            "name": name,
            "status": status,
            "detail": detail,
            "actionable": actionable,
        ]
    }
}

struct BatchRunPreflightReport: Equatable {
    let schemaVersion: String
    let status: String
    let checks: [BatchRunPreflightCheck]

    var blockers: [BatchRunPreflightCheck] {
        checks.filter(\.isBlocking)
    }

    func payload(plan: BatchRunPlan) -> [String: Any] {
        [
            "schema_version": schemaVersion,
            "run_id": plan.config.runID,
            "status": status,
            "blocker_count": blockers.count,
            "model_count": plan.selectedModels.count,
            "runtime": [
                "repo_root": plan.config.repoRoot,
                "melix_home": plan.config.melixHome,
                "runtime_dir": plan.config.runtimeDir,
                "http_port": plan.config.httpPort,
                "service_instance_name": plan.config.serviceInstanceName,
                "melix_cli": plan.config.cliPath,
            ],
            "judge": [
                "remote_server_id": plan.config.judgeRemoteServerID,
                "model": plan.config.judgeModelID,
            ],
            "models": plan.selectedModels.map { model in
                [
                    "index": model.index,
                    "repo_id": model.repoID,
                    "source_line": model.sourceLine,
                ]
            },
            "checks": checks.map { $0.payload() },
        ]
    }
}

enum BatchRunFailureRecoverability: String, Equatable {
    case retrySameModel = "retry_same_model"
    case cleanRestartAndRetry = "clean_restart_and_retry"
    case operatorActionRequired = "operator_action_required"
    case notRecoverable = "not_recoverable"
    case unknown = "unknown"
}

struct BatchRunFailureClassification: Equatable {
    let category: String
    let recoverability: BatchRunFailureRecoverability
    let reason: String

    func payload() -> [String: Any] {
        [
            "failure_category": category,
            "recoverability": recoverability.rawValue,
            "reason": reason,
        ]
    }
}

enum BatchRunFailureClassifier {
    static let unknown = BatchRunFailureClassification(
        category: "unknown_failure",
        recoverability: .unknown,
        reason: "No known batch runtime failure signature matched."
    )

    static func classify(stdout: String = "", stderr: String = "", metadata: [String: String] = [:]) -> BatchRunFailureClassification {
        let searchable = ([stdout, stderr] + metadata.map { "\($0.key)=\($0.value)" })
            .joined(separator: "\n")
            .lowercased()
        guard searchable.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            return unknown
        }

        if containsAny(searchable, [
            "kiogpucommandbuffercallbackerroroutofmemory",
            "metal oom",
            "outofmemory",
            "out of memory",
            "mpsndarray error",
        ]) {
            return .init(
                category: "metal_oom",
                recoverability: .cleanRestartAndRetry,
                reason: "Metal or unified-memory exhaustion requires a clean runtime before the next model."
            )
        }
        if containsAny(searchable, [
            "socket closed",
            "connection refused",
            "failed to connect to all addresses",
            "python-worker.sock",
            "swift-text-worker.sock",
        ]) {
            return .init(
                category: "worker_connectivity",
                recoverability: .cleanRestartAndRetry,
                reason: "Worker connectivity was lost; restart the local stack before continuing."
            )
        }
        if containsAny(searchable, [
            "requestfailed(code: \"unavailable\"",
            "worker_unavailable",
            "server unavailable",
            "unavailable: worker",
        ]) {
            return .init(
                category: "runtime_unavailable",
                recoverability: .cleanRestartAndRetry,
                reason: "The control plane reported an unavailable runtime."
            )
        }
        if containsAny(searchable, [
            "remote server",
            "semantic judge",
            "judge",
            "401",
            "403",
            "rate limit",
            "unauthorized",
        ]) {
            return .init(
                category: "judge_failure",
                recoverability: .operatorActionRequired,
                reason: "Semantic judge configuration or provider access failed."
            )
        }
        if containsAny(searchable, [
            "repo id",
            "repo_id",
            "repository not found",
            "model not found",
            "target resolution",
            "no loaded benchmark target",
        ]) {
            return .init(
                category: "target_resolution",
                recoverability: .operatorActionRequired,
                reason: "The model target could not be resolved before execution."
            )
        }
        if containsAny(searchable, [
            "load_model",
            "load model",
            "failed to load",
            "model load",
            "processor_asset_preflight",
        ]) {
            return .init(
                category: "model_load",
                recoverability: .operatorActionRequired,
                reason: "Model load failed after target resolution."
            )
        }
        if containsAny(searchable, [
            "export-csv",
            "export summary",
            "export samples",
            "artifact copy",
            "copy raw",
            "permission denied",
            "no such file or directory",
        ]) {
            return .init(
                category: "artifact_export",
                recoverability: .retrySameModel,
                reason: "The model work may have completed, but artifact export or copy failed."
            )
        }
        return unknown
    }

    static func runtimeFailureRequiresCleanStack(_ classification: BatchRunFailureClassification) -> Bool {
        classification.recoverability == .cleanRestartAndRetry
    }

    private static func containsAny(_ text: String, _ needles: [String]) -> Bool {
        needles.contains { text.contains($0) }
    }
}

enum BatchRunModelListParser {
    static func parse(contents: String) throws -> [BatchRunModelEntry] {
        var entries: [BatchRunModelEntry] = []
        var autoIndex = 1
        for (offset, rawLine) in contents.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
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
            guard index.isEmpty == false else {
                throw MelixCLIError.usage("Empty model index at \(lineNumber).")
            }
            guard repoID.isEmpty == false else {
                throw MelixCLIError.usage("Empty repo id at \(lineNumber).")
            }
            entries.append(BatchRunModelEntry(index: index, repoID: repoID, sourceLine: lineNumber))
            autoIndex += 1
        }
        return entries
    }
}

enum BatchRunConfigLoader {
    private static let supportedKeys: Set<String> = [
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

    static func load(path: String) throws -> [String: String] {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return [:]
        }
        let text = try String(contentsOfFile: trimmed, encoding: .utf8)
        var values: [String: String] = [:]
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
                throw MelixCLIError.usage("Invalid batch config line \(lineNumber); expected key: value.")
            }
            let key = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
            let value = line[line.index(after: separator)...]
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            guard key.isEmpty == false else {
                throw MelixCLIError.usage("Invalid batch config line \(lineNumber); key is empty.")
            }
            let keyString = String(key)
            try validateKey(keyString, lineNumber: lineNumber)
            values[keyString] = value
        }
        return values
    }

    private static func validateKey(_ key: String, lineNumber: Int) throws {
        guard supportedKeys.contains(key) else {
            if embedsRawSecret(key) {
                throw MelixCLIError.usage(
                    "Unsupported batch config key '\(key)' at line \(lineNumber). Batch configs must reference stored credentials by id instead of embedding raw secrets."
                )
            }
            throw MelixCLIError.usage(
                "Unsupported batch config key '\(key)' at line \(lineNumber). Supported keys: \(supportedKeys.sorted().joined(separator: ", "))."
            )
        }
    }

    private static func embedsRawSecret(_ key: String) -> Bool {
        let lowered = key.lowercased()
        return secretKeySubstrings.contains { lowered.contains($0) }
    }
}

enum BatchRunPlanner {
    static func makePlan(options: BatchRunOptions, environment: [String: String]) throws -> BatchRunPlan {
        let configValues = try BatchRunConfigLoader.load(path: options.configPath)
        let modelListPath = nonEmpty(options.modelListPath, configValues["model_list"], environment["MELIX_BATCH_MODEL_LIST"])
        guard modelListPath.isEmpty == false else {
            throw MelixCLIError.missingRequired("--models is required for melix batch run.")
        }
        let modelText = try String(contentsOfFile: modelListPath, encoding: .utf8)
        let models = try BatchRunModelListParser.parse(contents: modelText)
        guard models.isEmpty == false else {
            throw MelixCLIError.usage("Model list \(modelListPath) does not contain any models.")
        }

        let runID = nonEmpty(
            options.runID,
            configValues["run_id"],
            environment["MELIX_RUN_ID"],
            timestampRunID()
        )
        let outputRoot = nonEmpty(
            options.outputRoot,
            configValues["output_root"],
            environment["MELIX_DOWNLOAD_ROOT"],
            "\(homeDirectory(environment: environment))/Downloads/melix-bench-eval-\(runID)"
        )
        let tempRoot = nonEmpty(
            options.tempRoot,
            configValues["temp_root"],
            environment["MELIX_RUN_TMP_ROOT"],
            "\(FileManager.default.currentDirectoryPath)/.runtime/bench-eval-run/\(runID)"
        )
        let startIndex = try intValue(
            explicit: options.startIndex,
            explicitWasProvided: options.explicitOptions.contains("--start-index"),
            keys: ["start_index"],
            configValues: configValues,
            environmentValue: environment["MELIX_START_INDEX"],
            defaultValue: 1,
            option: "--start-index"
        )
        let maxModels = try intValue(
            explicit: options.maxModels,
            explicitWasProvided: options.explicitOptions.contains("--max-models"),
            keys: ["max_models"],
            configValues: configValues,
            environmentValue: environment["MELIX_MAX_MODELS"],
            defaultValue: 0,
            option: "--max-models"
        )
        let repoRoot = nonEmpty(environment["MELIX_REPO_ROOT"], FileManager.default.currentDirectoryPath)
        let serviceInstanceName = nonEmpty(environment["MELIX_SERVICE_INSTANCE_NAME"], "bench-eval-batch")
        let melixHome = nonEmpty(
            configValues["melix_home"],
            environment["MELIX_HOME"],
            "\(repoRoot)/.runtime/home-\(serviceInstanceName)"
        )
        let runtimeDir = nonEmpty(
            configValues["runtime_dir"],
            environment["MELIX_RUNTIME_DIR"],
            "\(repoRoot)/.runtime/sidecars/\(serviceInstanceName)"
        )
        let httpPort = nonEmpty(
            configValues["http_port"],
            environment["MELIX_HTTP_PORT"],
            "12436"
        )
        let cliPath = nonEmpty(
            configValues["melix_cli"],
            environment["MELIX_CLI"],
            "\(repoRoot)/.build/debug/melix"
        )
        let config = BatchRunEffectiveConfig(
            repoRoot: repoRoot,
            runID: runID,
            modelListPath: modelListPath,
            configPath: options.configPath,
            outputRoot: outputRoot,
            tempRoot: tempRoot,
            melixHome: melixHome,
            runtimeDir: runtimeDir,
            httpPort: httpPort,
            serviceInstanceName: serviceInstanceName,
            cliPath: cliPath,
            startIndex: max(1, startIndex),
            maxModels: max(0, maxModels),
            judgeRemoteServerID: nonEmpty(
                options.judgeRemoteServerID,
                configValues["judge_remote_server_id"],
                environment["MELIX_JUDGE_SERVER_ID"],
                "owlia-gpt-5-5-judge"
            ),
            judgeModelID: nonEmpty(
                options.judgeModelID,
                configValues["judge_model"],
                environment["MELIX_JUDGE_MODEL"],
                "gpt-5.5"
            ),
            benchSuite: nonEmpty(options.benchSuite, configValues["bench_suite"], environment["MELIX_BENCH_SUITE"], "smoke"),
            benchContextLength: try uint32Value(
                explicit: options.benchContextLength,
                explicitWasProvided: options.explicitOptions.contains("--bench-context-length"),
                configValue: configValues["bench_context_length"],
                environmentValue: environment["MELIX_BENCH_CONTEXT_LENGTH"],
                defaultValue: 1024,
                option: "--bench-context-length"
            ),
            benchGenerationLength: try uint32Value(
                explicit: options.benchGenerationLength,
                explicitWasProvided: options.explicitOptions.contains("--bench-generation-length"),
                configValue: configValues["bench_generation_length"],
                environmentValue: environment["MELIX_BENCH_GENERATION_LENGTH"],
                defaultValue: 128,
                option: "--bench-generation-length"
            ),
            benchBatchSize: try uint32Value(
                explicit: options.benchBatchSize,
                explicitWasProvided: options.explicitOptions.contains("--bench-batch-size"),
                configValue: configValues["bench_batch_size"],
                environmentValue: environment["MELIX_BENCH_BATCH_SIZE"],
                defaultValue: 1,
                option: "--bench-batch-size"
            ),
            benchRepeats: try uint32Value(
                explicit: options.benchRepeats,
                explicitWasProvided: options.explicitOptions.contains("--bench-repeats"),
                configValue: configValues["bench_repeats"],
                environmentValue: environment["MELIX_BENCH_REPEATS"],
                defaultValue: 1,
                option: "--bench-repeats"
            ),
            benchSampleSize: try uint32Value(
                explicit: options.benchSampleSize,
                explicitWasProvided: options.explicitOptions.contains("--bench-sample-size"),
                configValue: configValues["bench_sample_size"],
                environmentValue: environment["MELIX_BENCH_SAMPLE_SIZE"],
                defaultValue: 1,
                option: "--bench-sample-size"
            ),
            benchBatchFactor: try uint32Value(
                explicit: options.benchBatchFactor,
                explicitWasProvided: options.explicitOptions.contains("--bench-batch-factor"),
                configValue: configValues["bench_batch_factor"],
                environmentValue: environment["MELIX_BENCH_BATCH_FACTOR"],
                defaultValue: 1,
                option: "--bench-batch-factor"
            ),
            evalSuite: nonEmpty(options.evalSuite, configValues["eval_suite"], environment["MELIX_EVAL_SUITE"], "event_extraction"),
            evalDatasetID: nonEmpty(
                options.evalDatasetID,
                configValues["eval_dataset_id"],
                environment["MELIX_EVAL_DATASET_ID"],
                "top200.event-extraction.top20.v1"
            ),
            evalScoringMode: nonEmpty(
                options.evalScoringMode,
                configValues["eval_scoring_mode"],
                environment["MELIX_EVAL_SCORING_MODE"],
                "event_extraction_weighted_f1"
            ),
            evalSampleSize: try uint32Value(
                explicit: options.evalSampleSize,
                explicitWasProvided: options.explicitOptions.contains("--eval-sample-size"),
                configValue: configValues["eval_sample_size"],
                environmentValue: environment["MELIX_EVAL_SAMPLE_SIZE"],
                defaultValue: 20,
                option: "--eval-sample-size"
            ),
            evalBatchFactor: try uint32Value(
                explicit: options.evalBatchFactor,
                explicitWasProvided: options.explicitOptions.contains("--eval-batch-factor"),
                configValue: configValues["eval_batch_factor"],
                environmentValue: environment["MELIX_EVAL_BATCH_FACTOR"],
                defaultValue: 1,
                option: "--eval-batch-factor"
            ),
            continueOnFailure: try boolValue(
                explicit: options.continueOnFailure,
                explicitWasProvided: options.explicitOptions.contains("--continue-on-failure"),
                configValue: configValues["continue_on_failure"],
                environmentValue: environment["MELIX_CONTINUE_ON_FAILURE"],
                defaultValue: true,
                option: "--continue-on-failure"
            ),
            restartStackPerModel: try boolValue(
                explicit: options.restartStackPerModel,
                explicitWasProvided: options.explicitOptions.contains("--restart-stack-per-model"),
                configValue: configValues["restart_stack_per_model"],
                environmentValue: environment["MELIX_RESTART_STACK_PER_MODEL"],
                defaultValue: true,
                option: "--restart-stack-per-model"
            ),
            preflight: try boolValue(
                explicit: options.preflight,
                explicitWasProvided: options.preflight || options.explicitOptions.contains("--preflight"),
                configValue: configValues["preflight"],
                environmentValue: environment["MELIX_BATCH_PREFLIGHT"],
                defaultValue: false,
                option: "--preflight"
            ),
            dryRun: options.dryRun,
            isSubsetRun: max(1, startIndex) > 1 || max(0, maxModels) > 0
        )

        let selected = selectModels(models, startIndex: config.startIndex, maxModels: config.maxModels)
        return BatchRunPlan(
            config: config,
            models: models,
            selectedModels: selected,
            manifestPath: URL(fileURLWithPath: tempRoot).appendingPathComponent("manifest.jsonl").path,
            effectiveConfigPath: URL(fileURLWithPath: tempRoot).appendingPathComponent("effective-config.json").path,
            preflightReportPath: URL(fileURLWithPath: tempRoot).appendingPathComponent("preflight-report.json").path
        )
    }

    private static func selectModels(
        _ models: [BatchRunModelEntry],
        startIndex: Int,
        maxModels: Int
    ) -> [BatchRunModelEntry] {
        let start = max(0, startIndex - 1)
        let filtered = start < models.count ? Array(models[start...]) : []
        guard maxModels > 0 else {
            return filtered
        }
        return Array(filtered.prefix(maxModels))
    }

    private static func nonEmpty(_ values: String?...) -> String {
        for value in values {
            let trimmed = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty == false {
                return trimmed
            }
        }
        return ""
    }

    private static func homeDirectory(environment: [String: String]) -> String {
        nonEmpty(environment["HOME"], FileManager.default.homeDirectoryForCurrentUser.path)
    }

    private static func timestampRunID() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }

    private static func intValue(
        explicit: Int,
        explicitWasProvided: Bool,
        keys: [String],
        configValues: [String: String],
        environmentValue: String?,
        defaultValue: Int,
        option: String
    ) throws -> Int {
        if explicitWasProvided {
            return explicit
        }
        for key in keys {
            if let value = configValues[key], value.isEmpty == false {
                guard let parsed = Int(value) else {
                    throw MelixCLIError.usage("Invalid value for \(option): \(value).")
                }
                return parsed
            }
        }
        if let environmentValue, environmentValue.isEmpty == false {
            guard let parsed = Int(environmentValue) else {
                throw MelixCLIError.usage("Invalid value for \(option): \(environmentValue).")
            }
            return parsed
        }
        return defaultValue
    }

    private static func uint32Value(
        explicit: UInt32,
        explicitWasProvided: Bool,
        configValue: String?,
        environmentValue: String?,
        defaultValue: UInt32,
        option: String
    ) throws -> UInt32 {
        if explicitWasProvided {
            return explicit
        }
        let raw = nonEmpty(configValue, environmentValue)
        guard raw.isEmpty == false else {
            return defaultValue
        }
        guard let parsed = UInt32(raw) else {
            throw MelixCLIError.usage("Invalid value for \(option): \(raw).")
        }
        return parsed
    }

    private static func boolValue(
        explicit: Bool,
        explicitWasProvided: Bool,
        configValue: String?,
        environmentValue: String?,
        defaultValue: Bool,
        option: String
    ) throws -> Bool {
        if explicitWasProvided {
            return explicit
        }
        let raw = nonEmpty(configValue, environmentValue)
        guard raw.isEmpty == false else {
            return defaultValue
        }
        switch raw.lowercased() {
        case "1", "true", "yes", "y":
            return true
        case "0", "false", "no", "n":
            return false
        default:
            throw MelixCLIError.usage("Invalid value for \(option): \(raw).")
        }
    }
}

enum BatchRunArtifacts {
    static func writeFoundationArtifacts(plan: BatchRunPlan) throws {
        let tempRoot = URL(fileURLWithPath: plan.config.tempRoot)
        let outputRoot = URL(fileURLWithPath: plan.config.outputRoot)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
        try jsonData(effectiveConfigPayload(plan: plan)).write(
            to: URL(fileURLWithPath: plan.effectiveConfigPath),
            options: .atomic
        )
        try manifestText(plan: plan).write(
            to: URL(fileURLWithPath: plan.manifestPath),
            atomically: true,
            encoding: .utf8
        )
        try FileManager.default.copyItemReplacingExisting(
            at: URL(fileURLWithPath: plan.effectiveConfigPath),
            to: outputRoot.appendingPathComponent("effective-config.json")
        )
        try FileManager.default.copyItemReplacingExisting(
            at: URL(fileURLWithPath: plan.manifestPath),
            to: outputRoot.appendingPathComponent("manifest.jsonl")
        )
    }

    static func writePreflightReport(_ report: BatchRunPreflightReport, plan: BatchRunPlan) throws {
        let outputRoot = URL(fileURLWithPath: plan.config.outputRoot)
        try jsonData(report.payload(plan: plan)).write(
            to: URL(fileURLWithPath: plan.preflightReportPath),
            options: .atomic
        )
        try FileManager.default.copyItemReplacingExisting(
            at: URL(fileURLWithPath: plan.preflightReportPath),
            to: outputRoot.appendingPathComponent("preflight-report.json")
        )
    }

    static func effectiveConfigPayload(plan: BatchRunPlan) -> [String: Any] {
        let config = plan.config
        return [
            "schema_version": "melix.batch.effective_config.v1",
            "repo_root": config.repoRoot,
            "run_id": config.runID,
            "model_list": config.modelListPath,
            "config_path": config.configPath,
            "output_root": config.outputRoot,
            "temp_root": config.tempRoot,
            "melix_home": config.melixHome,
            "runtime_dir": config.runtimeDir,
            "http_port": config.httpPort,
            "service_instance_name": config.serviceInstanceName,
            "melix_cli": config.cliPath,
            "start_index": config.startIndex,
            "max_models": config.maxModels,
            "selected_model_count": plan.selectedModels.count,
            "total_model_count": plan.models.count,
            "is_subset_run": config.isSubsetRun,
            "dry_run": config.dryRun,
            "preflight": config.preflight,
            "continue_on_failure": config.continueOnFailure,
            "restart_stack_per_model": config.restartStackPerModel,
            "isolation_policy": isolationPolicyPayload(config: config),
            "preflight_report": config.preflight ? plan.preflightReportPath : "",
            "judge": [
                "remote_server_id": config.judgeRemoteServerID,
                "model": config.judgeModelID,
            ],
            "benchmark": [
                "suite": config.benchSuite,
                "context_length": NSNumber(value: config.benchContextLength),
                "generation_length": NSNumber(value: config.benchGenerationLength),
                "batch_size": NSNumber(value: config.benchBatchSize),
                "repeats": NSNumber(value: config.benchRepeats),
                "sample_size": NSNumber(value: config.benchSampleSize),
                "batch_factor": NSNumber(value: config.benchBatchFactor),
            ],
            "evaluation": [
                "suite": config.evalSuite,
                "dataset_id": config.evalDatasetID,
                "scoring_mode": config.evalScoringMode,
                "sample_size": NSNumber(value: config.evalSampleSize),
                "batch_factor": NSNumber(value: config.evalBatchFactor),
            ],
            "models": plan.selectedModels.map(modelPayload),
        ]
    }

    static func manifestText(plan: BatchRunPlan) throws -> String {
        try plan.selectedModels.map { model in
            let modelDir = URL(fileURLWithPath: plan.config.outputRoot)
                .appendingPathComponent(modelSlug(index: model.index, repoID: model.repoID))
                .path
            let payload: [String: Any] = [
                "schema_version": "melix.batch.manifest_entry.v1",
                "run_id": plan.config.runID,
                "model_index": model.index,
                "repo_id": model.repoID,
                "source_line": model.sourceLine,
                "status": "planned",
                "model_dir": modelDir,
                "steps": [
                    "preflight": stepPayload(),
                    "runtime_prepare": stepPayload(),
                    "model_unload": stepPayload(),
                    "hub_check": stepPayload(),
                    "benchmark": stepPayload(),
                    "evaluation": stepPayload(),
                    "exports": stepPayload(),
                    "artifact_copy": stepPayload(),
                ],
                "failure_category": "",
                "recoverability": "",
            ]
            return String(decoding: try compactJSONData(payload), as: UTF8.self)
        }.joined(separator: "\n") + "\n"
    }

    static func renderTextSummary(plan: BatchRunPlan) -> String {
        var lines: [String] = []
        lines.append("Melix batch run dry-run")
        lines.append("run_id=\(plan.config.runID)")
        lines.append("models=\(plan.selectedModels.count)/\(plan.models.count)")
        if plan.config.isSubsetRun {
            lines.append("subset=start_index:\(plan.config.startIndex),max_models:\(plan.config.maxModels)")
        }
        lines.append("repo_root=\(plan.config.repoRoot)")
        lines.append("temp_root=\(plan.config.tempRoot)")
        lines.append("output_root=\(plan.config.outputRoot)")
        lines.append("melix_home=\(plan.config.melixHome)")
        lines.append("runtime_dir=\(plan.config.runtimeDir)")
        lines.append("http_port=\(plan.config.httpPort)")
        lines.append("judge=\(plan.config.judgeRemoteServerID)/\(plan.config.judgeModelID)")
        lines.append("preflight=\(plan.config.preflight)")
        lines.append("restart_stack_per_model=\(plan.config.restartStackPerModel)")
        lines.append("continue_on_failure=\(plan.config.continueOnFailure)")
        lines.append("isolation=best_effort_unload:true,force_clean_after_runtime_failure:true")
        lines.append("effective_config=\(plan.effectiveConfigPath)")
        lines.append("manifest=\(plan.manifestPath)")
        if plan.config.preflight {
            lines.append("preflight_report=\(plan.preflightReportPath)")
        }
        for (offset, model) in plan.selectedModels.enumerated() {
            lines.append("[\(offset + 1)/\(plan.selectedModels.count)] PLAN \(model.index) \(model.repoID)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    static func renderPreflightTextSummary(plan: BatchRunPlan, report: BatchRunPreflightReport) -> String {
        var lines = renderTextSummary(plan: plan)
            .trimmingCharacters(in: .newlines)
            .components(separatedBy: "\n")
        lines.append("preflight_status=\(report.status)")
        lines.append("preflight_blockers=\(report.blockers.count)")
        for check in report.checks {
            lines.append("CHECK \(check.name) \(check.status) - \(check.detail)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private static func modelPayload(_ model: BatchRunModelEntry) -> [String: Any] {
        [
            "index": model.index,
            "repo_id": model.repoID,
            "source_line": model.sourceLine,
            "slug": modelSlug(index: model.index, repoID: model.repoID),
        ]
    }

    private static func stepPayload() -> [String: Any] {
        [
            "status": "pending",
            "job_id": "",
            "stdout_path": "",
            "stderr_path": "",
            "artifact_path": "",
            "failure_category": "",
            "recoverability": "",
        ]
    }

    private static func isolationPolicyPayload(config: BatchRunEffectiveConfig) -> [String: Any] {
        [
            "schema_version": "melix.batch.isolation_policy.v1",
            "best_effort_unload_previous_model": true,
            "best_effort_unload_after_model": true,
            "restart_stack_per_model": config.restartStackPerModel,
            "force_clean_stack_after_runtime_failure": true,
            "cleanup_failures_preserve_artifacts": true,
        ]
    }

    private static func modelSlug(index: String, repoID: String) -> String {
        let raw = "\(index)-\(repoID)"
        var slug = ""
        var lastWasDash = false
        for scalar in raw.lowercased().unicodeScalars {
            let allowed = CharacterSet.alphanumerics.contains(scalar)
                || scalar == "."
                || scalar == "_"
            if allowed {
                slug.unicodeScalars.append(scalar)
                lastWasDash = false
            } else if lastWasDash == false {
                slug.append("-")
                lastWasDash = true
            }
        }
        return slug.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    }

    private static func jsonData(_ payload: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    }

    private static func compactJSONData(_ payload: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    }
}

private extension FileManager {
    func copyItemReplacingExisting(at sourceURL: URL, to destinationURL: URL) throws {
        let sourcePath = sourceURL.standardizedFileURL.path
        let destinationPath = destinationURL.standardizedFileURL.path
        guard sourcePath != destinationPath else {
            return
        }
        if fileExists(atPath: destinationPath) {
            try removeItem(at: destinationURL)
        }
        try copyItem(at: sourceURL, to: destinationURL)
    }
}
