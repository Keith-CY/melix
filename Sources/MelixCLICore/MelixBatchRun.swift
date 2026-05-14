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
        self.explicitOptions = explicitOptions.union(Self.inferredExplicitOptions(
            startIndex: startIndex,
            maxModels: maxModels,
            benchContextLength: benchContextLength,
            benchGenerationLength: benchGenerationLength,
            benchBatchSize: benchBatchSize,
            benchRepeats: benchRepeats,
            benchSampleSize: benchSampleSize,
            benchBatchFactor: benchBatchFactor,
            evalSampleSize: evalSampleSize,
            evalBatchFactor: evalBatchFactor,
            continueOnFailure: continueOnFailure,
            restartStackPerModel: restartStackPerModel,
            preflight: preflight
        ))
    }

    private static func inferredExplicitOptions(
        startIndex: Int,
        maxModels: Int,
        benchContextLength: UInt32,
        benchGenerationLength: UInt32,
        benchBatchSize: UInt32,
        benchRepeats: UInt32,
        benchSampleSize: UInt32,
        benchBatchFactor: UInt32,
        evalSampleSize: UInt32,
        evalBatchFactor: UInt32,
        continueOnFailure: Bool,
        restartStackPerModel: Bool,
        preflight: Bool
    ) -> Set<String> {
        var options: Set<String> = []
        if startIndex != 1 { options.insert("--start-index") }
        if maxModels != 0 { options.insert("--max-models") }
        if benchContextLength != 0 { options.insert("--bench-context-length") }
        if benchGenerationLength != 0 { options.insert("--bench-generation-length") }
        if benchBatchSize != 0 { options.insert("--bench-batch-size") }
        if benchRepeats != 0 { options.insert("--bench-repeats") }
        if benchSampleSize != 0 { options.insert("--bench-sample-size") }
        if benchBatchFactor != 0 { options.insert("--bench-batch-factor") }
        if evalSampleSize != 0 { options.insert("--eval-sample-size") }
        if evalBatchFactor != 0 { options.insert("--eval-batch-factor") }
        if continueOnFailure { options.insert("--continue-on-failure") }
        if restartStackPerModel { options.insert("--restart-stack-per-model") }
        if preflight { options.insert("--preflight") }
        return options
    }
}

public struct BatchStatusOptions: Equatable, Sendable {
    public let runID: String
    public let outputRoot: String
    public let tempRoot: String
    public let json: Bool

    public init(
        runID: String = "",
        outputRoot: String = "",
        tempRoot: String = "",
        json: Bool = false
    ) {
        self.runID = runID
        self.outputRoot = outputRoot
        self.tempRoot = tempRoot
        self.json = json
    }
}

public struct BatchResumeOptions: Equatable, Sendable {
    public let runID: String
    public let outputRoot: String
    public let tempRoot: String
    public let modelListPath: String
    public let configPath: String
    public let evalOnly: Bool
    public let missingOnly: Bool
    public let continueOnFailure: Bool
    public let dryRun: Bool
    public let json: Bool

