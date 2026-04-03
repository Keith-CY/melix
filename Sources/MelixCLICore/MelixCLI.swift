import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public struct LoraListOptions: Equatable, Sendable {
    public let modelID: String
    public let json: Bool

    public init(modelID: String = "", json: Bool = false) {
        self.modelID = modelID
        self.json = json
    }
}

public struct LoraTrainOptions: Equatable, Sendable {
    public let modelID: String
    public let datasetSourceKind: String
    public let datasetURI: String
    public let adapterName: String
    public let targetRepo: String
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String,
        datasetSourceKind: String = "local_package",
        datasetURI: String,
        adapterName: String,
        targetRepo: String = "",
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.datasetSourceKind = datasetSourceKind
        self.datasetURI = datasetURI
        self.adapterName = adapterName
        self.targetRepo = targetRepo
        self.parameters = parameters
        self.json = json
    }
}

public struct LoraActivateOptions: Equatable, Sendable {
    public let modelID: String
    public let adapterPath: String
    public let derivedModelAlias: String
    public let json: Bool

    public init(
        modelID: String,
        adapterPath: String,
        derivedModelAlias: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.adapterPath = adapterPath
        self.derivedModelAlias = derivedModelAlias
        self.json = json
    }
}

public struct BenchRunOptions: Equatable, Sendable {
    public let modelID: String
    public let hfRepoID: String
    public let suites: [String]
    public let contextLengths: [UInt32]
    public let generationLength: UInt32
    public let batchSizes: [UInt32]
    public let repeats: UInt32
    public let cacheProfile: String
    public let reasoningMode: String
    public let structuredOutputMode: String
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String = "",
        hfRepoID: String = "",
        suites: [String] = [],
        contextLengths: [UInt32] = [],
        generationLength: UInt32 = 0,
        batchSizes: [UInt32] = [],
        repeats: UInt32 = 1,
        cacheProfile: String = "",
        reasoningMode: String = "",
        structuredOutputMode: String = "",
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.suites = suites
        self.contextLengths = ControlPlaneBenchRequest.normalizedBenchValues(contextLengths)
        self.generationLength = generationLength
        self.batchSizes = ControlPlaneBenchRequest.normalizedBenchValues(batchSizes)
        self.repeats = repeats == 0 ? 1 : repeats
        self.cacheProfile = cacheProfile
        self.reasoningMode = reasoningMode
        self.structuredOutputMode = structuredOutputMode
        self.parameters = parameters
        self.json = json
    }
}

public struct BenchListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct BenchMatrixRunOptions: Equatable, Sendable {
    public let modelID: String
    public let hfRepoID: String
    public let taskKind: String
    public let suites: [String]
    public let contextLengths: [UInt32]
    public let generationLengths: [UInt32]
    public let batchSizes: [UInt32]
    public let cacheProfiles: [String]
    public let reasoningModes: [String]
    public let structuredOutputModes: [String]
    public let concurrencyLevels: [UInt32]
    public let repeats: UInt32
    public let requests: UInt32
    public let durationSeconds: UInt32
    public let allowLargeMatrix: Bool
    public let json: Bool

    public init(
        modelID: String = "",
        hfRepoID: String = "",
        taskKind: String = "",
        suites: [String] = [],
        contextLengths: [UInt32] = [],
        generationLengths: [UInt32] = [],
        batchSizes: [UInt32] = [],
        cacheProfiles: [String] = [],
        reasoningModes: [String] = [],
        structuredOutputModes: [String] = [],
        concurrencyLevels: [UInt32] = [],
        repeats: UInt32 = 1,
        requests: UInt32 = 0,
        durationSeconds: UInt32 = 0,
        allowLargeMatrix: Bool = false,
        json: Bool = false
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.taskKind = taskKind
        self.suites = Array(Set(suites)).sorted()
        self.contextLengths = ControlPlaneBenchRequest.normalizedBenchValues(contextLengths)
        self.generationLengths = ControlPlaneBenchRequest.normalizedBenchValues(generationLengths)
        self.batchSizes = ControlPlaneBenchRequest.normalizedBenchValues(batchSizes)
        self.cacheProfiles = ControlPlaneBenchMatrixRequest.normalizedStringValues(cacheProfiles)
        self.reasoningModes = ControlPlaneBenchMatrixRequest.normalizedStringValues(reasoningModes)
        self.structuredOutputModes = ControlPlaneBenchMatrixRequest.normalizedStringValues(structuredOutputModes)
        self.concurrencyLevels = ControlPlaneBenchRequest.normalizedBenchValues(concurrencyLevels)
        self.repeats = repeats == 0 ? 1 : repeats
        self.requests = requests
        self.durationSeconds = durationSeconds
        self.allowLargeMatrix = allowLargeMatrix
        self.json = json
    }
}

public struct BenchMatrixListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct BenchExportCSVOptions: Equatable, Sendable {
    public let jobID: String
    public let outputPath: String
    public let json: Bool

    public init(jobID: String, outputPath: String, json: Bool = false) {
        self.jobID = jobID
        self.outputPath = outputPath
        self.json = json
    }
}

public struct EvalRunOptions: Equatable, Sendable {
    public let modelID: String
    public let hfRepoID: String
    public let suites: [String]
    public let datasetID: String
    public let sampleSize: UInt32
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String = "",
        hfRepoID: String = "",
        suites: [String] = [],
        datasetID: String = "",
        sampleSize: UInt32 = 0,
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.suites = suites
        self.datasetID = datasetID
        self.sampleSize = sampleSize
        self.parameters = parameters
        self.json = json
    }
}

public struct EvalListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct EvalExportOptions: Equatable, Sendable {
    public let jobID: String
    public let outputPath: String
    public let json: Bool

    public init(jobID: String, outputPath: String, json: Bool = false) {
        self.jobID = jobID
        self.outputPath = outputPath
        self.json = json
    }
}

