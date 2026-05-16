import Foundation
import MelixCLICore

public enum MelixCLIWorkflowSurface: String, Equatable, Sendable {
    case inProcess = "in_process"
    case subprocess
}

public enum MelixCLIWorkflowFailureKind: String, Equatable, Sendable {
    case processFailed = "process_failed"
    case invalidJSON = "invalid_json"
    case missingField = "missing_field"
    case unsupportedCommand = "unsupported_command"
}

public enum MelixCLIWorkflowError: Error, Equatable, Sendable, LocalizedError {
    case processFailed(commandID: String, surface: MelixCLIWorkflowSurface, exitCode: Int32, stderr: String)
    case invalidJSON(commandID: String, surface: MelixCLIWorkflowSurface, output: String)
    case missingField(commandID: String, surface: MelixCLIWorkflowSurface, field: String)
    case unsupportedCommand(commandID: String, surface: MelixCLIWorkflowSurface)

    public var failureKind: MelixCLIWorkflowFailureKind {
        switch self {
        case .processFailed:
            return .processFailed
        case .invalidJSON:
            return .invalidJSON
        case .missingField:
            return .missingField
        case .unsupportedCommand:
            return .unsupportedCommand
        }
    }

    public var errorDescription: String? {
        switch self {
        case .processFailed(let commandID, _, let exitCode, let stderr):
            let detail = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
            return detail.isEmpty
                ? "\(commandID) failed with exit code \(exitCode)."
                : "\(commandID) failed with exit code \(exitCode): \(detail)"
        case .invalidJSON(let commandID, _, _):
            return "\(commandID) returned malformed JSON."
        case .missingField(let commandID, _, let field):
            return "\(commandID) did not return required field \(field)."
        case .unsupportedCommand(let commandID, _):
            return "\(commandID) is not supported by the CLI subprocess bridge."
        }
    }
}

public struct MelixCLIServerSnapshotPayload: Codable, Equatable, Sendable {
    public let serverState: String
    public let runtimeSessions: [MelixCLIRuntimeSessionPayload]
}

public struct MelixCLIRuntimeSessionPayload: Codable, Equatable, Sendable {
    public let serverSessionID: String
    public let lifecycleState: String
    public let powerState: String
    public let wakeReason: String
    public let idleTimerSeconds: Int
    public let autoSleepEnabled: Bool
    public let lightSleepAfterSeconds: Int
    public let deepSleepAfterSeconds: Int
    public let updatedAtUnixMS: Int64
}

public struct MelixCLIBenchRunPayload: Codable, Equatable, Sendable {
    public let reportPath: String
    public let reportMarkdown: String
    public let metrics: [String: Double]
}

public struct MelixCLIBenchmarkMatrixRunPayload: Codable, Equatable, Sendable {
    public let job: MelixCLIBenchmarkMatrixJobPayload
    public let summaryRows: [MelixCLIBenchmarkMatrixSummaryRowPayload]
}

public struct MelixCLIBenchmarkMatrixJobPayload: Codable, Equatable, Sendable {
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
}

public struct MelixCLIBenchmarkMatrixSummaryRowPayload: Codable, Equatable, Sendable {
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
    public let createdAtUnixMS: Int64
}

public struct MelixCLIEvaluationRunPayload: Codable, Equatable, Sendable {
    public let job: MelixCLIEvaluationJobPayload
    public let results: [MelixCLIEvaluationResultPayload]
}

public struct MelixCLIEvaluationJobPayload: Codable, Equatable, Sendable {
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
}

public struct MelixCLIEvaluationResultPayload: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: Int
    public let reportPath: String
    public let metrics: [MelixCLIMetricPayload]
}

public struct MelixCLIMetricPayload: Codable, Equatable, Sendable {
    public let name: String
    public let value: Double
    public let unit: String
}

public struct MelixCLIExportResponse: Codable, Equatable, Sendable {
    public let jobID: String
    public let outputPath: String
    public let rowCount: Int
}

