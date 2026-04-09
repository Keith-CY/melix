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

public struct ServerSnapshotOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct ServerControlOptions: Equatable, Sendable {
    public let serverSessionID: String
    public let json: Bool

    public init(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        json: Bool = false
    ) {
        self.serverSessionID = serverSessionID.isEmpty
            ? ServerSessionRuntimeStore.defaultServerSessionID
            : serverSessionID
        self.json = json
    }
}

public struct ServerIdlePolicyOptions: Equatable, Sendable {
    public let serverSessionID: String
    public let autoSleepEnabled: Bool
    public let lightSleepAfterSeconds: UInt32
    public let deepSleepAfterSeconds: UInt32
    public let json: Bool

    public init(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32,
        json: Bool = false
    ) {
        self.serverSessionID = serverSessionID.isEmpty
            ? ServerSessionRuntimeStore.defaultServerSessionID
            : serverSessionID
        self.autoSleepEnabled = autoSleepEnabled
        self.lightSleepAfterSeconds = lightSleepAfterSeconds
        self.deepSleepAfterSeconds = deepSleepAfterSeconds
        self.json = json
    }
}

public struct ModelListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct ModelInspectOptions: Equatable, Sendable {
    public let modelID: String
    public let json: Bool

    public init(modelID: String, json: Bool = false) {
        self.modelID = modelID
        self.json = json
    }
}

public struct ModelLoadOptions: Equatable, Sendable {
    public let modelID: String
    public let memoryBudgetBytes: UInt64
    public let json: Bool

    public init(modelID: String, memoryBudgetBytes: UInt64 = 0, json: Bool = false) {
        self.modelID = modelID
        self.memoryBudgetBytes = memoryBudgetBytes
        self.json = json
    }
}

public struct ModelUnloadOptions: Equatable, Sendable {
    public let modelID: String
    public let json: Bool

    public init(modelID: String, json: Bool = false) {
        self.modelID = modelID
        self.json = json
    }
}

public struct ModelHubSearchOptions: Equatable, Sendable {
    public let query: String
    public let pageSize: UInt32
    public let cursor: String
    public let mlxOnly: Bool
    public let json: Bool

    public init(
        query: String,
        pageSize: UInt32 = 10,
        cursor: String = "",
        mlxOnly: Bool = true,
        json: Bool = false
    ) {
        self.query = query
        self.pageSize = pageSize == 0 ? 10 : pageSize
        self.cursor = cursor
        self.mlxOnly = mlxOnly
        self.json = json
    }
}

public struct ModelHubShowOptions: Equatable, Sendable {
    public let repoID: String
    public let json: Bool

    public init(repoID: String, json: Bool = false) {
        self.repoID = repoID
        self.json = json
    }
}

public struct ModelHubDownloadOptions: Equatable, Sendable {
    public let repoID: String
    public let revision: String
    public let json: Bool

    public init(repoID: String, revision: String = "main", json: Bool = false) {
        self.repoID = repoID
        self.revision = revision.isEmpty ? "main" : revision
        self.json = json
    }
}

public struct ModelDownloadOptions: Equatable, Sendable {
    public let modelID: String
    public let outputDir: String
    public let json: Bool

    public init(modelID: String, outputDir: String = "", json: Bool = false) {
        self.modelID = modelID
        self.outputDir = outputDir
        self.json = json
    }
}

public struct ModelRootsListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct ModelRootsMutateOptions: Equatable, Sendable {
    public let path: String
    public let json: Bool

    public init(path: String, json: Bool = false) {
        self.path = path
        self.json = json
    }
}

public struct ModelRootsMoveOptions: Equatable, Sendable {
    public let path: String
    public let index: Int
    public let json: Bool

    public init(path: String, index: Int, json: Bool = false) {
        self.path = path
        self.index = index
        self.json = json
    }
}

public struct ModelRootsRescanOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct ServerSessionListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct ServerSessionCreateOptions: Equatable, Sendable {
    public let title: String
    public let modelID: String
    public let host: String
    public let port: Int
    public let rateLimitPerMinute: Int
    public let timeoutSeconds: Int
    public let json: Bool

    public init(
        title: String,
        modelID: String,
        host: String = "127.0.0.1",
        port: Int = 8080,
        rateLimitPerMinute: Int = 120,
        timeoutSeconds: Int = 120,
        json: Bool = false
    ) {
        self.title = title
        self.modelID = modelID
        self.host = host
        self.port = port
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.json = json
    }
}

public struct ServerSessionUpdateOptions: Equatable, Sendable {
    public let serverSessionID: String
    public let title: String
    public let modelID: String
    public let host: String
    public let port: Int
    public let rateLimitPerMinute: Int
    public let timeoutSeconds: Int
    public let json: Bool

    public init(
        serverSessionID: String,
        title: String = "",
        modelID: String = "",
        host: String = "",
        port: Int = 0,
        rateLimitPerMinute: Int = 0,
        timeoutSeconds: Int = 0,
        json: Bool = false
    ) {
        self.serverSessionID = serverSessionID
        self.title = title
        self.modelID = modelID
        self.host = host
        self.port = port
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.json = json
    }
}

public struct ServerSessionIDOptions: Equatable, Sendable {
    public let serverSessionID: String
    public let json: Bool

    public init(serverSessionID: String, json: Bool = false) {
        self.serverSessionID = serverSessionID
        self.json = json
    }
}