public enum MelixCLICommand: Equatable, Sendable {
    case loraList(LoraListOptions)
    case loraTrain(LoraTrainOptions)
    case loraActivate(LoraActivateOptions)
    case benchRun(BenchRunOptions)
    case benchList(BenchListOptions)
    case benchExportCSV(BenchExportCSVOptions)
    case benchMatrixRun(BenchMatrixRunOptions)
    case benchMatrixList(BenchMatrixListOptions)
    case benchMatrixExportSummaryCSV(BenchExportCSVOptions)
    case benchMatrixExportRequestsCSV(BenchExportCSVOptions)
    case evalRun(EvalRunOptions)
    case evalList(EvalListOptions)
    case evalExportSummaryCSV(EvalExportOptions)
    case evalExportSamplesCSV(EvalExportOptions)
    case evalExportSamplesJSONL(EvalExportOptions)
}

public enum MelixCLIError: Error, LocalizedError, Equatable, Sendable {
    case usage(String)
    case missingValue(String)
    case missingRequired(String)
    case runtime(String)

    public var errorDescription: String? {
        switch self {
        case .usage(let message):
            return message
        case .missingValue(let option):
            return "Missing value for \(option)."
        case .missingRequired(let message):
            return message
        case .runtime(let message):
            return message
        }
    }
}

public enum MelixCLIParser {
    public static func parse(_ arguments: [String]) throws -> MelixCLICommand {
        guard let group = arguments.first else {
            throw MelixCLIError.usage(Self.usageText)
        }
        let tail = Array(arguments.dropFirst())
        switch group {
        case "lora":
            return try parseLora(tail)
        case "bench":
            return try parseBench(tail)
        case "eval":
            return try parseEval(tail)
        default:
            throw MelixCLIError.usage(Self.usageText)
        }
    }

    public static let usageText = """
    Usage:
      melix lora list [--model-id MODEL_ID] [--json]
      melix lora train --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) --adapter-name NAME [--target-repo REPO] [--rank N] [--alpha N] [--dropout N] [--target-modules CSV] [--num-layers N] [--batch-size N] [--epochs N] [--learning-rate N] [--max-seq-length N] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-train-split SPLIT] [--hf-valid-split SPLIT] [--text-feature NAME] [--prompt-feature NAME] [--completion-feature NAME] [--chat-feature NAME] [--derived-model-alias NAME] [--response-only] [--mask-prompt] [--gradient-checkpointing] [--json]
      melix lora activate --model-id MODEL_ID --adapter-path PATH [--alias NAME] [--json]
      melix bench run (--model-id MODEL_ID | --repo-id HF_REPO) [--suite SUITE ...] [--context-length N ...] [--generation-length N] [--batch-size N ...] [--repeats N] [--cache-profile MODE] [--reasoning-mode MODE] [--structured-output-mode MODE] [--sample-size N] [--batch-factor N] [--json]
      melix bench list [--json]
      melix bench export-csv --job-id JOB_ID --output PATH [--json]
      melix bench matrix run (--model-id MODEL_ID | --repo-id HF_REPO) --suite SUITE ... --context-length N ... --generation-length N ... --batch-size N ... --cache-profile MODE ... --reasoning-mode MODE ... --structured-output-mode MODE ... --concurrency N ... [--repeats N] (--requests N | --duration-seconds N) [--allow-large-matrix] [--json]
      melix bench matrix list [--json]
      melix bench matrix export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix bench matrix export-requests-csv --job-id JOB_ID --output PATH [--json]
      melix eval run (--model-id MODEL_ID | --repo-id HF_REPO) [--suite SUITE ...] [--dataset-id DATASET_ID] [--sample-size N] [--batch-factor N] [--seed N] [--few-shot N] [--json]
      melix eval list [--json]
      melix eval export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix eval export-samples-csv --job-id JOB_ID --output PATH [--json]
      melix eval export-samples-jsonl --job-id JOB_ID --output PATH [--json]
    """