public struct MelixCLIModelOperationManifestPayload: Codable, Equatable, Sendable {
    public let operation: String?
    public let jobID: String?
    public let sourceModel: String?
    public let outputPath: String?
    public let artifactPath: String?
    public let weightsPath: String?
    public let adapterName: String?
    public let datasetURI: String?
    public let derivedModelID: String?
    public let derivedModelPath: String?
    public let derivedModelAlias: String?
    public let activationMode: String?
}

public protocol MelixCLIWorkflowRunning: Sendable {
    var surface: MelixCLIWorkflowSurface { get }
    func run(_ command: MelixCLICommand) async throws -> String
}

extension MelixCLIRunner: MelixCLIWorkflowRunning {
    public nonisolated var surface: MelixCLIWorkflowSurface {
        .inProcess
    }
}

extension MelixCLIWorkflowRunning {
    func decodeJSON<Value: Decodable>(
        _ type: Value.Type,
        command: MelixCLICommand
    ) async throws -> Value {
        let output = try await run(command)
        return try decodeMelixCLIJSON(type, output: output, command: command, surface: surface)
    }

    func downloadHubModel(repoID: String, revision: String, hfToken: String = "") async throws -> ManagedModelReceipt {
        let command = MelixCLICommand.modelHubDownload(.init(repoID: repoID, revision: revision, hfToken: hfToken, json: true))
        let output = try await run(command)
        return try decodeManagedModelReceipt(output: output, command: command, surface: surface)
    }

    func importModel(
        path: String,
        modelID: String,
        modelKind: String,
        revision: String
    ) async throws -> ManagedModelReceipt {
        let command = MelixCLICommand.modelImport(
            .init(path: path, modelID: modelID, modelKind: modelKind, revision: revision, json: true)
        )
        let output = try await run(command)
        return try decodeManagedModelReceipt(output: output, command: command, surface: surface)
    }

    func listRuntimeJobs() async throws -> [RuntimeJobSummaryState] {
        let command = MelixCLICommand.jobsList(.init(json: true))
        let output = try await run(command)
        return try decodeRuntimeJobsList(output: output, command: command, surface: surface)
    }

    func showRuntimeJob(jobID: String) async throws -> RuntimeJobDetailState {
        let command = MelixCLICommand.jobsShow(.init(jobID: jobID, json: true))
        let output = try await run(command)
        return try decodeRuntimeJobDetail(output: output, command: command, surface: surface)
    }

    func fetchRuntimeJobLogs(jobID: String) async throws -> RuntimeJobLogSnapshotState {
        let command = MelixCLICommand.jobsLogs(.init(jobID: jobID, json: true))
        let output = try await run(command)
        return try decodeRuntimeJobLogSnapshot(output: output, command: command, surface: surface)
    }

    func fetchRuntimeJobArtifacts(jobID: String) async throws -> RuntimeJobArtifactSnapshotState {
        let command = MelixCLICommand.jobsArtifacts(.init(jobID: jobID, json: true))
        let output = try await run(command)
        return try decodeRuntimeJobArtifactSnapshot(output: output, command: command, surface: surface)
    }

    func cancelRuntimeJob(jobID: String) async throws -> RuntimeJobCancelResultState {
        let command = MelixCLICommand.jobsCancel(.init(jobID: jobID, json: true))
        let output = try await run(command)
        return try decodeRuntimeJobCancelResult(output: output, command: command, surface: surface)
    }

    func listWorkflowRecipes(task: String) async throws -> RuntimeWorkflowRecipeCatalogState {
        let command = MelixCLICommand.recipesList(.init(task: task, json: true))
        let output = try await run(command)
        return try decodeWorkflowRecipeCatalog(output: output, command: command, surface: surface)
    }

    func showWorkflowRecipe(recipeID: String, version: String = "") async throws -> RuntimeWorkflowRecipeDetailState {
        let command = MelixCLICommand.recipesShow(.init(recipeID: recipeID, version: version, json: true))
        let output = try await run(command)
        return try decodeWorkflowRecipeDetail(output: output, command: command, surface: surface)
    }
}