    public init(
        runID: String = "",
        outputRoot: String = "",
        tempRoot: String = "",
        modelListPath: String = "",
        configPath: String = "",
        evalOnly: Bool = false,
        missingOnly: Bool = true,
        continueOnFailure: Bool = true,
        dryRun: Bool = false,
        json: Bool = false
    ) {
        self.runID = runID
        self.outputRoot = outputRoot
        self.tempRoot = tempRoot
        self.modelListPath = modelListPath
        self.configPath = configPath
        self.evalOnly = evalOnly
        self.missingOnly = missingOnly
        self.continueOnFailure = continueOnFailure
        self.dryRun = dryRun
        self.json = json
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
    let category: String
    let metadata: [String: String]

    init(
        name: String,
        status: String,
        detail: String,
        actionable: String,
        category: String = "general",
        metadata: [String: String] = [:]
    ) {
        self.name = name
        self.status = status
        self.detail = detail
        self.actionable = actionable
        self.category = category
        self.metadata = metadata
    }

    var isBlocking: Bool {
        status == "blocked"
    }

    func payload() -> [String: Any] {
        [
            "name": name,
            "status": status,
            "detail": detail,
            "actionable": actionable,
            "category": category,
            "metadata": metadata,
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
        let searchable = [stdout, stderr] + metadata.map { "\($0.key)=\($0.value)" }
        guard searchable.contains(where: { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
            return unknown
        }

        if containsAny(searchable, needles: [
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
        if containsAny(searchable, needles: [
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
        if containsAny(searchable, needles: [
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
        if containsAny(searchable, needles: [
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
        if containsAny(searchable, needles: [
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
        if containsAny(searchable, needles: [
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
        if containsAny(searchable, needles: [
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

    private static func containsAny(_ haystacks: [String], needles: [String]) -> Bool {
        haystacks.contains { haystack in
            needles.contains { needle in
                haystack.range(of: needle, options: [.caseInsensitive]) != nil
            }
        }
    }
}

enum BatchRunModelListParser {
    static func parse(contents: String) throws -> [BatchRunModelEntry] {
        var entries: [BatchRunModelEntry] = []
        var autoIndex = 1
        for (offset, rawLine) in contents.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty, !line.hasPrefix("#") else {
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
            guard !index.isEmpty else {
                throw MelixCLIError.usage("Empty model index at \(lineNumber).")
            }
            guard !repoID.isEmpty else {
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
    static func writeFoundationArtifacts(plan: BatchRunPlan, writePlannedManifest: Bool = true) throws {
        let tempRoot = URL(fileURLWithPath: plan.config.tempRoot)
        let outputRoot = URL(fileURLWithPath: plan.config.outputRoot)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
        try jsonData(effectiveConfigPayload(plan: plan)).write(
            to: URL(fileURLWithPath: plan.effectiveConfigPath),
            options: .atomic
        )
        try FileManager.default.copyItemReplacingExisting(
            at: URL(fileURLWithPath: plan.effectiveConfigPath),
            to: outputRoot.appendingPathComponent("effective-config.json")
        )
        if writePlannedManifest {
            try manifestText(plan: plan).write(
                to: URL(fileURLWithPath: plan.manifestPath),
                atomically: true,
                encoding: .utf8
            )
            try FileManager.default.copyItemReplacingExisting(
                at: URL(fileURLWithPath: plan.manifestPath),
                to: outputRoot.appendingPathComponent("manifest.jsonl")
            )
        }
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
                .appendingPathComponent(BatchRunSlug.modelSlug(model: model))
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
            "slug": BatchRunSlug.modelSlug(model: model),
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

    private static func jsonData(_ payload: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    }

    private static func compactJSONData(_ payload: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    }
}

enum BatchRunStepName: String, CaseIterable {
    case preflight
    case runtimePrepare = "runtime_prepare"
    case modelUnload = "model_unload"
    case hubCheck = "hub_check"
    case benchmark
    case evaluation
    case exports
    case artifactCopy = "artifact_copy"
}

struct BatchRunStepRecord: Equatable {
    var status: String = "pending"
    var jobID: String = ""
    var stdoutPath: String = ""
    var stderrPath: String = ""
    var artifactPath: String = ""
    var startedAt: String = ""
    var finishedAt: String = ""
    var durationSeconds: Double = 0
    var failureCategory: String = ""
    var recoverability: String = ""
    var message: String = ""

    init(
        status: String = "pending",
        jobID: String = "",
        stdoutPath: String = "",
        stderrPath: String = "",
        artifactPath: String = "",
        startedAt: String = "",
        finishedAt: String = "",
        durationSeconds: Double = 0,
        failureCategory: String = "",
        recoverability: String = "",
        message: String = ""
    ) {
        self.status = status
        self.jobID = jobID
        self.stdoutPath = stdoutPath
        self.stderrPath = stderrPath
        self.artifactPath = artifactPath
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.durationSeconds = durationSeconds
        self.failureCategory = failureCategory
        self.recoverability = recoverability
        self.message = message
    }

    init(payload: [String: Any]) {
        status = payload["status"] as? String ?? "pending"
        jobID = payload["job_id"] as? String ?? ""
        stdoutPath = payload["stdout_path"] as? String ?? ""
        stderrPath = payload["stderr_path"] as? String ?? ""
        artifactPath = payload["artifact_path"] as? String ?? ""
        startedAt = payload["started_at"] as? String ?? ""
        finishedAt = payload["finished_at"] as? String ?? ""
        durationSeconds = BatchRunPayloadParser.doubleValue(payload["duration_seconds"]) ?? 0
        failureCategory = payload["failure_category"] as? String ?? ""
        recoverability = payload["recoverability"] as? String ?? ""
        message = payload["message"] as? String ?? ""
    }

    func payload() -> [String: Any] {
        [
            "status": status,
            "job_id": jobID,
            "stdout_path": stdoutPath,
            "stderr_path": stderrPath,
            "artifact_path": artifactPath,
            "started_at": startedAt,
            "finished_at": finishedAt,
            "duration_seconds": durationSeconds,
            "failure_category": failureCategory,
            "recoverability": recoverability,
            "message": message,
        ]
    }
}

struct BatchRunModelRecord: Equatable {
    let schemaVersion: String
    let runID: String
    let modelIndex: String
    let repoID: String
    let sourceLine: Int
    var status: String
    var modelDir: String
    var tempDir: String
    var startedAt: String
    var finishedAt: String
    var durationSeconds: Double
    var benchmarkJobID: String
    var evaluationJobID: String
    var benchmarkCSVPath: String
    var evaluationSummaryCSVPath: String
    var evaluationSamplesCSVPath: String
    var evaluationSamplesJSONLPath: String
    var rawArtifactPaths: [String]
    var metricFields: [String: Double]
    var failureCategory: String
    var recoverability: String
    var failureMessage: String
    var steps: [String: BatchRunStepRecord]

    init(
        runID: String,
        model: BatchRunModelEntry,
        modelDir: String,
        tempDir: String
    ) {
        schemaVersion = "melix.batch.manifest_entry.v1"
        self.runID = runID
        modelIndex = model.index
        repoID = model.repoID
        sourceLine = model.sourceLine
        status = "planned"
        self.modelDir = modelDir
        self.tempDir = tempDir
        startedAt = ""
        finishedAt = ""
        durationSeconds = 0
        benchmarkJobID = ""
        evaluationJobID = ""
        benchmarkCSVPath = ""
        evaluationSummaryCSVPath = ""
        evaluationSamplesCSVPath = ""
        evaluationSamplesJSONLPath = ""
        rawArtifactPaths = []
        metricFields = [:]
        failureCategory = ""
        recoverability = ""
        failureMessage = ""
        steps = Dictionary(uniqueKeysWithValues: BatchRunStepName.allCases.map { ($0.rawValue, BatchRunStepRecord()) })
    }

    init(payload: [String: Any]) {
        schemaVersion = payload["schema_version"] as? String ?? "melix.batch.manifest_entry.v1"
        runID = payload["run_id"] as? String ?? ""
        modelIndex = payload["model_index"] as? String ?? ""
        repoID = payload["repo_id"] as? String ?? ""
        sourceLine = payload["source_line"] as? Int ?? 0
        status = payload["status"] as? String ?? "planned"
        modelDir = payload["model_dir"] as? String ?? ""
        tempDir = payload["temp_dir"] as? String ?? ""
        startedAt = payload["started_at"] as? String ?? ""
        finishedAt = payload["finished_at"] as? String ?? ""
        durationSeconds = BatchRunPayloadParser.doubleValue(payload["duration_seconds"]) ?? 0
        benchmarkJobID = payload["benchmark_job_id"] as? String ?? ""
        evaluationJobID = payload["evaluation_job_id"] as? String ?? ""
        benchmarkCSVPath = payload["benchmark_csv_path"] as? String ?? ""
        evaluationSummaryCSVPath = payload["evaluation_summary_csv_path"] as? String ?? ""
        evaluationSamplesCSVPath = payload["evaluation_samples_csv_path"] as? String ?? ""
        evaluationSamplesJSONLPath = payload["evaluation_samples_jsonl_path"] as? String ?? ""
        rawArtifactPaths = payload["raw_artifact_paths"] as? [String] ?? []
        if let metrics = payload["metric_fields"] as? [String: Any] {
            metricFields = BatchRunPayloadParser.metricValues(from: metrics)
        } else {
            metricFields = [:]
        }
        failureCategory = payload["failure_category"] as? String ?? ""
        recoverability = payload["recoverability"] as? String ?? ""
        failureMessage = payload["failure_message"] as? String ?? ""
        let stepPayloads = payload["steps"] as? [String: Any] ?? [:]
        var parsedSteps = Dictionary(uniqueKeysWithValues: BatchRunStepName.allCases.map { ($0.rawValue, BatchRunStepRecord()) })
        for (name, value) in stepPayloads {
            if let payload = value as? [String: Any] {
                parsedSteps[name] = BatchRunStepRecord(payload: payload)
            }
        }
        steps = parsedSteps
    }

    var benchmarkSucceeded: Bool {
        steps[BatchRunStepName.benchmark.rawValue]?.status == "succeeded"
    }

    var evaluationSucceeded: Bool {
        steps[BatchRunStepName.evaluation.rawValue]?.status == "succeeded"
    }

    var completedSuccessfully: Bool {
        status == "succeeded"
    }

    func payload() -> [String: Any] {
        [
            "schema_version": schemaVersion,
            "run_id": runID,
            "model_index": modelIndex,
            "repo_id": repoID,
            "source_line": sourceLine,
            "status": status,
            "model_dir": modelDir,
            "temp_dir": tempDir,
            "started_at": startedAt,
            "finished_at": finishedAt,
            "duration_seconds": durationSeconds,
            "benchmark_job_id": benchmarkJobID,
            "evaluation_job_id": evaluationJobID,
            "benchmark_csv_path": benchmarkCSVPath,
            "evaluation_summary_csv_path": evaluationSummaryCSVPath,
            "evaluation_samples_csv_path": evaluationSamplesCSVPath,
            "evaluation_samples_jsonl_path": evaluationSamplesJSONLPath,
            "raw_artifact_paths": rawArtifactPaths,
            "metric_fields": metricFields,
            "failure_category": failureCategory,
            "recoverability": recoverability,
            "failure_message": failureMessage,
            "steps": Dictionary(uniqueKeysWithValues: steps.keys.sorted().map { key in
                (key, steps[key]?.payload() ?? BatchRunStepRecord().payload())
            }),
        ]
    }
}

struct BatchRunRecordIdentity: Hashable {
    let modelIndex: String
    let repoID: String
    let sourceLine: Int

    init(model: BatchRunModelEntry) {
        modelIndex = model.index
        repoID = model.repoID
        sourceLine = model.sourceLine
    }

    init(record: BatchRunModelRecord) {
        modelIndex = record.modelIndex
        repoID = record.repoID
        sourceLine = record.sourceLine
    }
}

struct BatchRunSummary {
    let schemaVersion: String
    let runID: String
    let status: String
    let totalModels: Int
    let succeededModels: Int
    let failedModels: Int
    let partialSuccessModels: Int
    let plannedModels: Int
    let runningModels: Int
    let records: [BatchRunModelRecord]
    let tempRoot: String
    let outputRoot: String
    let manifestPath: String

    func payload() -> [String: Any] {
        [
            "schema_version": schemaVersion,
            "run_id": runID,
            "status": status,
            "total_models": totalModels,
            "succeeded_models": succeededModels,
            "failed_models": failedModels,
            "partial_success_models": partialSuccessModels,
            "planned_models": plannedModels,
            "running_models": runningModels,
            "temp_root": tempRoot,
            "output_root": outputRoot,
            "manifest_path": manifestPath,
            "models": records.map { record in
                [
                    "model_index": record.modelIndex,
                    "repo_id": record.repoID,
                    "status": record.status,
                    "benchmark_job_id": record.benchmarkJobID,
                    "evaluation_job_id": record.evaluationJobID,
                    "failure_category": record.failureCategory,
                    "recoverability": record.recoverability,
                    "duration_seconds": record.durationSeconds,
                    "metric_fields": record.metricFields,
                ]
            },
        ]
    }
}

struct BatchRunStatusResolution {
    let runID: String
    let tempRoot: String
    let outputRoot: String
    let manifestPath: String
}

enum BatchRunStatusResolver {
    static func resolve(options: BatchStatusOptions, environment: [String: String]) throws -> BatchRunStatusResolution {
        try resolve(runID: options.runID, tempRoot: options.tempRoot, outputRoot: options.outputRoot, environment: environment)
    }

    static func resolve(runID: String, tempRoot: String, outputRoot: String, environment: [String: String]) throws -> BatchRunStatusResolution {
        let fm = FileManager.default
        let resolvedTempRoot = tempRoot.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedOutputRoot = outputRoot.trimmingCharacters(in: .whitespacesAndNewlines)
        if !resolvedTempRoot.isEmpty {
            let manifest = URL(fileURLWithPath: resolvedTempRoot).appendingPathComponent("manifest.jsonl").path
            let config = URL(fileURLWithPath: resolvedTempRoot).appendingPathComponent("effective-config.json").path
            let id = try resolvedRunID(explicit: runID, manifestPath: manifest)
            return .init(
                runID: id,
                tempRoot: resolvedTempRoot,
                outputRoot: nonEmpty(resolvedOutputRoot, configValue("output_root", from: config)),
                manifestPath: manifest
            )
        }
        if !resolvedOutputRoot.isEmpty {
            let manifest = URL(fileURLWithPath: resolvedOutputRoot).appendingPathComponent("manifest.jsonl").path
            let config = URL(fileURLWithPath: resolvedOutputRoot).appendingPathComponent("effective-config.json").path
            let id = try resolvedRunID(explicit: runID, manifestPath: manifest)
            return .init(
                runID: id,
                tempRoot: nonEmpty(configValue("temp_root", from: config), ""),
                outputRoot: resolvedOutputRoot,
                manifestPath: manifest
            )
        }
        let id = runID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty else {
            throw MelixCLIError.missingRequired("--run-id or --temp-root/--output-root is required for melix batch status.")
        }
        let repoRoot = environment["MELIX_REPO_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? environment["MELIX_REPO_ROOT"]!
            : FileManager.default.currentDirectoryPath
        let tempCandidate = URL(fileURLWithPath: repoRoot)
            .appendingPathComponent(".runtime/bench-eval-run/\(id)")
        let outputCandidate = URL(fileURLWithPath: homeDirectory(environment: environment))
            .appendingPathComponent("Downloads/melix-bench-eval-\(id)")
        let tempManifest = tempCandidate.appendingPathComponent("manifest.jsonl").path
        let outputManifest = outputCandidate.appendingPathComponent("manifest.jsonl").path
        if fm.fileExists(atPath: tempManifest) {
            let config = tempCandidate.appendingPathComponent("effective-config.json").path
            return .init(
                runID: id,
                tempRoot: tempCandidate.path,
                outputRoot: nonEmpty(configValue("output_root", from: config), outputCandidate.path),
                manifestPath: tempManifest
            )
        }
        if fm.fileExists(atPath: outputManifest) {
            let config = outputCandidate.appendingPathComponent("effective-config.json").path
            return .init(
                runID: id,
                tempRoot: nonEmpty(configValue("temp_root", from: config), tempCandidate.path),
                outputRoot: outputCandidate.path,
                manifestPath: outputManifest
            )
        }
        throw MelixCLIError.runtime("No batch manifest found for run \(id). Checked \(tempManifest) and \(outputManifest).")
    }

    private static func resolvedRunID(explicit: String, manifestPath: String) throws -> String {
        let trimmed = explicit.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            return trimmed
        }
        let records = try BatchRunManifestStore.loadRecords(manifestPath: manifestPath)
        if let runID = records.first?.runID, !runID.isEmpty {
            return runID
        }
        return URL(fileURLWithPath: manifestPath).deletingLastPathComponent().lastPathComponent
    }

    private static func configValue(_ key: String, from path: String) -> String {
        guard
            FileManager.default.fileExists(atPath: path),
            let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return ""
        }
        return payload[key] as? String ?? ""
    }

    private static func nonEmpty(_ values: String?...) -> String {
        for value in values {
            let trimmed = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return trimmed
            }
        }
        return ""
    }

    private static func homeDirectory(environment: [String: String]) -> String {
        let home = environment["HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return home.isEmpty ? FileManager.default.homeDirectoryForCurrentUser.path : home
    }
}

enum BatchRunManifestStore {
    static func initialRecords(plan: BatchRunPlan) -> [BatchRunModelRecord] {
        plan.selectedModels.map { model in
            BatchRunModelRecord(
                runID: plan.config.runID,
                model: model,
                modelDir: modelDir(plan: plan, model: model).path,
                tempDir: modelTempDir(plan: plan, model: model).path
            )
        }
    }

    static func alignedRecords(plan: BatchRunPlan, existingRecords: [BatchRunModelRecord]?) -> [BatchRunModelRecord] {
        guard let existingRecords, !existingRecords.isEmpty else {
            return initialRecords(plan: plan)
        }
        var recordsByIdentity: [BatchRunRecordIdentity: [BatchRunModelRecord]] = [:]
        for record in existingRecords {
            recordsByIdentity[BatchRunRecordIdentity(record: record), default: []].append(record)
        }
        var aligned = plan.selectedModels.map { model -> (model: BatchRunModelEntry, record: BatchRunModelRecord) in
            let identity = BatchRunRecordIdentity(model: model)
            if var matches = recordsByIdentity[identity], !matches.isEmpty {
                var record = matches.removeFirst()
                recordsByIdentity[identity] = matches
                if record.modelDir.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    record.modelDir = modelDir(plan: plan, model: model).path
                }
                if record.tempDir.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    record.tempDir = modelTempDir(plan: plan, model: model).path
                }
                return (model, record)
            }
            return (model, BatchRunModelRecord(
                runID: plan.config.runID,
                model: model,
                modelDir: modelDir(plan: plan, model: model).path,
                tempDir: modelTempDir(plan: plan, model: model).path
            ))
        }
        let duplicateModelDirs = duplicateValues(aligned.map { $0.record.modelDir })
        let duplicateTempDirs = duplicateValues(aligned.map { $0.record.tempDir })
        for index in aligned.indices {
            if duplicateModelDirs.contains(aligned[index].record.modelDir) {
                aligned[index].record.modelDir = modelDir(plan: plan, model: aligned[index].model).path
            }
            if duplicateTempDirs.contains(aligned[index].record.tempDir) {
                aligned[index].record.tempDir = modelTempDir(plan: plan, model: aligned[index].model).path
            }
        }
        return aligned.map { $0.record }
    }

    private static func duplicateValues(_ values: [String]) -> Set<String> {
        var seen: Set<String> = []
        var duplicates: Set<String> = []
        for value in values where !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            if !seen.insert(value).inserted {
                duplicates.insert(value)
            }
        }
        return duplicates
    }

    static func loadRecords(manifestPath: String) throws -> [BatchRunModelRecord] {
        guard FileManager.default.fileExists(atPath: manifestPath) else {
            throw MelixCLIError.runtime("Batch manifest was not found at \(manifestPath).")
        }
        let text = try String(contentsOfFile: manifestPath, encoding: .utf8)
        return try text
            .split(separator: "\n")
            .map(String.init)
            .filter { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false }
            .map { line in
                guard
                    let data = line.data(using: .utf8),
                    let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                else {
                    throw MelixCLIError.runtime("Invalid batch manifest JSON line in \(manifestPath).")
                }
                return BatchRunModelRecord(payload: payload)
            }
    }

    static func writeRecords(_ records: [BatchRunModelRecord], plan: BatchRunPlan) throws {
        try writeRecords(records, manifestPath: plan.manifestPath, outputRoot: plan.config.outputRoot)
    }

    static func writeRecords(_ records: [BatchRunModelRecord], manifestPath: String, outputRoot: String) throws {
        let manifestURL = URL(fileURLWithPath: manifestPath)
        try FileManager.default.createDirectory(at: manifestURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let text = try records.map { record in
            String(decoding: try JSONSerialization.data(withJSONObject: record.payload(), options: [.sortedKeys]), as: UTF8.self)
        }.joined(separator: "\n") + "\n"
        try text.write(to: manifestURL, atomically: true, encoding: .utf8)
        let trimmedOutputRoot = outputRoot.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedOutputRoot.isEmpty else {
            return
        }
        let outputURL = URL(fileURLWithPath: trimmedOutputRoot)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        try FileManager.default.copyItemReplacingExisting(
            at: manifestURL,
            to: outputURL.appendingPathComponent("manifest.jsonl")
        )
    }

    static func summarize(records: [BatchRunModelRecord], runID: String, tempRoot: String, outputRoot: String, manifestPath: String) -> BatchRunSummary {
        let succeeded = records.filter { $0.status == "succeeded" }.count
        let failed = records.filter { $0.status == "failed" }.count
        let partial = records.filter { $0.status == "partial_success" }.count
        let planned = records.filter { $0.status == "planned" || $0.status == "pending" }.count
        let running = records.filter { $0.status == "running" }.count
        let status: String
        if records.isEmpty {
            status = "empty"
        } else if failed == 0 && partial == 0 && running == 0 && planned == 0 {
            status = "succeeded"
        } else if succeeded > 0 || partial > 0 {
            status = failed > 0 || partial > 0 ? "partial_success" : "running"
        } else if failed > 0 {
            status = "failed"
        } else if running > 0 {
            status = "running"
        } else {
            status = "planned"
        }
        return .init(
            schemaVersion: "melix.batch.run_summary.v1",
            runID: runID,
            status: status,
            totalModels: records.count,
            succeededModels: succeeded,
            failedModels: failed,
            partialSuccessModels: partial,
            plannedModels: planned,
            runningModels: running,
            records: records,
            tempRoot: tempRoot,
            outputRoot: outputRoot,
            manifestPath: manifestPath
        )
    }

    static func modelDir(plan: BatchRunPlan, model: BatchRunModelEntry) -> URL {
        URL(fileURLWithPath: plan.config.outputRoot)
            .appendingPathComponent(BatchRunSlug.modelSlug(model: model), isDirectory: true)
    }

    static func modelTempDir(plan: BatchRunPlan, model: BatchRunModelEntry) -> URL {
        URL(fileURLWithPath: plan.config.tempRoot)
            .appendingPathComponent("models", isDirectory: true)
            .appendingPathComponent(BatchRunSlug.modelSlug(model: model), isDirectory: true)
    }
}

enum BatchRunReporter {
    static func writeReports(summary: BatchRunSummary) throws {
        let outputURL = URL(fileURLWithPath: summary.outputRoot)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        try jsonData(summary.payload()).write(
            to: outputURL.appendingPathComponent("run-summary.json"),
            options: .atomic
        )
        try csvText(summary: summary).write(
            to: outputURL.appendingPathComponent("run-summary.csv"),
            atomically: true,
            encoding: .utf8
        )
        try markdown(summary: summary).write(
            to: outputURL.appendingPathComponent("RUN_SUMMARY.md"),
            atomically: true,
            encoding: .utf8
        )
        try html(summary: summary).write(
            to: outputURL.appendingPathComponent("index.html"),
            atomically: true,
            encoding: .utf8
        )
    }

    static func renderStatusText(summary: BatchRunSummary) -> String {
        var lines: [String] = [
            "Melix batch status",
            "run_id=\(summary.runID)",
            "status=\(summary.status)",
            "models=\(summary.succeededModels) succeeded, \(summary.partialSuccessModels) partial, \(summary.failedModels) failed, \(summary.runningModels) running, \(summary.plannedModels) planned / \(summary.totalModels) total",
            "manifest=\(summary.manifestPath)",
            "output_root=\(summary.outputRoot)",
        ]
        for record in summary.records {
            var detail = "[\(record.modelIndex)] \(record.status) \(record.repoID)"
            if !record.failureCategory.isEmpty {
                detail += " failure=\(record.failureCategory)"
            }
            lines.append(detail)
        }
        return lines.joined(separator: "\n") + "\n"
    }

    static func renderRunText(summary: BatchRunSummary, progressLines: [String]) -> String {
        var lines = progressLines
        lines.append("Melix batch run complete")
        lines.append("run_id=\(summary.runID)")
        lines.append("status=\(summary.status)")
        lines.append("models=\(summary.succeededModels) succeeded, \(summary.partialSuccessModels) partial, \(summary.failedModels) failed / \(summary.totalModels) total")
        lines.append("manifest=\(summary.manifestPath)")
        lines.append("summary=\(URL(fileURLWithPath: summary.outputRoot).appendingPathComponent("RUN_SUMMARY.md").path)")
        lines.append("json_summary=\(URL(fileURLWithPath: summary.outputRoot).appendingPathComponent("run-summary.json").path)")
        return lines.joined(separator: "\n") + "\n"
    }

    private static func markdown(summary: BatchRunSummary) -> String {
        var lines: [String] = [
            "# Melix Batch Run Summary",
            "",
            "- Run ID: `\(summary.runID)`",
            "- Status: `\(summary.status)`",
            "- Totals: \(summary.succeededModels) succeeded, \(summary.partialSuccessModels) partial, \(summary.failedModels) failed, \(summary.runningModels) running, \(summary.plannedModels) planned / \(summary.totalModels) total",
            "- Manifest: `\(summary.manifestPath)`",
            "",
            "## Models",
            "",
            "| Index | Model | Status | Benchmark Job | Evaluation Job | Duration (s) | Failure |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
        for record in summary.records {
            lines.append("| \(escapeMarkdown(record.modelIndex)) | \(escapeMarkdown(record.repoID)) | \(record.status) | \(record.benchmarkJobID) | \(record.evaluationJobID) | \(String(format: "%.3f", record.durationSeconds)) | \(escapeMarkdown(record.failureCategory)) |")
        }
        let failures = summary.records.filter { !$0.failureCategory.isEmpty || !$0.failureMessage.isEmpty }
        if !failures.isEmpty {
            lines += ["", "## Failures", ""]
            for record in failures {
                lines.append("- `\(record.modelIndex)` \(record.repoID): \(record.failureCategory) \(record.failureMessage)")
            }
        }
        lines += [
            "",
            "## Artifacts",
            "",
            "- `manifest.jsonl`",
            "- `run-summary.json`",
            "- `run-summary.csv`",
            "- `index.html`",
        ]
        return lines.joined(separator: "\n") + "\n"
    }

    private static func html(summary: BatchRunSummary) -> String {
        let rows = summary.records.map { record in
            """
            <tr><td>\(htmlEscape(record.modelIndex))</td><td>\(htmlEscape(record.repoID))</td><td>\(htmlEscape(record.status))</td><td>\(htmlEscape(record.benchmarkJobID))</td><td>\(htmlEscape(record.evaluationJobID))</td><td>\(String(format: "%.3f", record.durationSeconds))</td><td>\(htmlEscape(record.failureCategory))</td></tr>
            """
        }.joined(separator: "\n")
        return """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <title>Melix Batch Run \(htmlEscape(summary.runID))</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #1f2328; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #d0d7de; padding: 6px 8px; text-align: left; }
            th { background: #f6f8fa; }
            code { background: #f6f8fa; padding: 1px 4px; border-radius: 4px; }
          </style>
        </head>
        <body>
          <h1>Melix Batch Run \(htmlEscape(summary.runID))</h1>
          <p>Status: <code>\(htmlEscape(summary.status))</code></p>
          <p>Totals: \(summary.succeededModels) succeeded, \(summary.partialSuccessModels) partial, \(summary.failedModels) failed / \(summary.totalModels) total.</p>
          <table>
            <thead><tr><th>Index</th><th>Model</th><th>Status</th><th>Benchmark Job</th><th>Evaluation Job</th><th>Duration</th><th>Failure</th></tr></thead>
            <tbody>
            \(rows)
            </tbody>
          </table>
        </body>
        </html>
        """
    }

    private static func csvText(summary: BatchRunSummary) -> String {
        var rows = ["run_id,model_index,repo_id,status,benchmark_job_id,evaluation_job_id,duration_seconds,failure_category,recoverability"]
        for record in summary.records {
            rows.append([
                summary.runID,
                record.modelIndex,
                record.repoID,
                record.status,
                record.benchmarkJobID,
                record.evaluationJobID,
                String(format: "%.6f", record.durationSeconds),
                record.failureCategory,
                record.recoverability,
            ].map(csvEscape).joined(separator: ","))
        }
        return rows.joined(separator: "\n") + "\n"
    }

    private static func jsonData(_ payload: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    }

    private static func csvEscape(_ value: String) -> String {
        if value.contains(",") || value.contains("\"") || value.contains("\n") {
            return "\"\(value.replacingOccurrences(of: "\"", with: "\"\""))\""
        }
        return value
    }

    private static func escapeMarkdown(_ value: String) -> String {
        value.replacingOccurrences(of: "|", with: "\\|")
    }

    private static func htmlEscape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }
}

enum BatchRunPayloadParser {
    static func object(from text: String) -> [String: Any] {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let data = trimmed.data(using: .utf8) else {
            return [:]
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    static func jobID(from payload: [String: Any]) -> String {
        for key in ["job_id", "jobID", "id", "run_id"] {
            if let value = payload[key] as? String, !value.isEmpty {
                return value
            }
        }
        if let job = payload["job"] as? [String: Any] {
            return jobID(from: job)
        }
        if let result = payload["result"] as? [String: Any] {
            return jobID(from: result)
        }
        return ""
    }

    static func artifactPaths(from payload: [String: Any]) -> [String] {
        var paths: [String] = []
        for key in ["output_dir", "artifact_dir", "artifact_path", "report_path", "path"] {
            if let value = payload[key] as? String, !value.isEmpty {
                paths.append(value)
            }
        }
        if let artifacts = payload["artifacts"] as? [[String: Any]] {
            paths += artifacts.compactMap { $0["path"] as? String }.filter { !$0.isEmpty }
        }
        if let result = payload["result"] as? [String: Any] {
            paths += artifactPaths(from: result)
        }
        return Array(Set(paths)).sorted()
    }

    static func metricValues(from payload: [String: Any]) -> [String: Double] {
        var values: [String: Double] = [:]
        for (key, value) in payload {
            if let metric = doubleValue(value) {
                values[key] = metric
            }
        }
        if let metrics = payload["metrics"] as? [String: Any] {
            for (key, value) in metricValues(from: metrics) {
                values[key] = value
            }
        }
        if let result = payload["result"] as? [String: Any] {
            for (key, value) in metricValues(from: result) {
                values[key] = value
            }
        }
        return values
    }

    static func doubleValue(_ value: Any?) -> Double? {
        if let double = value as? Double {
            return double
        }
        if let int = value as? Int {
            return Double(int)
        }
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let string = value as? String {
            return Double(string)
        }
        return nil
    }
}

struct BatchRunSubprocessResult {
    let stdout: String
    let stderr: String
    let exitCode: Int32
}

typealias BatchRunSubprocessExecutor = @Sendable ([String], [String: String], String) async -> BatchRunSubprocessResult

final class BatchRunExecutor {
    private let plan: BatchRunPlan
    private let commandExecutor: BatchRunSubprocessExecutor
    private let fileManager: FileManager

    init(
        plan: BatchRunPlan,
        commandExecutor: @escaping BatchRunSubprocessExecutor,
        fileManager: FileManager = .default
    ) {
        self.plan = plan
        self.commandExecutor = commandExecutor
        self.fileManager = fileManager
    }

    func execute(existingRecords: [BatchRunModelRecord]? = nil, resumeMode: BatchRunResumeMode = .none) async throws -> (summary: BatchRunSummary, progressLines: [String]) {
        try BatchRunArtifacts.writeFoundationArtifacts(plan: plan, writePlannedManifest: false)
        var records = BatchRunManifestStore.alignedRecords(plan: plan, existingRecords: existingRecords)
        try persist(records)
        var progress: [String] = [
            "Melix batch run",
            "run_id=\(plan.config.runID)",
            "models=\(plan.selectedModels.count)/\(plan.models.count)",
        ]
        let runStart = Date()

        for (offset, model) in plan.selectedModels.enumerated() {
            var record = records[offset]
            if resumeMode.shouldSkipModel(record) {
                progress.append("[\(offset + 1)/\(plan.selectedModels.count)] SKIP \(model.index) \(model.repoID) already succeeded")
                continue
            }
            progress.append("[\(offset + 1)/\(plan.selectedModels.count)] START \(model.index) \(model.repoID)")
            record.status = "running"
            record.startedAt = isoTimestamp()
            try persistRecord(record, in: &records)
            let modelStart = Date()
            do {
                try prepareDirectories(record: record)
                if !resumeMode.evalOnly {
                    try await runSyntheticStep(.preflight, record: &record, records: &records, message: "Per-model preflight accepted \(model.repoID).")
                    try await runSyntheticStep(.runtimePrepare, record: &record, records: &records, message: "Runtime uses \(plan.config.serviceInstanceName) on port \(plan.config.httpPort).")
                    try await runSyntheticStep(.modelUnload, record: &record, records: &records, message: "Best-effort previous model unload recorded.")
                    try await runHubCheck(record: &record, records: &records)
                    progress.append("[\(offset + 1)/\(plan.selectedModels.count)] benchmark start \(model.index)")
                    try await runBenchmark(record: &record, records: &records)
                    progress.append("[\(offset + 1)/\(plan.selectedModels.count)] benchmark succeeded \(model.index) job=\(record.benchmarkJobID)")
                } else {
                    markSkippedBeforeEval(record: &record)
                    try persistRecord(record, in: &records)
                    progress.append("[\(offset + 1)/\(plan.selectedModels.count)] resume eval-only \(model.index)")
                }
                progress.append("[\(offset + 1)/\(plan.selectedModels.count)] semantic judge heartbeat \(plan.config.judgeRemoteServerID)/\(plan.config.judgeModelID)")
                try await runEvaluation(record: &record, records: &records)
                progress.append("[\(offset + 1)/\(plan.selectedModels.count)] evaluation succeeded \(model.index) job=\(record.evaluationJobID)")
                try await runExports(record: &record, records: &records)
                try await copyRawArtifacts(record: &record, records: &records)
                record.status = record.benchmarkSucceeded ? "succeeded" : "partial_success"
                if record.status == "succeeded" {
                    record.failureCategory = ""
                    record.recoverability = ""
                    record.failureMessage = ""
                } else if record.failureCategory.isEmpty {
                    record.failureCategory = "unknown_failure"
                    record.recoverability = BatchRunFailureRecoverability.unknown.rawValue
                    record.failureMessage = "Evaluation completed, but benchmark did not succeed for this model."
                }
            } catch {
                applyFailure(error, record: &record)
                progress.append("[\(offset + 1)/\(plan.selectedModels.count)] FAILED \(model.index) \(record.failureCategory): \(record.failureMessage)")
                if !plan.config.continueOnFailure {
                    record.finishedAt = isoTimestamp()
                    record.durationSeconds = Date().timeIntervalSince(modelStart)
                    try persistRecord(record, in: &records)
                    throw error
                }
            }
            record.finishedAt = isoTimestamp()
            record.durationSeconds = Date().timeIntervalSince(modelStart)
            try persistRecord(record, in: &records)
            progress.append("[\(offset + 1)/\(plan.selectedModels.count)] DONE \(model.index) status=\(record.status) elapsed=\(formatDuration(record.durationSeconds))")
        }

        let summary = BatchRunManifestStore.summarize(
            records: records,
            runID: plan.config.runID,
            tempRoot: plan.config.tempRoot,
            outputRoot: plan.config.outputRoot,
            manifestPath: plan.manifestPath
        )
        try BatchRunReporter.writeReports(summary: summary)
        progress.append("elapsed=\(formatDuration(Date().timeIntervalSince(runStart)))")
        return (summary, progress)
    }

    private func persist(_ records: [BatchRunModelRecord]) throws {
        try BatchRunManifestStore.writeRecords(records, plan: plan)
    }

    private func persistRecord(_ record: BatchRunModelRecord, in records: inout [BatchRunModelRecord]) throws {
        if let index = records.firstIndex(where: { BatchRunRecordIdentity(record: $0) == BatchRunRecordIdentity(record: record) }) {
            records[index] = record
        }
        try persist(records)
    }

    private func prepareDirectories(record: BatchRunModelRecord) throws {
        try fileManager.createDirectory(atPath: record.modelDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(atPath: record.tempDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(atPath: URL(fileURLWithPath: record.modelDir).appendingPathComponent("exports", isDirectory: true).path, withIntermediateDirectories: true)
        try fileManager.createDirectory(atPath: URL(fileURLWithPath: record.modelDir).appendingPathComponent("commands", isDirectory: true).path, withIntermediateDirectories: true)
        try fileManager.createDirectory(atPath: URL(fileURLWithPath: record.modelDir).appendingPathComponent("raw", isDirectory: true).path, withIntermediateDirectories: true)
    }

    private func runSyntheticStep(_ step: BatchRunStepName, record: inout BatchRunModelRecord, records: inout [BatchRunModelRecord], message: String) async throws {
        let startedAt = isoTimestamp()
        let started = Date()
        record.steps[step.rawValue] = BatchRunStepRecord(
            status: "succeeded",
            startedAt: startedAt,
            finishedAt: isoTimestamp(),
            durationSeconds: Date().timeIntervalSince(started),
            message: message
        )
        try persistRecord(record, in: &records)
    }

    private func runHubCheck(record: inout BatchRunModelRecord, records: inout [BatchRunModelRecord]) async throws {
        let step = BatchRunStepName.hubCheck
        let startedAt = isoTimestamp()
        let started = Date()
        if !record.repoID.contains("/") {
            let classification = BatchRunFailureClassifier.classify(stderr: "repo id \(record.repoID) is not owner/name")
            record.steps[step.rawValue] = BatchRunStepRecord(
                status: "failed",
                startedAt: startedAt,
                finishedAt: isoTimestamp(),
                durationSeconds: Date().timeIntervalSince(started),
                failureCategory: classification.category,
                recoverability: classification.recoverability.rawValue,
                message: classification.reason
            )
            try persistRecord(record, in: &records)
            throw MelixCLIError.runtime(classification.reason)
        }
        record.steps[step.rawValue] = BatchRunStepRecord(
            status: "succeeded",
            startedAt: startedAt,
            finishedAt: isoTimestamp(),
            durationSeconds: Date().timeIntervalSince(started),
            message: "Repo id \(record.repoID) is owner/name-shaped."
        )
        try persistRecord(record, in: &records)
    }

    private func runBenchmark(record: inout BatchRunModelRecord, records: inout [BatchRunModelRecord]) async throws {
        let exportsDir = URL(fileURLWithPath: record.modelDir).appendingPathComponent("exports", isDirectory: true)
        let arguments = [
            "bench", "run",
            "--repo-id", record.repoID,
            "--suite", plan.config.benchSuite,
            "--context-length", "\(plan.config.benchContextLength)",
            "--generation-length", "\(plan.config.benchGenerationLength)",
            "--batch-size", "\(plan.config.benchBatchSize)",
            "--repeats", "\(plan.config.benchRepeats)",
            "--sample-size", "\(plan.config.benchSampleSize)",
            "--batch-factor", "\(plan.config.benchBatchFactor)",
            "--json",
        ]
        let result = try await runCommand(step: .benchmark, arguments: arguments, record: &record, records: &records)
        let payload = BatchRunPayloadParser.object(from: result.stdout)
        record.benchmarkJobID = BatchRunPayloadParser.jobID(from: payload)
        record.metricFields.merge(BatchRunPayloadParser.metricValues(from: payload), uniquingKeysWith: { _, new in new })
        record.rawArtifactPaths += BatchRunPayloadParser.artifactPaths(from: payload)
        guard !record.benchmarkJobID.isEmpty else {
            throw MelixCLIError.runtime("bench run did not return job_id; cannot export benchmark CSV.")
        }
        let csvPath = exportsDir.appendingPathComponent("benchmark.csv").path
        _ = try await runCommand(
            step: .exports,
            arguments: ["bench", "export-csv", "--job-id", record.benchmarkJobID, "--output", csvPath, "--json"],
            record: &record,
            records: &records,
            appendStep: true
        )
        record.benchmarkCSVPath = csvPath
        try persistRecord(record, in: &records)
    }

    private func runEvaluation(record: inout BatchRunModelRecord, records: inout [BatchRunModelRecord]) async throws {
        let arguments = [
            "eval", "run",
            "--repo-id", record.repoID,
            "--semantic-judge-remote-server-id", plan.config.judgeRemoteServerID,
            "--semantic-judge-model", plan.config.judgeModelID,
            "--suite", plan.config.evalSuite,
            "--dataset-id", plan.config.evalDatasetID,
            "--scoring-mode", plan.config.evalScoringMode,
            "--sample-size", "\(plan.config.evalSampleSize)",
            "--batch-factor", "\(plan.config.evalBatchFactor)",
            "--json",
        ]
        let result = try await runCommand(step: .evaluation, arguments: arguments, record: &record, records: &records)
        let payload = BatchRunPayloadParser.object(from: result.stdout)
        record.evaluationJobID = BatchRunPayloadParser.jobID(from: payload)
        record.metricFields.merge(BatchRunPayloadParser.metricValues(from: payload), uniquingKeysWith: { _, new in new })
        record.rawArtifactPaths += BatchRunPayloadParser.artifactPaths(from: payload)
        guard !record.evaluationJobID.isEmpty else {
            throw MelixCLIError.runtime("eval run did not return job_id; cannot export evaluation artifacts.")
        }
        try persistRecord(record, in: &records)
    }

    private func runExports(record: inout BatchRunModelRecord, records: inout [BatchRunModelRecord]) async throws {
        guard !record.evaluationJobID.isEmpty else {
            return
        }
        let exportsDir = URL(fileURLWithPath: record.modelDir).appendingPathComponent("exports", isDirectory: true)
        let summaryCSV = exportsDir.appendingPathComponent("evaluation-summary.csv").path
        let samplesCSV = exportsDir.appendingPathComponent("evaluation-samples.csv").path
        let samplesJSONL = exportsDir.appendingPathComponent("evaluation-samples.jsonl").path
        _ = try await runCommand(
            step: .exports,
            arguments: ["eval", "export-summary-csv", "--job-id", record.evaluationJobID, "--output", summaryCSV, "--json"],
            record: &record,
            records: &records,
            appendStep: true
        )
        _ = try await runCommand(
            step: .exports,
            arguments: ["eval", "export-samples-csv", "--job-id", record.evaluationJobID, "--output", samplesCSV, "--json"],
            record: &record,
            records: &records,
            appendStep: true
        )
        _ = try await runCommand(
            step: .exports,
            arguments: ["eval", "export-samples-jsonl", "--job-id", record.evaluationJobID, "--output", samplesJSONL, "--json"],
            record: &record,
            records: &records,
            appendStep: true
        )
        record.evaluationSummaryCSVPath = summaryCSV
        record.evaluationSamplesCSVPath = samplesCSV
        record.evaluationSamplesJSONLPath = samplesJSONL
        try persistRecord(record, in: &records)
    }

    private func copyRawArtifacts(record: inout BatchRunModelRecord, records: inout [BatchRunModelRecord]) async throws {
        let step = BatchRunStepName.artifactCopy
        let started = Date()
        let rawDir = URL(fileURLWithPath: record.modelDir).appendingPathComponent("raw", isDirectory: true)
        var copied: [String] = []
        for path in Array(Set(record.rawArtifactPaths)).sorted() {
            guard fileManager.fileExists(atPath: path) else {
                continue
            }
            let sourceURL = URL(fileURLWithPath: path)
            let destinationURL = rawDir.appendingPathComponent(sourceURL.lastPathComponent)
            do {
                if directoryExists(path) {
                    try fileManager.copyItemReplacingExisting(at: sourceURL, to: destinationURL)
                } else {
                    try fileManager.copyItemReplacingExisting(at: sourceURL, to: destinationURL)
                }
                copied.append(destinationURL.path)
            } catch {
                let classification = BatchRunFailureClassifier.classify(stderr: "artifact copy failed: \(error.localizedDescription)")
                record.steps[step.rawValue] = BatchRunStepRecord(
                    status: "failed",
                    artifactPath: rawDir.path,
                    startedAt: isoTimestamp(),
                    finishedAt: isoTimestamp(),
                    durationSeconds: Date().timeIntervalSince(started),
                    failureCategory: classification.category,
                    recoverability: classification.recoverability.rawValue,
                    message: error.localizedDescription
                )
                try persistRecord(record, in: &records)
                throw error
            }
        }
        record.rawArtifactPaths = copied
        record.steps[step.rawValue] = BatchRunStepRecord(
            status: "succeeded",
            artifactPath: rawDir.path,
            startedAt: isoTimestamp(),
            finishedAt: isoTimestamp(),
            durationSeconds: Date().timeIntervalSince(started),
            message: "Copied \(copied.count) raw artifact path(s)."
        )
        try persistRecord(record, in: &records)
    }

    private func runCommand(
        step: BatchRunStepName,
        arguments: [String],
        record: inout BatchRunModelRecord,
        records: inout [BatchRunModelRecord],
        appendStep: Bool = false
    ) async throws -> BatchRunSubprocessResult {
        let started = Date()
        let startedAt = isoTimestamp()
        let commandIndex = commandCount(record: record, step: step) + 1
        let receiptBase = URL(fileURLWithPath: record.modelDir)
            .appendingPathComponent("commands", isDirectory: true)
            .appendingPathComponent("\(step.rawValue)-\(commandIndex)")
        let stdoutPath = receiptBase.path + ".stdout"
        let stderrPath = receiptBase.path + ".stderr"
        let receiptPath = receiptBase.path + ".json"
        var runningStep = record.steps[step.rawValue] ?? BatchRunStepRecord()
        runningStep.status = "running"
        runningStep.startedAt = startedAt
        runningStep.stdoutPath = stdoutPath
        runningStep.stderrPath = stderrPath
        runningStep.artifactPath = receiptPath
        record.steps[step.rawValue] = runningStep
        try persistRecord(record, in: &records)

        let result = await commandExecutor(arguments, commandEnvironment(record: record), record.tempDir)
        try result.stdout.write(toFile: stdoutPath, atomically: true, encoding: .utf8)
        try result.stderr.write(toFile: stderrPath, atomically: true, encoding: .utf8)
        let duration = Date().timeIntervalSince(started)
        let receipt: [String: Any] = [
            "schema_version": "melix.batch.command_receipt.v1",
            "step": step.rawValue,
            "arguments": arguments,
            "exit_code": NSNumber(value: result.exitCode),
            "stdout_path": stdoutPath,
            "stderr_path": stderrPath,
            "duration_seconds": duration,
            "started_at": startedAt,
            "finished_at": isoTimestamp(),
        ]
        try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])
            .write(to: URL(fileURLWithPath: receiptPath), options: .atomic)
        if result.exitCode != 0 {
            let classification = BatchRunFailureClassifier.classify(stdout: result.stdout, stderr: result.stderr)
            let failureMessage = MelixCLIProcessFailureMessage.make(stdout: result.stdout, stderr: result.stderr, exitCode: result.exitCode)
            record.steps[step.rawValue] = BatchRunStepRecord(
                status: "failed",
                stdoutPath: stdoutPath,
                stderrPath: stderrPath,
                artifactPath: receiptPath,
                startedAt: startedAt,
                finishedAt: isoTimestamp(),
                durationSeconds: duration,
                failureCategory: classification.category,
                recoverability: classification.recoverability.rawValue,
                message: failureMessage
            )
            try persistRecord(record, in: &records)
            throw MelixCLIError.runtime(failureMessage)
        }
        let existingMessage = appendStep ? (record.steps[step.rawValue]?.message ?? "") : ""
        var message = appendStep && !existingMessage.isEmpty
            ? existingMessage + "; completed \(arguments.prefix(2).joined(separator: " "))"
            : "completed \(arguments.prefix(2).joined(separator: " "))"
        if !result.stderr.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            message += "; stderr captured"
        }
        var completed = BatchRunStepRecord(
            status: "succeeded",
            stdoutPath: stdoutPath,
            stderrPath: stderrPath,
            artifactPath: receiptPath,
            startedAt: startedAt,
            finishedAt: isoTimestamp(),
            durationSeconds: duration,
            message: message
        )
        if step == .benchmark {
            completed.jobID = BatchRunPayloadParser.jobID(from: BatchRunPayloadParser.object(from: result.stdout))
        }
        if step == .evaluation {
            completed.jobID = BatchRunPayloadParser.jobID(from: BatchRunPayloadParser.object(from: result.stdout))
        }
        record.steps[step.rawValue] = completed
        try persistRecord(record, in: &records)
        return result
    }

    private func commandEnvironment(record: BatchRunModelRecord) -> [String: String] {
        [
            "MELIX_HOME": plan.config.melixHome,
            "MELIX_RUNTIME_DIR": plan.config.runtimeDir,
            "MELIX_HTTP_PORT": plan.config.httpPort,
            "MELIX_SERVICE_INSTANCE_NAME": plan.config.serviceInstanceName,
            "MELIX_BATCH_RUN_ID": plan.config.runID,
            "MELIX_BATCH_MODEL_INDEX": record.modelIndex,
            "MELIX_BATCH_MODEL_REPO_ID": record.repoID,
            "MELIX_BATCH_MODEL_DIR": record.modelDir,
            "MELIX_BATCH_MODEL_TEMP_DIR": record.tempDir,
        ]
    }

    private func markSkippedBeforeEval(record: inout BatchRunModelRecord) {
        for step in [BatchRunStepName.preflight, .runtimePrepare, .modelUnload, .hubCheck, .benchmark] {
            if record.steps[step.rawValue]?.status == "succeeded" {
                continue
            }
            record.steps[step.rawValue] = BatchRunStepRecord(status: "skipped", message: "Skipped by eval-only resume.")
        }
    }

    private func applyFailure(_ error: Error, record: inout BatchRunModelRecord) {
        let message = error.localizedDescription
        let classification = BatchRunFailureClassifier.classify(stderr: message)
        record.status = record.benchmarkSucceeded || record.evaluationSucceeded ? "partial_success" : "failed"
        record.failureCategory = classification.category
        record.recoverability = classification.recoverability.rawValue
        record.failureMessage = message
        if BatchRunFailureClassifier.runtimeFailureRequiresCleanStack(classification) {
            record.steps[BatchRunStepName.runtimePrepare.rawValue]?.message = "Clean stack required before the next model: \(classification.reason)"
        }
    }

    private func commandCount(record: BatchRunModelRecord, step: BatchRunStepName) -> Int {
        let commands = URL(fileURLWithPath: record.modelDir).appendingPathComponent("commands", isDirectory: true)
        let names = (try? fileManager.contentsOfDirectory(atPath: commands.path)) ?? []
        return names.filter { $0.hasPrefix(step.rawValue + "-") && $0.hasSuffix(".json") }.count
    }

    private func directoryExists(_ path: String) -> Bool {
        var isDirectory = ObjCBool(false)
        return fileManager.fileExists(atPath: path, isDirectory: &isDirectory) && isDirectory.boolValue
    }

    private func isoTimestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    private func formatDuration(_ seconds: Double) -> String {
        String(format: "%.1fs", seconds)
    }
}

struct BatchRunResumeMode {
    let evalOnly: Bool
    let missingOnly: Bool

    static let none = BatchRunResumeMode(evalOnly: false, missingOnly: false)

    func shouldSkipModel(_ record: BatchRunModelRecord) -> Bool {
        if !missingOnly {
            return false
        }
        if evalOnly {
            return record.evaluationSucceeded
        }
        return record.completedSuccessfully
    }
}

enum BatchRunResumePlanner {
    static func makePlan(options: BatchResumeOptions, environment: [String: String]) throws -> (BatchRunPlan, [BatchRunModelRecord]) {
        let resolution = try BatchRunStatusResolver.resolve(
            runID: options.runID,
            tempRoot: options.tempRoot,
            outputRoot: options.outputRoot,
            environment: environment
        )
        let records = try BatchRunManifestStore.loadRecords(manifestPath: resolution.manifestPath)
        guard records.isEmpty == false else {
            throw MelixCLIError.runtime("Batch manifest \(resolution.manifestPath) has no model records.")
        }
        let effective = loadEffectiveConfig(resolution: resolution)
        let benchmark = effective["benchmark"] as? [String: Any] ?? [:]
        let evaluation = effective["evaluation"] as? [String: Any] ?? [:]
        let judge = effective["judge"] as? [String: Any] ?? [:]
        let recoveredExplicitOptions: Set<String> = effective.isEmpty ? ["--continue-on-failure"] : [
            "--continue-on-failure",
            "--restart-stack-per-model",
            "--judge-remote-server-id",
            "--judge-model",
            "--bench-suite",
            "--bench-context-length",
            "--bench-generation-length",
            "--bench-batch-size",
            "--bench-repeats",
            "--bench-sample-size",
            "--bench-batch-factor",
            "--eval-suite",
            "--eval-dataset-id",
            "--eval-scoring-mode",
            "--eval-sample-size",
            "--eval-batch-factor",
        ]
        let modelListPath = options.modelListPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? try writeRecoveredModelList(records: records, resolution: resolution)
            : options.modelListPath
        let runOptions = BatchRunOptions(
            modelListPath: modelListPath,
            configPath: options.configPath,
            runID: resolution.runID,
            outputRoot: resolution.outputRoot,
            tempRoot: resolution.tempRoot.isEmpty ? URL(fileURLWithPath: resolution.manifestPath).deletingLastPathComponent().path : resolution.tempRoot,
            judgeRemoteServerID: stringValue(judge["remote_server_id"]),
            judgeModelID: stringValue(judge["model"]),
            benchSuite: stringValue(benchmark["suite"]),
            benchContextLength: uint32Value(benchmark["context_length"]),
            benchGenerationLength: uint32Value(benchmark["generation_length"]),
            benchBatchSize: uint32Value(benchmark["batch_size"]),
            benchRepeats: uint32Value(benchmark["repeats"]),
            benchSampleSize: uint32Value(benchmark["sample_size"]),
            benchBatchFactor: uint32Value(benchmark["batch_factor"]),
            evalSuite: stringValue(evaluation["suite"]),
            evalDatasetID: stringValue(evaluation["dataset_id"]),
            evalScoringMode: stringValue(evaluation["scoring_mode"]),
            evalSampleSize: uint32Value(evaluation["sample_size"]),
            evalBatchFactor: uint32Value(evaluation["batch_factor"]),
            continueOnFailure: options.continueOnFailure,
            restartStackPerModel: boolValue(effective["restart_stack_per_model"], defaultValue: true),
            dryRun: options.dryRun,
            json: options.json,
            explicitOptions: recoveredExplicitOptions
        )
        return (try BatchRunPlanner.makePlan(options: runOptions, environment: environment), records)
    }

    static func renderDryRun(plan: BatchRunPlan, records: [BatchRunModelRecord], mode: BatchRunResumeMode, json: Bool) throws -> String {
        let selected = records.filter { !mode.shouldSkipModel($0) }
        let payload: [String: Any] = [
            "schema_version": "melix.batch.resume_plan.v1",
            "run_id": plan.config.runID,
            "mode": mode.evalOnly ? "eval_only" : "full",
            "missing_only": mode.missingOnly,
            "model_count": selected.count,
            "models": selected.map {
                [
                    "model_index": $0.modelIndex,
                    "repo_id": $0.repoID,
                    "status": $0.status,
                    "benchmark_status": $0.steps[BatchRunStepName.benchmark.rawValue]?.status ?? "pending",
                    "evaluation_status": $0.steps[BatchRunStepName.evaluation.rawValue]?.status ?? "pending",
                ]
            },
        ]
        if json {
            return String(decoding: try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]), as: UTF8.self) + "\n"
        }
        var lines = [
            "Melix batch resume dry-run",
            "run_id=\(plan.config.runID)",
            "mode=\(mode.evalOnly ? "eval_only" : "full")",
            "models=\(selected.count)",
        ]
        for record in selected {
            lines.append("RESUME \(record.modelIndex) \(record.repoID) status=\(record.status)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private static func writeRecoveredModelList(records: [BatchRunModelRecord], resolution: BatchRunStatusResolution) throws -> String {
        let root = resolution.tempRoot.isEmpty
            ? URL(fileURLWithPath: resolution.manifestPath).deletingLastPathComponent()
            : URL(fileURLWithPath: resolution.tempRoot)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let path = root.appendingPathComponent("resume-models.txt")
        var lines: [String] = []
        for record in records {
            let targetLine = record.sourceLine > 0
                ? max(record.sourceLine, lines.count + 1)
                : lines.count + 1
            while lines.count + 1 < targetLine {
                lines.append("")
            }
            lines.append("\(record.modelIndex)|\(record.repoID)")
        }
        let text = lines.joined(separator: "\n") + "\n"
        try text.write(to: path, atomically: true, encoding: .utf8)
        return path.path
    }

    private static func loadEffectiveConfig(resolution: BatchRunStatusResolution) -> [String: Any] {
        let candidates = [
            resolution.tempRoot.isEmpty ? "" : URL(fileURLWithPath: resolution.tempRoot).appendingPathComponent("effective-config.json").path,
            resolution.outputRoot.isEmpty ? "" : URL(fileURLWithPath: resolution.outputRoot).appendingPathComponent("effective-config.json").path,
        ].filter { !$0.isEmpty }
        for path in candidates {
            guard
                let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
                let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else {
                continue
            }
            return payload
        }
        return [:]
    }

    private static func stringValue(_ value: Any?) -> String {
        value as? String ?? ""
    }

    private static func uint32Value(_ value: Any?) -> UInt32 {
        if let number = value as? NSNumber {
            return number.uint32Value
        }
        if let int = value as? Int {
            return UInt32(max(0, int))
        }
        if let string = value as? String, let parsed = UInt32(string) {
            return parsed
        }
        return 0
    }

    private static func boolValue(_ value: Any?, defaultValue: Bool) -> Bool {
        if let bool = value as? Bool {
            return bool
        }
        if let string = value as? String {
            switch string.lowercased() {
            case "1", "true", "yes", "y":
                return true
            case "0", "false", "no", "n":
                return false
            default:
                return defaultValue
            }
        }
        return defaultValue
    }
}

enum BatchRunSlug {
    static func modelSlug(model: BatchRunModelEntry) -> String {
        modelSlug(index: model.index, repoID: model.repoID, sourceLine: model.sourceLine)
    }

    static func modelSlug(index: String, repoID: String, sourceLine: Int) -> String {
        modelSlug(raw: "\(index)-line-\(sourceLine)-\(repoID)")
    }

    static func modelSlug(index: String, repoID: String) -> String {
        modelSlug(raw: "\(index)-\(repoID)")
    }

    private static func modelSlug(raw: String) -> String {
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