    private static func parseLora(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let cursor = ArgumentCursor(arguments: Array(arguments.dropFirst()))
        switch action {
        case "list":
            let values = try cursor.parse()
            return .loraList(
                LoraListOptions(
                    modelID: values.single["--model-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "train":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora train.")
            }
            let datasetURI = values.single["--dataset-uri"] ?? ""
            let hfDatasetPath = values.single["--hf-dataset-path"] ?? ""
            guard !datasetURI.isEmpty || !hfDatasetPath.isEmpty else {
                throw MelixCLIError.missingRequired("Either --dataset-uri or --hf-dataset-path is required for melix lora train.")
            }
            guard let adapterName = values.single["--adapter-name"], !adapterName.isEmpty else {
                throw MelixCLIError.missingRequired("--adapter-name is required for melix lora train.")
            }
            let datasetSourceKind = datasetURI.isEmpty ? "hf_dataset" : "local_package"
            var parameters: [String: String] = [:]
            for option in [
                "--rank",
                "--alpha",
                "--dropout",
                "--target-modules",
                "--num-layers",
                "--batch-size",
                "--epochs",
                "--learning-rate",
                "--max-seq-length",
                "--hf-dataset-path",
                "--hf-dataset-name",
                "--hf-dataset-revision",
                "--hf-train-split",
                "--hf-valid-split",
                "--chat-feature",
                "--prompt-feature",
                "--completion-feature",
                "--text-feature",
                "--derived-model-alias",
            ] {
                if let value = values.single[option] {
                    parameters[normalizedParameterKey(option)] = value
                }
            }
            for flag in ["--response-only", "--mask-prompt", "--gradient-checkpointing"] where values.flags.contains(flag) {
                parameters[normalizedParameterKey(flag)] = "true"
            }
            return .loraTrain(
                LoraTrainOptions(
                    modelID: modelID,
                    datasetSourceKind: datasetSourceKind,
                    datasetURI: datasetURI,
                    adapterName: adapterName,
                    targetRepo: values.single["--target-repo"] ?? "",
                    parameters: parameters,
                    json: values.flags.contains("--json")
                )
            )
        case "activate":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora activate.")
            }
            guard let adapterPath = values.single["--adapter-path"], !adapterPath.isEmpty else {
                throw MelixCLIError.missingRequired("--adapter-path is required for melix lora activate.")
            }
            return .loraActivate(
                LoraActivateOptions(
                    modelID: modelID,
                    adapterPath: adapterPath,
                    derivedModelAlias: values.single["--alias"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseBench(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        if action == "matrix" {
            return try parseBenchMatrix(Array(arguments.dropFirst()))
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
            multiValueOptions: ["--suite", "--context-length", "--batch-size"]
        )
        switch action {
        case "run":
            let modelID = values.single["--model-id"] ?? ""
            let hfRepoID = values.single["--repo-id"] ?? ""
            let explicitTargetCount = [modelID, hfRepoID].filter { !$0.isEmpty }.count
            guard explicitTargetCount == 1 else {
                throw MelixCLIError.missingRequired("Exactly one of --model-id or --repo-id is required for melix bench run.")
            }
            let contextLengths = try parseUInt32List(values.multi["--context-length"] ?? [], option: "--context-length")
            let generationLength = try parseUInt32Value(values.single["--generation-length"], option: "--generation-length") ?? 0
            let batchSizes = try parseUInt32List(values.multi["--batch-size"] ?? [], option: "--batch-size")
            let repeats = try parseUInt32Value(values.single["--repeats"], option: "--repeats", defaultValue: 1) ?? 1
            let cacheProfile = values.single["--cache-profile"] ?? ""
            guard cacheProfile.isEmpty || ControlPlaneBenchRequest.validCacheProfiles.contains(cacheProfile) else {
                throw MelixCLIError.usage("Invalid value for --cache-profile. Expected one of: \(ControlPlaneBenchRequest.validCacheProfiles.joined(separator: ", ")).")
            }
            let reasoningMode = values.single["--reasoning-mode"] ?? ""
            let structuredOutputMode = values.single["--structured-output-mode"] ?? ""
            var parameters: [String: String] = [:]
            if let sampleSize = values.single["--sample-size"] {
                parameters["sample_size"] = sampleSize
            }
            if let batchFactor = values.single["--batch-factor"] {
                parameters["batch_factor"] = batchFactor
            }
            return .benchRun(
                BenchRunOptions(
                    modelID: modelID,
                    hfRepoID: hfRepoID,
                    suites: values.multi["--suite"] ?? [],
                    contextLengths: contextLengths,
                    generationLength: generationLength,
                    batchSizes: batchSizes,
                    repeats: repeats,
                    cacheProfile: cacheProfile,
                    reasoningMode: reasoningMode,
                    structuredOutputMode: structuredOutputMode,
                    parameters: parameters,
                    json: values.flags.contains("--json")
                )
            )
        case "list":
            return .benchList(BenchListOptions(json: values.flags.contains("--json")))
        case "export-csv":
            guard let jobID = values.single["--job-id"], !jobID.isEmpty else {
                throw MelixCLIError.missingRequired("--job-id is required for melix bench export-csv.")
            }
            guard let outputPath = values.single["--output"], !outputPath.isEmpty else {
                throw MelixCLIError.missingRequired("--output is required for melix bench export-csv.")
            }
            return .benchExportCSV(
                BenchExportCSVOptions(
                    jobID: jobID,
                    outputPath: outputPath,
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseBenchMatrix(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
            multiValueOptions: [
                "--suite",
                "--context-length",
                "--generation-length",
                "--batch-size",
                "--cache-profile",
                "--reasoning-mode",
                "--structured-output-mode",
                "--concurrency",
            ]
        )
        switch action {
        case "run":
            let modelID = values.single["--model-id"] ?? ""
            let hfRepoID = values.single["--repo-id"] ?? ""
            let explicitTargetCount = [modelID, hfRepoID].filter { !$0.isEmpty }.count
            guard explicitTargetCount == 1 else {
                throw MelixCLIError.missingRequired("Exactly one of --model-id or --repo-id is required for melix bench matrix run.")
            }
            let contextLengths = try parseUInt32List(values.multi["--context-length"] ?? [], option: "--context-length")
            let generationLengths = try parseUInt32List(values.multi["--generation-length"] ?? [], option: "--generation-length")
            let batchSizes = try parseUInt32List(values.multi["--batch-size"] ?? [], option: "--batch-size")
            let concurrencyLevels = try parseUInt32List(values.multi["--concurrency"] ?? [], option: "--concurrency")
            let repeats = try parseUInt32Value(values.single["--repeats"], option: "--repeats", defaultValue: 1) ?? 1
            let requests = try parseUInt32Value(values.single["--requests"], option: "--requests", defaultValue: 0) ?? 0
            let durationSeconds = try parseUInt32Value(
                values.single["--duration-seconds"],
                option: "--duration-seconds",
                defaultValue: 0
            ) ?? 0
            let loadBudgetCount = [requests > 0, durationSeconds > 0].filter(\.self).count
            guard loadBudgetCount == 1 else {
                throw MelixCLIError.missingRequired("Exactly one of --requests or --duration-seconds is required for melix bench matrix run.")
            }
            let cacheProfiles = values.multi["--cache-profile"] ?? []
            for cacheProfile in cacheProfiles where ControlPlaneBenchRequest.validCacheProfiles.contains(cacheProfile) == false {
                throw MelixCLIError.usage(
                    "Invalid value for --cache-profile. Expected one of: \(ControlPlaneBenchRequest.validCacheProfiles.joined(separator: ", "))."
                )
            }
            guard (values.multi["--suite"] ?? []).isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --suite is required for melix bench matrix run.")
            }
            guard contextLengths.isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --context-length is required for melix bench matrix run.")
            }
            guard generationLengths.isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --generation-length is required for melix bench matrix run.")
            }
            guard batchSizes.isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --batch-size is required for melix bench matrix run.")
            }
            guard cacheProfiles.isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --cache-profile is required for melix bench matrix run.")
            }
            guard (values.multi["--reasoning-mode"] ?? []).isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --reasoning-mode is required for melix bench matrix run.")
            }
            guard (values.multi["--structured-output-mode"] ?? []).isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --structured-output-mode is required for melix bench matrix run.")
            }
            guard concurrencyLevels.isEmpty == false else {
                throw MelixCLIError.missingRequired("At least one --concurrency is required for melix bench matrix run.")
            }
            return .benchMatrixRun(
                BenchMatrixRunOptions(
                    modelID: modelID,
                    hfRepoID: hfRepoID,
                    taskKind: values.single["--task-kind"] ?? "",
                    suites: values.multi["--suite"] ?? [],
                    contextLengths: contextLengths,
                    generationLengths: generationLengths,
                    batchSizes: batchSizes,
                    cacheProfiles: cacheProfiles,
                    reasoningModes: values.multi["--reasoning-mode"] ?? [],
                    structuredOutputModes: values.multi["--structured-output-mode"] ?? [],
                    concurrencyLevels: concurrencyLevels,
                    repeats: repeats,
                    requests: requests,
                    durationSeconds: durationSeconds,
                    allowLargeMatrix: values.flags.contains("--allow-large-matrix"),
                    json: values.flags.contains("--json")
                )
            )
        case "list":
            return .benchMatrixList(BenchMatrixListOptions(json: values.flags.contains("--json")))
        case "export-summary-csv":
            guard let jobID = values.single["--job-id"], !jobID.isEmpty else {
                throw MelixCLIError.missingRequired("--job-id is required for melix bench matrix export-summary-csv.")
            }
            guard let outputPath = values.single["--output"], !outputPath.isEmpty else {
                throw MelixCLIError.missingRequired("--output is required for melix bench matrix export-summary-csv.")
            }
            return .benchMatrixExportSummaryCSV(
                BenchExportCSVOptions(jobID: jobID, outputPath: outputPath, json: values.flags.contains("--json"))
            )
        case "export-requests-csv":
            guard let jobID = values.single["--job-id"], !jobID.isEmpty else {
                throw MelixCLIError.missingRequired("--job-id is required for melix bench matrix export-requests-csv.")
            }
            guard let outputPath = values.single["--output"], !outputPath.isEmpty else {
                throw MelixCLIError.missingRequired("--output is required for melix bench matrix export-requests-csv.")
            }
            return .benchMatrixExportRequestsCSV(
                BenchExportCSVOptions(jobID: jobID, outputPath: outputPath, json: values.flags.contains("--json"))
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseEval(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
            multiValueOptions: ["--suite"]
        )
        switch action {
        case "run":
            let modelID = values.single["--model-id"] ?? ""
            let hfRepoID = values.single["--repo-id"] ?? ""
            let explicitTargetCount = [modelID, hfRepoID].filter { !$0.isEmpty }.count
            guard explicitTargetCount == 1 else {
                throw MelixCLIError.missingRequired("Exactly one of --model-id or --repo-id is required for melix eval run.")
            }
            var parameters: [String: String] = [:]
            if let batchFactor = values.single["--batch-factor"] {
                parameters["batch_factor"] = batchFactor
            }
            if let seed = values.single["--seed"] {
                parameters["seed"] = seed
            }
            if let fewShot = values.single["--few-shot"] {
                parameters["few_shot"] = fewShot
            }
            if let scoringMode = values.single["--scoring-mode"] {
                parameters["scoring_mode"] = scoringMode
            }
            if let codeExecPolicy = values.single["--code-exec-policy"] {
                parameters["code_exec_policy"] = codeExecPolicy
            }
            let sampleSize = UInt32(values.single["--sample-size"] ?? "") ?? 0
            return .evalRun(
                EvalRunOptions(
                    modelID: modelID,
                    hfRepoID: hfRepoID,
                    suites: values.multi["--suite"] ?? [],
                    datasetID: values.single["--dataset-id"] ?? "",
                    sampleSize: sampleSize,
                    parameters: parameters,
                    json: values.flags.contains("--json")
                )
            )
        case "list":
            return .evalList(EvalListOptions(json: values.flags.contains("--json")))
        case "export-summary-csv":
            return .evalExportSummaryCSV(try parseEvalExportOptions(values, command: "melix eval export-summary-csv"))
        case "export-samples-csv":
            return .evalExportSamplesCSV(try parseEvalExportOptions(values, command: "melix eval export-samples-csv"))
        case "export-samples-jsonl":
            return .evalExportSamplesJSONL(try parseEvalExportOptions(values, command: "melix eval export-samples-jsonl"))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseEvalExportOptions(
        _ values: ParsedArguments,
        command: String
    ) throws -> EvalExportOptions {
        guard let jobID = values.single["--job-id"], !jobID.isEmpty else {
            throw MelixCLIError.missingRequired("--job-id is required for \(command).")
        }
        guard let outputPath = values.single["--output"], !outputPath.isEmpty else {
            throw MelixCLIError.missingRequired("--output is required for \(command).")
        }
        return EvalExportOptions(jobID: jobID, outputPath: outputPath, json: values.flags.contains("--json"))
    }

    private static func normalizedParameterKey(_ option: String) -> String {
        option
            .replacingOccurrences(of: "--", with: "")
            .replacingOccurrences(of: "-", with: "_")
    }

    private static func parseUInt32Value(
        _ value: String?,
        option: String,
        defaultValue: UInt32? = nil
    ) throws -> UInt32? {
        guard let value else {
            return defaultValue
        }
        guard let parsed = UInt32(value) else {
            throw MelixCLIError.usage("Invalid value for \(option). Expected an unsigned integer.")
        }
        return parsed
    }

    private static func parseUInt32List(
        _ values: [String],
        option: String
    ) throws -> [UInt32] {
        try values.map { value in
            guard let parsed = UInt32(value) else {
                throw MelixCLIError.usage("Invalid value for \(option). Expected an unsigned integer.")
            }
            return parsed
        }
    }
}

private struct ParsedArguments {
    var single: [String: String] = [:]
    var multi: [String: [String]] = [:]
    var flags: Set<String> = []
}

private struct ArgumentCursor {
    let arguments: [String]

    func parse(multiValueOptions: Set<String> = ["--suite"]) throws -> ParsedArguments {
        var result = ParsedArguments()
        var index = 0
        let valueLessFlags: Set<String> = [
            "--json",
            "--response-only",
            "--mask-prompt",
            "--gradient-checkpointing",
            "--allow-large-matrix",
        ]
        while index < arguments.count {
            let token = arguments[index]
            if valueLessFlags.contains(token) {
                result.flags.insert(token)
                index += 1
                continue
            }
            guard token.hasPrefix("--") else {
                throw MelixCLIError.usage(MelixCLIParser.usageText)
            }
            let valueIndex = index + 1
            guard valueIndex < arguments.count else {
                throw MelixCLIError.missingValue(token)
            }
            let value = arguments[valueIndex]
            if multiValueOptions.contains(token) {
                result.multi[token, default: []].append(value)
            } else {
                result.single[token] = value
            }
            index += 2
        }
        return result
    }
}

public actor MelixCLIRunner {
    private let client: any ControlPlaneXPCClient

    public init(
        client: (any ControlPlaneXPCClient)? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        serviceBuilder: (@Sendable ([String: String]) -> any ControlPlaneExecuting)? = nil
    ) {
        if let client {
            self.client = client
        } else {
            let resolvedServiceBuilder = serviceBuilder ?? MelixCLILocalRuntime.makeService
            self.client = LocalControlPlaneXPCClient(service: resolvedServiceBuilder(environment))
        }
    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        switch command {
        case .loraList(let options):
            let modelID = try await resolveModelID(preferred: options.modelID)
            let result = try await client.runModelOperation(
                modelID: modelID,
                operation: "registry_snapshot",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: [:]
            )
            return options.json ? result.manifestJson : renderRegistrySnapshot(result.manifestJson)
        case .loraTrain(let options):
            var ext = options.parameters
            ext["adapter_name"] = options.adapterName
            ext["dataset_source_kind"] = options.datasetSourceKind
            if !options.datasetURI.isEmpty {
                ext["dataset_uri"] = options.datasetURI
            }
            if !options.targetRepo.isEmpty {
                ext["target_repo"] = options.targetRepo
            }
            let result = try await client.runModelOperation(
                modelID: options.modelID,
                operation: "train_lora",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .loraActivate(let options):
            var ext = ["artifact_path": options.adapterPath]
            if !options.derivedModelAlias.isEmpty {
                ext["derived_model_alias"] = options.derivedModelAlias
            }
            let result = try await client.runModelOperation(
                modelID: options.modelID,
                operation: "activate_adapter",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .benchRun(let options):
            if !options.modelID.isEmpty {
                _ = try await client.loadModel(modelID: options.modelID)
            }
            let result = try await client.runBench(
                ControlPlaneBenchRequest(
                    modelID: options.modelID,
                    hfRepoID: options.hfRepoID,
                    suites: options.suites,
                    contextLengths: options.contextLengths,
                    generationLength: options.generationLength,
                    batchSizes: options.batchSizes,
                    repeats: options.repeats,
                    cacheProfile: options.cacheProfile,
                    reasoningMode: options.reasoningMode,
                    structuredOutputMode: options.structuredOutputMode,
                    parameters: options.parameters
                )
            )
            if options.json {
                return try prettyJSON(
                    [
                        "report_path": result.reportPath,
                        "report_markdown": result.reportMarkdown,
                        "metrics": result.metrics,
                    ]
                )
            }
            return result.reportMarkdown.isEmpty ? result.reportPath : result.reportMarkdown
        case .benchList(let options):
            let bundle = try await benchmarkExportBundle()
            let entries = bundle.benchmarkHistoryEntries()
            if options.json {
                return try prettyJSON(entries)
            }
            return renderBenchmarkHistory(entries)
        case .benchExportCSV(let options):
            let bundle = try await benchmarkExportBundle()
            let rows = bundle.benchmarkCSVRows(jobID: options.jobID)
            guard rows.isEmpty == false else {
                throw MelixCLIError.runtime("No benchmark metrics were found for job \(options.jobID).")
            }
            let csv = bundle.benchmarkCSV(jobID: options.jobID)
            let outputURL = URL(fileURLWithPath: options.outputPath)
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            try csv.write(to: outputURL, atomically: true, encoding: .utf8)
            if options.json {
                return try prettyJSON(
                    BenchExportCSVResponse(
                        jobID: options.jobID,
                        outputPath: outputURL.path,
                        rowCount: rows.count
                    )
                )
            }
            return outputURL.path + "\n"
        case .benchMatrixRun(let options):
            if !options.modelID.isEmpty {
                _ = try await client.loadModel(modelID: options.modelID)
            }
            let result = try await client.runBenchMatrix(
                ControlPlaneBenchMatrixRequest(
                    modelID: options.modelID,
                    hfRepoID: options.hfRepoID,
                    taskKind: options.taskKind,
                    suites: options.suites,
                    contextLengths: options.contextLengths,
                    generationLengths: options.generationLengths,
                    batchSizes: options.batchSizes,
                    cacheProfiles: options.cacheProfiles,
                    reasoningModes: options.reasoningModes,
                    structuredOutputModes: options.structuredOutputModes,
                    concurrencyLevels: options.concurrencyLevels,
                    repeats: options.repeats,
                    requests: options.requests,
                    durationSeconds: options.durationSeconds,
                    allowLargeMatrix: options.allowLargeMatrix
                )
            )
            if options.json {
                return try prettyJSON(makeBenchmarkMatrixPayload(result))
            }
            return renderBenchmarkMatrixRun(result)
        case .benchMatrixList(let options):
            let bundle = try await benchmarkExportBundle()
            let entries = bundle.benchmarkMatrixHistoryEntries()
            if options.json {
                return try prettyJSON(entries)
            }
            return renderBenchmarkMatrixHistory(entries)
        case .benchMatrixExportSummaryCSV(let options):
            let bundle = try await benchmarkExportBundle()
            let rows = bundle.benchmarkMatrixSummaryCSVRows(jobID: options.jobID)
            guard rows.isEmpty == false else {
                throw MelixCLIError.runtime("No benchmark matrix summary rows were found for job \(options.jobID).")
            }
            let csv = bundle.benchmarkMatrixSummaryCSV(jobID: options.jobID)
            let outputURL = URL(fileURLWithPath: options.outputPath)
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            try csv.write(to: outputURL, atomically: true, encoding: .utf8)
            if options.json {
                return try prettyJSON(
                    BenchExportCSVResponse(jobID: options.jobID, outputPath: outputURL.path, rowCount: rows.count)
                )
            }
            return outputURL.path + "\n"
        case .benchMatrixExportRequestsCSV(let options):
            let bundle = try await benchmarkExportBundle()
            let rows = bundle.benchmarkMatrixRequestRows(jobID: options.jobID)
            guard rows.isEmpty == false else {
                throw MelixCLIError.runtime("No benchmark matrix request rows were found for job \(options.jobID).")
            }
            let csv = bundle.benchmarkMatrixRequestsCSV(jobID: options.jobID)
            let outputURL = URL(fileURLWithPath: options.outputPath)
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            try csv.write(to: outputURL, atomically: true, encoding: .utf8)
            if options.json {
                return try prettyJSON(
                    BenchExportCSVResponse(jobID: options.jobID, outputPath: outputURL.path, rowCount: rows.count)
                )
            }
            return outputURL.path + "\n"
        case .evalRun(let options):
            let suites = options.suites.isEmpty ? ["mmlu"] : options.suites
            let results = try await runEvaluationSuites(options: options, suites: suites)
            if options.json {
                return try prettyJSON(results.map(makeEvaluationPayload))
            }
            return renderEvaluationRuns(results)
        case .evalList(let options):
            let bundle = try await benchmarkExportBundle()
            let entries = bundle.evaluationHistoryEntries()
            if options.json {
                return try prettyJSON(entries)
            }
            return renderEvaluationHistory(entries)
        case .evalExportSummaryCSV(let options):
            return try await exportEvaluationArtifact(
                options: options,
                rowCount: { bundle in bundle.evaluationSummaryCSVRows(jobID: options.jobID).count },
                contents: { bundle in bundle.evaluationSummaryCSV(jobID: options.jobID) }
            )
        case .evalExportSamplesCSV(let options):
            return try await exportEvaluationArtifact(
                options: options,
                rowCount: { bundle in bundle.evaluationSampleRows(jobID: options.jobID).count },
                contents: { bundle in bundle.evaluationSamplesCSV(jobID: options.jobID) }
            )
        case .evalExportSamplesJSONL(let options):
            return try await exportEvaluationArtifact(
                options: options,
                rowCount: { bundle in bundle.evaluationSampleRows(jobID: options.jobID).count },
                contents: { bundle in try bundle.evaluationSamplesJSONL(jobID: options.jobID) }
            )
        }
    }

    private func resolveModelID(preferred: String) async throws -> String {
        if !preferred.isEmpty {
            return preferred
        }
        let snapshot = try await client.serverSnapshot()
        if let model = snapshot.models.first(where: { $0.kind == "text" }) ?? snapshot.models.first {
            return model.modelID
        }
        throw MelixCLIError.missingRequired("No model is available in the current server snapshot.")
    }

    private func renderRegistrySnapshot(_ manifestJSON: String) -> String {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let adapters = payload["adapters"] as? [[String: Any]]
        else {
            return manifestJSON
        }
        if adapters.isEmpty {
            return "No adapters found.\n"
        }
        let lines = adapters.map { adapter in
            let name = (adapter["adapter_name"] as? String) ?? "adapter"
            let status = (adapter["status"] as? String) ?? "unknown"
            let sourceModel = (adapter["source_model"] as? String) ?? ""
            return "\(name)\t\(status)\t\(sourceModel)"
        }
        return (["adapter\tstatus\tsource_model"] + lines).joined(separator: "\n") + "\n"
    }

    private func benchmarkExportBundle() async throws -> ControlPlaneBenchmarkExportBundle {
        let export = try await client.exportResults(outputDir: "")
        return try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
    }

    private func runEvaluationSuites(
        options: EvalRunOptions,
        suites: [String]
    ) async throws -> [ControlPlaneEvaluationResult] {
        var collected: [ControlPlaneEvaluationResult] = []
        for suiteID in suites {
            let request = ControlPlaneEvaluationRequest(
                modelID: options.modelID,
                hfRepoID: options.hfRepoID,
                suiteID: suiteID,
                datasetID: options.datasetID.isEmpty ? Self.defaultEvaluationDatasetID(for: suiteID) : options.datasetID,
                sampleSize: options.sampleSize,
                parameters: options.parameters
            )
            collected.append(try await client.runEvaluation(request))
        }
        return collected
    }

    private func exportEvaluationArtifact(
        options: EvalExportOptions,
        rowCount: (ControlPlaneBenchmarkExportBundle) throws -> Int,
        contents: (ControlPlaneBenchmarkExportBundle) throws -> String
    ) async throws -> String {
        let bundle = try await benchmarkExportBundle()
        let rows = try rowCount(bundle)
        guard rows > 0 else {
            throw MelixCLIError.runtime("No evaluation rows were found for job \(options.jobID).")
        }
        let outputURL = URL(fileURLWithPath: options.outputPath)
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: nil
        )
        try contents(bundle).write(to: outputURL, atomically: true, encoding: .utf8)
        if options.json {
            return try prettyJSON(
                EvalExportResponse(
                    jobID: options.jobID,
                    outputPath: outputURL.path,
                    rowCount: rows
                )
            )
        }
        return outputURL.path + "\n"
    }

    private func renderBenchmarkHistory(_ entries: [ControlPlaneBenchmarkHistoryEntry]) -> String {
        guard entries.isEmpty == false else {
            return "No benchmark runs found.\n"
        }
        let lines = entries.map { entry in
            [
                entry.jobID,
                entry.modelID,
                entry.taskKind.isEmpty ? "-" : entry.taskKind,
                entry.sourceRepo.isEmpty ? "-" : entry.sourceRepo,
                entry.suiteID,
                benchmarkDatasetLabel(entry),
                entry.sampleSize.map(String.init) ?? "-",
                entry.batchFactor.map(String.init) ?? "-",
                entry.status,
                String(entry.createdAtUnixMS),
            ].joined(separator: "\t")
        }
        return ([
            "job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tdataset\tsample_size\tbatch_factor\tstatus\tcreated_at_unix_ms",
        ] + lines).joined(separator: "\n") + "\n"
    }

    private func renderBenchmarkMatrixRun(_ result: ControlPlaneBenchMatrixResult) -> String {
        guard result.summaryRows.isEmpty == false else {
            return "No benchmark matrix rows were returned.\n"
        }
        let lines = result.summaryRows.map { row in
            [
                row.jobID,
                row.modelID,
                row.taskKind.isEmpty ? "-" : row.taskKind,
                row.sourceRepo.isEmpty ? "-" : row.sourceRepo,
                row.suiteID,
                String(row.contextLength),
                String(row.generationLength),
                String(row.batchSize),
                row.cacheProfile,
                row.reasoningMode,
                row.structuredOutputMode,
                String(row.concurrencyLevel),
                String(row.repeats),
                matrixLoadBudgetLabel(requests: Int(row.requests), durationSeconds: Int(row.durationSeconds)),
                String(row.ttftMeanMs),
            ].joined(separator: "\t")
        }
        return ([
            "job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tcontext_length\tgeneration_length\tbatch_size\tcache_profile\treasoning_mode\tstructured_output_mode\tconcurrency_level\trepeats\tload_budget\tttft_mean_ms",
        ] + lines).joined(separator: "\n") + "\n"
    }

    private func renderBenchmarkMatrixHistory(_ entries: [ControlPlaneBenchmarkMatrixHistoryEntry]) -> String {
        guard entries.isEmpty == false else {
            return "No benchmark matrix runs found.\n"
        }
        let lines = entries.map { entry in
            [
                entry.jobID,
                entry.modelID,
                entry.taskKind.isEmpty ? "-" : entry.taskKind,
                entry.sourceRepo.isEmpty ? "-" : entry.sourceRepo,
                entry.suiteID,
                String(entry.contextLength),
                String(entry.generationLength),
                String(entry.batchSize),
                entry.cacheProfile,
                entry.reasoningMode,
                entry.structuredOutputMode,
                String(entry.concurrencyLevel),
                String(entry.repeats),
                matrixLoadBudgetLabel(requests: entry.requests, durationSeconds: entry.durationSeconds),
                entry.status,
                String(entry.createdAtUnixMS),
            ].joined(separator: "\t")
        }
        return ([
            "job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tcontext_length\tgeneration_length\tbatch_size\tcache_profile\treasoning_mode\tstructured_output_mode\tconcurrency_level\trepeats\tload_budget\tstatus\tcreated_at_unix_ms",
        ] + lines).joined(separator: "\n") + "\n"
    }

    private func renderEvaluationHistory(_ entries: [ControlPlaneEvaluationHistoryEntry]) -> String {
        guard entries.isEmpty == false else {
            return "No evaluation runs found.\n"
        }
        let lines = entries.map { entry in
            [
                entry.jobID,
                entry.modelID,
                entry.taskKind.isEmpty ? "-" : entry.taskKind,
                entry.sourceRepo.isEmpty ? "-" : entry.sourceRepo,
                entry.suiteID,
                entry.datasetID,
                String(entry.sampleSize),
                entry.scoringMode,
                entry.status,
                String(entry.createdAtUnixMS),
            ].joined(separator: "\t")
        }
        return ([
            "job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tdataset\tsample_size\tscoring_mode\tstatus\tcreated_at_unix_ms",
        ] + lines).joined(separator: "\n") + "\n"
    }

    private func renderEvaluationRuns(_ runs: [ControlPlaneEvaluationResult]) -> String {
        guard runs.isEmpty == false else {
            return "No evaluation runs completed.\n"
        }
        let lines = runs.map { run in
            let metrics = run.results
                .flatMap(\.metrics)
                .map { metric in
                    metric.unit.isEmpty ? "\(metric.name)=\(metric.value)" : "\(metric.name)=\(metric.value)\(metric.unit)"
                }
                .joined(separator: ", ")
            return [run.job.jobID, run.job.suiteID, run.job.datasetID, run.job.status, metrics].joined(separator: "\t")
        }
        return (["job_id\tsuite\tdataset\tstatus\tmetrics"] + lines).joined(separator: "\n") + "\n"
    }

    private func benchmarkDatasetLabel(_ entry: ControlPlaneBenchmarkHistoryEntry) -> String {
        var pieces: [String] = []
        if !entry.datasetRepo.isEmpty {
            pieces.append(entry.datasetRepo)
        }
        if !entry.datasetConfig.isEmpty {
            pieces.append(entry.datasetConfig)
        }
        var label = pieces.joined(separator: "/")
        if !entry.datasetSplit.isEmpty {
            label = label.isEmpty ? entry.datasetSplit : "\(label):\(entry.datasetSplit)"
        }
        return label.isEmpty ? "-" : label
    }

    private func makeEvaluationPayload(_ result: ControlPlaneEvaluationResult) -> [String: Any] {
        [
            "job": [
                "schema_version": result.job.schemaVersion,
                "job_id": result.job.jobID,
                "model_id": result.job.modelID,
                "task_kind": result.job.taskKind,
                "source_repo": result.job.sourceRepo,
                "suite_id": result.job.suiteID,
                "dataset_id": result.job.datasetID,
                "sample_size": Int(result.job.sampleSize),
                "scoring_mode": result.job.scoringMode,
                "parameters": result.job.parameters,
                "status": result.job.status,
                "output_dir": result.job.outputDir,
                "created_at_unix_ms": result.job.createdAtUnixMs,
                "updated_at_unix_ms": result.job.updatedAtUnixMs,
            ],
            "results": result.results.map { record in
                [
                    "schema_version": record.schemaVersion,
                    "job_id": record.jobID,
                    "suite_id": record.suiteID,
                    "dataset_id": record.datasetID,
                    "sample_size": Int(record.sampleSize),
                    "report_path": record.reportPath,
                    "metrics": record.metrics.map { metric in
                        [
                            "name": metric.name,
                            "value": metric.value,
                            "unit": metric.unit,
                        ]
                    },
                ]
            },
        ]
    }

    private func makeBenchmarkMatrixPayload(_ result: ControlPlaneBenchMatrixResult) -> [String: Any] {
        [
            "job": [
                "schema_version": result.job.schemaVersion,
                "job_id": result.job.jobID,
                "model_id": result.job.modelID,
                "task_kind": result.job.taskKind,
                "source_repo": result.job.sourceRepo,
                "suite_ids": result.job.suiteIds,
                "benchmark_mode": result.job.benchmarkMode,
                "status": result.job.status,
                "output_dir": result.job.outputDir,
                "created_at_unix_ms": result.job.createdAtUnixMs,
                "updated_at_unix_ms": result.job.updatedAtUnixMs,
            ],
            "summary_rows": result.summaryRows.map { row in
                [
                    "job_id": row.jobID,
                    "task_kind": row.taskKind,
                    "source_repo": row.sourceRepo,
                    "model_id": row.modelID,
                    "suite_id": row.suiteID,
                    "context_length": Int(row.contextLength),
                    "generation_length": Int(row.generationLength),
                    "batch_size": Int(row.batchSize),
                    "cache_profile": row.cacheProfile,
                    "reasoning_mode": row.reasoningMode,
                    "structured_output_mode": row.structuredOutputMode,
                    "concurrency_level": Int(row.concurrencyLevel),
                    "repeats": Int(row.repeats),
                    "requests": Int(row.requests),
                    "duration_seconds": Int(row.durationSeconds),
                    "ttft_mean_ms": row.ttftMeanMs,
                    "ttft_std_ms": row.ttftStdMs,
                    "request_latency_mean_ms": row.requestLatencyMeanMs,
                    "request_latency_std_ms": row.requestLatencyStdMs,
                    "prefill_tokens_per_second_mean": row.prefillTokensPerSecondMean,
                    "decode_tokens_per_second_mean": row.decodeTokensPerSecondMean,
                    "throughput_requests_per_second": row.throughputRequestsPerSecond,
                    "throughput_tokens_per_second": row.throughputTokensPerSecond,
                    "success_rate": row.successRate,
                    "peak_memory_bytes_max": row.peakMemoryBytesMax,
                    "queue_wait_mean_ms": row.queueWaitMeanMs,
                    "queue_wait_p95_ms": row.queueWaitP95Ms,
                    "created_at_unix_ms": row.createdAtUnixMs,
                ]
            },
        ]
    }

    private func matrixLoadBudgetLabel(requests: UInt32, durationSeconds: UInt32) -> String {
        matrixLoadBudgetLabel(requests: Int(requests), durationSeconds: Int(durationSeconds))
    }

    private func matrixLoadBudgetLabel(requests: Int, durationSeconds: Int) -> String {
        if requests > 0 {
            return "requests=\(requests)"
        }
        if durationSeconds > 0 {
            return "duration_seconds=\(durationSeconds)"
        }
        return "-"
    }

    private func prettyJSON(_ payload: [String: Any]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    private func prettyJSON(_ payload: [[String: Any]]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    private func prettyJSON<Value: Encodable>(_ payload: Value) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(payload)
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    private static func defaultEvaluationDatasetID(for suiteID: String) -> String {
        "\(suiteID).dev.v1"
    }
}

private struct BenchExportCSVResponse: Encodable {
    let jobID: String
    let outputPath: String
    let rowCount: Int
}

private struct EvalExportResponse: Encodable {
    let jobID: String
    let outputPath: String
    let rowCount: Int
}

private enum MelixCLILocalRuntime {
    static func makeService(environment: [String: String]) -> any ControlPlaneExecuting {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let metricsStore = MetricsStore(exportPath: environment["MELIX_CONTROL_PLANE_METRICS_PATH"])
        let mcpToolCatalog = MCPToolCatalog.load(environment: environment)
        let gatewayAccessPolicyStore = GatewayAccessPolicyStore(GatewayAccessPolicy.load(environment: environment))

        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock"
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: environment["MELIX_WORKER_SOCKET_PATH"] ?? "/tmp/melix-worker.sock",
            repoRoot: repoRoot(environment: environment),
            processEnvironment: environment
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: swiftTextWorkerClient,
            pythonCompatibilityClient: pythonCompatibilityClient,
            modelCatalog: modelCatalog
        )

        return ControlPlaneService(
            modelCatalog: modelCatalog,
            metricsStore: metricsStore,
            workerRegistry: workerRegistry,
            mcpToolCatalog: mcpToolCatalog,
            gatewayAccessPolicyStore: gatewayAccessPolicyStore
        )
    }

    private static func repoRoot(environment: [String: String]) -> String {
        if let repoRoot = environment["MELIX_REPO_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !repoRoot.isEmpty {
            return repoRoot
        }

        return URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path
    }
}