func decodeMelixCLIJSON<Value: Decodable>(
    _ type: Value.Type,
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> Value {
    guard let data = output.data(using: .utf8) else {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }

    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .custom { codingPath in
        let rawKey = codingPath.last?.stringValue ?? ""
        let convertedKey = melixCLIConvertedDecodingKey(rawKey)
        return MelixCLIJSONCodingKey(stringValue: convertedKey)
            ?? MelixCLIJSONCodingKey(stringValue: rawKey)
            ?? MelixCLIJSONCodingKey(intValue: 0)!
    }
    do {
        return try decoder.decode(Value.self, from: data)
    } catch {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }
}

private func decodeManagedModelReceipt(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> ManagedModelReceipt {
    guard let data = output.data(using: .utf8) else {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }

    do {
        return try JSONDecoder().decode(ManagedModelReceipt.self, from: data)
    } catch {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }
}

private func decodeRuntimeJobsList(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> [RuntimeJobSummaryState] {
    try decodeRuntimeJobPayload(output: output, command: command, surface: surface) {
        try RuntimeJobsPayloadDecoder.decodeList($0)
    }
}

private func decodeRuntimeJobDetail(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> RuntimeJobDetailState {
    try decodeRuntimeJobPayload(output: output, command: command, surface: surface) {
        try RuntimeJobsPayloadDecoder.decodeDetail($0)
    }
}

private func decodeRuntimeJobLogSnapshot(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> RuntimeJobLogSnapshotState {
    try decodeRuntimeJobPayload(output: output, command: command, surface: surface) {
        try RuntimeJobsPayloadDecoder.decodeLogSnapshot($0)
    }
}

private func decodeRuntimeJobArtifactSnapshot(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> RuntimeJobArtifactSnapshotState {
    try decodeRuntimeJobPayload(output: output, command: command, surface: surface) {
        try RuntimeJobsPayloadDecoder.decodeArtifactSnapshot($0)
    }
}

private func decodeRuntimeJobCancelResult(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> RuntimeJobCancelResultState {
    try decodeRuntimeJobPayload(output: output, command: command, surface: surface) {
        try RuntimeJobsPayloadDecoder.decodeCancelResult($0)
    }
}

private func decodeWorkflowRecipeCatalog(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> RuntimeWorkflowRecipeCatalogState {
    do {
        return try RuntimeWorkflowRecipesPayloadDecoder.decodeCatalog(output)
    } catch {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }
}

private func decodeWorkflowRecipeDetail(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface
) throws -> RuntimeWorkflowRecipeDetailState {
    do {
        return try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(output)
    } catch {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }
}

private func decodeRuntimeJobPayload<Value>(
    output: String,
    command: MelixCLICommand,
    surface: MelixCLIWorkflowSurface,
    decode: (Data) throws -> Value
) throws -> Value {
    let data = Data(output.utf8)

    do {
        return try decode(data)
    } catch {
        throw MelixCLIWorkflowError.invalidJSON(
            commandID: command.workflowCommandID,
            surface: surface,
            output: output
        )
    }
}

private struct MelixCLIJSONCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?

    init?(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }

    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

private let melixCLIJSONAcronymSegments: [String: String] = [
    "api": "API",
    "hf": "HF",
    "id": "ID",
    "ids": "IDs",
    "json": "JSON",
    "jsonl": "JSONL",
    "ms": "MS",
    "ocr": "OCR",
    "ttl": "TTL",
    "uri": "URI",
    "uris": "URIs",
    "url": "URL",
    "urls": "URLs",
]

private func melixCLIConvertedDecodingKey(_ rawKey: String) -> String {
    guard rawKey.contains("_") else {
        return rawKey
    }

    let segments = rawKey.split(separator: "_").map { $0.lowercased() }
    guard let first = segments.first else {
        return rawKey
    }

    var converted = String(first)
    for segment in segments.dropFirst() {
        if let acronym = melixCLIJSONAcronymSegments[String(segment)] {
            converted += acronym
            continue
        }
        converted += segment.prefix(1).uppercased() + segment.dropFirst()
    }
    return converted
}

extension MelixCLICommand {
    var workflowCommandID: String {
        MelixCLICommandCodec.commandID(for: self)
    }
}