public enum MelixCLICommand: Equatable, Sendable {
    case modelList(ModelListOptions)
    case modelInspect(ModelInspectOptions)
    case modelLoad(ModelLoadOptions)
    case modelUnload(ModelUnloadOptions)
    case modelDownload(ModelDownloadOptions)
    case modelHubSearch(ModelHubSearchOptions)
    case modelHubShow(ModelHubShowOptions)
    case modelHubDownload(ModelHubDownloadOptions)
    case modelRootsList(ModelRootsListOptions)
    case modelRootsAdd(ModelRootsMutateOptions)
    case modelRootsRemove(ModelRootsMutateOptions)
    case modelRootsMove(ModelRootsMoveOptions)
    case modelRootsRescan(ModelRootsRescanOptions)
    case serverSnapshot(ServerSnapshotOptions)
    case serverSessionList(ServerSessionListOptions)
    case serverSessionCreate(ServerSessionCreateOptions)
    case serverSessionUpdate(ServerSessionUpdateOptions)
    case serverSessionRemove(ServerSessionIDOptions)
    case serverSessionSelect(ServerSessionIDOptions)
    case serverStart(ServerControlOptions)
    case serverPause(ServerControlOptions)
    case serverResume(ServerControlOptions)
    case serverWake(ServerControlOptions)
    case serverStop(ServerControlOptions)
    case serverSetIdlePolicy(ServerIdlePolicyOptions)
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
        case "model":
            return try parseModel(tail)
        case "server":
            return try parseServer(tail)
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
      melix model list [--json]
      melix model inspect --model-id MODEL_ID [--json]
      melix model load --model-id MODEL_ID [--memory-budget-bytes N] [--json]
      melix model unload --model-id MODEL_ID [--json]
      melix model download --model-id MODEL_ID [--output-dir PATH] [--json]
      melix model hub search --query QUERY [--page-size N] [--cursor TOKEN] [--mlx-only (true|false)] [--json]
      melix model hub show --repo-id HF_REPO [--json]
      melix model hub download --repo-id HF_REPO [--revision REV] [--json]
      melix model roots list [--json]
      melix model roots add --path PATH [--json]
      melix model roots remove --path PATH [--json]
      melix model roots move --path PATH --index N [--json]
      melix model roots rescan [--json]
      melix server snapshot [--json]
      melix server session list [--json]
      melix server session create --title TITLE --model-id MODEL_ID [--host HOST] [--port PORT] [--rate-limit-per-minute N] [--timeout-seconds N] [--json]
      melix server session update --server-session-id ID [--title TITLE] [--model-id MODEL_ID] [--host HOST] [--port PORT] [--rate-limit-per-minute N] [--timeout-seconds N] [--json]
      melix server session remove --server-session-id ID [--json]
      melix server session select --server-session-id ID [--json]
      melix server start [--server-session-id ID] [--json]
      melix server pause [--server-session-id ID] [--json]
      melix server resume [--server-session-id ID] [--json]
      melix server wake [--server-session-id ID] [--json]
      melix server stop [--server-session-id ID] [--json]
      melix server set-idle-policy [--server-session-id ID] --auto-sleep (true|false) --light-sleep-after N --deep-sleep-after N [--json]
      melix lora list [--model-id MODEL_ID] [--json]
      melix lora train --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) --adapter-name NAME [--target-repo REPO] [--rank N] [--alpha N] [--dropout N] [--target-modules CSV] [--num-layers N] [--batch-size N] [--epochs N] [--learning-rate N] [--max-seq-length N] [--sample-limit N] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-train-split SPLIT] [--hf-valid-split SPLIT] [--text-feature NAME] [--prompt-feature NAME] [--completion-feature NAME] [--chat-feature NAME] [--derived-model-alias NAME] [--response-only] [--mask-prompt] [--gradient-checkpointing] [--json]
      melix lora activate --model-id MODEL_ID --adapter-path PATH [--alias NAME] [--json]
      melix bench run (--model-id MODEL_ID | --repo-id HF_REPO) [--suite SUITE ...] [--context-length N ...] [--generation-length N] [--batch-size N ...] [--repeats N] [--cache-profile MODE] [--reasoning-mode MODE] [--structured-output-mode MODE] [--sample-size N] [--batch-factor N] [--json]
      melix bench list [--json]
      melix bench export-csv --job-id JOB_ID --output PATH [--json]
      melix bench matrix run (--model-id MODEL_ID | --repo-id HF_REPO) --suite SUITE ... --context-length N ... --generation-length N ... --batch-size N ... --cache-profile MODE ... --reasoning-mode MODE ... --structured-output-mode MODE ... --concurrency N ... [--repeats N] (--requests N | --duration-seconds N) [--allow-large-matrix] [--json]
      melix bench matrix list [--json]
      melix bench matrix export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix bench matrix export-requests-csv --job-id JOB_ID --output PATH [--json]
      melix eval run (--model-id MODEL_ID | --repo-id HF_REPO) [--suite SUITE ...] [--dataset-id DATASET_ID] [--dataset-root PATH] [--sample-size N] [--batch-factor N] [--seed N] [--few-shot N] [--json]
      melix eval list [--json]
      melix eval export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix eval export-samples-csv --job-id JOB_ID --output PATH [--json]
      melix eval export-samples-jsonl --job-id JOB_ID --output PATH [--json]
    """

    private static func parseModel(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        switch action {
        case "list":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            return .modelList(.init(json: values.flags.contains("--json")))
        case "inspect":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix model inspect.")
            }
            return .modelInspect(.init(modelID: modelID, json: values.flags.contains("--json")))
        case "load":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix model load.")
            }
            let budget = try parseUInt64Value(values.single["--memory-budget-bytes"], option: "--memory-budget-bytes") ?? 0
            return .modelLoad(.init(modelID: modelID, memoryBudgetBytes: budget, json: values.flags.contains("--json")))
        case "unload":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix model unload.")
            }
            return .modelUnload(.init(modelID: modelID, json: values.flags.contains("--json")))
        case "download":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix model download.")
            }
            return .modelDownload(
                .init(
                    modelID: modelID,
                    outputDir: values.single["--output-dir"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "hub":
            return try parseModelHub(Array(arguments.dropFirst()))
        case "roots":
            return try parseModelRoots(Array(arguments.dropFirst()))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseModelHub(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "search":
            guard let query = values.single["--query"], !query.isEmpty else {
                throw MelixCLIError.missingRequired("--query is required for melix model hub search.")
            }
            let pageSize = try parseUInt32Value(values.single["--page-size"], option: "--page-size", defaultValue: 10) ?? 10
            let mlxOnly = parseBooleanValue(values.single["--mlx-only"], option: "--mlx-only") ?? true
            return .modelHubSearch(
                .init(
                    query: query,
                    pageSize: pageSize,
                    cursor: values.single["--cursor"] ?? "",
                    mlxOnly: mlxOnly,
                    json: values.flags.contains("--json")
                )
            )
        case "show":
            guard let repoID = values.single["--repo-id"], !repoID.isEmpty else {
                throw MelixCLIError.missingRequired("--repo-id is required for melix model hub show.")
            }
            return .modelHubShow(.init(repoID: repoID, json: values.flags.contains("--json")))
        case "download":
            guard let repoID = values.single["--repo-id"], !repoID.isEmpty else {
                throw MelixCLIError.missingRequired("--repo-id is required for melix model hub download.")
            }
            return .modelHubDownload(
                .init(
                    repoID: repoID,
                    revision: values.single["--revision"] ?? "main",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseModelRoots(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "list":
            return .modelRootsList(.init(json: values.flags.contains("--json")))
        case "add":
            guard let path = values.single["--path"], !path.isEmpty else {
                throw MelixCLIError.missingRequired("--path is required for melix model roots add.")
            }
            return .modelRootsAdd(.init(path: path, json: values.flags.contains("--json")))
        case "remove":
            guard let path = values.single["--path"], !path.isEmpty else {
                throw MelixCLIError.missingRequired("--path is required for melix model roots remove.")
            }
            return .modelRootsRemove(.init(path: path, json: values.flags.contains("--json")))
        case "move":
            guard let path = values.single["--path"], !path.isEmpty else {
                throw MelixCLIError.missingRequired("--path is required for melix model roots move.")
            }
            guard let index = try parseIntValue(values.single["--index"], option: "--index") else {
                throw MelixCLIError.missingRequired("--index is required for melix model roots move.")
            }
            return .modelRootsMove(.init(path: path, index: index, json: values.flags.contains("--json")))
        case "rescan":
            return .modelRootsRescan(.init(json: values.flags.contains("--json")))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseServer(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        if action == "session" {
            return try parseServerSession(Array(arguments.dropFirst()))
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        let serverSessionID = values.single["--server-session-id"] ?? ServerSessionRuntimeStore.defaultServerSessionID
        let json = values.flags.contains("--json")
        switch action {
        case "snapshot":
            return .serverSnapshot(.init(json: json))
        case "start":
            return .serverStart(.init(serverSessionID: serverSessionID, json: json))
        case "pause":
            return .serverPause(.init(serverSessionID: serverSessionID, json: json))
        case "resume":
            return .serverResume(.init(serverSessionID: serverSessionID, json: json))
        case "wake":
            return .serverWake(.init(serverSessionID: serverSessionID, json: json))
        case "stop":
            return .serverStop(.init(serverSessionID: serverSessionID, json: json))
        case "set-idle-policy":
            guard let autoSleepValue = values.single["--auto-sleep"] else {
                throw MelixCLIError.missingRequired("--auto-sleep is required for melix server set-idle-policy.")
            }
            guard let autoSleepEnabled = parseBooleanValue(autoSleepValue, option: "--auto-sleep") else {
                throw MelixCLIError.usage("Invalid value for --auto-sleep. Expected true or false.")
            }
            guard let lightSleepAfterSeconds = try parseUInt32Value(
                values.single["--light-sleep-after"],
                option: "--light-sleep-after"
            ) else {
                throw MelixCLIError.missingRequired("--light-sleep-after is required for melix server set-idle-policy.")
            }
            guard let deepSleepAfterSeconds = try parseUInt32Value(
                values.single["--deep-sleep-after"],
                option: "--deep-sleep-after"
            ) else {
                throw MelixCLIError.missingRequired("--deep-sleep-after is required for melix server set-idle-policy.")
            }
            return .serverSetIdlePolicy(
                .init(
                    serverSessionID: serverSessionID,
                    autoSleepEnabled: autoSleepEnabled,
                    lightSleepAfterSeconds: lightSleepAfterSeconds,
                    deepSleepAfterSeconds: deepSleepAfterSeconds,
                    json: json
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseServerSession(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "list":
            return .serverSessionList(.init(json: values.flags.contains("--json")))
        case "create":
            guard let title = values.single["--title"], !title.isEmpty else {
                throw MelixCLIError.missingRequired("--title is required for melix server session create.")
            }
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix server session create.")
            }
            let port = try parseIntValue(values.single["--port"], option: "--port", defaultValue: 8080) ?? 8080
            let rateLimit = try parseIntValue(
                values.single["--rate-limit-per-minute"],
                option: "--rate-limit-per-minute",
                defaultValue: 120
            ) ?? 120
            let timeoutSeconds = try parseIntValue(
                values.single["--timeout-seconds"],
                option: "--timeout-seconds",
                defaultValue: 120
            ) ?? 120
            return .serverSessionCreate(
                .init(
                    title: title,
                    modelID: modelID,
                    host: values.single["--host"] ?? "127.0.0.1",
                    port: port,
                    rateLimitPerMinute: rateLimit,
                    timeoutSeconds: timeoutSeconds,
                    json: values.flags.contains("--json")
                )
            )
        case "update":
            guard let serverSessionID = values.single["--server-session-id"], !serverSessionID.isEmpty else {
                throw MelixCLIError.missingRequired("--server-session-id is required for melix server session update.")
            }
            return .serverSessionUpdate(
                .init(
                    serverSessionID: serverSessionID,
                    title: values.single["--title"] ?? "",
                    modelID: values.single["--model-id"] ?? "",
                    host: values.single["--host"] ?? "",
                    port: try parseIntValue(values.single["--port"], option: "--port", defaultValue: 0) ?? 0,
                    rateLimitPerMinute: try parseIntValue(
                        values.single["--rate-limit-per-minute"],
                        option: "--rate-limit-per-minute",
                        defaultValue: 0
                    ) ?? 0,
                    timeoutSeconds: try parseIntValue(
                        values.single["--timeout-seconds"],
                        option: "--timeout-seconds",
                        defaultValue: 0
                    ) ?? 0,
                    json: values.flags.contains("--json")
                )
            )
        case "remove":
            guard let serverSessionID = values.single["--server-session-id"], !serverSessionID.isEmpty else {
                throw MelixCLIError.missingRequired("--server-session-id is required for melix server session remove.")
            }
            return .serverSessionRemove(.init(serverSessionID: serverSessionID, json: values.flags.contains("--json")))
        case "select":
            guard let serverSessionID = values.single["--server-session-id"], !serverSessionID.isEmpty else {
                throw MelixCLIError.missingRequired("--server-session-id is required for melix server session select.")
            }
            return .serverSessionSelect(.init(serverSessionID: serverSessionID, json: values.flags.contains("--json")))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

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
                "--sample-limit",
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
            if let datasetRoot = values.single["--dataset-root"] {
                parameters["dataset_root"] = datasetRoot
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

    private static func parseBooleanValue(
        _ value: String?,
        option: String
    ) -> Bool? {
        guard let value else {
            return nil
        }
        switch value.lowercased() {
        case "true":
            return true
        case "false":
            return false
        default:
            _ = option
            return nil
        }
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

    private static func parseUInt64Value(
        _ value: String?,
        option: String,
        defaultValue: UInt64? = nil
    ) throws -> UInt64? {
        guard let value else {
            return defaultValue
        }
        guard let parsed = UInt64(value) else {
            throw MelixCLIError.usage("Invalid value for \(option). Expected an unsigned integer.")
        }
        return parsed
    }

    private static func parseIntValue(
        _ value: String?,
        option: String,
        defaultValue: Int? = nil
    ) throws -> Int? {
        guard let value else {
            return defaultValue
        }
        guard let parsed = Int(value) else {
            throw MelixCLIError.usage("Invalid value for \(option). Expected an integer.")
        }
        return parsed
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
    private let operatorSessionStore: any MelixOperatorSessionStoring
    private let environment: [String: String]

    public init(
        client: (any ControlPlaneXPCClient)? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        operatorSessionStore: (any MelixOperatorSessionStoring)? = nil,
        serviceBuilder: (@Sendable ([String: String]) -> any ControlPlaneExecuting)? = nil
    ) {
        self.environment = environment
        self.operatorSessionStore = operatorSessionStore ?? MelixOperatorSessionStore(
            melixHome: MelixHome(environment: environment)
        )
        if let client {
            self.client = client
        } else {
            let resolvedServiceBuilder = serviceBuilder ?? MelixLocalRuntimeFactory.makeService
            self.client = LocalControlPlaneXPCClient(service: resolvedServiceBuilder(environment))
        }
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
        try await client.runModelOperation(
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
        try await client.modelInfo(modelID: modelID)
    }

    public func loadModel(
        modelID: String,
        memoryBudgetBytes: UInt64 = 0
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await client.loadModel(modelID: modelID, memoryBudgetBytes: memoryBudgetBytes)
    }

    public func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await client.unloadModel(modelID: modelID)
    }

    public func searchHubModels(
        query: String,
        pageSize: UInt32 = 10,
        cursor: String = "",
        mlxOnly: Bool = true
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        try await client.searchHubModels(
            query: query,
            pageSize: pageSize,
            cursor: cursor,
            mlxOnly: mlxOnly
        )
    }

    public func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        try await client.getHubModelCard(repoID: repoID)
    }

    public func downloadHubModel(
        repoID: String,
        revision: String = "main"
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        var ext: [String: String] = [
            "melix.source_kind": "hub_repo",
            "melix.hf_repo_id": repoID,
            "melix.hf_revision": revision.isEmpty ? "main" : revision,
            "melix.managed_import": "true",
        ]
        if let managedRoot = environment["MELIX_MANAGED_MODEL_ROOT"], managedRoot.isEmpty == false {
            ext["melix.managed_root"] = managedRoot
        }
        return try await performModelOperation(
            modelID: repoID,
            operation: "download",
            outputDir: "",
            ext: ext
        )
    }

    public func downloadModel(
        modelID: String,
        outputDir: String = ""
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await performModelOperation(
            modelID: modelID,
            operation: "download",
            outputDir: resolvedDownloadOutputDirectory(modelID: modelID, explicitOutputDir: outputDir)
        )
    }

    public func applyConfiguredServerSessionGatewayConfig(
        serverSessionID: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        let configuredSession = try loadConfiguredServerSession(id: serverSessionID)
        return try await client.applyServerSessionGatewayConfig(
            serverSessionID: configuredSession.id,
            host: configuredSession.host,
            port: configuredSession.port,
            servedModelID: configuredSession.modelID,
            rateLimitPerMinute: configuredSession.rateLimitPerMinute,
            timeoutSeconds: configuredSession.timeoutSeconds
        )
    }

    public func applyConfiguredServerSessionServingDefaults(
        serverSessionID: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        let configuredSession = try loadConfiguredServerSession(id: serverSessionID)
        return try await client.applyServerSessionServingDefaults(
            serverSessionID: configuredSession.id,
            temperature: configuredSession.servingDefaults.temperature,
            topP: configuredSession.servingDefaults.topP,
            maxTokens: configuredSession.servingDefaults.maxTokens,
            streamIntervalTokens: configuredSession.servingDefaults.streamIntervalTokens,
            maxConcurrentRequests: configuredSession.servingDefaults.maxConcurrentRequests,
            concurrentProcessingEnabled: configuredSession.servingDefaults.concurrentProcessingEnabled,
            prefillBatchSize: configuredSession.servingDefaults.prefillBatchSize,
            completionBatchSize: configuredSession.servingDefaults.completionBatchSize,
            accelerationMode: accelerationMode(for: configuredSession.servingDefaults.accelerationMode),
            draftModelID: configuredSession.servingDefaults.draftModelID,
            numDraftTokens: configuredSession.servingDefaults.numDraftTokens
        )
    }

    public func runBenchmark(_ options: BenchRunOptions) async throws -> ControlPlaneBenchResult {
        if !options.modelID.isEmpty {
            _ = try await client.loadModel(modelID: options.modelID)
        }
        return try await client.runBench(
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
    }

    public func runBenchmarkMatrix(_ options: BenchMatrixRunOptions) async throws -> ControlPlaneBenchMatrixResult {
        if !options.modelID.isEmpty {
            _ = try await client.loadModel(modelID: options.modelID)
        }
        return try await client.runBenchMatrix(
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
    }

    public func fetchBenchmarkExportBundle(outputDir: String = "") async throws -> ControlPlaneBenchmarkExportBundle {
        let export = try await client.exportResults(outputDir: outputDir)
        return try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
    }

    public func runEvaluations(_ options: EvalRunOptions) async throws -> [ControlPlaneEvaluationResult] {
        let suites = options.suites.isEmpty ? ["mmlu"] : options.suites
        return try await runEvaluationSuites(options: options, suites: suites)
    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        if commandRequiresConfiguredRegistryRootPriming(command) {
            try await primeConfiguredRegistryRootsIfNeeded()
        }
        switch command {
        case .modelList(let options):
            let snapshot = try await client.serverSnapshot()
            if options.json {
                return try prettyJSON(makeModelListPayload(snapshot.models))
            }
            return renderModelList(snapshot.models)
        case .modelInspect(let options):
            let info = try await client.modelInfo(modelID: options.modelID)
            if options.json {
                return try prettyJSON(makeModelInfoPayload(info, modelID: options.modelID))
            }
            return renderModelInfo(info, modelID: options.modelID)
        case .modelLoad(let options):
            let model = try await client.loadModel(modelID: options.modelID, memoryBudgetBytes: options.memoryBudgetBytes)
            if options.json {
                return try prettyJSON(makeModelSummaryPayload(model))
            }
            return renderModelSummary(model)
        case .modelUnload(let options):
            let model = try await client.unloadModel(modelID: options.modelID)
            if options.json {
                return try prettyJSON(makeModelSummaryPayload(model))
            }
            return renderModelSummary(model)
        case .modelDownload(let options):
            let result = try await downloadModel(modelID: options.modelID, outputDir: options.outputDir)
            return options.json ? result.manifestJson : result.outputPath + "\n"
        case .modelHubSearch(let options):
            let result = try await searchHubModels(
                query: options.query,
                pageSize: options.pageSize,
                cursor: options.cursor,
                mlxOnly: options.mlxOnly
            )
            if options.json {
                return try prettyJSON(makeHubSearchPayload(result))
            }
            return renderHubSearch(result)
        case .modelHubShow(let options):
            let card = try await getHubModelCard(repoID: options.repoID)
            if options.json {
                return try prettyJSON(makeHubModelCardPayload(card))
            }
            return renderHubModelCard(card)
        case .modelHubDownload(let options):
            let result = try await downloadHubModel(repoID: options.repoID, revision: options.revision)
            return options.json ? result.manifestJson : result.outputPath + "\n"
        case .modelRootsList(let options):
            let state = try loadOperatorState()
            if options.json {
                return try prettyJSON(["registry_roots": state.registryRoots])
            }
            return renderRegistryRoots(state.registryRoots)
        case .modelRootsAdd(let options):
            let state = try mutateOperatorState { current in
                let canonical = canonicalRootPath(options.path)
                if current.registryRoots.contains(canonical) == false {
                    current.registryRoots.append(canonical)
                }
            }
            if options.json {
                return try prettyJSON(["registry_roots": state.registryRoots])
            }
            return renderRegistryRoots(state.registryRoots)
        case .modelRootsRemove(let options):
            let state = try mutateOperatorState { current in
                let canonical = canonicalRootPath(options.path)
                current.registryRoots.removeAll { $0 == canonical }
            }
            if options.json {
                return try prettyJSON(["registry_roots": state.registryRoots])
            }
            return renderRegistryRoots(state.registryRoots)
        case .modelRootsMove(let options):
            let state = try mutateOperatorState { current in
                let canonical = canonicalRootPath(options.path)
                guard let existingIndex = current.registryRoots.firstIndex(of: canonical) else {
                    return
                }
                let root = current.registryRoots.remove(at: existingIndex)
                let targetIndex = max(0, min(options.index, current.registryRoots.count))
                current.registryRoots.insert(root, at: targetIndex)
            }
            if options.json {
                return try prettyJSON(["registry_roots": state.registryRoots])
            }
            return renderRegistryRoots(state.registryRoots)
        case .modelRootsRescan(let options):
            let state = try loadOperatorState()
            var ext: [String: String] = [
                "melix.registry_rescan": "true",
            ]
            if state.registryRoots.isEmpty == false {
                ext["melix.registry_roots_json"] = try encodeRegistryRoots(state.registryRoots)
            }
            let result = try await performModelOperation(
                modelID: "melix-dev-text",
                operation: "registry_snapshot",
                outputDir: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath + "\n"
        case .serverSnapshot(let options):
            let snapshot = try await client.serverSnapshot()
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverSessionList(let options):
            let state = try loadOperatorState()
            if options.json {
                return try prettyJSON(state)
            }
            return renderServerSessions(state)
        case .serverSessionCreate(let options):
            let state = try mutateOperatorState { current in
                let nextIndex = current.serverSessions.count + 1
                let created = MelixOperatorServerSessionState(
                    id: "server-session-\(nextIndex)",
                    title: options.title,
                    modelID: options.modelID,
                    host: options.host,
                    port: options.port,
                    rateLimitPerMinute: options.rateLimitPerMinute,
                    timeoutSeconds: options.timeoutSeconds,
                    lifecycle: .draft
                )
                current.serverSessions.append(created)
                current.selectedServerSessionID = created.id
            }
            if options.json {
                return try prettyJSON(state)
            }
            return renderServerSessions(state)
        case .serverSessionUpdate(let options):
            let state = try mutateOperatorState { current in
                guard let index = current.serverSessions.firstIndex(where: { $0.id == options.serverSessionID }) else {
                    return
                }
                var session = current.serverSessions[index]
                if options.title.isEmpty == false {
                    session.title = options.title
                }
                if options.modelID.isEmpty == false {
                    session.modelID = options.modelID
                }
                if options.host.isEmpty == false {
                    session.host = options.host
                }
                if options.port > 0 {
                    session.port = options.port
                }
                if options.rateLimitPerMinute > 0 {
                    session.rateLimitPerMinute = options.rateLimitPerMinute
                }
                if options.timeoutSeconds > 0 {
                    session.timeoutSeconds = options.timeoutSeconds
                }
                session.updatedAt = Date()
                current.serverSessions[index] = session
            }
            if options.json {
                return try prettyJSON(state)
            }
            return renderServerSessions(state)
        case .serverSessionRemove(let options):
            let state = try mutateOperatorState { current in
                current.serverSessions.removeAll { $0.id == options.serverSessionID }
                if current.selectedServerSessionID == options.serverSessionID {
                    current.selectedServerSessionID = current.serverSessions.first?.id ?? ""
                }
            }
            if options.json {
                return try prettyJSON(state)
            }
            return renderServerSessions(state)
        case .serverSessionSelect(let options):
            let state = try mutateOperatorState { current in
                if current.serverSessions.contains(where: { $0.id == options.serverSessionID }) {
                    current.selectedServerSessionID = options.serverSessionID
                }
            }
            if options.json {
                return try prettyJSON(state)
            }
            return renderServerSessions(state)
        case .serverStart(let options):
            guard let configuredSession = try configuredServerSessionIfAvailable(id: options.serverSessionID) else {
                let snapshot = try await client.startServerSession(serverSessionID: options.serverSessionID)
                return try renderServerSnapshot(snapshot, json: options.json)
            }
            let serverSnapshot = try await client.serverSnapshot()
            guard try await boundServerStartModelIsAvailable(
                modelID: configuredSession.modelID,
                serverSnapshot: serverSnapshot
            ) else {
                try markServerSessionUnavailable(
                    id: configuredSession.id,
                    message: "Unavailable",
                    lastError: "Bound model \(configuredSession.modelID) is missing."
                )
                throw MelixCLIError.runtime("Bound model \(configuredSession.modelID) is missing.")
            }
            guard try await boundServerStartModelIsServeable(
                modelID: configuredSession.modelID,
                serverSnapshot: serverSnapshot
            ) else {
                try markServerSessionUnavailable(
                    id: configuredSession.id,
                    message: "Unavailable",
                    lastError: "Bound model \(configuredSession.modelID) is not serveable."
                )
                throw MelixCLIError.runtime("Bound model \(configuredSession.modelID) is not serveable.")
            }
            _ = try await client.applyServerSessionGatewayConfig(
                serverSessionID: configuredSession.id,
                host: configuredSession.host,
                port: configuredSession.port,
                servedModelID: configuredSession.modelID,
                rateLimitPerMinute: configuredSession.rateLimitPerMinute,
                timeoutSeconds: configuredSession.timeoutSeconds
            )
            _ = try await client.applyServerSessionServingDefaults(
                serverSessionID: configuredSession.id,
                temperature: configuredSession.servingDefaults.temperature,
                topP: configuredSession.servingDefaults.topP,
                maxTokens: configuredSession.servingDefaults.maxTokens,
                streamIntervalTokens: configuredSession.servingDefaults.streamIntervalTokens,
                maxConcurrentRequests: configuredSession.servingDefaults.maxConcurrentRequests,
                concurrentProcessingEnabled: configuredSession.servingDefaults.concurrentProcessingEnabled,
                prefillBatchSize: configuredSession.servingDefaults.prefillBatchSize,
                completionBatchSize: configuredSession.servingDefaults.completionBatchSize,
                accelerationMode: accelerationMode(for: configuredSession.servingDefaults.accelerationMode),
                draftModelID: configuredSession.servingDefaults.draftModelID,
                numDraftTokens: configuredSession.servingDefaults.numDraftTokens
            )
            let snapshot = try await client.startServerSession(serverSessionID: configuredSession.id)
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverPause(let options):
            let snapshot = try await client.pauseServerSession(serverSessionID: options.serverSessionID)
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverResume(let options):
            let snapshot = try await client.resumeServerSession(serverSessionID: options.serverSessionID)
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverWake(let options):
            let snapshot = try await client.wakeServerSession(serverSessionID: options.serverSessionID)
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverStop(let options):
            let snapshot = try await client.stopServerSession(serverSessionID: options.serverSessionID)
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverSetIdlePolicy(let options):
            if let configuredSession = try configuredServerSessionIfAvailable(id: options.serverSessionID) {
                _ = try mutateOperatorState { state in
                    guard let index = state.serverSessions.firstIndex(where: { $0.id == configuredSession.id }) else {
                        return
                    }
                    state.serverSessions[index].autoSleepEnabled = options.autoSleepEnabled
                    state.serverSessions[index].lightSleepAfterSeconds = Int(options.lightSleepAfterSeconds)
                    state.serverSessions[index].deepSleepAfterSeconds = Int(options.deepSleepAfterSeconds)
                    state.serverSessions[index].updatedAt = Date()
                }
            }
            let snapshot = try await client.updateServerIdlePolicy(
                serverSessionID: options.serverSessionID,
                autoSleepEnabled: options.autoSleepEnabled,
                lightSleepAfterSeconds: options.lightSleepAfterSeconds,
                deepSleepAfterSeconds: options.deepSleepAfterSeconds
            )
            return try renderServerSnapshot(snapshot, json: options.json)
        case .loraList(let options):
            let modelID = try await resolveModelID(preferred: options.modelID)
            let result = try await performModelOperation(
                modelID: modelID,
                operation: "registry_snapshot",
                outputDir: "",
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
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "train_lora",
                outputDir: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .loraActivate(let options):
            var ext = ["artifact_path": options.adapterPath]
            if !options.derivedModelAlias.isEmpty {
                ext["derived_model_alias"] = options.derivedModelAlias
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "activate_adapter",
                outputDir: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .benchRun(let options):
            let result = try await runBenchmark(options)
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
            let bundle = try await fetchBenchmarkExportBundle()
            let entries = bundle.benchmarkHistoryEntries()
            if options.json {
                return try prettyJSON(entries)
            }
            return renderBenchmarkHistory(entries)
        case .benchExportCSV(let options):
            let bundle = try await fetchBenchmarkExportBundle()
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
            let result = try await runBenchmarkMatrix(options)
            if options.json {
                return try prettyJSON(makeBenchmarkMatrixPayload(result))
            }
            return renderBenchmarkMatrixRun(result)
        case .benchMatrixList(let options):
            let bundle = try await fetchBenchmarkExportBundle()
            let entries = bundle.benchmarkMatrixHistoryEntries()
            if options.json {
                return try prettyJSON(entries)
            }
            return renderBenchmarkMatrixHistory(entries)
        case .benchMatrixExportSummaryCSV(let options):
            let bundle = try await fetchBenchmarkExportBundle()
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
            let bundle = try await fetchBenchmarkExportBundle()
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
            let results = try await runEvaluations(options)
            if options.json {
                return try prettyJSON(results.map(makeEvaluationPayload))
            }
            return renderEvaluationRuns(results)
        case .evalList(let options):
            let bundle = try await fetchBenchmarkExportBundle()
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

    private func loadOperatorState() throws -> MelixOperatorSessionState {
        try operatorSessionStore.load() ?? MelixOperatorSessionState(selectedServerSessionID: "", serverSessions: [])
    }

    private func commandRequiresConfiguredRegistryRootPriming(_ command: MelixCLICommand) -> Bool {
        switch command {
        case .modelList,
             .modelInspect,
             .modelLoad,
             .modelUnload,
             .serverSnapshot,
             .serverStart,
             .loraList,
             .loraTrain,
             .loraActivate,
             .benchRun,
             .benchMatrixRun,
             .evalRun:
            return true
        default:
            return false
        }
    }

    private func primeConfiguredRegistryRootsIfNeeded() async throws {
        let state = loadOperatorStateForRegistryPriming()
        var ext: [String: String] = [
            "melix.registry_rescan": "true",
        ]
        if state.registryRoots.isEmpty == false {
            ext["melix.registry_roots_json"] = try encodeRegistryRoots(state.registryRoots)
        }
        _ = try await performModelOperation(
            modelID: "melix-dev-text",
            operation: "registry_snapshot",
            outputDir: "",
            ext: ext
        )
    }

    private func loadOperatorStateForRegistryPriming() -> MelixOperatorSessionState {
        do {
            return try loadOperatorState()
        } catch CocoaError.fileReadNoPermission,
                CocoaError.fileReadNoSuchFile {
            return MelixOperatorSessionState(selectedServerSessionID: "", serverSessions: [])
        } catch {
            return MelixOperatorSessionState(selectedServerSessionID: "", serverSessions: [])
        }
    }

    @discardableResult
    private func mutateOperatorState(
        _ update: (inout MelixOperatorSessionState) throws -> Void
    ) throws -> MelixOperatorSessionState {
        var state = try loadOperatorState()
        try update(&state)
        try operatorSessionStore.save(state)
        return state
    }

    private func loadConfiguredServerSession(id: String) throws -> MelixOperatorServerSessionState {
        let state = try loadOperatorState()
        let resolvedID = id.isEmpty ? state.selectedServerSessionID : id
        if let session = state.serverSessions.first(where: { $0.id == resolvedID }) {
            return session
        }
        throw MelixCLIError.runtime("Server session \(resolvedID) is not configured.")
    }

    private func configuredServerSessionIfAvailable(
        id: String
    ) throws -> MelixOperatorServerSessionState? {
        do {
            return try loadConfiguredServerSession(id: id)
        } catch let error as MelixCLIError {
            if case .runtime = error {
                return nil
            }
            throw error
        } catch CocoaError.fileReadNoPermission {
            return nil
        } catch CocoaError.fileReadNoSuchFile {
            return nil
        } catch {
            throw error
        }
    }

    private func markServerSessionUnavailable(
        id: String,
        message: String,
        lastError: String
    ) throws {
        _ = try mutateOperatorState { state in
            guard let index = state.serverSessions.firstIndex(where: { $0.id == id }) else {
                return
            }
            state.serverSessions[index].lifecycle = .unavailable
            state.serverSessions[index].lastKnownModelStateText = message
            state.serverSessions[index].lastError = lastError
            state.serverSessions[index].updatedAt = Date()
        }
    }

    private func encodeRegistryRoots(_ roots: [String]) throws -> String {
        let data = try JSONEncoder().encode(roots)
        return String(decoding: data, as: UTF8.self)
    }

    private func canonicalRootPath(_ rawPath: String) -> String {
        URL(fileURLWithPath: rawPath).standardizedFileURL.path
    }

    private func resolvedDownloadOutputDirectory(modelID: String, explicitOutputDir: String) -> String {
        let trimmedOutputDir = explicitOutputDir.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedOutputDir.isEmpty == false {
            return canonicalRootPath(trimmedOutputDir)
        }

        let sanitizedNamespace = sanitizedDownloadPathComponent("melix-downloads", fallback: "melix-downloads")
        let sanitizedModelID = sanitizedDownloadPathComponent(modelID, fallback: "model")
        return URL(fileURLWithPath: "/tmp", isDirectory: true)
            .appendingPathComponent(sanitizedNamespace, isDirectory: true)
            .appendingPathComponent(sanitizedModelID, isDirectory: true)
            .path
    }

    private func sanitizedDownloadPathComponent(_ rawValue: String, fallback: String) -> String {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return fallback
        }
        let sanitized = trimmed.map { character -> Character in
            if character.isLetter || character.isNumber || character == "-" || character == "_" || character == "." {
                return character
            }
            return "-"
        }
        let normalized = String(sanitized).trimmingCharacters(in: CharacterSet(charactersIn: "-._"))
        return normalized.isEmpty ? fallback : normalized
    }

    private func isServeableModel(_ model: Melix_Controlplane_V1_ModelSummary) -> Bool {
        MelixServeableModelRules.isServeable(kind: model.kind, features: model.features)
    }

    private func isServeableModel(_ info: Melix_Controlplane_V1_ModelInfo) -> Bool {
        let normalizedTasks = info.supportedTasks.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        let normalizedModalities = info.supportedModalities.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        if MelixServeableModelRules.isServeable(kind: info.modelKind) {
            return true
        }
        let taskSet = Set(normalizedTasks)
        let modalitySet = Set(normalizedModalities)
        let supportsTextServing = modalitySet.contains("text")
            && (taskSet.contains("chat") || taskSet.contains("generate"))
        let excludesImageServing = taskSet.contains("image_generate") || taskSet.contains("image_edit")
        return supportsTextServing && !excludesImageServing
    }

    private func boundServerStartModelIsAvailable(
        modelID: String,
        serverSnapshot: Melix_Controlplane_V1_ServerSnapshot
    ) async throws -> Bool {
        if serverSnapshot.models.contains(where: { $0.modelID == modelID }) {
            return true
        }
        do {
            _ = try await client.modelInfo(modelID: modelID)
            return true
        } catch let error as ControlPlaneXPCClientError {
            if case .requestFailed(let code, _) = error, code == "not_found" {
                return false
            }
            throw error
        }
    }

    private func boundServerStartModelIsServeable(
        modelID: String,
        serverSnapshot: Melix_Controlplane_V1_ServerSnapshot
    ) async throws -> Bool {
        if let model = serverSnapshot.models.first(where: { $0.modelID == modelID }) {
            return isServeableModel(model)
        }
        let info = try await client.modelInfo(modelID: modelID)
        return isServeableModel(info)
    }

    private func accelerationMode(for rawValue: String) -> Melix_Controlplane_V1_AccelerationMode {
        switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "baseline":
            return .baseline
        case "speculative_decode":
            return .speculativeDecode
        case "accelerated_prefill":
            return .acceleratedPrefill
        case "active_kv_quantized":
            return .activeKvQuantized
        case "sparse_prefill":
            return .sparsePrefill
        default:
            return .unspecified
        }
    }

    private func renderModelList(_ models: [Melix_Controlplane_V1_ModelSummary]) -> String {
        guard models.isEmpty == false else {
            return "No models found.\n"
        }
        let rows = models
            .sorted { $0.modelID < $1.modelID }
            .map { model in
                "\(model.modelID)\t\(model.kind)\t\(modelStateLabel(model.state))"
            }
        return (["model_id\tkind\tstate"] + rows).joined(separator: "\n") + "\n"
    }

    private func renderModelSummary(_ model: Melix_Controlplane_V1_ModelSummary) -> String {
        "\(model.modelID)\t\(model.kind)\t\(modelStateLabel(model.state))\n"
    }

    private func renderModelInfo(_ info: Melix_Controlplane_V1_ModelInfo, modelID: String) -> String {
        [
            "model_id=\(modelID)",
            "model_kind=\(info.modelKind)",
            "backend_id=\(info.backendID)",
            "family_id=\(info.familyID)",
            "max_context=\(info.maxContext)",
            "supported_tasks=\(info.supportedTasks.joined(separator: ","))",
        ].joined(separator: "\n") + "\n"
    }

    private func renderHubSearch(_ result: Melix_Controlplane_V1_HubSearchResult) -> String {
        guard result.models.isEmpty == false else {
            return "No hub models found.\n"
        }
        let lines = result.models.map { model in
            "\(model.repoID)\t\(model.pipelineTag)\t\(model.mlxCompatible ? "mlx" : "generic")"
        }
        return (["repo_id\tpipeline_tag\tcompatibility"] + lines).joined(separator: "\n") + "\n"
    }

    private func renderHubModelCard(_ card: Melix_Controlplane_V1_HubModelCard) -> String {
        [
            "repo_id=\(card.repoID)",
            "author=\(card.author)",
            "model_name=\(card.modelName)",
            "pipeline_tag=\(card.pipelineTag)",
            "mlx_compatible=\(card.mlxCompatible ? "true" : "false")",
        ].joined(separator: "\n") + "\n"
    }

    private func renderRegistryRoots(_ roots: [String]) -> String {
        guard roots.isEmpty == false else {
            return "No registry roots configured.\n"
        }
        return roots.enumerated().map { index, root in
            "\(index + 1)\t\(root)"
        }.joined(separator: "\n") + "\n"
    }

    private func renderServerSessions(_ state: MelixOperatorSessionState) -> String {
        guard state.serverSessions.isEmpty == false else {
            return "No server sessions configured.\n"
        }
        let rows = state.serverSessions.map { session in
            let selectedMarker = session.id == state.selectedServerSessionID ? "*" : ""
            return "\(selectedMarker)\(session.id)\t\(session.title)\t\(session.modelID)\t\(session.lifecycle.rawValue)"
        }
        return (["server_session_id\ttitle\tmodel_id\tlifecycle"] + rows).joined(separator: "\n") + "\n"
    }

    private func makeModelSummaryPayload(_ model: Melix_Controlplane_V1_ModelSummary) -> [String: Any] {
        [
            "model_id": model.modelID,
            "kind": model.kind,
            "state": modelStateLabel(model.state),
            "features": model.features,
        ]
    }

    private func makeModelListPayload(_ models: [Melix_Controlplane_V1_ModelSummary]) -> [[String: Any]] {
        models.sorted { $0.modelID < $1.modelID }.map(makeModelSummaryPayload)
    }

    private func makeModelInfoPayload(
        _ info: Melix_Controlplane_V1_ModelInfo,
        modelID: String
    ) -> [String: Any] {
        [
            "model_id": modelID,
            "model_kind": info.modelKind,
            "backend_id": info.backendID,
            "family_id": info.familyID,
            "max_context": Int(info.maxContext),
            "supported_tasks": info.supportedTasks,
            "supported_modalities": info.supportedModalities,
            "supported_parsers": info.supportedParsers,
        ]
    }

    private func makeHubSearchPayload(_ result: Melix_Controlplane_V1_HubSearchResult) -> [String: Any] {
        [
            "next_cursor": result.nextCursor,
            "models": result.models.map { model in
                [
                    "repo_id": model.repoID,
                    "author": model.author,
                    "model_name": model.modelName,
                    "pipeline_tag": model.pipelineTag,
                    "downloads": NSNumber(value: model.downloads),
                    "likes": NSNumber(value: model.likes),
                    "mlx_compatible": model.mlxCompatible,
                ]
            },
        ]
    }

    private func makeHubModelCardPayload(_ card: Melix_Controlplane_V1_HubModelCard) -> [String: Any] {
        [
            "repo_id": card.repoID,
            "author": card.author,
            "model_name": card.modelName,
            "summary": card.summary,
            "pipeline_tag": card.pipelineTag,
            "mlx_compatible": card.mlxCompatible,
            "tags": card.tags,
            "base_models": card.baseModels,
        ]
    }

    private func modelStateLabel(_ value: Melix_Controlplane_V1_ModelState) -> String {
        switch value {
        case .modelDiscovered:
            return "discovered"
        case .modelLoading:
            return "loading"
        case .modelWarm:
            return "warm"
        case .modelPinned:
            return "pinned"
        case .modelEvicting:
            return "evicting"
        case .modelUnloaded:
            return "unloaded"
        case .modelFailed:
            return "failed"
        default:
            return "unspecified"
        }
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
        let bundle = try await fetchBenchmarkExportBundle()
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

    private func renderServerSnapshot(
        _ snapshot: Melix_Controlplane_V1_ServerSnapshot,
        json: Bool
    ) throws -> String {
        if json {
            return try prettyJSON(makeServerSnapshotPayload(snapshot))
        }
        return renderServerSnapshotText(snapshot)
    }

    private func renderServerSnapshotText(_ snapshot: Melix_Controlplane_V1_ServerSnapshot) -> String {
        guard snapshot.runtimeSessions.isEmpty == false else {
            return "server_state=\(serverStateLabel(snapshot.serverState))\nNo runtime sessions found.\n"
        }
        let lines = snapshot.runtimeSessions.map { session in
            [
                serverStateLabel(snapshot.serverState),
                session.serverSessionID,
                lifecycleStateLabel(session.lifecycleState),
                powerStateLabel(session.powerState),
                wakeReasonLabel(session.wakeReason),
                session.autoSleepEnabled ? "true" : "false",
                String(session.lightSleepAfterSeconds),
                String(session.deepSleepAfterSeconds),
                String(session.idleTimerSeconds),
                String(session.updatedAtUnixMs),
            ].joined(separator: "\t")
        }
        return ([
            "server_state\tserver_session_id\tlifecycle_state\tpower_state\twake_reason\tauto_sleep_enabled\tlight_sleep_after_seconds\tdeep_sleep_after_seconds\tidle_timer_seconds\tupdated_at_unix_ms",
        ] + lines).joined(separator: "\n") + "\n"
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

    private func makeServerSnapshotPayload(
        _ snapshot: Melix_Controlplane_V1_ServerSnapshot
    ) -> [String: Any] {
        [
            "server_state": serverStateLabel(snapshot.serverState),
            "runtime_sessions": snapshot.runtimeSessions.map { session in
                [
                    "server_session_id": session.serverSessionID,
                    "lifecycle_state": lifecycleStateLabel(session.lifecycleState),
                    "power_state": powerStateLabel(session.powerState),
                    "wake_reason": wakeReasonLabel(session.wakeReason),
                    "idle_timer_seconds": Int(session.idleTimerSeconds),
                    "auto_sleep_enabled": session.autoSleepEnabled,
                    "light_sleep_after_seconds": Int(session.lightSleepAfterSeconds),
                    "deep_sleep_after_seconds": Int(session.deepSleepAfterSeconds),
                    "updated_at_unix_ms": session.updatedAtUnixMs,
                ]
            },
        ]
    }

    private func serverStateLabel(_ value: Melix_Controlplane_V1_ServerState) -> String {
        switch value {
        case .serverReady:
            return "server_ready"
        case .serverBooting:
            return "server_booting"
        case .serverDegraded:
            return "server_degraded"
        case .serverDraining:
            return "server_draining"
        case .serverStopped:
            return "server_stopped"
        case .serverFailed:
            return "server_failed"
        default:
            return "server_state_unspecified"
        }
    }

    private func lifecycleStateLabel(
        _ value: Melix_Controlplane_V1_ServerSessionLifecycleState
    ) -> String {
        switch value {
        case .ready:
            return "ready"
        case .paused:
            return "paused"
        case .sleeping:
            return "sleeping"
        case .stopped:
            return "stopped"
        case .loading:
            return "loading"
        case .error:
            return "error"
        default:
            return "lifecycle_unspecified"
        }
    }

    private func powerStateLabel(
        _ value: Melix_Controlplane_V1_ServerSessionPowerState
    ) -> String {
        switch value {
        case .active:
            return "active"
        case .lightSleep:
            return "light_sleep"
        case .deepSleep:
            return "deep_sleep"
        case .stopped:
            return "stopped"
        default:
            return "power_unspecified"
        }
    }

    private func wakeReasonLabel(
        _ value: Melix_Controlplane_V1_ServerWakeReason
    ) -> String {
        switch value {
        case .initialBoot:
            return "initial_boot"
        case .requestActivity:
            return "request_activity"
        case .operatorResume:
            return "operator_resume"
        case .toolActivity:
            return "tool_activity"
        case .policyApply:
            return "policy_apply"
        default:
            return "wake_unspecified"
        }
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
