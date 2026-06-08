import CryptoKit
import Darwin
import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public struct SettingsShowOptions: Equatable, Sendable {
    public let json: Bool
    public let overrides: [String: String]

    public init(json: Bool = false, overrides: [String: String] = [:]) {
        self.json = json
        self.overrides = overrides
    }
}

public struct SettingsSetOptions: Equatable, Sendable {
    public let key: String
    public let value: String
    public let json: Bool

    public init(key: String, value: String, json: Bool = false) {
        self.key = key
        self.value = value
        self.json = json
    }
}

public struct SettingsValidateOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct SettingsResetOptions: Equatable, Sendable {
    public let key: String
    public let json: Bool

    public init(key: String, json: Bool = false) {
        self.key = key
        self.json = json
    }
}

public struct DiscoveryJSONOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct WorkspacePreflightOptions: Equatable, Sendable {
    public let manifestPath: String
    public let outputPath: String
    public let json: Bool

    public init(
        manifestPath: String,
        outputPath: String = "",
        json: Bool = false
    ) {
        self.manifestPath = manifestPath
        self.outputPath = outputPath
        self.json = json
    }
}

public struct DatasetPrepareIngestOptions: Equatable, Sendable {
    public let workspaceProjectID: String
    public let workspaceManifestPath: String
    public let inputPath: String
    public let outputDir: String
    public let datasetPreparationID: String
    public let receiptOutputPath: String
    public let piiMask: Bool
    public let exactDedup: Bool
    public let fuzzyDedup: Bool
    public let segmentation: Bool
    public let segmentationStrategy: String
    public let json: Bool

    public init(
        workspaceProjectID: String,
        workspaceManifestPath: String,
        inputPath: String,
        outputDir: String,
        datasetPreparationID: String,
        receiptOutputPath: String = "",
        piiMask: Bool = true,
        exactDedup: Bool = true,
        fuzzyDedup: Bool = true,
        segmentation: Bool = true,
        segmentationStrategy: String = "paragraph",
        json: Bool = false
    ) {
        self.workspaceProjectID = workspaceProjectID
        self.workspaceManifestPath = workspaceManifestPath
        self.inputPath = inputPath
        self.outputDir = outputDir
        self.datasetPreparationID = datasetPreparationID
        self.receiptOutputPath = receiptOutputPath
        self.piiMask = piiMask
        self.exactDedup = exactDedup
        self.fuzzyDedup = fuzzyDedup
        self.segmentation = segmentation
        self.segmentationStrategy = segmentationStrategy
        self.json = json
    }
}

public struct DatasetPrepareVersionOptions: Equatable, Sendable {
    public let workspaceManifestPath: String
    public let ingestReceiptPath: String
    public let outputRoot: String
    public let datasetID: String
    public let versionID: String
    public let createdAt: String
    public let mode: String
    public let generatorModel: String
    public let outputKind: String
    public let outputFormat: String
    public let validationRatio: String
    public let failSegmentIDs: [String]
    public let json: Bool

    public init(
        workspaceManifestPath: String,
        ingestReceiptPath: String,
        outputRoot: String,
        datasetID: String,
        versionID: String = "",
        createdAt: String = "",
        mode: String = "chat",
        generatorModel: String = "melix.local.dataset-versioner.v1",
        outputKind: String = "training",
        outputFormat: String = "prompt_completion",
        validationRatio: String = "",
        failSegmentIDs: [String] = [],
        json: Bool = false
    ) {
        self.workspaceManifestPath = workspaceManifestPath
        self.ingestReceiptPath = ingestReceiptPath
        self.outputRoot = outputRoot
        self.datasetID = datasetID
        self.versionID = versionID
        self.createdAt = createdAt
        self.mode = mode
        self.generatorModel = generatorModel
        self.outputKind = outputKind
        self.outputFormat = outputFormat
        self.validationRatio = validationRatio
        self.failSegmentIDs = failSegmentIDs
        self.json = json
    }
}

public struct DatasetPrepareRetryFailedOptions: Equatable, Sendable {
    public let workspaceManifestPath: String
    public let datasetVersionPath: String
    public let outputRoot: String
    public let versionID: String
    public let createdAt: String
    public let generatorModel: String
    public let json: Bool

    public init(
        workspaceManifestPath: String,
        datasetVersionPath: String,
        outputRoot: String,
        versionID: String = "",
        createdAt: String = "",
        generatorModel: String = "",
        json: Bool = false
    ) {
        self.workspaceManifestPath = workspaceManifestPath
        self.datasetVersionPath = datasetVersionPath
        self.outputRoot = outputRoot
        self.versionID = versionID
        self.createdAt = createdAt
        self.generatorModel = generatorModel
        self.json = json
    }
}

public struct DatasetPrepareListVersionsOptions: Equatable, Sendable {
    public let workspaceManifestPath: String
    public let outputRoot: String
    public let datasetID: String
    public let json: Bool

    public init(
        workspaceManifestPath: String,
        outputRoot: String,
        datasetID: String,
        json: Bool = false
    ) {
        self.workspaceManifestPath = workspaceManifestPath
        self.outputRoot = outputRoot
        self.datasetID = datasetID
        self.json = json
    }
}

public struct CapabilitiesOptions: Equatable, Sendable {
    public let json: Bool
    public let modelQuery: String

    public init(json: Bool = false, modelQuery: String = "") {
        self.json = json
        self.modelQuery = modelQuery
    }
}

enum MelixQuantizationAllowedValues {
    static let quantizationModes = ["ptq", "qat"]
    static let sourceArtifactKinds = ["base_model", "merged_adapter", "adapter_export"]
    static let quantizationBackends = ["manifest_only", "mlx_lm_convert"]
    static let mlxLMQModes = ["affine", "mxfp4", "nvfp4", "mxfp8"]

    static func renderedList(_ values: [String]) -> String {
        values.joined(separator: ", ")
    }
}

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
    public let trainingMode: String
    public let parameters: [String: String]
    public let preflightFitCheck: Bool
    public let allowMemoryRisk: Bool
    public let json: Bool

    public init(
        modelID: String,
        datasetSourceKind: String = "local_package",
        datasetURI: String,
        adapterName: String,
        targetRepo: String = "",
        trainingMode: String = "",
        parameters: [String: String] = [:],
        preflightFitCheck: Bool = false,
        allowMemoryRisk: Bool = false,
        json: Bool = false
    ) {
        self.modelID = modelID
        self.datasetSourceKind = datasetSourceKind
        self.datasetURI = datasetURI
        self.adapterName = adapterName
        self.targetRepo = targetRepo
        self.trainingMode = trainingMode
        self.parameters = parameters
        self.preflightFitCheck = preflightFitCheck
        self.allowMemoryRisk = allowMemoryRisk
        self.json = json
    }
}

public struct LoraRunOptions: Equatable, Sendable {
    public let training: LoraTrainOptions
    public let activationMode: String
    public let evaluation: EvalCompareOptions
    public let outputDir: String
    public let json: Bool

    public init(
        training: LoraTrainOptions,
        activationMode: String = "adapter_backed_runtime",
        evaluation: EvalCompareOptions,
        outputDir: String = "",
        json: Bool = false
    ) {
        self.training = training
        self.activationMode = activationMode
        self.evaluation = evaluation
        self.outputDir = outputDir
        self.json = json
    }
}

public struct AlignmentTrainOptions: Equatable, Sendable {
    public let modelID: String
    public let datasetSourceKind: String
    public let datasetURI: String
    public let adapterName: String
    public let targetRepo: String
    public let algorithm: String
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String,
        datasetSourceKind: String = "local_package",
        datasetURI: String,
        adapterName: String,
        targetRepo: String = "",
        algorithm: String,
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.datasetSourceKind = datasetSourceKind
        self.datasetURI = datasetURI
        self.adapterName = adapterName
        self.targetRepo = targetRepo
        self.algorithm = algorithm
        self.parameters = parameters
        self.json = json
    }
}

public struct LoraDatasetInspectOptions: Equatable, Sendable {
    public let modelID: String
    public let datasetSourceKind: String
    public let datasetURI: String
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String,
        datasetSourceKind: String = "local_path",
        datasetURI: String,
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.datasetSourceKind = datasetSourceKind
        self.datasetURI = datasetURI
        self.parameters = parameters
        self.json = json
    }
}

public struct LoraDatasetBuildOptions: Equatable, Sendable {
    public let modelID: String
    public let datasetSourceKind: String
    public let datasetURI: String
    public let outputDir: String
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String,
        datasetSourceKind: String = "local_path",
        datasetURI: String,
        outputDir: String = "",
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.datasetSourceKind = datasetSourceKind
        self.datasetURI = datasetURI
        self.outputDir = outputDir
        self.parameters = parameters
        self.json = json
    }
}

public struct LoraActivateOptions: Equatable, Sendable {
    public let modelID: String
    public let adapterPath: String
    public let derivedModelAlias: String
    public let activationMode: String
    public let json: Bool

    public init(
        modelID: String,
        adapterPath: String,
        derivedModelAlias: String = "",
        activationMode: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.adapterPath = adapterPath
        self.derivedModelAlias = derivedModelAlias
        self.activationMode = activationMode
        self.json = json
    }
}

public struct LoraRemoveDerivedOptions: Equatable, Sendable {
    public let modelID: String
    public let derivedModelID: String
    public let manifestPath: String
    public let json: Bool

    public init(
        modelID: String,
        derivedModelID: String = "",
        manifestPath: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.derivedModelID = derivedModelID
        self.manifestPath = manifestPath
        self.json = json
    }
}

public enum LoraPublishExportKind: String, Equatable, Sendable {
    case adapterExport = "adapter_export"
    case mergedExport = "merged_export"
}

public struct LoraPublishOptions: Equatable, Sendable {
    public let modelID: String
    public let targetRepo: String
    /// `nil` defers export-kind classification to the runner, which reads
    /// the manifest at `artifactManifestPath` and picks adapter vs merged
    /// based on `schema_version` / `artifact_kind` / `activation_mode`.
    /// Non-nil values are validated against the manifest when the file is
    /// readable, so a mismatched override surfaces as a clean CLI usage
    /// error rather than a downstream worker error.
    public let exportKind: LoraPublishExportKind?
    public let artifactPath: String
    public let artifactManifestPath: String
    public let publishBackend: String
    public let localPublishRoot: String
    public let json: Bool

    public init(
        modelID: String,
        targetRepo: String,
        exportKind: LoraPublishExportKind?,
        artifactPath: String,
        artifactManifestPath: String = "",
        publishBackend: String = "",
        localPublishRoot: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.targetRepo = targetRepo
        self.exportKind = exportKind
        self.artifactPath = artifactPath
        self.artifactManifestPath = artifactManifestPath
        self.publishBackend = publishBackend
        self.localPublishRoot = localPublishRoot
        self.json = json
    }
}

public struct LoraExperimentsListOptions: Equatable, Sendable {
    public let modelID: String
    public let json: Bool

    public init(modelID: String = "", json: Bool = false) {
        self.modelID = modelID
        self.json = json
    }
}

public struct LoraExperimentsShowOptions: Equatable, Sendable {
    public let modelID: String
    public let groupID: String
    public let json: Bool

    public init(modelID: String = "", groupID: String, json: Bool = false) {
        self.modelID = modelID
        self.groupID = groupID
        self.json = json
    }
}

public struct LoraPublishesListOptions: Equatable, Sendable {
    public let modelID: String
    public let json: Bool

    public init(modelID: String = "", json: Bool = false) {
        self.modelID = modelID
        self.json = json
    }
}

public struct LoraPublishesShowOptions: Equatable, Sendable {
    public let modelID: String
    public let jobID: String
    public let json: Bool

    public init(modelID: String = "", jobID: String, json: Bool = false) {
        self.modelID = modelID
        self.jobID = jobID
        self.json = json
    }
}

public struct LoraResumeOptions: Equatable, Sendable {
    public let modelID: String
    public let groupID: String
    public let presetID: String
    public let adapterName: String
    public let datasetURI: String
    public let json: Bool

    public init(
        modelID: String = "",
        groupID: String,
        presetID: String = "",
        adapterName: String = "",
        datasetURI: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.groupID = groupID
        self.presetID = presetID
        self.adapterName = adapterName
        self.datasetURI = datasetURI
        self.json = json
    }
}

public struct EstimateImportOptions: Equatable, Sendable {
    public let repoID: String
    public let targetKind: String
    public let targetInputs: [String: String]
    public let json: Bool

    public init(
        repoID: String,
        targetKind: String = "import",
        targetInputs: [String: String] = [:],
        json: Bool = false
    ) {
        self.repoID = repoID
        self.targetKind = targetKind
        self.targetInputs = targetInputs
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
    public let preflightFitCheck: Bool
    public let allowMemoryRisk: Bool
    public let json: Bool
    public let liveProgress: Bool

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
        preflightFitCheck: Bool = false,
        allowMemoryRisk: Bool = false,
        json: Bool = false,
        liveProgress: Bool = true
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.suites = suites
        self.contextLengths = ControlPlaneBenchRequest.normalizedBenchValues(contextLengths)
        self.generationLength = generationLength
        self.batchSizes = ControlPlaneBenchRequest.normalizedBenchValues(batchSizes)
        self.repeats = ControlPlaneBenchRequest.normalizedRepeats(repeats)
        self.cacheProfile = cacheProfile
        self.reasoningMode = reasoningMode
        self.structuredOutputMode = structuredOutputMode
        self.parameters = parameters
        self.preflightFitCheck = preflightFitCheck
        self.allowMemoryRisk = allowMemoryRisk
        self.json = json
        self.liveProgress = liveProgress
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
    public let liveProgress: Bool

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
        json: Bool = false,
        liveProgress: Bool = true
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
        self.repeats = ControlPlaneBenchRequest.normalizedRepeats(repeats)
        self.requests = requests
        self.durationSeconds = durationSeconds
        self.allowLargeMatrix = allowLargeMatrix
        self.json = json
        self.liveProgress = liveProgress
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

public struct EvalRemoteTargetOptions: Equatable, Sendable {
    public let remoteServerID: String
    public let remoteModelID: String

    public init(remoteServerID: String, remoteModelID: String = "") {
        self.remoteServerID = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.remoteModelID = remoteModelID.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

public struct EvalRunOptions: Equatable, Sendable {
    public let modelID: String
    public let hfRepoID: String
    public let remoteServerID: String
    public let remoteModelID: String
    public let remoteTargets: [EvalRemoteTargetOptions]
    public let suites: [String]
    public let datasetID: String
    public let sampleSize: UInt32
    public let source: ControlPlaneEvaluationRequest.Source
    public let fieldMapping: ControlPlaneEvaluationRequest.FieldMapping
    public let profile: ControlPlaneEvaluationRequest.Profile
    public let parameters: [String: String]
    public let evalPromptID: String
    public let evalPromptRevisionID: String
    public let evalPrompt: String
    public let evalPromptFile: String
    public let semanticJudgeRemoteServerID: String
    public let semanticJudgeModelID: String
    public let remoteParallelism: UInt32
    public let preflightFitCheck: Bool
    public let allowMemoryRisk: Bool
    public let json: Bool
    public let liveProgress: Bool

    public init(
        modelID: String = "",
        hfRepoID: String = "",
        remoteServerID: String = "",
        remoteModelID: String = "",
        remoteTargets: [EvalRemoteTargetOptions] = [],
        suites: [String] = [],
        datasetID: String = "",
        sampleSize: UInt32 = 0,
        source: ControlPlaneEvaluationRequest.Source = .builtinPackage,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping = .init(),
        profile: ControlPlaneEvaluationRequest.Profile = .init(),
        parameters: [String: String] = [:],
        evalPromptID: String = "",
        evalPromptRevisionID: String = "",
        evalPrompt: String = "",
        evalPromptFile: String = "",
        semanticJudgeRemoteServerID: String = "",
        semanticJudgeModelID: String = "",
        remoteParallelism: UInt32 = 0,
        preflightFitCheck: Bool = false,
        allowMemoryRisk: Bool = false,
        json: Bool = false,
        liveProgress: Bool = true
    ) {
        let normalizedRemoteTargets = remoteTargets
            .map { EvalRemoteTargetOptions(remoteServerID: $0.remoteServerID, remoteModelID: $0.remoteModelID) }
            .filter { $0.remoteServerID.isEmpty == false }
        let compatibilityRemoteTarget = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? []
            : [
                EvalRemoteTargetOptions(
                    remoteServerID: remoteServerID,
                    remoteModelID: remoteModelID
                ),
            ]
        let resolvedRemoteTargets = normalizedRemoteTargets.isEmpty
            ? compatibilityRemoteTarget
            : normalizedRemoteTargets
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.remoteServerID = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? (resolvedRemoteTargets.first?.remoteServerID ?? "")
            : remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.remoteModelID = remoteModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? (resolvedRemoteTargets.first?.remoteModelID ?? "")
            : remoteModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.remoteTargets = resolvedRemoteTargets
        self.suites = suites
        self.datasetID = datasetID
        self.sampleSize = sampleSize
        self.source = source
        self.fieldMapping = fieldMapping
        self.profile = profile
        self.parameters = parameters
        self.evalPromptID = evalPromptID
        self.evalPromptRevisionID = evalPromptRevisionID
        self.evalPrompt = evalPrompt
        self.evalPromptFile = evalPromptFile
        self.semanticJudgeRemoteServerID = semanticJudgeRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.semanticJudgeModelID = semanticJudgeModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.remoteParallelism = remoteParallelism
        self.preflightFitCheck = preflightFitCheck
        self.allowMemoryRisk = allowMemoryRisk
        self.json = json
        self.liveProgress = liveProgress
    }
}

public struct EvalPromptListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct EvalPromptShowOptions: Equatable, Sendable {
    public let promptID: String
    public let revisionID: String
    public let json: Bool

    public init(promptID: String, revisionID: String = "", json: Bool = false) {
        self.promptID = promptID
        self.revisionID = revisionID
        self.json = json
    }
}

public struct EvalPromptCreateOptions: Equatable, Sendable {
    public let promptID: String
    public let title: String
    public let systemPromptFile: String
    public let json: Bool

    public init(promptID: String, title: String, systemPromptFile: String, json: Bool = false) {
        self.promptID = promptID
        self.title = title
        self.systemPromptFile = systemPromptFile
        self.json = json
    }
}

public struct EvalPromptUpdateOptions: Equatable, Sendable {
    public let promptID: String
    public let systemPromptFile: String
    public let json: Bool

    public init(promptID: String, systemPromptFile: String, json: Bool = false) {
        self.promptID = promptID
        self.systemPromptFile = systemPromptFile
        self.json = json
    }
}

public struct EvalPromptFreezeOptions: Equatable, Sendable {
    public let promptID: String
    public let revisionID: String
    public let json: Bool

    public init(promptID: String, revisionID: String = "", json: Bool = false) {
        self.promptID = promptID
        self.revisionID = revisionID
        self.json = json
    }
}

public struct EvalPromptArchiveOptions: Equatable, Sendable {
    public let promptID: String
    public let json: Bool

    public init(promptID: String, json: Bool = false) {
        self.promptID = promptID
        self.json = json
    }
}

private struct PlannedEvaluationRequest: Sendable {
    let index: Int
    let request: ControlPlaneEvaluationRequest
}

public struct MelixCLITerminalCapabilities: Equatable, Sendable {
    public let isInteractive: Bool
    public let supportsANSI: Bool

    public init(isInteractive: Bool, supportsANSI: Bool) {
        self.isInteractive = isInteractive
        self.supportsANSI = supportsANSI
    }

    public static func detect(environment: [String: String]) -> MelixCLITerminalCapabilities {
        let term = environment["TERM"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        let noColor = environment["NO_COLOR"] != nil
        let interactive = Darwin.isatty(STDOUT_FILENO) == 1
        return MelixCLITerminalCapabilities(
            isInteractive: interactive,
            supportsANSI: interactive && term.isEmpty == false && term != "dumb" && noColor == false
        )
    }
}

public struct MelixCLILiveRunStep: Equatable, Sendable {
    public enum Phase: String, Sendable {
        case pending
        case running
        case completed
        case failed
    }

    public let id: String
    public let title: String
    public var phase: Phase

    public init(id: String, title: String, phase: Phase = .pending) {
        self.id = id
        self.title = title
        self.phase = phase
    }
}

public struct MelixCLILiveRunState: Equatable, Sendable {
    public enum Phase: String, Sendable {
        case running
        case completed
        case failed
    }

    public let title: String
    public let targetText: String
    public let suiteText: String
    public var phase: Phase
    public var statusText: String
    public var steps: [MelixCLILiveRunStep]
    public var primaryMetricText: String
    public var artifactText: String
    public var detailText: String
    public var elapsedSeconds: Double
    public var progressFraction: Double {
        if phase == .completed {
            return 1
        }
        guard steps.isEmpty == false else {
            return phase == .failed ? 0 : 0.1
        }
        if let activeIndex = steps.firstIndex(where: { $0.phase == .running }) {
            return min(0.95, max(0.1, (Double(activeIndex) + 0.35) / Double(steps.count)))
        }
        let completedCount = steps.filter { $0.phase == .completed }.count
        if phase == .failed {
            return min(0.95, max(0.1, Double(completedCount) / Double(steps.count)))
        }
        return min(0.95, max(0.1, Double(completedCount) / Double(steps.count)))
    }

    public init(
        title: String,
        targetText: String,
        suiteText: String,
        phase: Phase = .running,
        statusText: String = "Running",
        steps: [MelixCLILiveRunStep],
        primaryMetricText: String = "",
        artifactText: String = "",
        detailText: String = "",
        elapsedSeconds: Double = 0
    ) {
        self.title = title
        self.targetText = targetText
        self.suiteText = suiteText
        self.phase = phase
        self.statusText = statusText
        self.steps = steps
        self.primaryMetricText = primaryMetricText
        self.artifactText = artifactText
        self.detailText = detailText
        self.elapsedSeconds = elapsedSeconds
    }

    mutating func move(to stepID: String, detailText: String, elapsedSeconds: Double) {
        phase = .running
        statusText = "Running"
        self.detailText = detailText
        self.elapsedSeconds = elapsedSeconds
        guard let activeIndex = steps.firstIndex(where: { $0.id == stepID }) else {
            return
        }
        for index in steps.indices {
            if index < activeIndex {
                steps[index].phase = .completed
            } else if index == activeIndex {
                steps[index].phase = .running
            } else {
                steps[index].phase = .pending
            }
        }
    }

    mutating func finish(
        primaryMetricText: String,
        artifactText: String,
        detailText: String,
        elapsedSeconds: Double
    ) {
        phase = .completed
        statusText = "Completed"
        self.primaryMetricText = primaryMetricText
        self.artifactText = artifactText
        self.detailText = detailText
        self.elapsedSeconds = elapsedSeconds
        for index in steps.indices {
            steps[index].phase = .completed
        }
    }

    mutating func fail(detailText: String, elapsedSeconds: Double) {
        phase = .failed
        statusText = "Failed"
        self.detailText = detailText
        self.elapsedSeconds = elapsedSeconds
        if let activeIndex = steps.firstIndex(where: { $0.phase == .running }) {
            steps[activeIndex].phase = .failed
        } else if let pendingIndex = steps.firstIndex(where: { $0.phase == .pending }) {
            steps[pendingIndex].phase = .failed
        } else if let lastIndex = steps.indices.last {
            steps[lastIndex].phase = .failed
        }
    }
}

public final class MelixCLILiveRunDisplay: @unchecked Sendable {
    private let capabilities: MelixCLITerminalCapabilities
    private let write: @Sendable (String) -> Void
    private var renderedLineCount = 0

    public var supportsContinuousRefresh: Bool {
        capabilities.isInteractive && capabilities.supportsANSI
    }

    public init(
        capabilities: MelixCLITerminalCapabilities,
        write: @escaping @Sendable (String) -> Void
    ) {
        self.capabilities = capabilities
        self.write = write
    }

    public func render(_ state: MelixCLILiveRunState, final: Bool = false) {
        guard capabilities.isInteractive else {
            if final {
                write(Self.appendOnlySummary(state))
            }
            return
        }
        let text = Self.renderPanel(state)
        if capabilities.supportsANSI {
            if renderedLineCount > 0 {
                write("\u{001B}[\(renderedLineCount)A")
            }
            let lines = text.split(separator: "\n", omittingEmptySubsequences: false)
            write(lines.map { "\u{001B}[2K" + $0 }.joined(separator: "\n") + "\n")
            renderedLineCount = lines.count
            if final {
                renderedLineCount = 0
            }
        } else {
            write(Self.appendOnlySummary(state))
        }
    }

    public static func renderPanel(_ state: MelixCLILiveRunState) -> String {
        let progressPercent = progressPercentText(state.progressFraction)
        var lines = [
            "Melix \(state.title)",
            "\(phaseLabel(state.phase)) \(state.statusText)   progress \(progressPercent)   elapsed \(durationText(state.elapsedSeconds))",
            "Target \(emptyPlaceholder(state.targetText))",
            "Suite  \(emptyPlaceholder(state.suiteText))",
            "",
            "Progress \(progressPercent) \(progressBar(fraction: state.progressFraction))",
        ]
        lines.append(contentsOf: state.steps.map { step in
            "  \(stepSymbol(step.phase)) \(step.title)"
        })
        lines.append("")
        lines.append("Metric   \(emptyPlaceholder(state.primaryMetricText, placeholder: "Collecting metrics"))")
        lines.append("Artifact \(emptyPlaceholder(state.artifactText, placeholder: "Pending"))")
        if state.detailText.isEmpty == false {
            lines.append("Detail   \(state.detailText)")
        }
        return lines.joined(separator: "\n")
    }

    public static func appendOnlySummary(_ state: MelixCLILiveRunState) -> String {
        let activeStep = state.steps.last(where: { $0.phase == .running })?.title
            ?? state.steps.last(where: { $0.phase == .failed })?.title
            ?? state.steps.last(where: { $0.phase == .completed })?.title
            ?? state.title
        var segments = [
            "[\(phaseLabel(state.phase))]",
            state.title,
            activeStep,
            "progress=\(progressPercentText(state.progressFraction))",
            "elapsed=\(durationText(state.elapsedSeconds))",
        ]
        if state.primaryMetricText.isEmpty == false {
            segments.append("metric=\(state.primaryMetricText)")
        }
        if state.artifactText.isEmpty == false {
            segments.append("artifact=\(state.artifactText)")
        }
        if state.detailText.isEmpty == false {
            segments.append(state.detailText)
        }
        return segments.joined(separator: " ") + "\n"
    }

    private static func phaseLabel(_ phase: MelixCLILiveRunState.Phase) -> String {
        switch phase {
        case .running:
            return "RUNNING"
        case .completed:
            return "DONE"
        case .failed:
            return "FAILED"
        }
    }

    private static func stepSymbol(_ phase: MelixCLILiveRunStep.Phase) -> String {
        switch phase {
        case .pending:
            return "○"
        case .running:
            return "●"
        case .completed:
            return "✓"
        case .failed:
            return "!"
        }
    }

    private static func durationText(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds > 0 else {
            return "0s"
        }
        if seconds < 10 {
            return String(format: "%.1fs", seconds)
        }
        return "\(Int(seconds.rounded()))s"
    }

    private static func progressPercentText(_ fraction: Double) -> String {
        let percent = Int((min(1, max(0, fraction)) * 100).rounded())
        return "\(percent)%"
    }

    private static func progressBar(fraction: Double, width: Int = 24) -> String {
        let clampedFraction = min(1, max(0, fraction))
        let filled = Int((clampedFraction * Double(width)).rounded())
        return "[" + String(repeating: "█", count: filled) + String(repeating: "░", count: max(0, width - filled)) + "]"
    }

    private static func emptyPlaceholder(_ value: String, placeholder: String = "n/a") -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? placeholder : value
    }
}

public struct EvalCompareOptions: Equatable, Sendable {
    public let modelID: String
    public let hfRepoID: String
    public let targetModelIDs: [String]
    /// Adapter-manifest paths to materialize as ephemeral compare targets.
    /// Each is a path to a ``melix.lora_adapter_package.v1`` manifest; the
    /// worker loads the adapter for the compare run and unloads it before
    /// returning (Module 2 from the LoRA capability plan).
    public let targetAdapterManifestPaths: [String]
    public let suites: [String]
    public let datasetID: String
    public let sampleSize: UInt32
    public let source: ControlPlaneEvaluationRequest.Source
    public let fieldMapping: ControlPlaneEvaluationRequest.FieldMapping
    public let profile: ControlPlaneEvaluationRequest.Profile
    public let parameters: [String: String]
    public let evalPromptID: String
    public let evalPromptRevisionID: String
    public let evalPrompt: String
    public let evalPromptFile: String
    public let semanticJudgeRemoteServerID: String
    public let semanticJudgeModelID: String
    public let json: Bool
    public let liveProgress: Bool

    public init(
        modelID: String = "",
        hfRepoID: String = "",
        targetModelIDs: [String] = [],
        targetAdapterManifestPaths: [String] = [],
        suites: [String] = [],
        datasetID: String = "",
        sampleSize: UInt32 = 0,
        source: ControlPlaneEvaluationRequest.Source = .builtinPackage,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping = .init(),
        profile: ControlPlaneEvaluationRequest.Profile = .init(),
        parameters: [String: String] = [:],
        evalPromptID: String = "",
        evalPromptRevisionID: String = "",
        evalPrompt: String = "",
        evalPromptFile: String = "",
        semanticJudgeRemoteServerID: String = "",
        semanticJudgeModelID: String = "",
        json: Bool = false,
        liveProgress: Bool = true
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.targetModelIDs = targetModelIDs.filter { $0.isEmpty == false }
        self.targetAdapterManifestPaths = targetAdapterManifestPaths.filter { $0.isEmpty == false }
        self.suites = suites
        self.datasetID = datasetID
        self.sampleSize = sampleSize
        self.source = source
        self.fieldMapping = fieldMapping
        self.profile = profile
        self.parameters = parameters
        self.evalPromptID = evalPromptID
        self.evalPromptRevisionID = evalPromptRevisionID
        self.evalPrompt = evalPrompt
        self.evalPromptFile = evalPromptFile
        self.semanticJudgeRemoteServerID = semanticJudgeRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.semanticJudgeModelID = semanticJudgeModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.json = json
        self.liveProgress = liveProgress
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
    public let serverTitle: String
    public let defaultModelID: String
    public let servedModelIDs: [String]
    public let host: String
    public let port: Int
    public let allowedHosts: [String]
    public let allowedOrigins: [String]
    public let rateLimitPerMinute: Int
    public let timeoutSeconds: Int
    public let modelIdleTimeoutSeconds: Int
    public let json: Bool

    public init(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        serverTitle: String = "",
        defaultModelID: String = "",
        servedModelIDs: [String] = [],
        host: String = "",
        port: Int = 0,
        allowedHosts: [String] = [],
        allowedOrigins: [String] = [],
        rateLimitPerMinute: Int = 0,
        timeoutSeconds: Int = 0,
        modelIdleTimeoutSeconds: Int = 0,
        json: Bool = false
    ) {
        if serverSessionID.isEmpty || serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID {
            self.serverSessionID = MelixServerStartShortcutName.sessionIDCandidate(for: serverTitle)
                ?? ServerSessionRuntimeStore.defaultServerSessionID
        } else {
            self.serverSessionID = serverSessionID
        }
        self.serverTitle = serverTitle
        let resolvedDefaultModelID = MelixServerModelRosterNormalizer.resolvedDefaultModelID(
            defaultModelID,
            servedModelIDs: servedModelIDs
        )
        self.defaultModelID = resolvedDefaultModelID
        self.servedModelIDs = servedModelIDs.isEmpty
            ? []
            : MelixServerModelRosterNormalizer.normalized(
                servedModelIDs,
                defaultModelID: resolvedDefaultModelID
            )
        self.host = host
        self.port = port
        self.allowedHosts = normalizedServerAllowlist(allowedHosts)
        self.allowedOrigins = normalizedServerAllowlist(allowedOrigins)
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
        self.json = json
    }

}

private enum MelixServerStartShortcutName {
    private static let allowedSessionIDScalars = CharacterSet(
        charactersIn: "abcdefghijklmnopqrstuvwxyz0123456789._-"
    )

    static func sessionIDCandidate(for title: String) -> String? {
        let candidate = title.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !candidate.isEmpty else {
            return nil
        }
        guard candidate.rangeOfCharacter(from: allowedSessionIDScalars.inverted) == nil else {
            return nil
        }
        return candidate
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
    public let hfToken: String
    public let json: Bool

    public init(repoID: String, revision: String = "main", hfToken: String = "", json: Bool = false) {
        self.repoID = repoID
        self.revision = revision.isEmpty ? "main" : revision
        self.hfToken = hfToken
        self.json = json
    }
}

public struct DatasetListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct DatasetHubDownloadOptions: Equatable, Sendable {
    public let repoID: String
    public let revision: String
    public let hfToken: String
    public let json: Bool

    public init(repoID: String, revision: String = "main", hfToken: String = "", json: Bool = false) {
        self.repoID = repoID
        self.revision = revision.isEmpty ? "main" : revision
        self.hfToken = hfToken
        self.json = json
    }
}

public struct DatasetRemoveOptions: Equatable, Sendable {
    public let repoID: String
    public let revision: String
    public let snapshotID: String
    public let json: Bool

    public init(repoID: String, revision: String = "main", snapshotID: String = "", json: Bool = false) {
        self.repoID = repoID
        self.revision = revision.isEmpty ? "main" : revision
        self.snapshotID = snapshotID
        self.json = json
    }
}

public struct DatasetSyntheticOptions: Equatable, Sendable {
    public let mode: String
    public let datasetID: String
    public let datasetName: String
    public let numRecords: UInt32
    public let outputKind: String
    public let outputFormat: String
    public let outputDir: String
    public let providerEndpoint: String
    public let providerName: String
    public let providerType: String
    public let apiKey: String
    public let headers: [String]
    public let modelAlias: String
    public let model: String
    public let temperature: String
    public let topP: String
    public let maxTokens: UInt32
    public let timeoutSeconds: String
    public let maxParallelRequests: UInt32
    public let extraBodyJSON: String
    public let columns: [String]
    public let seedSourceKind: String
    public let seedSourcePath: String
    public let validationRatio: String
    public let previewCount: UInt32
    public let randomSeed: Int?
    public let resume: String
    public let enableDataDesignerTelemetry: Bool
    public let json: Bool

    public init(
        mode: String,
        datasetID: String,
        datasetName: String,
        numRecords: UInt32,
        outputKind: String,
        outputFormat: String,
        outputDir: String,
        providerEndpoint: String,
        providerName: String = "melix",
        providerType: String = "openai",
        apiKey: String = "",
        headers: [String] = [],
        modelAlias: String = "generator",
        model: String,
        temperature: String = "",
        topP: String = "",
        maxTokens: UInt32 = 0,
        timeoutSeconds: String = "",
        maxParallelRequests: UInt32 = 0,
        extraBodyJSON: String = "",
        columns: [String],
        seedSourceKind: String = "",
        seedSourcePath: String = "",
        validationRatio: String = "",
        previewCount: UInt32 = 3,
        randomSeed: Int? = nil,
        resume: String = "never",
        enableDataDesignerTelemetry: Bool = false,
        json: Bool = false
    ) {
        self.mode = mode
        self.datasetID = datasetID
        self.datasetName = datasetName
        self.numRecords = numRecords
        self.outputKind = outputKind
        self.outputFormat = outputFormat
        self.outputDir = outputDir
        self.providerEndpoint = providerEndpoint
        self.providerName = providerName.isEmpty ? "melix" : providerName
        self.providerType = providerType.isEmpty ? "openai" : providerType
        self.apiKey = apiKey
        self.headers = headers
        self.modelAlias = modelAlias.isEmpty ? "generator" : modelAlias
        self.model = model
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.timeoutSeconds = timeoutSeconds
        self.maxParallelRequests = maxParallelRequests
        self.extraBodyJSON = extraBodyJSON
        self.columns = columns
        self.seedSourceKind = seedSourceKind
        self.seedSourcePath = seedSourcePath
        self.validationRatio = validationRatio
        self.previewCount = previewCount == 0 ? 3 : previewCount
        self.randomSeed = randomSeed
        self.resume = resume.isEmpty ? "never" : resume
        self.enableDataDesignerTelemetry = enableDataDesignerTelemetry
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

public struct ModelImportOptions: Equatable, Sendable {
    public let path: String
    public let modelID: String
    public let modelKind: String
    public let revision: String
    public let json: Bool

    public init(
        path: String,
        modelID: String,
        modelKind: String = "text",
        revision: String = "main",
        json: Bool = false
    ) {
        self.path = path
        self.modelID = modelID
        self.modelKind = modelKind.isEmpty ? "text" : modelKind
        self.revision = revision.isEmpty ? "main" : revision
        self.json = json
    }
}

public struct DoctorOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct SystemOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct MonitorOptions: Equatable, Sendable {
    public let sourcePath: String
    public let json: Bool

    public init(sourcePath: String = "", json: Bool = false) {
        self.sourcePath = sourcePath
        self.json = json
    }
}

public struct ConvertOptions: Equatable, Sendable {
    public let modelID: String
    public let outputDir: String
    public let targetFormat: String
    public let json: Bool

    public init(
        modelID: String,
        outputDir: String = "",
        targetFormat: String = "melix_model_bundle",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.outputDir = outputDir
        self.targetFormat = targetFormat.isEmpty ? "melix_model_bundle" : targetFormat
        self.json = json
    }
}

public struct QuantizeOptions: Equatable, Sendable {
    public let modelID: String
    public let outputDir: String
    public let quantProfileID: String
    public let weightQuant: String
    public let kvQuant: String
    public let quantizationMode: String
    public let sourceArtifactKind: String
    public let sourceArtifactPath: String
    public let quantizationBackend: String
    public let mlxLMQBits: String
    public let mlxLMQGroupSize: String
    public let mlxLMQMode: String
    public let calibrationDatasetURI: String
    public let qualityDelta: String
    public let latencyDelta: String
    public let localInferenceSmokeMode: String
    public let localInferenceSmokePrompt: String
    public let json: Bool

    // The parser and pipeline runner pass optional enum-like fields already
    // trimmed and lowercased; this initializer preserves direct caller input.
    public init(
        modelID: String,
        outputDir: String = "",
        quantProfileID: String = "",
        weightQuant: String = "",
        kvQuant: String = "",
        quantizationMode: String = "",
        sourceArtifactKind: String = "",
        sourceArtifactPath: String = "",
        quantizationBackend: String = "",
        mlxLMQBits: String = "",
        mlxLMQGroupSize: String = "",
        mlxLMQMode: String = "",
        calibrationDatasetURI: String = "",
        qualityDelta: String = "",
        latencyDelta: String = "",
        localInferenceSmokeMode: String = "",
        localInferenceSmokePrompt: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.outputDir = outputDir
        self.quantProfileID = quantProfileID
        self.weightQuant = weightQuant
        self.kvQuant = kvQuant
        self.quantizationMode = quantizationMode
        self.sourceArtifactKind = sourceArtifactKind
        self.sourceArtifactPath = sourceArtifactPath
        self.quantizationBackend = quantizationBackend
        self.mlxLMQBits = mlxLMQBits
        self.mlxLMQGroupSize = mlxLMQGroupSize
        self.mlxLMQMode = mlxLMQMode
        self.calibrationDatasetURI = calibrationDatasetURI
        self.qualityDelta = qualityDelta
        self.latencyDelta = latencyDelta
        self.localInferenceSmokeMode = localInferenceSmokeMode
        self.localInferenceSmokePrompt = localInferenceSmokePrompt
        self.json = json
    }
}

public struct UploadOptions: Equatable, Sendable {
    public let modelID: String
    public let outputDir: String
    public let targetRepo: String
    public let artifactPath: String
    public let artifactKind: String
    public let artifactManifestPath: String
    public let publishBackend: String
    public let localPublishRoot: String
    public let json: Bool

    public init(
        modelID: String,
        outputDir: String = "",
        targetRepo: String,
        artifactPath: String = "",
        artifactKind: String = "",
        artifactManifestPath: String = "",
        publishBackend: String = "",
        localPublishRoot: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.outputDir = outputDir
        self.targetRepo = targetRepo
        self.artifactPath = artifactPath
        self.artifactKind = artifactKind
        self.artifactManifestPath = artifactManifestPath
        self.publishBackend = publishBackend
        self.localPublishRoot = localPublishRoot
        self.json = json
    }
}

public struct ManagedModelReceipt: Codable, Equatable, Sendable {
    public let modelID: String
    public let managedModelPath: String
    public let sourceKind: String
    public let sourceLocator: String
    public let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id"
        case managedModelPath = "managed_model_path"
        case sourceKind = "source_kind"
        case sourceLocator = "source_locator"
        case warnings
    }

    public init(
        modelID: String,
        managedModelPath: String,
        sourceKind: String,
        sourceLocator: String,
        warnings: [String] = []
    ) {
        self.modelID = modelID
        self.managedModelPath = managedModelPath
        self.sourceKind = sourceKind
        self.sourceLocator = sourceLocator
        self.warnings = warnings
    }
}

public struct ManagedDatasetReceipt: Codable, Equatable, Sendable {
    public let datasetID: String
    public let repoID: String
    public let revision: String
    public let snapshotID: String
    public let managedDatasetPath: String
    public let sourceKind: String

    enum CodingKeys: String, CodingKey {
        case datasetID = "dataset_id"
        case repoID = "repo_id"
        case revision
        case snapshotID = "snapshot_id"
        case managedDatasetPath = "managed_dataset_path"
        case sourceKind = "source_kind"
    }

    public init(
        datasetID: String,
        repoID: String,
        revision: String,
        snapshotID: String,
        managedDatasetPath: String,
        sourceKind: String
    ) {
        self.datasetID = datasetID
        self.repoID = repoID
        self.revision = revision
        self.snapshotID = snapshotID
        self.managedDatasetPath = managedDatasetPath
        self.sourceKind = sourceKind
    }
}

public struct ChatRunOptions: Equatable, Sendable {
    public let modelID: String
    public let remoteServerID: String
    public let remoteModelID: String
    public let message: String
    public let systemPrompt: String
    public let serverSessionID: String
    public let json: Bool

    public init(
        modelID: String = "",
        remoteServerID: String = "",
        remoteModelID: String = "",
        message: String,
        systemPrompt: String = "",
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        json: Bool = false
    ) {
        self.modelID = modelID
        self.remoteServerID = remoteServerID
        self.remoteModelID = remoteModelID
        self.message = message
        self.systemPrompt = systemPrompt
        self.serverSessionID = serverSessionID.isEmpty
            ? ServerSessionRuntimeStore.defaultServerSessionID
            : serverSessionID
        self.json = json
    }
}

public struct ChatRunReceipt: Codable, Equatable, Sendable {
    public let modelID: String
    public let serverSessionID: String
    public let assistantText: String
    public let finishReason: String
    public let requestID: String

    public init(
        modelID: String,
        serverSessionID: String,
        assistantText: String,
        finishReason: String,
        requestID: String
    ) {
        self.modelID = modelID
        self.serverSessionID = serverSessionID
        self.assistantText = assistantText
        self.finishReason = finishReason
        self.requestID = requestID
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
    public let defaultModelID: String
    public let servedModelIDs: [String]
    public let host: String
    public let port: Int
    public let allowedHosts: [String]
    public let allowedOrigins: [String]
    public let rateLimitPerMinute: Int
    public let timeoutSeconds: Int
    public let modelIdleTimeoutSeconds: Int
    public let accelerationProfile: String
    public let accelerationMode: String
    public let draftModelID: String
    public let numDraftTokens: Int
    public let json: Bool

    public init(
        title: String,
        defaultModelID: String = "",
        servedModelIDs: [String] = [],
        host: String = MelixGatewayDefaults.host,
        port: Int = MelixGatewayDefaults.port,
        allowedHosts: [String] = [],
        allowedOrigins: [String] = [],
        rateLimitPerMinute: Int = 120,
        timeoutSeconds: Int = 120,
        modelIdleTimeoutSeconds: Int = 600,
        accelerationProfile: String = ServingAccelerationProfiles.defaultProfileID,
        accelerationMode: String = "baseline",
        draftModelID: String = "",
        numDraftTokens: Int = 0,
        json: Bool = false
    ) {
        self.title = title
        let trimmedServedModelIDs = servedModelIDs.map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty }
        let resolvedDefaultModelID = MelixServerModelRosterNormalizer.resolvedDefaultModelID(
            defaultModelID,
            servedModelIDs: trimmedServedModelIDs
        )
        self.defaultModelID = resolvedDefaultModelID
        self.servedModelIDs = MelixServerModelRosterNormalizer.normalizedOrDefault(
            trimmedServedModelIDs,
            defaultModelID: resolvedDefaultModelID
        )
        self.host = host
        self.port = port
        self.allowedHosts = normalizedServerAllowlist(allowedHosts)
        self.allowedOrigins = normalizedServerAllowlist(allowedOrigins)
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
        self.accelerationProfile = accelerationProfile
        self.accelerationMode = accelerationMode
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
        self.json = json
    }

}

public struct ServerSessionUpdateOptions: Equatable, Sendable {
    public let serverSessionID: String
    public let title: String
    public let defaultModelID: String
    public let servedModelIDs: [String]
    public let host: String
    public let port: Int
    public let allowedHosts: [String]
    public let allowedOrigins: [String]
    public let clearAllowedHosts: Bool
    public let clearAllowedOrigins: Bool
    public let rateLimitPerMinute: Int
    public let timeoutSeconds: Int
    public let modelIdleTimeoutSeconds: Int
    public let accelerationProfile: String
    public let accelerationMode: String
    public let draftModelID: String
    public let numDraftTokens: Int
    public let json: Bool

    public init(
        serverSessionID: String,
        title: String = "",
        defaultModelID: String = "",
        servedModelIDs: [String] = [],
        host: String = "",
        port: Int = 0,
        allowedHosts: [String] = [],
        allowedOrigins: [String] = [],
        clearAllowedHosts: Bool = false,
        clearAllowedOrigins: Bool = false,
        rateLimitPerMinute: Int = 0,
        timeoutSeconds: Int = 0,
        modelIdleTimeoutSeconds: Int = 0,
        accelerationProfile: String = "",
        accelerationMode: String = "",
        draftModelID: String = "",
        numDraftTokens: Int = 0,
        json: Bool = false
    ) {
        self.serverSessionID = serverSessionID
        self.title = title
        let resolvedDefaultModelID = MelixServerModelRosterNormalizer.resolvedDefaultModelID(
            defaultModelID,
            servedModelIDs: servedModelIDs
        )
        self.defaultModelID = resolvedDefaultModelID
        self.servedModelIDs = servedModelIDs.isEmpty
            ? []
            : MelixServerModelRosterNormalizer.normalized(
                servedModelIDs,
                defaultModelID: resolvedDefaultModelID
            )
        self.host = host
        self.port = port
        self.allowedHosts = normalizedServerAllowlist(allowedHosts)
        self.allowedOrigins = normalizedServerAllowlist(allowedOrigins)
        self.clearAllowedHosts = clearAllowedHosts
        self.clearAllowedOrigins = clearAllowedOrigins
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
        self.accelerationProfile = accelerationProfile
        self.accelerationMode = accelerationMode
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
        self.json = json
    }

}

private func normalizedServerAllowlist(_ values: [String]) -> [String] {
    values.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
}

public struct ServerSessionIDOptions: Equatable, Sendable {
    public let serverSessionID: String
    public let json: Bool

    public init(serverSessionID: String, json: Bool = false) {
        self.serverSessionID = serverSessionID
        self.json = json
    }
}

public struct RemoteServerListOptions: Equatable, Sendable {
    public let json: Bool

    public init(json: Bool = false) {
        self.json = json
    }
}

public struct RemoteServerMutationOptions: Equatable, Sendable {
    public let remoteServerID: String
    public let title: String
    public let providerPreset: RemoteServerProviderPreset?
    public let providerKind: String
    public let baseURL: String
    public let defaultModelID: String
    public let apiKey: String
    public let timeoutSeconds: UInt32
    public let rateLimitPerMinute: UInt32
    public let json: Bool

    public init(
        remoteServerID: String,
        title: String = "",
        providerPreset: RemoteServerProviderPreset? = nil,
        providerKind: String = "openai-compatible",
        baseURL: String = "",
        defaultModelID: String = "",
        apiKey: String = "",
        timeoutSeconds: UInt32 = 60,
        rateLimitPerMinute: UInt32 = 0,
        json: Bool = false
    ) {
        self.remoteServerID = remoteServerID
        self.title = title
        self.providerPreset = providerPreset
        self.providerKind = providerKind
        self.baseURL = baseURL
        self.defaultModelID = defaultModelID
        self.apiKey = apiKey
        self.timeoutSeconds = timeoutSeconds
        self.rateLimitPerMinute = rateLimitPerMinute
        self.json = json
    }
}

public typealias RemoteServerAddOptions = RemoteServerMutationOptions
public typealias RemoteServerUpdateOptions = RemoteServerMutationOptions

public struct RemoteServerIDOptions: Equatable, Sendable {
    public let remoteServerID: String
    public let json: Bool

    public init(remoteServerID: String, json: Bool = false) {
        self.remoteServerID = remoteServerID
        self.json = json
    }
}

public struct RemoteServerTestOptions: Equatable, Sendable {
    public let remoteServerID: String
    public let remoteModelID: String
    public let json: Bool

    public init(remoteServerID: String, remoteModelID: String = "", json: Bool = false) {
        self.remoteServerID = remoteServerID
        self.remoteModelID = remoteModelID
        self.json = json
    }
}

public struct PipelineRunOptions: Equatable, Sendable {
    public let filePath: String
    public let inputsPath: String
    public let receiptDir: String
    public let traceID: String
    public let resume: Bool
    public let fromStepID: String
    public let dryRun: Bool

    public init(
        filePath: String,
        inputsPath: String = "",
        receiptDir: String = "",
        traceID: String = "",
        resume: Bool = false,
        fromStepID: String = "",
        dryRun: Bool = false
    ) {
        self.filePath = filePath
        self.inputsPath = inputsPath
        self.receiptDir = receiptDir
        self.traceID = traceID
        self.resume = resume
        self.fromStepID = fromStepID
        self.dryRun = dryRun
    }
}

public struct URIInspectOptions: Equatable, Sendable {
    public let uri: String
    public let json: Bool

    public init(uri: String, json: Bool = false) {
        self.uri = uri
        self.json = json
    }
}

public struct URIImportOptions: Equatable, Sendable {
    public let uri: String
    public let modelID: String
    public let revision: String
    public let dryRun: Bool
    public let json: Bool

    public init(
        uri: String,
        modelID: String = "",
        revision: String = "",
        dryRun: Bool = false,
        json: Bool = false
    ) {
        self.uri = uri
        self.modelID = modelID
        self.revision = revision
        self.dryRun = dryRun
        self.json = json
    }
}

public struct RecipeListOptions: Equatable, Sendable {
    public let task: String
    public let json: Bool

    public init(task: String = "", json: Bool = false) {
        self.task = task
        self.json = json
    }
}

public struct RecipeShowOptions: Equatable, Sendable {
    public let recipeID: String
    public let version: String
    public let json: Bool

    public init(recipeID: String, version: String = "", json: Bool = false) {
        self.recipeID = recipeID
        self.version = version
        self.json = json
    }
}

public struct RecipeValidateOptions: Equatable, Sendable {
    public let target: String
    public let json: Bool

    public init(target: String, json: Bool = false) {
        self.target = target
        self.json = json
    }
}

public struct RecipePlanOptions: Equatable, Sendable {
    public let recipeID: String
    public let version: String
    public let values: [String: String]
    public let outputPath: String
    public let json: Bool

    public init(
        recipeID: String,
        version: String = "",
        values: [String: String] = [:],
        outputPath: String = "",
        json: Bool = false
    ) {
        self.recipeID = recipeID
        self.version = version
        self.values = values
        self.outputPath = outputPath
        self.json = json
    }
}

public struct RecipeApplyOptions: Equatable, Sendable {
    public let recipeID: String
    public let version: String
    public let values: [String: String]
    public let dryRun: Bool
    public let resume: Bool
    public let fromStepID: String
    public let json: Bool

    public init(
        recipeID: String,
        version: String = "",
        values: [String: String] = [:],
        dryRun: Bool = false,
        resume: Bool = false,
        fromStepID: String = "",
        json: Bool = false
    ) {
        self.recipeID = recipeID
        self.version = version
        self.values = values
        self.dryRun = dryRun
        self.resume = resume
        self.fromStepID = fromStepID
        self.json = json
    }
}

public struct RecipeInitOptions: Equatable, Sendable {
    public let sourceURI: String
    public let task: String
    public let outputPath: String
    public let json: Bool

    public init(
        sourceURI: String,
        task: String,
        outputPath: String = "",
        json: Bool = false
    ) {
        self.sourceURI = sourceURI
        self.task = task
        self.outputPath = outputPath
        self.json = json
    }
}

public struct CookbookRecommendOptions: Equatable, Sendable {
    public let modelID: String
    public let workload: String
    public let serverPlatform: String
    public let serverArch: String
    public let operatorPlatform: String
    public let operatorArch: String
    public let browserPlatform: String
    public let browserArch: String
    public let json: Bool

    public init(
        modelID: String,
        workload: String,
        serverPlatform: String = "",
        serverArch: String = "",
        operatorPlatform: String = "",
        operatorArch: String = "",
        browserPlatform: String = "",
        browserArch: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.workload = workload
        self.serverPlatform = serverPlatform
        self.serverArch = serverArch
        self.operatorPlatform = operatorPlatform
        self.operatorArch = operatorArch
        self.browserPlatform = browserPlatform
        self.browserArch = browserArch
        self.json = json
    }
}

public enum MelixCLIOutputFormat: String, Equatable, Sendable {
    case legacy
    case jsonV1 = "json-v1"
}

public struct MelixCLIInvocation: Equatable, Sendable {
    public let command: MelixCLICommand
    public let outputFormat: MelixCLIOutputFormat
    public let traceID: String
    public let parseDurationMS: Double

    public init(
        command: MelixCLICommand,
        outputFormat: MelixCLIOutputFormat = .legacy,
        traceID: String = "",
        parseDurationMS: Double = 0
    ) {
        self.command = command
        self.outputFormat = outputFormat
        self.traceID = traceID
        self.parseDurationMS = parseDurationMS
    }
}

public enum MelixCLICommand: Equatable, Sendable {
    case settingsShow(SettingsShowOptions)
    case settingsSet(SettingsSetOptions)
    case settingsValidate(SettingsValidateOptions)
    case settingsReset(SettingsResetOptions)
    case info(DiscoveryJSONOptions)
    case capabilities(CapabilitiesOptions)
    case instructions(DiscoveryJSONOptions)
    case schema(DiscoveryJSONOptions)
    case configMetadata(DiscoveryJSONOptions)
    case workspacePreflight(WorkspacePreflightOptions)
    case doctor(DoctorOptions)
    case system(SystemOptions)
    case monitor(MonitorOptions)
    case logs(LogsOptions)
    case jobsList(JobsListOptions)
    case jobsShow(JobsShowOptions)
    case jobsLogs(LogsOptions)
    case jobsArtifacts(JobsArtifactsOptions)
    case jobsCancel(JobsCancelOptions)
    case debugBundle(DebugBundleOptions)
    case estimateImport(EstimateImportOptions)
    case convert(ConvertOptions)
    case quantize(QuantizeOptions)
    case upload(UploadOptions)
    case modelList(ModelListOptions)
    case modelInspect(ModelInspectOptions)
    case modelLoad(ModelLoadOptions)
    case modelUnload(ModelUnloadOptions)
    case modelDownload(ModelDownloadOptions)
    case modelImport(ModelImportOptions)
    case modelHubSearch(ModelHubSearchOptions)
    case modelHubShow(ModelHubShowOptions)
    case modelHubDownload(ModelHubDownloadOptions)
    case datasetList(DatasetListOptions)
    case datasetHubDownload(DatasetHubDownloadOptions)
    case datasetRemove(DatasetRemoveOptions)
    case datasetPrepareIngest(DatasetPrepareIngestOptions)
    case datasetPrepareVersion(DatasetPrepareVersionOptions)
    case datasetPrepareRetryFailed(DatasetPrepareRetryFailedOptions)
    case datasetPrepareListVersions(DatasetPrepareListVersionsOptions)
    case datasetSynthetic(DatasetSyntheticOptions)
    case uriInspect(URIInspectOptions)
    case uriImport(URIImportOptions)
    case recipesList(RecipeListOptions)
    case recipesShow(RecipeShowOptions)
    case recipesValidate(RecipeValidateOptions)
    case recipesPlan(RecipePlanOptions)
    case recipesApply(RecipeApplyOptions)
    case recipesInit(RecipeInitOptions)
    case cookbookRecommend(CookbookRecommendOptions)
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
    case remoteServerList(RemoteServerListOptions)
    case remoteServerAdd(RemoteServerAddOptions)
    case remoteServerUpdate(RemoteServerUpdateOptions)
    case remoteServerRemove(RemoteServerIDOptions)
    case remoteServerTest(RemoteServerTestOptions)
    case chatRun(ChatRunOptions)
    case loraList(LoraListOptions)
    case loraRun(LoraRunOptions)
    case loraTrain(LoraTrainOptions)
    case alignmentTrain(AlignmentTrainOptions)
    case loraDatasetInspect(LoraDatasetInspectOptions)
    case loraDatasetBuild(LoraDatasetBuildOptions)
    case loraActivate(LoraActivateOptions)
    case loraRemoveDerived(LoraRemoveDerivedOptions)
    case loraPublish(LoraPublishOptions)
    case loraExperimentsList(LoraExperimentsListOptions)
    case loraExperimentsShow(LoraExperimentsShowOptions)
    case loraPublishesList(LoraPublishesListOptions)
    case loraPublishesShow(LoraPublishesShowOptions)
    case loraResume(LoraResumeOptions)
    case benchRun(BenchRunOptions)
    case benchList(BenchListOptions)
    case benchExportCSV(BenchExportCSVOptions)
    case benchReport(RunReportOptions)
    case benchMatrixRun(BenchMatrixRunOptions)
    case benchMatrixList(BenchMatrixListOptions)
    case benchMatrixExportSummaryCSV(BenchExportCSVOptions)
    case benchMatrixExportRequestsCSV(BenchExportCSVOptions)
    case evalRun(EvalRunOptions)
    case evalPromptList(EvalPromptListOptions)
    case evalPromptShow(EvalPromptShowOptions)
    case evalPromptCreate(EvalPromptCreateOptions)
    case evalPromptUpdate(EvalPromptUpdateOptions)
    case evalPromptFreeze(EvalPromptFreezeOptions)
    case evalPromptArchive(EvalPromptArchiveOptions)
    case evalCompare(EvalCompareOptions)
    case evalList(EvalListOptions)
    case evalCompareExportSummaryCSV(EvalExportOptions)
    case evalCompareExportSamplesCSV(EvalExportOptions)
    case evalCompareExportSamplesJSONL(EvalExportOptions)
    case evalExportSummaryCSV(EvalExportOptions)
    case evalExportSamplesCSV(EvalExportOptions)
    case evalExportSamplesJSONL(EvalExportOptions)
    case evalReport(RunReportOptions)
    case batchRun(BatchRunOptions)
    case batchStatus(BatchStatusOptions)
    case batchResume(BatchResumeOptions)
    case runsList(RunsListOptions)
    case runsShow(RunsShowOptions)
    case runsExport(RunsExportOptions)
    case pipelineRun(PipelineRunOptions)
}

public enum MelixCLIError: Error, LocalizedError, Equatable, Sendable {
    case usage(String)
    case missingValue(String)
    case missingRequired(String)
    case runtime(String)
    case requestFailed(code: String, message: String)

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
        case .requestFailed(_, let message):
            return message
        }
    }
}

public enum MelixCLIParser {
    private static let defaultSpeculativeNumDraftTokens = 4

    public static func parseInvocation(_ arguments: [String]) throws -> MelixCLIInvocation {
        let parseStart = DispatchTime.now()
        let (format, strippedArguments) = try extractOutputFormat(arguments)
        let command = try parseCommand(strippedArguments)
        let parseDurationMS = elapsedMilliseconds(since: parseStart)
        return MelixCLIInvocation(
            command: command,
            outputFormat: format,
            traceID: traceID(for: command),
            parseDurationMS: parseDurationMS
        )
    }

    public static func requestedOutputFormat(_ arguments: [String]) -> MelixCLIOutputFormat {
        if commandOwnsFormatOption(arguments) {
            return .legacy
        }
        if let format = try? extractOutputFormat(arguments).0 {
            return format
        }
        return arguments.contains("--format") ? .jsonV1 : .legacy
    }

    public static func parse(_ arguments: [String]) throws -> MelixCLICommand {
        try parseCommand(arguments)
    }

    private static func parseCommand(_ arguments: [String]) throws -> MelixCLICommand {
        guard let group = arguments.first else {
            throw MelixCLIError.usage(Self.usageText)
        }
        let tail = Array(arguments.dropFirst())
        switch group {
        case "settings":
            return try parseSettings(tail)
        case "info":
            return try parseInfo(tail)
        case "capabilities":
            return try parseCapabilities(tail)
        case "instructions":
            return try parseInstructions(tail)
        case "schema":
            return try parseSchema(tail)
        case "config":
            return try parseConfig(tail)
        case "workspace":
            return try parseWorkspace(tail)
        case "doctor":
            return try parseDoctor(tail)
        case "system":
            return try parseSystem(tail)
        case "monitor":
            return try parseMonitor(tail)
        case "logs":
            return try parseLogs(tail)
        case "jobs":
            return try parseJobs(tail)
        case "debug":
            return try parseDebug(tail)
        case "estimate":
            return try parseEstimate(tail)
        case "convert":
            return try parseConvert(tail)
        case "quantize":
            return try parseQuantize(tail)
        case "upload":
            return try parseUpload(tail)
        case "model":
            return try parseModel(tail)
        case "dataset":
            return try parseDataset(tail)
        case "uri":
            return try parseURI(tail)
        case "recipes":
            return try parseRecipes(tail)
        case "cookbook":
            return try parseCookbook(tail)
        case "server":
            return try parseServer(tail)
        case "remote-server":
            return try parseRemoteServer(tail)
        case "chat":
            return try parseChat(tail)
        case "lora":
            return try parseLora(tail)
        case "alignment":
            return try parseAlignment(tail)
        case "bench":
            return try parseBench(tail)
        case "eval":
            return try parseEval(tail)
        case "batch":
            return try parseBatch(tail)
        case "runs":
            return try parseRuns(tail)
        case "pipeline":
            return try parsePipeline(tail)
        default:
            throw MelixCLIError.usage(Self.usageText)
        }
    }

    public static let usageText = """
    Usage:
      melix settings show --json [--override KEY=VALUE ...]
      melix settings set KEY VALUE [--json]
      melix settings validate [--json]
      melix settings reset KEY [--json]
      melix info --json
      melix capabilities --json [--model-query MODEL]
      melix instructions --json
      melix schema --json
      melix config metadata --json
      melix workspace preflight --manifest PATH [--output PATH] [--json]
      melix doctor [--json]
      melix system --json
      melix monitor [--from PATH] [--json]
      melix logs JOB_ID [--from PATH] [--follow] [--json]
      melix jobs list [--from PATH] [--json]
      melix jobs show JOB_ID [--from PATH] [--json]
      melix jobs logs JOB_ID [--from PATH] [--follow] [--json]
      melix jobs artifacts JOB_ID [--from PATH] [--json]
      melix jobs cancel JOB_ID [--from PATH] [--json]
      melix debug bundle RUN_OR_JOB_ID [--from PATH] [--output PATH] [--json]
      melix estimate import HF_REPO [--json]
      melix estimate import --repo-id HF_REPO [--json]
      melix estimate benchmark HF_REPO [--context-length N] [--batch-size N] [--json]
      melix estimate benchmark --repo-id HF_REPO [--context-length N] [--batch-size N] [--json]
      melix estimate eval HF_REPO [--context TEXT] [--context-length N] [--dataset URI] [--sample-size N] [--json]
      melix estimate eval --repo-id HF_REPO [--context TEXT] [--context-length N] [--dataset URI] [--sample-size N] [--json]
      melix estimate train HF_REPO [--dataset URI] [--lora NAME_OR_PATH] [--batch-size N] [--json]
      melix estimate train --model HF_REPO [--dataset URI] [--lora NAME_OR_PATH] [--batch-size N] [--json]
      melix convert --model-id MODEL_ID [--output-dir PATH] [--target-format FORMAT] [--json]
      melix quantize --model-id MODEL_ID [--output-dir PATH] [--quant-profile-id ID] [--weight-quant MODE] [--kv-quant MODE] [--quantization-mode (ptq|qat)] [--source-artifact-kind (base_model|merged_adapter|adapter_export)] [--source-artifact-path PATH] [--quantization-backend (manifest_only|mlx_lm_convert)] [--mlx-lm-q-bits N] [--mlx-lm-q-group-size N] [--mlx-lm-q-mode (affine|mxfp4|nvfp4|mxfp8)] [--calibration-dataset-uri PATH] [--quality-delta N] [--latency-delta N] [--local-inference-smoke-mode (structural|runtime_generate)] [--local-inference-smoke-prompt TEXT] [--json]
      melix upload --model-id MODEL_ID --target-repo REPO [--output-dir PATH] [--artifact-path PATH] [--artifact-kind KIND] [--artifact-manifest-path PATH] [--publish-backend BACKEND] [--local-publish-root PATH] [--json]
      melix model list [--json]
      melix model inspect --model-id MODEL_ID [--json]
      melix model load --model-id MODEL_ID [--memory-budget-bytes N] [--json]
      melix model unload --model-id MODEL_ID [--json]
      melix model download --model-id MODEL_ID [--output-dir PATH] [--json]
      melix model import --path PATH --model-id MODEL_ID [--model-kind KIND] [--revision REV] [--json]
      melix model hub search --query QUERY [--page-size N] [--cursor TOKEN] [--mlx-only (true|false)] [--json]
      melix model hub show --repo-id HF_REPO [--json]
      melix model hub download --repo-id HF_REPO [--revision REV] [--hf-token TOKEN] [--json]
      melix dataset list [--json]
      melix dataset hub download --repo-id HF_DATASET [--revision REV] [--hf-token TOKEN] [--json]
      melix dataset remove --repo-id HF_DATASET [--revision REV | --snapshot-id SHA] [--json]
      melix dataset prepare ingest --workspace-project-id ID --workspace-manifest PATH --input PATH --output-dir PATH --dataset-preparation-id ID [--output PATH] [--pii-mask true|false] [--exact-dedup true|false] [--fuzzy-dedup true|false] [--segmentation true|false] [--segmentation-strategy STRATEGY] [--json]
      melix dataset prepare version --workspace-manifest PATH --ingest-receipt PATH --output-root PATH --dataset-id ID [--version-id ID] [--created-at ISO8601] [--mode MODE] [--generator-model MODEL] [--output-kind KIND] [--output-format FORMAT] [--validation-ratio N] [--fail-segment-id ID ...] [--json]
      melix dataset prepare retry-failed --workspace-manifest PATH --dataset-version PATH --output-root PATH [--version-id ID] [--created-at ISO8601] [--generator-model MODEL] [--json]
      melix dataset prepare list-versions --workspace-manifest PATH --output-root PATH --dataset-id ID [--json]
      melix dataset synthetic preview --dataset-id ID --dataset-name NAME --num-records N --output-kind KIND --output-format FORMAT --output-dir PATH --provider-endpoint URL --model MODEL --column NAME:TYPE:JSON [--model-alias ALIAS] [--api-key TOKEN] [--header KEY=VALUE ...] [--json]
      melix dataset synthetic create --dataset-id ID --dataset-name NAME --num-records N --output-kind KIND --output-format FORMAT --output-dir PATH --provider-endpoint URL --model MODEL --column NAME:TYPE:JSON [--model-alias ALIAS] [--validation-ratio N] [--resume MODE] [--json]
      melix uri inspect URI [--json]
      melix uri import URI [--model-id MODEL_ID] [--revision REV] [--dry-run] [--json]
      melix recipes list [--task TASK] [--json]
      melix recipes show RECIPE_ID [--version VERSION] [--json]
      melix recipes validate PATH_OR_ID [--json]
      melix recipes plan RECIPE_ID [--version VERSION] [--set KEY=VALUE ...] [--output PATH] [--json]
      melix recipes apply RECIPE_ID [--version VERSION] [--set KEY=VALUE ...] [--dry-run] [--resume] [--from-step STEP_ID] [--json]
      melix recipes init --from URI --task TASK [--output PATH] [--json]
      melix cookbook recommend MODEL_ID --workload WORKLOAD [--server-platform PLATFORM] [--server-arch ARCH] [--operator-platform PLATFORM] [--operator-arch ARCH] [--browser-platform PLATFORM] [--browser-arch ARCH] [--json]
      melix model roots list [--json]
      melix model roots add --path PATH [--json]
      melix model roots remove --path PATH [--json]
      melix model roots move --path PATH --index N [--json]
      melix model roots rescan [--json]
      melix server snapshot [--json]
      melix server session list [--json]
      melix server session create --title TITLE (--model MODEL_ID ... | --models MODEL_ID[,MODEL_ID...]) [--default-model MODEL_ID] [--host HOST] [--port PORT] [--allowed-host HOST ...] [--allowed-origin ORIGIN ...] [--rate-limit-per-minute N] [--timeout-seconds N] [--model-idle-timeout-seconds N] [--acceleration-profile PROFILE] [--acceleration-mode MODE] [--draft-model-id MODEL_ID] [--num-draft-tokens N] [--json]
      melix server session update --server-session-id ID [--title TITLE] [--model MODEL_ID ... | --models MODEL_ID[,MODEL_ID...]] [--default-model MODEL_ID] [--host HOST] [--port PORT] [--allowed-host HOST ... | --clear-allowed-hosts] [--allowed-origin ORIGIN ... | --clear-allowed-origins] [--rate-limit-per-minute N] [--timeout-seconds N] [--model-idle-timeout-seconds N] [--acceleration-profile PROFILE] [--acceleration-mode MODE] [--draft-model-id MODEL_ID] [--num-draft-tokens N] [--json]
      melix server session remove --server-session-id ID [--json]
      melix server session select --server-session-id ID [--json]
      melix server start [TITLE] [--model MODEL_ID ... | --models MODEL_ID[,MODEL_ID...]] [--default-model MODEL_ID] [--host HOST] [--port PORT] [--allowed-host HOST ...] [--allowed-origin ORIGIN ...] [--rate-limit-per-minute N] [--timeout-seconds N] [--model-idle-timeout-seconds N] [--server-session-id ID] [--json]
      melix server pause [--server-session-id ID] [--json]
      melix server resume [--server-session-id ID] [--json]
      melix server wake [--server-session-id ID] [--json]
      melix server stop [--server-session-id ID] [--json]
      melix server set-idle-policy [--server-session-id ID] --auto-sleep (true|false) --light-sleep-after N --deep-sleep-after N [--json]
      melix remote-server list [--json]
      melix remote-server add --remote-server-id ID --title TITLE --provider kimi|gemini|deepseek|glm|custom [--base-url URL] --model MODEL [--api-key KEY] [--timeout-seconds N] [--rate-limit-per-minute N] [--json]
      melix remote-server update --remote-server-id ID [--title TITLE] [--provider PROVIDER] [--base-url URL] [--model MODEL] [--api-key KEY] [--timeout-seconds N] [--rate-limit-per-minute N] [--json]
      melix remote-server remove --remote-server-id ID [--json]
      melix remote-server test --remote-server-id ID [--model MODEL] [--json]
      melix chat run (--model-id MODEL_ID | --remote-server-id ID --model MODEL) --message TEXT [--system TEXT] [--server-session-id ID] [--json]
      melix lora list [--model-id MODEL_ID] [--json]
      melix lora run --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) --adapter-name NAME --eval-dataset-id DATASET_ID [--eval-suite SUITE ...] [--output-dir PATH] [--activation-mode (adapter_backed_runtime|fused_derived_model)] [--training-mode auto|lora|qlora|dora] [training options...] [evaluation options...] [--json]
      melix lora train --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) --adapter-name NAME [--target-repo REPO] [--training-mode (lora|qlora|dora)] [--preset PRESET] [--experiment-group GROUP] [--rank N] [--alpha N] [--dropout N] [--target-modules CSV] [--num-layers N] [--batch-size N] [--epochs N] [--max-steps N] [--learning-rate N] [--max-seq-length N] [--sample-limit N] [--gradient-accumulation N] [--resume-adapter PATH | --resume-from-manifest PATH] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-train-split SPLIT] [--hf-valid-split SPLIT] [--text-feature NAME] [--prompt-feature NAME] [--completion-feature NAME] [--chat-feature NAME] [--derived-model-alias NAME] [--response-only] [--mask-prompt] [--gradient-checkpointing] [--preflight-fit-check] [--allow-memory-risk] [--json]
      melix alignment train --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) --adapter-name NAME --algorithm dpo|orpo|cpo|grpo|rlhf [--target-repo REPO] [--source-adapter-path PATH] [--grpo-candidate-count N] [--candidate-generation-mode scored_trace|runtime_generate] [--candidate-scoring-mode dataset_score|seed_overlap_proxy|reward_model] [--candidate-generation-max-tokens N] [--reference-model-path PATH] [--reward-model-manifest-path PATH] [--kl-penalty N] [--preset PRESET] [--experiment-group GROUP] [--rank N] [--alpha N] [--dropout N] [--target-modules CSV] [--num-layers N] [--batch-size N] [--epochs N] [--max-steps N] [--learning-rate N] [--max-seq-length N] [--sample-limit N] [--gradient-accumulation N] [--json]
        note: --source-adapter-path is the upstream/base LoRA adapter to carry into GRPO/RLHF output; it is not checkpoint resumption.
      melix lora dataset inspect --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) [--template TEMPLATE] [--dataset-id ID] [--validation-ratio N] [--sample-limit N] [--preview-count N] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-train-split SPLIT] [--hf-valid-split SPLIT] [--text-feature NAME] [--prompt-feature NAME] [--completion-feature NAME] [--chat-feature NAME] [--json]
      melix lora dataset build --model-id MODEL_ID (--dataset-uri PATH | --hf-dataset-path REPO) [--output-dir PATH] [--template TEMPLATE] [--dataset-id ID] [--validation-ratio N] [--sample-limit N] [--preview-count N] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-train-split SPLIT] [--hf-valid-split SPLIT] [--text-feature NAME] [--prompt-feature NAME] [--completion-feature NAME] [--chat-feature NAME] [--json]
      melix lora activate --model-id MODEL_ID --adapter-path PATH [--activation-mode (fused_derived_model|adapter_backed_runtime)] [--alias NAME] [--json]
      melix lora remove-derived --model-id MODEL_ID (--derived-model-id ID | --manifest-path PATH) [--json]
      melix lora publish --model-id MODEL_ID --target-repo REPO (--adapter-path PATH | --merged-model-path PATH | --manifest-path PATH) [--export-kind (adapter|merged)] [--publish-backend BACKEND] [--local-publish-root PATH] [--json]
      melix lora experiments list [--model-id MODEL_ID] [--json]
      melix lora experiments show --group-id GROUP_ID [--model-id MODEL_ID] [--json]
      melix lora resume --group-id GROUP_ID [--model-id MODEL_ID] [--preset PRESET] [--adapter-name NAME] [--dataset-uri URI] [--json]
      melix lora publishes list [--model-id MODEL_ID] [--json]
      melix lora publishes show --job-id JOB_ID [--model-id MODEL_ID] [--json]
      melix bench run (--model-id MODEL_ID | --repo-id HF_REPO) [--suite SUITE ...] [--dataset-ref HF_DATASET[@REV]] [--hf-dataset-name NAME] [--hf-dataset-split SPLIT] [--prompt-feature NAME] [--text-feature NAME] [--image-feature NAME] [--source-image-feature NAME] [--mask-feature NAME] [--context-length N ...] [--generation-length N] [--batch-size N ...] [--repeats N] [--cache-profile MODE] [--reasoning-mode MODE] [--structured-output-mode MODE] [--sample-size N] [--batch-factor N] [--preflight-fit-check] [--allow-memory-risk] [--no-live] [--json]
      melix bench list [--json]
      melix bench export-csv --job-id JOB_ID --output PATH [--json]
      melix bench report --from PATH [--format terminal|markdown|json]
      melix bench matrix run (--model-id MODEL_ID | --repo-id HF_REPO) --suite SUITE ... --context-length N ... --generation-length N ... --batch-size N ... --cache-profile MODE ... --reasoning-mode MODE ... --structured-output-mode MODE ... --concurrency N ... [--repeats N] (--requests N | --duration-seconds N) [--allow-large-matrix] [--no-live] [--json]
      melix bench matrix list [--json]
      melix bench matrix export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix bench matrix export-requests-csv --job-id JOB_ID --output PATH [--json]
      melix eval run (--model-id MODEL_ID | --repo-id HF_REPO | --remote-server-id ID [--remote-model MODEL] ...) [--semantic-judge-remote-server-id ID] [--semantic-judge-model MODEL] [--remote-parallelism N] [--suite SUITE ...] [--dataset-id DATASET_ID] [--dataset-root PATH] [--source-csv PATH | --source-jsonl PATH | --hf-dataset-path REPO | --dataset-ref HF_DATASET[@REV]] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-dataset-split SPLIT] [--field-system-path PATH] [--field-input-text-path PATH] [--field-target-path PATH] [--field-sample-id-path PATH] [--profile-type TYPE] [--result-kind KIND] [--extraction-mode MODE] [--scoring-mode MODE] [--threshold N] [--schema PATH | --output-schema-json JSON] [--hints PATH] [--ignored-path PATH ...] [--sample-size N] [--batch-factor N] [--seed N] [--few-shot N] [--code-exec-policy MODE] [--remote-extra-body-json JSON] [--eval-prompt TEXT | --eval-prompt-file PATH | --eval-prompt-id ID [--eval-prompt-revision REV]] [--preflight-fit-check] [--allow-memory-risk] [--no-live] [--json]
      melix eval prompt list [--json]
      melix eval prompt show --prompt-id ID [--revision-id REV] [--json]
      melix eval prompt create --prompt-id ID --title TITLE --system-prompt-file PATH [--json]
      melix eval prompt update --prompt-id ID --system-prompt-file PATH [--json]
      melix eval prompt freeze --prompt-id ID [--revision-id REV] [--json]
      melix eval prompt archive --prompt-id ID [--json]
      melix eval compare (--model-id MODEL_ID | --repo-id HF_REPO) (--target-model-id MODEL_ID | --target-adapter ADAPTER_MANIFEST_PATH)... [--suite SUITE ...] [--dataset-id DATASET_ID] [--dataset-root PATH] [--source-csv PATH | --source-jsonl PATH | --hf-dataset-path REPO | --dataset-ref HF_DATASET[@REV]] [--hf-dataset-name NAME] [--hf-dataset-revision REV] [--hf-dataset-split SPLIT] [--field-system-path PATH] [--field-input-text-path PATH] [--field-target-path PATH] [--field-sample-id-path PATH] [--profile-type TYPE] [--result-kind KIND] [--extraction-mode MODE] [--scoring-mode MODE] [--threshold N] [--schema PATH | --output-schema-json JSON] [--hints PATH] [--eval-prompt TEXT | --eval-prompt-file PATH | --eval-prompt-id ID [--eval-prompt-revision REV]] [--semantic-judge-remote-server-id ID [--semantic-judge-model MODEL]] [--ignored-path PATH ...] [--sample-size N] [--batch-factor N] [--seed N] [--few-shot N] [--code-exec-policy MODE] [--no-live] [--json]
      melix eval compare export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix eval compare export-samples-csv --job-id JOB_ID --output PATH [--json]
      melix eval compare export-samples-jsonl --job-id JOB_ID --output PATH [--json]
      melix eval list [--json]
      melix eval export-summary-csv --job-id JOB_ID --output PATH [--json]
      melix eval export-samples-csv --job-id JOB_ID --output PATH [--json]
      melix eval export-samples-jsonl --job-id JOB_ID --output PATH [--json]
      melix eval report --from PATH [--format terminal|markdown|json]
      melix batch run --models PATH [--config PATH] [--run-id ID] [--output-root PATH] [--temp-root PATH] [--start-index N] [--max-models N] [--judge-remote-server-id ID] [--judge-model MODEL] [--bench-suite SUITE] [--bench-context-length N] [--bench-generation-length N] [--bench-batch-size N] [--bench-repeats N] [--bench-sample-size N] [--bench-batch-factor N] [--eval-suite SUITE] [--eval-dataset-id ID] [--eval-scoring-mode MODE] [--eval-sample-size N] [--eval-batch-factor N] [--continue-on-failure true|false] [--restart-stack-per-model true|false] [--preflight] [--dry-run] [--json]
      melix batch status [--run-id ID] [--output-root PATH] [--temp-root PATH] [--json]
      melix batch resume [--run-id ID] [--output-root PATH] [--temp-root PATH] [--models PATH] [--config PATH] [--eval-only] [--missing-only true|false] [--continue-on-failure true|false] [--dry-run] [--json]
      melix runs list [--from PATH] [--json]
      melix runs show RUN_ID [--from PATH] [--json]
      melix runs export RUN_ID --format json|md [--from PATH] [--output PATH]
      melix pipeline run --file PIPELINE.json [--inputs INPUTS.json] [--receipt-dir PATH] [--trace-id ID] [--resume] [--from-step STEP_ID] [--dry-run] [--format json-v1]

    Notes:
      --hf-token passed to model or dataset hub download is saved for later Hugging Face operations.
      For eval run/compare, --hf-dataset-revision overrides a revision embedded in --dataset-ref.
    """

    private static func extractOutputFormat(
        _ arguments: [String]
    ) throws -> (MelixCLIOutputFormat, [String]) {
        var stripped: [String] = []
        var format = MelixCLIOutputFormat.legacy
        var index = 0
        while index < arguments.count {
            let token = arguments[index]
            if token == "--format", Self.commandOwnsFormatOption(arguments) {
                let valueIndex = index + 1
                guard valueIndex < arguments.count else {
                    throw MelixCLIError.missingValue("--format")
                }
                stripped.append(token)
                stripped.append(arguments[valueIndex])
                index += 2
                continue
            }
            guard token == "--format" else {
                stripped.append(token)
                index += 1
                continue
            }
            let valueIndex = index + 1
            guard valueIndex < arguments.count else {
                throw MelixCLIError.missingValue("--format")
            }
            let value = arguments[valueIndex]
            guard let parsedFormat = MelixCLIOutputFormat(rawValue: value) else {
                throw MelixCLIError.usage("Invalid value for --format. Expected json-v1.")
            }
            format = parsedFormat
            index += 2
        }
        return (format, stripped)
    }

    private static func commandOwnsFormatOption(_ arguments: [String]) -> Bool {
        guard arguments.count >= 2 else {
            return false
        }
        let group = arguments[0]
        let action = arguments[1]
        return (group == "bench" && action == "report")
            || (group == "eval" && action == "report")
            || (group == "runs" && action == "export")
    }

    private static func traceID(for command: MelixCLICommand) -> String {
        if case .pipelineRun(let options) = command {
            return options.traceID
        }
        return ""
    }

    private static func parseSettings(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(Self.usageText)
        }
        let tail = Array(arguments.dropFirst())
        switch action {
        case "show":
            let values = try ArgumentCursor(arguments: tail).parse(multiValueOptions: ["--override"])
            guard values.flags.contains("--json") else {
                throw MelixCLIError.usage("melix settings show requires --json.")
            }
            var overrides: [String: String] = [:]
            for rawOverride in values.multi["--override", default: []] {
                let parts = rawOverride.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
                guard parts.count == 2, parts[0].isEmpty == false else {
                    throw MelixCLIError.usage("--override must use KEY=VALUE.")
                }
                overrides[String(parts[0])] = String(parts[1])
            }
            return .settingsShow(.init(json: true, overrides: overrides))
        case "set":
            var positional: [String] = []
            var optionArguments: [String] = []
            for token in tail {
                if token == "--json" {
                    optionArguments.append(token)
                } else if token.hasPrefix("--") {
                    throw MelixCLIError.usage(Self.usageText)
                } else {
                    positional.append(token)
                }
            }
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            guard positional.count == 2 else {
                throw MelixCLIError.missingRequired("KEY and VALUE are required for melix settings set.")
            }
            return .settingsSet(.init(key: positional[0], value: positional[1], json: values.flags.contains("--json")))
        case "validate":
            let values = try ArgumentCursor(arguments: tail).parse()
            return .settingsValidate(.init(json: values.flags.contains("--json")))
        case "reset":
            var positional: [String] = []
            var optionArguments: [String] = []
            for token in tail {
                if token == "--json" {
                    optionArguments.append(token)
                } else if token.hasPrefix("--") {
                    throw MelixCLIError.usage(Self.usageText)
                } else {
                    positional.append(token)
                }
            }
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            guard positional.count == 1 else {
                throw MelixCLIError.missingRequired("KEY is required for melix settings reset.")
            }
            return .settingsReset(.init(key: positional[0], json: values.flags.contains("--json")))
        default:
            throw MelixCLIError.usage(Self.usageText)
        }
    }

    private static func parseInfo(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard values.flags.contains("--json") else {
            throw MelixCLIError.usage("melix info requires --json.")
        }
        return .info(.init(json: true))
    }

    private static func parseCapabilities(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard values.flags.contains("--json") else {
            throw MelixCLIError.usage("melix capabilities requires --json.")
        }
        return .capabilities(.init(json: true, modelQuery: values.single["--model-query"] ?? ""))
    }

    private static func parseInstructions(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard values.flags.contains("--json") else {
            throw MelixCLIError.usage("melix instructions requires --json.")
        }
        return .instructions(.init(json: true))
    }

    private static func parseSchema(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard values.flags.contains("--json") else {
            throw MelixCLIError.usage("melix schema requires --json.")
        }
        return .schema(.init(json: true))
    }

    private static func parseConfig(_ arguments: [String]) throws -> MelixCLICommand {
        guard arguments.first == "metadata" else {
            throw MelixCLIError.usage(Self.usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        guard values.flags.contains("--json") else {
            throw MelixCLIError.usage("melix config metadata requires --json.")
        }
        return .configMetadata(.init(json: true))
    }

    private static func parseWorkspace(_ arguments: [String]) throws -> MelixCLICommand {
        guard arguments.first == "preflight" else {
            throw MelixCLIError.usage(Self.usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        let manifestPath = values.single["--manifest"] ?? ""
        guard manifestPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            throw MelixCLIError.missingRequired("--manifest is required for melix workspace preflight.")
        }
        return .workspacePreflight(
            .init(
                manifestPath: manifestPath,
                outputPath: values.single["--output"] ?? "",
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseDoctor(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        return .doctor(.init(json: values.flags.contains("--json")))
    }

    private static func parseSystem(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        return .system(.init(json: values.flags.contains("--json")))
    }

    private static func parseMonitor(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        return .monitor(.init(sourcePath: values.single["--from"] ?? "", json: values.flags.contains("--json")))
    }

    private static func parseLogs(_ arguments: [String]) throws -> MelixCLICommand {
        var optionArguments = arguments
        let jobID = try extractRunID(from: &optionArguments, command: "melix logs", fieldName: "JOB_ID")
        let values = try ArgumentCursor(arguments: optionArguments).parse()
        return .logs(
            LogsOptions(
                jobID: jobID,
                sourcePath: values.single["--from"] ?? "",
                follow: values.flags.contains("--follow"),
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseJobs(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let tail = Array(arguments.dropFirst())
        switch action {
        case "list":
            let values = try ArgumentCursor(arguments: tail).parse()
            return .jobsList(.init(sourcePath: values.single["--from"] ?? "", json: values.flags.contains("--json")))
        case "show":
            var optionArguments = tail
            let jobID = try extractRunID(from: &optionArguments, command: "melix jobs show", fieldName: "JOB_ID")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .jobsShow(.init(jobID: jobID, sourcePath: values.single["--from"] ?? "", json: values.flags.contains("--json")))
        case "logs":
            var optionArguments = tail
            let jobID = try extractRunID(from: &optionArguments, command: "melix jobs logs", fieldName: "JOB_ID")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .jobsLogs(
                .init(
                    jobID: jobID,
                    sourcePath: values.single["--from"] ?? "",
                    follow: values.flags.contains("--follow"),
                    json: values.flags.contains("--json")
                )
            )
        case "artifacts":
            var optionArguments = tail
            let jobID = try extractRunID(from: &optionArguments, command: "melix jobs artifacts", fieldName: "JOB_ID")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .jobsArtifacts(.init(jobID: jobID, sourcePath: values.single["--from"] ?? "", json: values.flags.contains("--json")))
        case "cancel":
            var optionArguments = tail
            let jobID = try extractRunID(from: &optionArguments, command: "melix jobs cancel", fieldName: "JOB_ID")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .jobsCancel(.init(jobID: jobID, sourcePath: values.single["--from"] ?? "", json: values.flags.contains("--json")))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseDebug(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        switch action {
        case "bundle":
            var optionArguments = Array(arguments.dropFirst())
            let runID = try extractRunID(from: &optionArguments, command: "melix debug bundle")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .debugBundle(
                DebugBundleOptions(
                    runID: runID,
                    sourcePath: values.single["--from"] ?? "",
                    outputPath: values.single["--output"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseEstimate(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(Self.usageText)
        }
        switch action {
        case "import", "benchmark", "eval", "train":
            var optionArguments = Array(arguments.dropFirst())
            var repoID = ""
            if let positionalRepoID = optionArguments.first, positionalRepoID.hasPrefix("--") == false {
                repoID = positionalRepoID
                optionArguments.removeFirst()
            }
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            if let optionRepoID = values.single["--repo-id"], optionRepoID.isEmpty == false {
                if repoID.isEmpty == false, repoID != optionRepoID {
                    throw MelixCLIError.usage("melix estimate \(action) accepts only one Hugging Face repo id.")
                }
                repoID = optionRepoID
            }
            if let modelRepoID = values.single["--model"], modelRepoID.isEmpty == false {
                if repoID.isEmpty == false, repoID != modelRepoID {
                    throw MelixCLIError.usage("melix estimate \(action) accepts only one Hugging Face repo id.")
                }
                repoID = modelRepoID
            }
            repoID = repoID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard repoID.isEmpty == false else {
                throw MelixCLIError.missingRequired("HF_REPO or --repo-id is required for melix estimate \(action).")
            }
            return .estimateImport(.init(
                repoID: repoID,
                targetKind: normalizedEstimateTargetKind(action),
                targetInputs: estimateTargetInputs(values),
                json: values.flags.contains("--json")
            ))
        default:
            throw MelixCLIError.usage(Self.usageText)
        }
    }

    private static func normalizedEstimateTargetKind(_ action: String) -> String {
        action
    }

    private static func estimateTargetInputs(_ values: ParsedArguments) -> [String: String] {
        var inputs: [String: String] = [:]
        for option in [
            "--context",
            "--context-length",
            "--dataset",
            "--lora",
            "--batch-size",
            "--sample-size",
        ] {
            if let value = values.single[option], value.isEmpty == false {
                inputs[normalizedParameterKey(option)] = value
            }
        }
        return inputs
    }

    private static func parseConvert(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model-id is required for melix convert.")
        }
        return .convert(
            .init(
                modelID: modelID,
                outputDir: values.single["--output-dir"] ?? "",
                targetFormat: values.single["--target-format"] ?? "melix_model_bundle",
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseQuantize(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model-id is required for melix quantize.")
        }
        let quantizationMode = (values.single["--quantization-mode"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if !quantizationMode.isEmpty, MelixQuantizationAllowedValues.quantizationModes.contains(quantizationMode) == false {
            throw MelixCLIError.usage(
                "Invalid value for --quantization-mode. Expected one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.quantizationModes))."
            )
        }
        let sourceArtifactKind = (values.single["--source-artifact-kind"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if !sourceArtifactKind.isEmpty, MelixQuantizationAllowedValues.sourceArtifactKinds.contains(sourceArtifactKind) == false {
            throw MelixCLIError.usage(
                "Invalid value for --source-artifact-kind. Expected one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.sourceArtifactKinds))."
            )
        }
        let quantizationBackend = (values.single["--quantization-backend"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if !quantizationBackend.isEmpty, MelixQuantizationAllowedValues.quantizationBackends.contains(quantizationBackend) == false {
            throw MelixCLIError.usage(
                "Invalid value for --quantization-backend. Expected one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.quantizationBackends))."
            )
        }
        let mlxLMQBits = (values.single["--mlx-lm-q-bits"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !mlxLMQBits.isEmpty, Int(mlxLMQBits) == nil {
            throw MelixCLIError.usage("Invalid value for --mlx-lm-q-bits. Expected an integer.")
        }
        let mlxLMQGroupSize = (values.single["--mlx-lm-q-group-size"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !mlxLMQGroupSize.isEmpty, Int(mlxLMQGroupSize) == nil {
            throw MelixCLIError.usage("Invalid value for --mlx-lm-q-group-size. Expected an integer.")
        }
        let mlxLMQMode = (values.single["--mlx-lm-q-mode"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if !mlxLMQMode.isEmpty, MelixQuantizationAllowedValues.mlxLMQModes.contains(mlxLMQMode) == false {
            throw MelixCLIError.usage(
                "Invalid value for --mlx-lm-q-mode. Expected one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.mlxLMQModes))."
            )
        }
        let localInferenceSmokeMode = (values.single["--local-inference-smoke-mode"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if !localInferenceSmokeMode.isEmpty, ["structural", "runtime_generate"].contains(localInferenceSmokeMode) == false {
            throw MelixCLIError.usage("Invalid value for --local-inference-smoke-mode. Expected one of: structural, runtime_generate.")
        }
        return .quantize(
            .init(
                modelID: modelID,
                outputDir: values.single["--output-dir"] ?? "",
                quantProfileID: values.single["--quant-profile-id"] ?? "",
                weightQuant: values.single["--weight-quant"] ?? "",
                kvQuant: values.single["--kv-quant"] ?? "",
                quantizationMode: quantizationMode,
                sourceArtifactKind: sourceArtifactKind,
                sourceArtifactPath: values.single["--source-artifact-path"] ?? "",
                quantizationBackend: quantizationBackend,
                mlxLMQBits: mlxLMQBits,
                mlxLMQGroupSize: mlxLMQGroupSize,
                mlxLMQMode: mlxLMQMode,
                calibrationDatasetURI: values.single["--calibration-dataset-uri"] ?? "",
                qualityDelta: values.single["--quality-delta"] ?? "",
                latencyDelta: values.single["--latency-delta"] ?? "",
                localInferenceSmokeMode: localInferenceSmokeMode,
                localInferenceSmokePrompt: values.single["--local-inference-smoke-prompt"] ?? "",
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseUpload(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model-id is required for melix upload.")
        }
        guard let targetRepo = values.single["--target-repo"], !targetRepo.isEmpty else {
            throw MelixCLIError.missingRequired("--target-repo is required for melix upload.")
        }
        return .upload(
            .init(
                modelID: modelID,
                outputDir: values.single["--output-dir"] ?? "",
                targetRepo: targetRepo,
                artifactPath: values.single["--artifact-path"] ?? "",
                artifactKind: values.single["--artifact-kind"] ?? "",
                artifactManifestPath: values.single["--artifact-manifest-path"] ?? "",
                publishBackend: values.single["--publish-backend"] ?? "",
                localPublishRoot: values.single["--local-publish-root"] ?? "",
                json: values.flags.contains("--json")
            )
        )
    }

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
        case "import":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            guard let path = values.single["--path"], !path.isEmpty else {
                throw MelixCLIError.missingRequired("--path is required for melix model import.")
            }
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix model import.")
            }
            return .modelImport(
                .init(
                    path: path,
                    modelID: modelID,
                    modelKind: values.single["--model-kind"] ?? "text",
                    revision: values.single["--revision"] ?? "main",
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
                    hfToken: values.single["--hf-token"] ?? "",
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

    private static func parseDataset(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        switch action {
        case "list":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            return .datasetList(.init(json: values.flags.contains("--json")))
        case "hub":
            return try parseDatasetHub(Array(arguments.dropFirst()))
        case "remove":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
            guard let repoID = values.single["--repo-id"], !repoID.isEmpty else {
                throw MelixCLIError.missingRequired("--repo-id is required for melix dataset remove.")
            }
            return .datasetRemove(
                .init(
                    repoID: repoID,
                    revision: values.single["--revision"] ?? "main",
                    snapshotID: values.single["--snapshot-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "prepare":
            return try parseDatasetPrepare(Array(arguments.dropFirst()))
        case "synthetic":
            return try parseDatasetSynthetic(Array(arguments.dropFirst()))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseDatasetPrepare(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        if action == "version" {
            return try parseDatasetPrepareVersion(Array(arguments.dropFirst()))
        }
        if action == "retry-failed" {
            return try parseDatasetPrepareRetryFailed(Array(arguments.dropFirst()))
        }
        if action == "list-versions" {
            return try parseDatasetPrepareListVersions(Array(arguments.dropFirst()))
        }
        guard action == "ingest" else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        guard let workspaceProjectID = nonEmpty(values.single["--workspace-project-id"]) else {
            throw MelixCLIError.missingRequired("--workspace-project-id is required for melix dataset prepare ingest.")
        }
        guard let workspaceManifestPath = nonEmpty(values.single["--workspace-manifest"]) else {
            throw MelixCLIError.missingRequired("--workspace-manifest is required for melix dataset prepare ingest.")
        }
        guard let inputPath = nonEmpty(values.single["--input"]) else {
            throw MelixCLIError.missingRequired("--input is required for melix dataset prepare ingest.")
        }
        guard let outputDir = nonEmpty(values.single["--output-dir"]) else {
            throw MelixCLIError.missingRequired("--output-dir is required for melix dataset prepare ingest.")
        }
        guard let datasetPreparationID = nonEmpty(values.single["--dataset-preparation-id"]) else {
            throw MelixCLIError.missingRequired("--dataset-preparation-id is required for melix dataset prepare ingest.")
        }
        return .datasetPrepareIngest(
            .init(
                workspaceProjectID: workspaceProjectID,
                workspaceManifestPath: workspaceManifestPath,
                inputPath: inputPath,
                outputDir: outputDir,
                datasetPreparationID: datasetPreparationID,
                receiptOutputPath: values.single["--output"] ?? "",
                piiMask: try parseRequiredBooleanValue(values.single["--pii-mask"], option: "--pii-mask", defaultValue: true),
                exactDedup: try parseRequiredBooleanValue(values.single["--exact-dedup"], option: "--exact-dedup", defaultValue: true),
                fuzzyDedup: try parseRequiredBooleanValue(values.single["--fuzzy-dedup"], option: "--fuzzy-dedup", defaultValue: true),
                segmentation: try parseRequiredBooleanValue(values.single["--segmentation"], option: "--segmentation", defaultValue: true),
                segmentationStrategy: values.single["--segmentation-strategy"] ?? "paragraph",
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseDatasetPrepareVersion(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse(multiValueOptions: ["--fail-segment-id"])
        guard let workspaceManifestPath = nonEmpty(values.single["--workspace-manifest"]) else {
            throw MelixCLIError.missingRequired("--workspace-manifest is required for melix dataset prepare version.")
        }
        guard let ingestReceiptPath = nonEmpty(values.single["--ingest-receipt"]) else {
            throw MelixCLIError.missingRequired("--ingest-receipt is required for melix dataset prepare version.")
        }
        guard let outputRoot = nonEmpty(values.single["--output-root"]) else {
            throw MelixCLIError.missingRequired("--output-root is required for melix dataset prepare version.")
        }
        guard let datasetID = nonEmpty(values.single["--dataset-id"]) else {
            throw MelixCLIError.missingRequired("--dataset-id is required for melix dataset prepare version.")
        }
        return .datasetPrepareVersion(
            .init(
                workspaceManifestPath: workspaceManifestPath,
                ingestReceiptPath: ingestReceiptPath,
                outputRoot: outputRoot,
                datasetID: datasetID,
                versionID: values.single["--version-id"] ?? "",
                createdAt: values.single["--created-at"] ?? "",
                mode: values.single["--mode"] ?? "chat",
                generatorModel: values.single["--generator-model"] ?? "melix.local.dataset-versioner.v1",
                outputKind: values.single["--output-kind"] ?? "training",
                outputFormat: values.single["--output-format"] ?? "prompt_completion",
                validationRatio: values.single["--validation-ratio"] ?? "",
                failSegmentIDs: values.multi["--fail-segment-id"] ?? [],
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseDatasetPrepareRetryFailed(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard let workspaceManifestPath = nonEmpty(values.single["--workspace-manifest"]) else {
            throw MelixCLIError.missingRequired("--workspace-manifest is required for melix dataset prepare retry-failed.")
        }
        guard let datasetVersionPath = nonEmpty(values.single["--dataset-version"]) else {
            throw MelixCLIError.missingRequired("--dataset-version is required for melix dataset prepare retry-failed.")
        }
        guard let outputRoot = nonEmpty(values.single["--output-root"]) else {
            throw MelixCLIError.missingRequired("--output-root is required for melix dataset prepare retry-failed.")
        }
        return .datasetPrepareRetryFailed(
            .init(
                workspaceManifestPath: workspaceManifestPath,
                datasetVersionPath: datasetVersionPath,
                outputRoot: outputRoot,
                versionID: values.single["--version-id"] ?? "",
                createdAt: values.single["--created-at"] ?? "",
                generatorModel: values.single["--generator-model"] ?? "",
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseDatasetPrepareListVersions(_ arguments: [String]) throws -> MelixCLICommand {
        let values = try ArgumentCursor(arguments: arguments).parse()
        guard let workspaceManifestPath = nonEmpty(values.single["--workspace-manifest"]) else {
            throw MelixCLIError.missingRequired("--workspace-manifest is required for melix dataset prepare list-versions.")
        }
        guard let outputRoot = nonEmpty(values.single["--output-root"]) else {
            throw MelixCLIError.missingRequired("--output-root is required for melix dataset prepare list-versions.")
        }
        guard let datasetID = nonEmpty(values.single["--dataset-id"]) else {
            throw MelixCLIError.missingRequired("--dataset-id is required for melix dataset prepare list-versions.")
        }
        return .datasetPrepareListVersions(
            .init(
                workspaceManifestPath: workspaceManifestPath,
                outputRoot: outputRoot,
                datasetID: datasetID,
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseDatasetSynthetic(_ arguments: [String]) throws -> MelixCLICommand {
        guard let mode = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        guard ["preview", "create"].contains(mode) else {
            throw MelixCLIError.usage(usageText)
        }

        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
            multiValueOptions: ["--column", "--header"],
            valueLessFlags: ArgumentCursor.defaultValueLessFlags.subtracting(["--resume"]).union([
                "--enable-datadesigner-telemetry",
                "--disable-datadesigner-telemetry",
            ])
        )
        guard let datasetID = nonEmpty(values.single["--dataset-id"]) else {
            throw MelixCLIError.missingRequired("--dataset-id is required for melix dataset synthetic \(mode).")
        }
        guard let datasetName = nonEmpty(values.single["--dataset-name"]) else {
            throw MelixCLIError.missingRequired("--dataset-name is required for melix dataset synthetic \(mode).")
        }
        guard let numRecords = try parseUInt32Value(values.single["--num-records"], option: "--num-records") else {
            throw MelixCLIError.missingRequired("--num-records is required for melix dataset synthetic \(mode).")
        }
        guard let outputKind = nonEmpty(values.single["--output-kind"]) else {
            throw MelixCLIError.missingRequired("--output-kind is required for melix dataset synthetic \(mode).")
        }
        guard let outputFormat = nonEmpty(values.single["--output-format"]) else {
            throw MelixCLIError.missingRequired("--output-format is required for melix dataset synthetic \(mode).")
        }
        guard let outputDir = nonEmpty(values.single["--output-dir"]) else {
            throw MelixCLIError.missingRequired("--output-dir is required for melix dataset synthetic \(mode).")
        }
        guard let providerEndpoint = nonEmpty(values.single["--provider-endpoint"]) else {
            throw MelixCLIError.missingRequired("--provider-endpoint is required for melix dataset synthetic \(mode).")
        }
        guard let model = nonEmpty(values.single["--model"]) else {
            throw MelixCLIError.missingRequired("--model is required for melix dataset synthetic \(mode).")
        }
        let columns = values.multi["--column"] ?? []
        guard columns.isEmpty == false else {
            throw MelixCLIError.missingRequired("--column is required for melix dataset synthetic \(mode).")
        }
        let resume = values.single["--resume"] ?? "never"
        guard ["never", "if_possible", "always"].contains(resume) else {
            throw MelixCLIError.usage("Invalid value for --resume. Expected never, if_possible, or always.")
        }
        guard values.flags.contains("--enable-datadesigner-telemetry") == false ||
            values.flags.contains("--disable-datadesigner-telemetry") == false
        else {
            throw MelixCLIError.usage(
                "--enable-datadesigner-telemetry and --disable-datadesigner-telemetry are mutually exclusive."
            )
        }
        let seedSourceKind = values.single["--seed-source-kind"] ?? ""
        let seedSourcePath = values.single["--seed-source-path"] ?? ""
        if seedSourceKind.isEmpty != seedSourcePath.isEmpty {
            throw MelixCLIError.usage("--seed-source-kind and --seed-source-path must be provided together.")
        }

        return .datasetSynthetic(
            .init(
                mode: mode,
                datasetID: datasetID,
                datasetName: datasetName,
                numRecords: numRecords,
                outputKind: outputKind,
                outputFormat: outputFormat,
                outputDir: outputDir,
                providerEndpoint: providerEndpoint,
                providerName: values.single["--provider-name"] ?? "melix",
                providerType: values.single["--provider-type"] ?? "openai",
                apiKey: values.single["--api-key"] ?? "",
                headers: values.multi["--header"] ?? [],
                modelAlias: values.single["--model-alias"] ?? "generator",
                model: model,
                temperature: values.single["--temperature"] ?? "",
                topP: values.single["--top-p"] ?? "",
                maxTokens: try parseUInt32Value(values.single["--max-tokens"], option: "--max-tokens") ?? 0,
                timeoutSeconds: values.single["--timeout-seconds"] ?? "",
                maxParallelRequests: try parseUInt32Value(
                    values.single["--max-parallel-requests"],
                    option: "--max-parallel-requests"
                ) ?? 0,
                extraBodyJSON: try canonicalInlineJSONObject(
                    values.single["--extra-body-json"],
                    option: "--extra-body-json"
                ),
                columns: columns,
                seedSourceKind: seedSourceKind,
                seedSourcePath: seedSourcePath,
                validationRatio: values.single["--validation-ratio"] ?? "",
                previewCount: try parseUInt32Value(values.single["--preview-count"], option: "--preview-count") ?? 3,
                randomSeed: try parseIntValue(values.single["--random-seed"], option: "--random-seed"),
                resume: resume,
                enableDataDesignerTelemetry: values.flags.contains("--enable-datadesigner-telemetry"),
                json: values.flags.contains("--json")
            )
        )
    }

    private static func parseDatasetHub(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "download":
            guard let repoID = values.single["--repo-id"], !repoID.isEmpty else {
                throw MelixCLIError.missingRequired("--repo-id is required for melix dataset hub download.")
            }
            return .datasetHubDownload(
                .init(
                    repoID: repoID,
                    revision: values.single["--revision"] ?? "main",
                    hfToken: values.single["--hf-token"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseURI(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        var optionArguments = Array(arguments.dropFirst())
        switch action {
        case "inspect":
            let uri = try extractPositionalValue(
                from: &optionArguments,
                label: "URI",
                command: "melix uri inspect"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .uriInspect(.init(uri: uri, json: values.flags.contains("--json")))
        case "import":
            let uri = try extractPositionalValue(
                from: &optionArguments,
                label: "URI",
                command: "melix uri import"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .uriImport(
                .init(
                    uri: uri,
                    modelID: values.single["--model-id"] ?? "",
                    revision: values.single["--revision"] ?? "",
                    dryRun: values.flags.contains("--dry-run"),
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseRecipes(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        var optionArguments = Array(arguments.dropFirst())
        switch action {
        case "list":
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .recipesList(
                .init(
                    task: values.single["--task"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "show":
            let recipeID = try extractPositionalValue(
                from: &optionArguments,
                label: "RECIPE_ID",
                command: "melix recipes show"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .recipesShow(
                .init(
                    recipeID: recipeID,
                    version: values.single["--version"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "validate":
            let target = try extractPositionalValue(
                from: &optionArguments,
                label: "PATH_OR_ID",
                command: "melix recipes validate"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .recipesValidate(.init(target: target, json: values.flags.contains("--json")))
        case "plan":
            let recipeID = try extractPositionalValue(
                from: &optionArguments,
                label: "RECIPE_ID",
                command: "melix recipes plan"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse(multiValueOptions: ["--set"])
            return .recipesPlan(
                .init(
                    recipeID: recipeID,
                    version: values.single["--version"] ?? "",
                    values: try keyValueMap(from: values.multi["--set"] ?? [], option: "--set"),
                    outputPath: values.single["--output"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "apply":
            let recipeID = try extractPositionalValue(
                from: &optionArguments,
                label: "RECIPE_ID",
                command: "melix recipes apply"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse(multiValueOptions: ["--set"])
            return .recipesApply(
                .init(
                    recipeID: recipeID,
                    version: values.single["--version"] ?? "",
                    values: try keyValueMap(from: values.multi["--set"] ?? [], option: "--set"),
                    dryRun: values.flags.contains("--dry-run"),
                    resume: values.flags.contains("--resume"),
                    fromStepID: values.single["--from-step"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "init":
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            guard let sourceURI = values.single["--from"], sourceURI.isEmpty == false else {
                throw MelixCLIError.missingRequired("--from is required for melix recipes init.")
            }
            guard let task = values.single["--task"], task.isEmpty == false else {
                throw MelixCLIError.missingRequired("--task is required for melix recipes init.")
            }
            return .recipesInit(
                .init(
                    sourceURI: sourceURI,
                    task: task,
                    outputPath: values.single["--output"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseCookbook(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        var optionArguments = Array(arguments.dropFirst())
        switch action {
        case "recommend":
            let modelID = try extractPositionalValue(
                from: &optionArguments,
                label: "MODEL_ID",
                command: "melix cookbook recommend"
            )
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            guard let workload = values.single["--workload"],
                  workload.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            else {
                throw MelixCLIError.missingRequired("--workload is required for melix cookbook recommend.")
            }
            return .cookbookRecommend(
                .init(
                    modelID: modelID,
                    workload: workload,
                    serverPlatform: values.single["--server-platform"] ?? "",
                    serverArch: values.single["--server-arch"] ?? "",
                    operatorPlatform: values.single["--operator-platform"] ?? "",
                    operatorArch: values.single["--operator-arch"] ?? "",
                    browserPlatform: values.single["--browser-platform"] ?? "",
                    browserArch: values.single["--browser-arch"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func extractPositionalValue(
        from arguments: inout [String],
        label: String,
        command: String
    ) throws -> String {
        guard let first = arguments.first, first.hasPrefix("--") == false else {
            throw MelixCLIError.missingRequired("\(label) is required for \(command).")
        }
        arguments.removeFirst()
        let value = first.trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.isEmpty == false else {
            throw MelixCLIError.missingRequired("\(label) is required for \(command).")
        }
        return value
    }

    private static func keyValueMap(from rawValues: [String], option: String) throws -> [String: String] {
        var values: [String: String] = [:]
        for rawValue in rawValues {
            let parts = rawValue.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard parts.count == 2, parts[0].isEmpty == false else {
                throw MelixCLIError.usage("\(option) must use KEY=VALUE.")
            }
            values[String(parts[0])] = String(parts[1])
        }
        return values
    }

    private static func parseServer(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        if action == "session" {
            return try parseServerSession(Array(arguments.dropFirst()))
        }
        if action == "start" {
            return try parseServerStart(Array(arguments.dropFirst()))
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        let serverSessionID = values.single["--server-session-id"] ?? ServerSessionRuntimeStore.defaultServerSessionID
        let json = values.flags.contains("--json")
        switch action {
        case "snapshot":
            return .serverSnapshot(.init(json: json))
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

    private static func parseServerStart(_ arguments: [String]) throws -> MelixCLICommand {
        let serverTitle: String
        let optionArguments: [String]
        if let first = arguments.first, first.hasPrefix("--") == false {
            serverTitle = first
            optionArguments = Array(arguments.dropFirst())
        } else {
            serverTitle = ""
            optionArguments = arguments
        }
        let values = try ArgumentCursor(arguments: optionArguments).parse(
            multiValueOptions: ["--model", "--models", "--allowed-host", "--allowed-origin"]
        )
        let serverSessionID = values.single["--server-session-id"] ?? ServerSessionRuntimeStore.defaultServerSessionID
        let json = values.flags.contains("--json")
        let modelIDs = parsedModelRoster(
            singleModel: "",
            modelValues: values.multi["--model"] ?? [],
            modelsValues: values.multi["--models"] ?? []
        )
        let defaultModelID = (values.single["--default-model"] ?? modelIDs.first ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return .serverStart(.init(
            serverSessionID: serverSessionID,
            serverTitle: serverTitle,
            defaultModelID: defaultModelID,
            servedModelIDs: modelIDs,
            host: values.single["--host"] ?? "",
            port: try parseIntValue(values.single["--port"], option: "--port", defaultValue: 0) ?? 0,
            allowedHosts: values.multi["--allowed-host"] ?? [],
            allowedOrigins: values.multi["--allowed-origin"] ?? [],
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
            modelIdleTimeoutSeconds: try parseIntValue(
                values.single["--model-idle-timeout-seconds"],
                option: "--model-idle-timeout-seconds",
                defaultValue: 0
            ) ?? 0,
            json: json
        ))
    }

    private static func parseServerSession(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
            multiValueOptions: ["--model", "--models", "--allowed-host", "--allowed-origin"],
            valueLessFlags: ArgumentCursor.defaultValueLessFlags.union([
                "--clear-allowed-hosts",
                "--clear-allowed-origins",
            ])
        )
        switch action {
        case "list":
            return .serverSessionList(.init(json: values.flags.contains("--json")))
        case "create":
            guard let title = values.single["--title"], !title.isEmpty else {
                throw MelixCLIError.missingRequired("--title is required for melix server session create.")
            }
            let modelIDs = parsedModelRoster(
                singleModel: "",
                modelValues: values.multi["--model"] ?? [],
                modelsValues: values.multi["--models"] ?? []
            )
            let defaultModelID = (values.single["--default-model"] ?? modelIDs.first ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !defaultModelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model or --models is required for melix server session create.")
            }
            let port = try parseIntValue(
                values.single["--port"],
                option: "--port",
                defaultValue: MelixGatewayDefaults.port
            ) ?? MelixGatewayDefaults.port
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
            let modelIdleTimeoutSeconds = try parseIntValue(
                values.single["--model-idle-timeout-seconds"],
                option: "--model-idle-timeout-seconds",
                defaultValue: 600
            ) ?? 600
            let servingDefaults = try parseCreateServerSessionServingDefaults(values)
            return .serverSessionCreate(
                .init(
                    title: title,
                    defaultModelID: defaultModelID,
                    servedModelIDs: modelIDs,
                    host: values.single["--host"] ?? MelixGatewayDefaults.host,
                    port: port,
                    allowedHosts: values.multi["--allowed-host"] ?? [],
                    allowedOrigins: values.multi["--allowed-origin"] ?? [],
                    rateLimitPerMinute: rateLimit,
                    timeoutSeconds: timeoutSeconds,
                    modelIdleTimeoutSeconds: modelIdleTimeoutSeconds,
                    accelerationProfile: servingDefaults.accelerationProfile,
                    accelerationMode: servingDefaults.accelerationMode,
                    draftModelID: servingDefaults.draftModelID,
                    numDraftTokens: servingDefaults.numDraftTokens,
                    json: values.flags.contains("--json")
                )
            )
        case "update":
            guard let serverSessionID = values.single["--server-session-id"], !serverSessionID.isEmpty else {
                throw MelixCLIError.missingRequired("--server-session-id is required for melix server session update.")
            }
            let clearAllowedHosts = values.flags.contains("--clear-allowed-hosts")
            let clearAllowedOrigins = values.flags.contains("--clear-allowed-origins")
            if clearAllowedHosts && (values.multi["--allowed-host"] ?? []).isEmpty == false {
                throw MelixCLIError.usage("--allowed-host and --clear-allowed-hosts are mutually exclusive.")
            }
            if clearAllowedOrigins && (values.multi["--allowed-origin"] ?? []).isEmpty == false {
                throw MelixCLIError.usage("--allowed-origin and --clear-allowed-origins are mutually exclusive.")
            }
            let modelIDs = parsedModelRoster(
                singleModel: "",
                modelValues: values.multi["--model"] ?? [],
                modelsValues: values.multi["--models"] ?? []
            )
            let defaultModelID = (values.single["--default-model"] ?? modelIDs.first ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let servingDefaults = try parseUpdateServerSessionServingDefaults(values)
            return .serverSessionUpdate(
                .init(
                    serverSessionID: serverSessionID,
                    title: values.single["--title"] ?? "",
                    defaultModelID: defaultModelID,
                    servedModelIDs: modelIDs,
                    host: values.single["--host"] ?? "",
                    port: try parseIntValue(values.single["--port"], option: "--port", defaultValue: 0) ?? 0,
                    allowedHosts: values.multi["--allowed-host"] ?? [],
                    allowedOrigins: values.multi["--allowed-origin"] ?? [],
                    clearAllowedHosts: clearAllowedHosts,
                    clearAllowedOrigins: clearAllowedOrigins,
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
                    modelIdleTimeoutSeconds: try parseIntValue(
                        values.single["--model-idle-timeout-seconds"],
                        option: "--model-idle-timeout-seconds",
                        defaultValue: 0
                    ) ?? 0,
                    accelerationProfile: servingDefaults.accelerationProfile,
                    accelerationMode: servingDefaults.accelerationMode,
                    draftModelID: servingDefaults.draftModelID,
                    numDraftTokens: servingDefaults.numDraftTokens,
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

    private static func parseCreateServerSessionServingDefaults(
        _ values: ParsedArguments
    ) throws -> (accelerationProfile: String, accelerationMode: String, draftModelID: String, numDraftTokens: Int) {
        let profileID = try normalizedServingDefaultsAccelerationProfile(
            values.single["--acceleration-profile"],
            defaultValue: ServingAccelerationProfiles.defaultProfileID,
            allowEmpty: false
        )
        let profile = ServingAccelerationProfiles.profile(id: profileID)
        let draftModelID = trimmedOption(values.single["--draft-model-id"])
        let accelerationMode = try normalizedServingDefaultsAccelerationMode(
            values.single["--acceleration-mode"],
            defaultValue: draftModelID.isEmpty
                ? ServingAccelerationProfiles.controlPlaneRawValue(profile.accelerationMode)
                : "speculative_decode"
        )
        let numDraftTokens = try parseNonNegativeIntValue(
            values.single["--num-draft-tokens"],
            option: "--num-draft-tokens",
            defaultValue: accelerationMode == "speculative_decode" ? Int(max(profile.numDraftTokens, UInt32(defaultSpeculativeNumDraftTokens))) : 0
        )

        if accelerationMode == "baseline" {
            guard draftModelID.isEmpty else {
                throw MelixCLIError.usage("--draft-model-id requires --acceleration-mode speculative_decode.")
            }
            return (profileID, accelerationMode, "", 0)
        }

        guard !draftModelID.isEmpty else {
            throw MelixCLIError.missingRequired("--draft-model-id is required for speculative decode serving defaults.")
        }
        guard numDraftTokens > 0 else {
            throw MelixCLIError.usage("--num-draft-tokens must be greater than zero for speculative decode.")
        }
        return (profileID, accelerationMode, draftModelID, numDraftTokens)
    }

    private static func parseUpdateServerSessionServingDefaults(
        _ values: ParsedArguments
    ) throws -> (accelerationProfile: String, accelerationMode: String, draftModelID: String, numDraftTokens: Int) {
        let profileID = try normalizedServingDefaultsAccelerationProfile(
            values.single["--acceleration-profile"],
            defaultValue: "",
            allowEmpty: true
        )
        let profile = profileID.isEmpty ? nil : ServingAccelerationProfiles.profile(id: profileID)
        let draftModelID = trimmedOption(values.single["--draft-model-id"])
        let accelerationMode = try normalizedServingDefaultsAccelerationMode(
            values.single["--acceleration-mode"],
            defaultValue: draftModelID.isEmpty
                ? profile.map { ServingAccelerationProfiles.controlPlaneRawValue($0.accelerationMode) } ?? ""
                : "speculative_decode",
            allowEmpty: true
        )
        let numDraftTokens = try parseNonNegativeIntValue(
            values.single["--num-draft-tokens"],
            option: "--num-draft-tokens",
            defaultValue: profile.map { Int($0.numDraftTokens) } ?? 0
        )

        if accelerationMode == "baseline" {
            guard draftModelID.isEmpty else {
                throw MelixCLIError.usage("--draft-model-id requires --acceleration-mode speculative_decode.")
            }
            return (profileID, accelerationMode, "", 0)
        }
        return (profileID, accelerationMode, draftModelID, numDraftTokens)
    }

    private static func parsedModelRoster(
        singleModel: String,
        modelValues: [String],
        modelsValues: [String]
    ) -> [String] {
        var ordered: [String] = []
        var seen: Set<String> = []
        for rawValue in [singleModel] + modelValues + modelsValues {
            for modelID in rawValue
                .split(separator: ",")
                .map({ String($0).trimmingCharacters(in: .whitespacesAndNewlines) })
                where !modelID.isEmpty {
                guard seen.insert(modelID).inserted else {
                    continue
                }
                ordered.append(modelID)
            }
        }
        return ordered
    }

    private static func parseChat(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "run":
            let modelID = values.single["--model-id"] ?? ""
            let remoteServerID = values.single["--remote-server-id"] ?? ""
            let remoteModelID = values.single["--model"] ?? values.single["--remote-model"] ?? ""
            let explicitTargetCount = [modelID, remoteServerID].filter { !$0.isEmpty }.count
            guard explicitTargetCount == 1 else {
                throw MelixCLIError.missingRequired(
                    "Exactly one of --model-id or --remote-server-id is required for melix chat run."
                )
            }
            if remoteServerID.isEmpty == false, remoteModelID.isEmpty {
                throw MelixCLIError.missingRequired("--model is required when using --remote-server-id for melix chat run.")
            }
            guard let message = values.single["--message"], !message.isEmpty else {
                throw MelixCLIError.missingRequired("--message is required for melix chat run.")
            }
            return .chatRun(
                .init(
                    modelID: modelID,
                    remoteServerID: remoteServerID,
                    remoteModelID: remoteModelID,
                    message: message,
                    systemPrompt: values.single["--system"] ?? "",
                    serverSessionID: values.single["--server-session-id"] ?? ServerSessionRuntimeStore.defaultServerSessionID,
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseRemoteServer(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        let json = values.flags.contains("--json")
        switch action {
        case "list":
            return .remoteServerList(.init(json: json))
        case "add":
            guard let remoteServerID = values.single["--remote-server-id"], remoteServerID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--remote-server-id is required for melix remote-server add.")
            }
            guard let title = values.single["--title"], title.isEmpty == false else {
                throw MelixCLIError.missingRequired("--title is required for melix remote-server add.")
            }
            let providerPreset = try parseRemoteServerProviderPreset(values.single["--provider"] ?? "custom")
            let baseURL = try parseRemoteServerBaseURL(
                providerPreset: providerPreset,
                explicitBaseURL: values.single["--base-url"] ?? "",
                requiresCustomBaseURL: true,
                action: "add"
            )
            guard let modelID = values.single["--model"], modelID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--model is required for melix remote-server add.")
            }
            return .remoteServerAdd(
                .init(
                    remoteServerID: remoteServerID,
                    title: title,
                    providerPreset: providerPreset,
                    providerKind: providerPreset.providerKind,
                    baseURL: baseURL,
                    defaultModelID: modelID,
                    apiKey: values.single["--api-key"] ?? "",
                    timeoutSeconds: try parseUInt32Value(
                        values.single["--timeout-seconds"],
                        option: "--timeout-seconds",
                        defaultValue: 60
                    ) ?? 60,
                    rateLimitPerMinute: try parseUInt32Value(
                        values.single["--rate-limit-per-minute"],
                        option: "--rate-limit-per-minute",
                        defaultValue: 0
                    ) ?? 0,
                    json: json
                )
            )
        case "update":
            guard let remoteServerID = values.single["--remote-server-id"], remoteServerID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--remote-server-id is required for melix remote-server update.")
            }
            let providerPreset = try values.single["--provider"].map { try parseRemoteServerProviderPreset($0) }
            let baseURL: String
            if let providerPreset {
                baseURL = try parseRemoteServerBaseURL(
                    providerPreset: providerPreset,
                    explicitBaseURL: values.single["--base-url"] ?? "",
                    requiresCustomBaseURL: providerPreset == .custom,
                    action: "update"
                )
            } else {
                baseURL = values.single["--base-url"] ?? ""
            }
            return .remoteServerUpdate(
                .init(
                    remoteServerID: remoteServerID,
                    title: values.single["--title"] ?? "",
                    providerPreset: providerPreset,
                    providerKind: providerPreset?.providerKind ?? "",
                    baseURL: baseURL,
                    defaultModelID: values.single["--model"] ?? "",
                    apiKey: values.single["--api-key"] ?? "",
                    timeoutSeconds: try parseUInt32Value(
                        values.single["--timeout-seconds"],
                        option: "--timeout-seconds",
                        defaultValue: 0
                    ) ?? 0,
                    rateLimitPerMinute: try parseUInt32Value(
                        values.single["--rate-limit-per-minute"],
                        option: "--rate-limit-per-minute",
                        defaultValue: 0
                    ) ?? 0,
                    json: json
                )
            )
        case "remove":
            guard let remoteServerID = values.single["--remote-server-id"], remoteServerID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--remote-server-id is required for melix remote-server remove.")
            }
            return .remoteServerRemove(.init(remoteServerID: remoteServerID, json: json))
        case "test":
            guard let remoteServerID = values.single["--remote-server-id"], remoteServerID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--remote-server-id is required for melix remote-server test.")
            }
            return .remoteServerTest(
                .init(
                    remoteServerID: remoteServerID,
                    remoteModelID: values.single["--model"] ?? values.single["--remote-model"] ?? "",
                    json: json
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseRemoteServerProviderPreset(_ rawValue: String) throws -> RemoteServerProviderPreset {
        if let providerPreset = RemoteServerProviderPreset.normalized(rawValue) {
            return providerPreset
        }
        throw MelixCLIError.usage(
            "--provider must be one of kimi, gemini, deepseek, glm, or custom."
        )
    }

    private static func parseRemoteServerBaseURL(
        providerPreset: RemoteServerProviderPreset,
        explicitBaseURL: String,
        requiresCustomBaseURL: Bool,
        action: String
    ) throws -> String {
        let trimmedBaseURL = explicitBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if let fixedBaseURL = providerPreset.fixedBaseURL {
            if trimmedBaseURL.isEmpty == false {
                throw MelixCLIError.usage(
                    "--base-url cannot be used with --provider \(providerPreset.rawValue); Melix uses \(fixedBaseURL)."
                )
            }
            return fixedBaseURL
        }
        if requiresCustomBaseURL && trimmedBaseURL.isEmpty {
            throw MelixCLIError.missingRequired(
                "--base-url is required for melix remote-server \(action) when --provider custom is used."
            )
        }
        return trimmedBaseURL
    }

    private static func parseAlignment(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let cursor = ArgumentCursor(arguments: Array(arguments.dropFirst()))
        switch action {
        case "train":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix alignment train.")
            }
            let datasetURI = values.single["--dataset-uri"] ?? ""
            let hfDatasetPath = values.single["--hf-dataset-path"] ?? ""
            guard !datasetURI.isEmpty || !hfDatasetPath.isEmpty else {
                throw MelixCLIError.missingRequired("Either --dataset-uri or --hf-dataset-path is required for melix alignment train.")
            }
            guard let adapterName = values.single["--adapter-name"], !adapterName.isEmpty else {
                throw MelixCLIError.missingRequired("--adapter-name is required for melix alignment train.")
            }
            let algorithm = (values.single["--algorithm"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !algorithm.isEmpty else {
                throw MelixCLIError.missingRequired("--algorithm is required for melix alignment train.")
            }
            if ["dpo", "orpo", "cpo", "grpo", "rlhf"].contains(algorithm) == false {
                throw MelixCLIError.usage("Invalid value for --algorithm. Expected one of: dpo, orpo, cpo, grpo, rlhf.")
            }
            let candidateGenerationMode = (values.single["--candidate-generation-mode"] ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            if candidateGenerationMode.isEmpty == false,
               ["scored_trace", "runtime_generate"].contains(candidateGenerationMode) == false {
                throw MelixCLIError.usage("Invalid value for --candidate-generation-mode. Expected one of: scored_trace, runtime_generate.")
            }
            let candidateScoringMode = (values.single["--candidate-scoring-mode"] ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            if candidateScoringMode.isEmpty == false,
               ["dataset_score", "seed_overlap_proxy", "reward_model"].contains(candidateScoringMode) == false {
                throw MelixCLIError.usage("Invalid value for --candidate-scoring-mode. Expected one of: dataset_score, seed_overlap_proxy, reward_model.")
            }
            let loraResumeAdapter = (values.single["--resume-adapter"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let loraResumeManifest = (values.single["--resume-from-manifest"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if loraResumeAdapter.isEmpty == false || loraResumeManifest.isEmpty == false {
                throw MelixCLIError.usage(
                    "--resume-adapter and --resume-from-manifest are only for melix lora train checkpoint resumption. For melix alignment train, use --source-adapter-path for the upstream/base LoRA adapter to carry into GRPO/RLHF output."
                )
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
                "--max-steps",
                "--learning-rate",
                "--max-seq-length",
                "--sample-limit",
                "--gradient-accumulation",
                "--hf-dataset-path",
                "--hf-dataset-name",
                "--hf-dataset-revision",
                "--hf-train-split",
                "--hf-valid-split",
                "--chat-feature",
                "--prompt-feature",
                "--completion-feature",
                "--text-feature",
                "--grpo-candidate-count",
                "--candidate-generation-max-tokens",
                "--source-adapter-path",
                "--reference-model-path",
                "--reward-model-manifest-path",
                "--kl-penalty",
            ] {
                if let value = values.single[option] {
                    parameters[normalizedParameterKey(option)] = value
                }
            }
            if candidateGenerationMode.isEmpty == false {
                parameters["candidate_generation_mode"] = candidateGenerationMode
            }
            if candidateScoringMode.isEmpty == false {
                parameters["candidate_scoring_mode"] = candidateScoringMode
            }
            if let presetID = values.single["--preset"] {
                parameters["preset_id"] = presetID
            }
            if let experimentGroupID = values.single["--experiment-group"] {
                parameters["experiment_group_id"] = experimentGroupID
            }
            return .alignmentTrain(
                AlignmentTrainOptions(
                    modelID: modelID,
                    datasetSourceKind: datasetSourceKind,
                    datasetURI: datasetURI,
                    adapterName: adapterName,
                    targetRepo: values.single["--target-repo"] ?? "",
                    algorithm: algorithm,
                    parameters: parameters,
                    json: values.flags.contains("--json")
                )
            )
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
            return .loraTrain(
                try parseLoraTrainOptions(
                    values,
                    command: "melix lora train",
                    allowAutoTrainingMode: false,
                    jsonOverride: nil
                )
            )
        case "run":
            let values = try cursor.parse(multiValueOptions: ["--suite", "--eval-suite", "--ignored-path"])
            let training = try parseLoraTrainOptions(
                values,
                command: "melix lora run",
                allowAutoTrainingMode: true,
                jsonOverride: false
            )
            let activationMode = values.single["--activation-mode"] ?? "adapter_backed_runtime"
            if ["fused_derived_model", "adapter_backed_runtime"].contains(activationMode) == false {
                throw MelixCLIError.usage(
                    "Invalid value for --activation-mode. Expected one of: fused_derived_model, adapter_backed_runtime."
                )
            }
            let evalDatasetID = values.single["--eval-dataset-id"] ?? values.single["--dataset-id"] ?? ""
            guard evalDatasetID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--eval-dataset-id is required for melix lora run.")
            }
            let evalSuites = (values.multi["--eval-suite"] ?? []) + (values.multi["--suite"] ?? [])
            var evalParameters = try parseEvalParameters(values)
            if let evalDatasetRoot = values.single["--eval-dataset-root"], evalDatasetRoot.isEmpty == false {
                evalParameters["dataset_root"] = evalDatasetRoot
            }
            let sourceConfiguration = try parseLoraRunEvaluationSourceConfiguration(values)
            return .loraRun(
                LoraRunOptions(
                    training: training,
                    activationMode: activationMode,
                    evaluation: EvalCompareOptions(
                        modelID: training.modelID,
                        suites: evalSuites,
                        datasetID: evalDatasetID,
                        sampleSize: UInt32(values.single["--eval-sample-size"] ?? values.single["--sample-size"] ?? "") ?? 0,
                        source: sourceConfiguration.source,
                        fieldMapping: sourceConfiguration.fieldMapping,
                        profile: sourceConfiguration.profile,
                        parameters: evalParameters,
                        json: false
                    ),
                    outputDir: values.single["--output-dir"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "dataset":
            return try parseLoraDataset(Array(arguments.dropFirst()))
        case "activate":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora activate.")
            }
            guard let adapterPath = values.single["--adapter-path"], !adapterPath.isEmpty else {
                throw MelixCLIError.missingRequired("--adapter-path is required for melix lora activate.")
            }
            let activationMode = values.single["--activation-mode"] ?? ""
            if !activationMode.isEmpty,
               ["fused_derived_model", "adapter_backed_runtime"].contains(activationMode) == false {
                throw MelixCLIError.usage(
                    "Invalid value for --activation-mode. Expected one of: fused_derived_model, adapter_backed_runtime."
                )
            }
            return .loraActivate(
                LoraActivateOptions(
                    modelID: modelID,
                    adapterPath: adapterPath,
                    derivedModelAlias: values.single["--alias"] ?? "",
                    activationMode: activationMode,
                    json: values.flags.contains("--json")
                )
            )
        case "remove-derived":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora remove-derived.")
            }
            let derivedModelID = values.single["--derived-model-id"] ?? ""
            let manifestPath = values.single["--manifest-path"] ?? ""
            guard !derivedModelID.isEmpty || !manifestPath.isEmpty else {
                throw MelixCLIError.missingRequired(
                    "Either --derived-model-id or --manifest-path is required for melix lora remove-derived."
                )
            }
            return .loraRemoveDerived(
                LoraRemoveDerivedOptions(
                    modelID: modelID,
                    derivedModelID: derivedModelID,
                    manifestPath: manifestPath,
                    json: values.flags.contains("--json")
                )
            )
        case "publish":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora publish.")
            }
            guard let targetRepo = values.single["--target-repo"], !targetRepo.isEmpty else {
                throw MelixCLIError.missingRequired("--target-repo is required for melix lora publish.")
            }
            let adapterPath = values.single["--adapter-path"] ?? ""
            let mergedModelPath = values.single["--merged-model-path"] ?? ""
            let manifestPath = values.single["--manifest-path"] ?? ""
            let selectedCount = [adapterPath, mergedModelPath, manifestPath].filter { $0.isEmpty == false }.count
            guard selectedCount == 1 else {
                throw MelixCLIError.missingRequired(
                    "Exactly one of --adapter-path, --merged-model-path, or --manifest-path is required for melix lora publish."
                )
            }
            let explicitExportKind: LoraPublishExportKind?
            if let rawKind = values.single["--export-kind"], !rawKind.isEmpty {
                switch rawKind {
                case "adapter", "adapter_export":
                    explicitExportKind = .adapterExport
                case "merged", "merged_export":
                    explicitExportKind = .mergedExport
                default:
                    throw MelixCLIError.usage("Invalid value for --export-kind. Expected one of: adapter, merged.")
                }
            } else {
                explicitExportKind = nil
            }
            // Parser stays pure — we only check the flag combinations here;
            // any manifest read + classification happens in the runner
            // (`resolveLoraPublishExportKind`) at dispatch time.
            let exportKind: LoraPublishExportKind?
            let artifactPath: String
            let artifactManifestPath: String
            if adapterPath.isEmpty == false {
                if explicitExportKind == .mergedExport {
                    throw MelixCLIError.usage("--export-kind merged is incompatible with --adapter-path.")
                }
                exportKind = .adapterExport
                artifactPath = adapterPath
                // Adapter publish accepts the adapter manifest JSON itself as the source artifact.
                artifactManifestPath = adapterPath
            } else if mergedModelPath.isEmpty == false {
                if explicitExportKind == .adapterExport {
                    throw MelixCLIError.usage("--export-kind adapter is incompatible with --merged-model-path.")
                }
                exportKind = .mergedExport
                artifactPath = mergedModelPath
                artifactManifestPath = ""
            } else {
                // --manifest-path: defer classification to the runner unless --export-kind overrode it.
                exportKind = explicitExportKind
                artifactPath = manifestPath
                artifactManifestPath = manifestPath
            }
            return .loraPublish(
                LoraPublishOptions(
                    modelID: modelID,
                    targetRepo: targetRepo,
                    exportKind: exportKind,
                    artifactPath: artifactPath,
                    artifactManifestPath: artifactManifestPath,
                    publishBackend: values.single["--publish-backend"] ?? "",
                    localPublishRoot: values.single["--local-publish-root"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "experiments":
            return try parseLoraExperiments(Array(arguments.dropFirst()))
        case "publishes":
            return try parseLoraPublishes(Array(arguments.dropFirst()))
        case "resume":
            let values = try cursor.parse()
            guard let groupID = values.single["--group-id"], !groupID.isEmpty else {
                throw MelixCLIError.missingRequired("--group-id is required for melix lora resume.")
            }
            return .loraResume(
                LoraResumeOptions(
                    modelID: values.single["--model-id"] ?? "",
                    groupID: groupID,
                    presetID: values.single["--preset"] ?? "",
                    adapterName: values.single["--adapter-name"] ?? "",
                    datasetURI: values.single["--dataset-uri"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseLoraExperiments(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "list":
            return .loraExperimentsList(
                LoraExperimentsListOptions(
                    modelID: values.single["--model-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "show":
            guard let groupID = values.single["--group-id"], !groupID.isEmpty else {
                throw MelixCLIError.missingRequired(
                    "--group-id is required for melix lora experiments show."
                )
            }
            return .loraExperimentsShow(
                LoraExperimentsShowOptions(
                    modelID: values.single["--model-id"] ?? "",
                    groupID: groupID,
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseLoraPublishes(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "list":
            return .loraPublishesList(
                LoraPublishesListOptions(
                    modelID: values.single["--model-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "show":
            guard let jobID = values.single["--job-id"], !jobID.isEmpty else {
                throw MelixCLIError.missingRequired(
                    "--job-id is required for melix lora publishes show."
                )
            }
            return .loraPublishesShow(
                LoraPublishesShowOptions(
                    modelID: values.single["--model-id"] ?? "",
                    jobID: jobID,
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseLoraDataset(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model-id is required for melix lora dataset \(action).")
        }
        let datasetURI = values.single["--dataset-uri"] ?? ""
        let hfDatasetPath = values.single["--hf-dataset-path"] ?? ""
        guard !datasetURI.isEmpty || !hfDatasetPath.isEmpty else {
            throw MelixCLIError.missingRequired(
                "Either --dataset-uri or --hf-dataset-path is required for melix lora dataset \(action)."
            )
        }

        let datasetSourceKind = hfDatasetPath.isEmpty ? "local_path" : "hf_dataset"
        var parameters: [String: String] = [:]
        for option in [
            "--hf-dataset-path",
            "--hf-dataset-name",
            "--hf-dataset-revision",
            "--hf-train-split",
            "--hf-valid-split",
            "--text-feature",
            "--prompt-feature",
            "--completion-feature",
            "--chat-feature",
            "--template",
            "--dataset-id",
            "--validation-ratio",
            "--sample-limit",
            "--preview-count",
        ] {
            if let value = values.single[option] {
                parameters[normalizedParameterKey(option)] = value
            }
        }

        switch action {
        case "inspect":
            return .loraDatasetInspect(
                LoraDatasetInspectOptions(
                    modelID: modelID,
                    datasetSourceKind: datasetSourceKind,
                    datasetURI: datasetURI,
                    parameters: parameters,
                    json: values.flags.contains("--json")
                )
            )
        case "build":
            return .loraDatasetBuild(
                LoraDatasetBuildOptions(
                    modelID: modelID,
                    datasetSourceKind: datasetSourceKind,
                    datasetURI: datasetURI,
                    outputDir: values.single["--output-dir"] ?? "",
                    parameters: parameters,
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
            let repeats = try parseBenchmarkRepeatValue(values.single["--repeats"], option: "--repeats", defaultValue: 1) ?? 1
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
            if let datasetRef = values.single["--dataset-ref"], datasetRef.isEmpty == false {
                let parsedRef = try parseDatasetReference(datasetRef)
                parameters["dataset_ref"] = datasetRef
                parameters["hf_dataset_path"] = parsedRef.repoID
                parameters["hf_dataset_revision"] = parsedRef.revision
            }
            for option in [
                "--hf-dataset-name",
                "--hf-dataset-split",
                "--prompt-feature",
                "--text-feature",
                "--image-feature",
                "--source-image-feature",
                "--mask-feature",
            ] {
                if let value = values.single[option], value.isEmpty == false {
                    parameters[normalizedParameterKey(option)] = value
                }
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
                    preflightFitCheck: values.flags.contains("--preflight-fit-check"),
                    allowMemoryRisk: values.flags.contains("--allow-memory-risk"),
                    json: values.flags.contains("--json"),
                    liveProgress: values.flags.contains("--no-live") == false
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
        case "report":
            let format = values.single["--format"] ?? "markdown"
            guard let sourcePath = values.single["--from"], !sourcePath.isEmpty else {
                throw MelixCLIError.missingRequired("--from is required for melix bench report.")
            }
            return .benchReport(RunReportOptions(sourcePath: sourcePath, format: format))
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
            let repeats = try parseBenchmarkRepeatValue(values.single["--repeats"], option: "--repeats", defaultValue: 1) ?? 1
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
                    json: values.flags.contains("--json"),
                    liveProgress: values.flags.contains("--no-live") == false
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
        switch action {
        case "run":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
                multiValueOptions: ["--suite", "--target-model-id", "--ignored-path", "--remote-server-id", "--remote-model"]
            )
            let modelID = values.single["--model-id"] ?? ""
            let hfRepoID = values.single["--repo-id"] ?? ""
            let remoteServerIDs = (values.multi["--remote-server-id"] ?? [])
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { $0.isEmpty == false }
            var remoteModelIDs = (values.multi["--remote-model"] ?? [])
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            if let modelAlias = values.single["--model"]?.trimmingCharacters(in: .whitespacesAndNewlines),
               modelAlias.isEmpty == false
            {
                remoteModelIDs.append(modelAlias)
            }
            let remoteTargets = try parseEvalRemoteTargets(
                remoteServerIDs: remoteServerIDs,
                remoteModelIDs: remoteModelIDs
            )
            let remoteServerID = remoteTargets.first?.remoteServerID ?? ""
            let remoteModelID = remoteTargets.first?.remoteModelID ?? ""
            let explicitTargetCount = [modelID, hfRepoID].filter { !$0.isEmpty }.count
                + (remoteTargets.isEmpty ? 0 : 1)
            guard explicitTargetCount == 1 else {
                throw MelixCLIError.missingRequired(
                    "Exactly one of --model-id, --repo-id, or --remote-server-id is required for melix eval run."
                )
            }
            let sourceConfiguration = try parseEvaluationSourceConfiguration(
                values,
                command: "melix eval run"
            )
            let semanticJudgeRemoteServerID = values.single["--semantic-judge-remote-server-id"] ?? ""
            let semanticJudgeModelID = values.single["--semantic-judge-model"] ?? ""
            if semanticJudgeRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
               semanticJudgeModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            {
                throw MelixCLIError.missingRequired(
                    "--semantic-judge-remote-server-id is required when using --semantic-judge-model for melix eval run."
                )
            }
            let sampleSize = UInt32(values.single["--sample-size"] ?? "") ?? 0
            let scoringMode = sourceConfiguration.profile.scoringMode
            let suites = defaultedEvaluationSuites(
                explicitSuites: values.multi["--suite"] ?? [],
                scoringMode: scoringMode
            )
            try validateEvalPromptOptions(values)
            return .evalRun(
                EvalRunOptions(
                    modelID: modelID,
                    hfRepoID: hfRepoID,
                    remoteServerID: remoteServerID,
                    remoteModelID: remoteModelID,
                    remoteTargets: remoteTargets,
                    suites: suites,
                    datasetID: values.single["--dataset-id"] ?? "",
                    sampleSize: sampleSize,
                    source: sourceConfiguration.source,
                    fieldMapping: sourceConfiguration.fieldMapping,
                    profile: sourceConfiguration.profile,
                    parameters: try parseEvalParameters(values),
                    evalPromptID: values.single["--eval-prompt-id"] ?? "",
                    evalPromptRevisionID: values.single["--eval-prompt-revision"] ?? "",
                    evalPrompt: values.single["--eval-prompt"] ?? "",
                    evalPromptFile: values.single["--eval-prompt-file"] ?? "",
                    semanticJudgeRemoteServerID: semanticJudgeRemoteServerID,
                    semanticJudgeModelID: semanticJudgeModelID,
                    remoteParallelism: UInt32(values.single["--remote-parallelism"] ?? "") ?? 0,
                    preflightFitCheck: values.flags.contains("--preflight-fit-check"),
                    allowMemoryRisk: values.flags.contains("--allow-memory-risk"),
                    json: values.flags.contains("--json"),
                    liveProgress: values.flags.contains("--no-live") == false
                )
            )
        case "prompt":
            return try parseEvalPrompt(Array(arguments.dropFirst()))
        case "compare":
            return try parseEvalCompare(Array(arguments.dropFirst()))
        case "list":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
                multiValueOptions: ["--suite", "--target-model-id"]
            )
            return .evalList(EvalListOptions(json: values.flags.contains("--json")))
        case "export-summary-csv":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
                multiValueOptions: ["--suite", "--target-model-id"]
            )
            return .evalExportSummaryCSV(try parseEvalExportOptions(values, command: "melix eval export-summary-csv"))
        case "export-samples-csv":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
                multiValueOptions: ["--suite", "--target-model-id"]
            )
            return .evalExportSamplesCSV(try parseEvalExportOptions(values, command: "melix eval export-samples-csv"))
        case "export-samples-jsonl":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
                multiValueOptions: ["--suite", "--target-model-id"]
            )
            return .evalExportSamplesJSONL(try parseEvalExportOptions(values, command: "melix eval export-samples-jsonl"))
        case "report":
            let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse(
                multiValueOptions: ["--suite", "--target-model-id"]
            )
            guard let sourcePath = values.single["--from"], !sourcePath.isEmpty else {
                throw MelixCLIError.missingRequired("--from is required for melix eval report.")
            }
            return .evalReport(RunReportOptions(sourcePath: sourcePath, format: values.single["--format"] ?? "markdown"))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseBatch(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst()))
            .parse(valueLessFlags: ArgumentCursor.defaultValueLessFlags.union(["--preflight"]))
        switch action {
        case "run":
            let explicitOptions = Set(values.single.keys).union(values.flags)
            let continueOnFailure = try parseRequiredBooleanValue(
                values.single["--continue-on-failure"],
                option: "--continue-on-failure",
                defaultValue: true
            )
            let restartStackPerModel = try parseRequiredBooleanValue(
                values.single["--restart-stack-per-model"],
                option: "--restart-stack-per-model",
                defaultValue: true
            )
            return .batchRun(
                BatchRunOptions(
                    modelListPath: values.single["--models"] ?? "",
                    configPath: values.single["--config"] ?? "",
                    runID: values.single["--run-id"] ?? "",
                    outputRoot: values.single["--output-root"] ?? "",
                    tempRoot: values.single["--temp-root"] ?? "",
                    startIndex: try parseIntValue(values.single["--start-index"], option: "--start-index", defaultValue: 1) ?? 1,
                    maxModels: try parseNonNegativeIntValue(values.single["--max-models"], option: "--max-models", defaultValue: 0),
                    judgeRemoteServerID: values.single["--judge-remote-server-id"] ?? "",
                    judgeModelID: values.single["--judge-model"] ?? "",
                    benchSuite: values.single["--bench-suite"] ?? "",
                    benchContextLength: try parseUInt32Value(values.single["--bench-context-length"], option: "--bench-context-length") ?? 0,
                    benchGenerationLength: try parseUInt32Value(values.single["--bench-generation-length"], option: "--bench-generation-length") ?? 0,
                    benchBatchSize: try parseUInt32Value(values.single["--bench-batch-size"], option: "--bench-batch-size") ?? 0,
                    benchRepeats: try parseBenchmarkRepeatValue(values.single["--bench-repeats"], option: "--bench-repeats") ?? 0,
                    benchSampleSize: try parseUInt32Value(values.single["--bench-sample-size"], option: "--bench-sample-size") ?? 0,
                    benchBatchFactor: try parseUInt32Value(values.single["--bench-batch-factor"], option: "--bench-batch-factor") ?? 0,
                    evalSuite: values.single["--eval-suite"] ?? "",
                    evalDatasetID: values.single["--eval-dataset-id"] ?? "",
                    evalScoringMode: values.single["--eval-scoring-mode"] ?? "",
                    evalSampleSize: try parseUInt32Value(values.single["--eval-sample-size"], option: "--eval-sample-size") ?? 0,
                    evalBatchFactor: try parseUInt32Value(values.single["--eval-batch-factor"], option: "--eval-batch-factor") ?? 0,
                    continueOnFailure: continueOnFailure,
                    restartStackPerModel: restartStackPerModel,
                    preflight: values.flags.contains("--preflight"),
                    dryRun: values.flags.contains("--dry-run"),
                    json: values.flags.contains("--json"),
                    explicitOptions: explicitOptions
                )
            )
        case "status":
            return .batchStatus(
                BatchStatusOptions(
                    runID: values.single["--run-id"] ?? "",
                    outputRoot: values.single["--output-root"] ?? "",
                    tempRoot: values.single["--temp-root"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "resume":
            let continueOnFailure = try parseRequiredBooleanValue(
                values.single["--continue-on-failure"],
                option: "--continue-on-failure",
                defaultValue: true
            )
            let missingOnly = try parseRequiredBooleanValue(
                values.single["--missing-only"],
                option: "--missing-only",
                defaultValue: true
            )
            return .batchResume(
                BatchResumeOptions(
                    runID: values.single["--run-id"] ?? "",
                    outputRoot: values.single["--output-root"] ?? "",
                    tempRoot: values.single["--temp-root"] ?? "",
                    modelListPath: values.single["--models"] ?? "",
                    configPath: values.single["--config"] ?? "",
                    evalOnly: values.flags.contains("--eval-only"),
                    missingOnly: missingOnly,
                    continueOnFailure: continueOnFailure,
                    dryRun: values.flags.contains("--dry-run"),
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseEvalRemoteTargets(
        remoteServerIDs: [String],
        remoteModelIDs: [String]
    ) throws -> [EvalRemoteTargetOptions] {
        guard remoteServerIDs.isEmpty == false else {
            if remoteModelIDs.isEmpty == false {
                throw MelixCLIError.missingRequired("--remote-server-id is required when using --remote-model for melix eval run.")
            }
            return []
        }
        if remoteModelIDs.isEmpty {
            return remoteServerIDs.map { EvalRemoteTargetOptions(remoteServerID: $0) }
        }
        guard remoteModelIDs.count == remoteServerIDs.count else {
            throw MelixCLIError.missingRequired(
                "Pass either no --remote-model values or exactly one --remote-model for each --remote-server-id."
            )
        }
        return zip(remoteServerIDs, remoteModelIDs).map {
            EvalRemoteTargetOptions(remoteServerID: $0.0, remoteModelID: $0.1)
        }
    }

    private static func defaultedEvaluationSuites(
        explicitSuites: [String],
        scoringMode: String
    ) -> [String] {
        guard explicitSuites.isEmpty else {
            return explicitSuites
        }
        if scoringMode == EvaluationPromptStore.eventExtractionScoringMode {
            return [EvaluationPromptStore.eventExtractionTaskKind]
        }
        if EvaluationPromptStore.topicMembershipScoringModes.contains(scoringMode) {
            return [EvaluationPromptStore.topicMembershipTaskKind]
        }
        return []
    }

    private static func isDedicatedEvaluationScoringMode(_ scoringMode: String) -> Bool {
        scoringMode == EvaluationPromptStore.eventExtractionScoringMode
            || EvaluationPromptStore.topicMembershipScoringModes.contains(scoringMode)
    }

    private static func parseEvalPrompt(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        switch action {
        case "list":
            return .evalPromptList(.init(json: values.flags.contains("--json")))
        case "show":
            guard let promptID = values.single["--prompt-id"], promptID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--prompt-id is required for melix eval prompt show.")
            }
            return .evalPromptShow(
                .init(
                    promptID: promptID,
                    revisionID: values.single["--revision-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "create":
            guard let promptID = values.single["--prompt-id"], promptID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--prompt-id is required for melix eval prompt create.")
            }
            guard let title = values.single["--title"], title.isEmpty == false else {
                throw MelixCLIError.missingRequired("--title is required for melix eval prompt create.")
            }
            guard let systemPromptFile = values.single["--system-prompt-file"], systemPromptFile.isEmpty == false else {
                throw MelixCLIError.missingRequired("--system-prompt-file is required for melix eval prompt create.")
            }
            return .evalPromptCreate(
                .init(
                    promptID: promptID,
                    title: title,
                    systemPromptFile: systemPromptFile,
                    json: values.flags.contains("--json")
                )
            )
        case "update":
            guard let promptID = values.single["--prompt-id"], promptID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--prompt-id is required for melix eval prompt update.")
            }
            guard let systemPromptFile = values.single["--system-prompt-file"], systemPromptFile.isEmpty == false else {
                throw MelixCLIError.missingRequired("--system-prompt-file is required for melix eval prompt update.")
            }
            return .evalPromptUpdate(
                .init(
                    promptID: promptID,
                    systemPromptFile: systemPromptFile,
                    json: values.flags.contains("--json")
                )
            )
        case "freeze":
            guard let promptID = values.single["--prompt-id"], promptID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--prompt-id is required for melix eval prompt freeze.")
            }
            return .evalPromptFreeze(
                .init(
                    promptID: promptID,
                    revisionID: values.single["--revision-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "archive":
            guard let promptID = values.single["--prompt-id"], promptID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--prompt-id is required for melix eval prompt archive.")
            }
            return .evalPromptArchive(.init(promptID: promptID, json: values.flags.contains("--json")))
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseRuns(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        var optionArguments = Array(arguments.dropFirst())
        switch action {
        case "list":
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .runsList(
                RunsListOptions(
                    sourcePath: values.single["--from"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "show":
            let runID = try extractRunID(from: &optionArguments, command: "melix runs show")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            return .runsShow(
                RunsShowOptions(
                    runID: runID,
                    sourcePath: values.single["--from"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "export":
            let runID = try extractRunID(from: &optionArguments, command: "melix runs export")
            let values = try ArgumentCursor(arguments: optionArguments).parse()
            guard let format = values.single["--format"], !format.isEmpty else {
                throw MelixCLIError.missingRequired("--format is required for melix runs export.")
            }
            return .runsExport(
                RunsExportOptions(
                    runID: runID,
                    sourcePath: values.single["--from"] ?? "",
                    format: format,
                    outputPath: values.single["--output"] ?? ""
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func extractRunID(
        from arguments: inout [String],
        command: String,
        fieldName: String = "RUN_ID"
    ) throws -> String {
        guard let first = arguments.first, !first.hasPrefix("--") else {
            throw MelixCLIError.missingRequired("\(fieldName) is required for \(command).")
        }
        arguments.removeFirst()
        let runID = first.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !runID.isEmpty else {
            throw MelixCLIError.missingRequired("\(fieldName) is required for \(command).")
        }
        return runID
    }

    private static func parsePipeline(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        guard action == "run" else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        guard let filePath = values.single["--file"], !filePath.isEmpty else {
            throw MelixCLIError.missingRequired("--file is required for melix pipeline run.")
        }
        return .pipelineRun(
            PipelineRunOptions(
                filePath: filePath,
                inputsPath: values.single["--inputs"] ?? "",
                receiptDir: values.single["--receipt-dir"] ?? "",
                traceID: values.single["--trace-id"] ?? "",
                resume: values.flags.contains("--resume"),
                fromStepID: values.single["--from-step"] ?? "",
                dryRun: values.flags.contains("--dry-run")
            )
        )
    }

    private static func parseEvalCompare(_ arguments: [String]) throws -> MelixCLICommand {
        if let action = arguments.first,
           ["export-summary-csv", "export-samples-csv", "export-samples-jsonl"].contains(action)
        {
            let exportCommand = "melix eval compare \(action)"
            let exportArguments = Array(arguments.dropFirst())
            let exportValues = try ArgumentCursor(arguments: exportArguments).parse()
            switch action {
            case "export-summary-csv":
                return .evalCompareExportSummaryCSV(try parseEvalExportOptions(exportValues, command: exportCommand))
            case "export-samples-csv":
                return .evalCompareExportSamplesCSV(try parseEvalExportOptions(exportValues, command: exportCommand))
            case "export-samples-jsonl":
                return .evalCompareExportSamplesJSONL(try parseEvalExportOptions(exportValues, command: exportCommand))
            default:
                break
            }
        }

        let values = try ArgumentCursor(arguments: arguments).parse(
            multiValueOptions: ["--suite", "--target-model-id", "--target-adapter", "--ignored-path"]
        )
        let modelID = values.single["--model-id"] ?? ""
        let hfRepoID = values.single["--repo-id"] ?? ""
        let explicitTargetCount = [modelID, hfRepoID].filter { !$0.isEmpty }.count
        guard explicitTargetCount == 1 else {
            throw MelixCLIError.missingRequired("Exactly one of --model-id or --repo-id is required for melix eval compare.")
        }
        let targetModelIDs = values.multi["--target-model-id"] ?? []
        let targetAdapterManifestPaths = values.multi["--target-adapter"] ?? []
        // Module 2 admits either registered-model targets (via --target-model-id)
        // or adapter-manifest targets (via --target-adapter), or both. At least
        // one must be provided.
        guard !targetModelIDs.isEmpty || !targetAdapterManifestPaths.isEmpty else {
            throw MelixCLIError.missingRequired(
                "At least one --target-model-id or --target-adapter is required for melix eval compare."
            )
        }
        let sourceConfiguration = try parseEvaluationSourceConfiguration(
            values,
            command: "melix eval compare"
        )
        let scoringMode = sourceConfiguration.profile.scoringMode
        let suites = defaultedEvaluationSuites(
            explicitSuites: values.multi["--suite"] ?? [],
            scoringMode: scoringMode
        )
        let semanticJudgeRemoteServerID = values.single["--semantic-judge-remote-server-id"] ?? ""
        let semanticJudgeModelID = values.single["--semantic-judge-model"] ?? ""
        if semanticJudgeRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           semanticJudgeModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        {
            throw MelixCLIError.missingRequired(
                "--semantic-judge-remote-server-id is required when using --semantic-judge-model for melix eval compare."
            )
        }
        try validateEvalPromptOptions(values)
        return .evalCompare(
            EvalCompareOptions(
                modelID: modelID,
                hfRepoID: hfRepoID,
                targetModelIDs: targetModelIDs,
                targetAdapterManifestPaths: targetAdapterManifestPaths,
                suites: suites,
                datasetID: values.single["--dataset-id"] ?? "",
                sampleSize: UInt32(values.single["--sample-size"] ?? "") ?? 0,
                source: sourceConfiguration.source,
                fieldMapping: sourceConfiguration.fieldMapping,
                profile: sourceConfiguration.profile,
                parameters: try parseEvalParameters(values),
                evalPromptID: values.single["--eval-prompt-id"] ?? "",
                evalPromptRevisionID: values.single["--eval-prompt-revision"] ?? "",
                evalPrompt: values.single["--eval-prompt"] ?? "",
                evalPromptFile: values.single["--eval-prompt-file"] ?? "",
                semanticJudgeRemoteServerID: semanticJudgeRemoteServerID,
                semanticJudgeModelID: semanticJudgeModelID,
                json: values.flags.contains("--json"),
                liveProgress: values.flags.contains("--no-live") == false
            )
        )
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

    private static func parseEvalParameters(_ values: ParsedArguments) throws -> [String: String] {
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
        if let remoteExtraBodyJSON = values.single["--remote-extra-body-json"] {
            parameters["remote_provider_extra_body_json"] = remoteExtraBodyJSON
        }
        if let schemaPath = values.single["--schema"], schemaPath.isEmpty == false {
            let file = try evaluationFileMetadata(path: schemaPath, option: "--schema")
            parameters["schema_path"] = file.resolvedPath
            parameters["schema_sha256"] = file.sha256
            parameters["schema_size_bytes"] = String(file.sizeBytes)
        }
        if let hintsPath = values.single["--hints"], hintsPath.isEmpty == false {
            let file = try evaluationFileMetadata(path: hintsPath, option: "--hints")
            guard let hintsText = String(data: file.data, encoding: .utf8) else {
                throw MelixCLIError.usage("--hints must contain UTF-8 text.")
            }
            parameters["hints_path"] = file.resolvedPath
            parameters["hints_sha256"] = file.sha256
            parameters["hints_size_bytes"] = String(file.sizeBytes)
            parameters["hints_format"] = evaluationHintsFormat(path: file.resolvedPath)
            parameters["evaluation_hints_text"] = hintsText.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let datasetRef = values.single["--dataset-ref"], datasetRef.isEmpty == false {
            let parsedRef = try parseDatasetReference(datasetRef)
            parameters["dataset_ref"] = datasetRef
            parameters["hf_dataset_path"] = parsedRef.repoID
            parameters["hf_dataset_revision"] = values.single["--hf-dataset-revision"] ?? parsedRef.revision
        }
        return parameters
    }

    private static func validateEvalPromptOptions(_ values: ParsedArguments) throws {
        let hasInlinePrompt = values.single["--eval-prompt"] != nil
        let hasPromptFile = values.single["--eval-prompt-file"] != nil
        let inlinePrompt = values.single["--eval-prompt"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let promptFile = values.single["--eval-prompt-file"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let promptID = values.single["--eval-prompt-id"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let promptRevision = values.single["--eval-prompt-revision"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard hasInlinePrompt == false || hasPromptFile == false else {
            throw MelixCLIError.usage("--eval-prompt and --eval-prompt-file are mutually exclusive.")
        }
        if hasInlinePrompt {
            guard inlinePrompt.isEmpty == false else {
                throw MelixCLIError.usage("--eval-prompt must contain non-empty text.")
            }
        }
        if hasPromptFile {
            guard promptFile.isEmpty == false else {
                throw MelixCLIError.usage("--eval-prompt-file must be a non-empty path.")
            }
        }
        if hasInlinePrompt || hasPromptFile {
            guard promptID.isEmpty else {
                throw MelixCLIError.usage("--eval-prompt and --eval-prompt-file cannot be combined with --eval-prompt-id.")
            }
            guard promptRevision.isEmpty else {
                throw MelixCLIError.usage("--eval-prompt-revision requires --eval-prompt-id.")
            }
        }
        if promptRevision.isEmpty == false && promptID.isEmpty {
            throw MelixCLIError.usage("--eval-prompt-revision requires --eval-prompt-id.")
        }
    }

    private static func parseEvaluationSourceConfiguration(
        _ values: ParsedArguments,
        command: String
    ) throws -> (
        source: ControlPlaneEvaluationRequest.Source,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping,
        profile: ControlPlaneEvaluationRequest.Profile
    ) {
        let localCSVPath = values.single["--source-csv"] ?? ""
        let localJSONLPath = values.single["--source-jsonl"] ?? ""
        let hfDatasetPath = values.single["--hf-dataset-path"] ?? ""
        let datasetRef = values.single["--dataset-ref"] ?? ""
        let customSourceCount = [localCSVPath, localJSONLPath, hfDatasetPath, datasetRef].filter { $0.isEmpty == false }.count
        guard customSourceCount <= 1 else {
            throw MelixCLIError.usage(
                "At most one of --source-csv, --source-jsonl, --hf-dataset-path, or --dataset-ref may be provided for \(command)."
            )
        }
        let parsedDatasetRef: (repoID: String, revision: String)?
        if datasetRef.isEmpty {
            parsedDatasetRef = nil
        } else {
            parsedDatasetRef = try parseDatasetReference(datasetRef)
        }

        let fieldMapping = ControlPlaneEvaluationRequest.FieldMapping(
            systemPath: values.single["--field-system-path"] ?? "",
            inputTextPath: values.single["--field-input-text-path"] ?? "",
            targetPath: values.single["--field-target-path"] ?? "",
            sampleIDPath: values.single["--field-sample-id-path"] ?? ""
        )
        let outputSchemaJSON = try parseEvaluationOutputSchemaJSON(values)
        let profile = ControlPlaneEvaluationRequest.Profile(
            profileType: values.single["--profile-type"] ?? "final_result",
            resultKind: values.single["--result-kind"] ?? "text",
            extractionMode: values.single["--extraction-mode"] ?? "heuristic_final",
            scoringMode: values.single["--scoring-mode"] ?? "",
            threshold: try parseDoubleValue(values.single["--threshold"], option: "--threshold", defaultValue: 1.0) ?? 1.0,
            outputSchemaJSON: outputSchemaJSON,
            ignoredPaths: values.multi["--ignored-path"] ?? []
        )

        let source: ControlPlaneEvaluationRequest.Source
        if localCSVPath.isEmpty == false {
            source = .localCSV(path: localCSVPath)
        } else if localJSONLPath.isEmpty == false {
            source = .localJSONL(path: localJSONLPath)
        } else if hfDatasetPath.isEmpty == false {
            source = .huggingFaceDataset(
                datasetPath: hfDatasetPath,
                datasetName: values.single["--hf-dataset-name"] ?? "",
                datasetRevision: values.single["--hf-dataset-revision"] ?? "main",
                split: values.single["--hf-dataset-split"] ?? "train"
            )
        } else if let parsedDatasetRef {
            source = .huggingFaceDataset(
                datasetPath: parsedDatasetRef.repoID,
                datasetName: values.single["--hf-dataset-name"] ?? "",
                datasetRevision: values.single["--hf-dataset-revision"] ?? parsedDatasetRef.revision,
                split: values.single["--hf-dataset-split"] ?? "train"
            )
        } else {
            source = .builtinPackage
        }

        if source.kind != .builtinPackage {
            if values.single["--dataset-root"]?.isEmpty == false {
                throw MelixCLIError.usage("--dataset-root is only supported for builtin evaluation datasets.")
            }
            if isDedicatedEvaluationScoringMode(profile.scoringMode) {
                return (source, fieldMapping, profile)
            }
            guard fieldMapping.inputTextPath.isEmpty == false else {
                throw MelixCLIError.missingRequired("--field-input-text-path is required when using a custom evaluation dataset source.")
            }
            guard fieldMapping.targetPath.isEmpty == false else {
                throw MelixCLIError.missingRequired("--field-target-path is required when using a custom evaluation dataset source.")
            }
        }

        return (source, fieldMapping, profile)
    }

    private static func parseEvaluationOutputSchemaJSON(_ values: ParsedArguments) throws -> String {
        let schemaPath = values.single["--schema"] ?? ""
        let inlineSchemaJSON = values.single["--output-schema-json"] ?? ""
        guard schemaPath.isEmpty || inlineSchemaJSON.isEmpty else {
            throw MelixCLIError.usage("--schema and --output-schema-json are mutually exclusive.")
        }
        guard schemaPath.isEmpty == false else {
            return inlineSchemaJSON
        }
        return try canonicalJSONFileObject(path: schemaPath, option: "--schema")
    }

    private static func canonicalJSONFileObject(path: String, option: String) throws -> String {
        let expandedPath = (path as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: expandedPath)
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw MelixCLIError.usage("Failed to read \(option) at \(path): \(error.localizedDescription)")
        }
        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.usage("\(option) must contain valid JSON: \(error.localizedDescription)")
        }
        guard parsed is [String: Any] else {
            throw MelixCLIError.usage("\(option) must contain a JSON object.")
        }
        let canonicalData = try JSONSerialization.data(withJSONObject: parsed, options: [.sortedKeys])
        return String(decoding: canonicalData, as: UTF8.self)
    }

    private static func canonicalInlineJSONObject(_ value: String?, option: String) throws -> String {
        guard let value, value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            return ""
        }
        guard let data = value.data(using: .utf8) else {
            throw MelixCLIError.usage("\(option) must contain valid UTF-8 JSON.")
        }
        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.usage("\(option) must contain valid JSON: \(error.localizedDescription)")
        }
        guard parsed is [String: Any] else {
            throw MelixCLIError.usage("\(option) must contain a JSON object.")
        }
        let canonicalData = try JSONSerialization.data(withJSONObject: parsed, options: [.sortedKeys])
        return String(decoding: canonicalData, as: UTF8.self)
    }

    private static func canonicalJSONStringArray(_ values: [String]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: values, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }

    private struct EvaluationFileMetadata {
        let resolvedPath: String
        let data: Data
        let sha256: String
        let sizeBytes: Int
    }

    private static func evaluationFileMetadata(path: String, option: String) throws -> EvaluationFileMetadata {
        let expandedPath = (path as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: expandedPath)
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw MelixCLIError.usage("Failed to read \(option) at \(path): \(error.localizedDescription)")
        }
        let resolvedPath = url.resolvingSymlinksInPath().standardizedFileURL.path
        return EvaluationFileMetadata(
            resolvedPath: resolvedPath,
            data: data,
            sha256: sha256Hex(data),
            sizeBytes: data.count
        )
    }

    private static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data)
            .map { String(format: "%02x", $0) }
            .joined()
    }

    private static func evaluationHintsFormat(path: String) -> String {
        switch URL(fileURLWithPath: path).pathExtension.lowercased() {
        case "json":
            return "json"
        case "md":
            return "markdown"
        case "txt":
            return "text"
        case let suffix where suffix.isEmpty == false:
            return suffix
        default:
            return "text"
        }
    }

    private static func parseLoraTrainOptions(
        _ values: ParsedArguments,
        command: String,
        allowAutoTrainingMode: Bool,
        jsonOverride: Bool?
    ) throws -> LoraTrainOptions {
        guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model-id is required for \(command).")
        }
        let datasetURI = values.single["--dataset-uri"] ?? ""
        let hfDatasetPath = values.single["--hf-dataset-path"] ?? ""
        guard !datasetURI.isEmpty || !hfDatasetPath.isEmpty else {
            throw MelixCLIError.missingRequired("Either --dataset-uri or --hf-dataset-path is required for \(command).")
        }
        guard let adapterName = values.single["--adapter-name"], !adapterName.isEmpty else {
            throw MelixCLIError.missingRequired("--adapter-name is required for \(command).")
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
            "--max-steps",
            "--learning-rate",
            "--max-seq-length",
            "--sample-limit",
            "--gradient-accumulation",
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
        let resumeAdapter = (values.single["--resume-adapter"] ?? "").trimmingCharacters(in: .whitespaces)
        let resumeManifest = (values.single["--resume-from-manifest"] ?? "").trimmingCharacters(in: .whitespaces)
        if !resumeAdapter.isEmpty, !resumeManifest.isEmpty {
            throw MelixCLIError.usage("--resume-adapter and --resume-from-manifest are mutually exclusive.")
        }
        if !resumeAdapter.isEmpty {
            parameters["resume_source_path"] = resumeAdapter
        }
        if !resumeManifest.isEmpty {
            parameters["resume_manifest_path"] = resumeManifest
        }
        if let presetID = values.single["--preset"] {
            parameters["preset_id"] = presetID
        }
        if let experimentGroupID = values.single["--experiment-group"] {
            parameters["experiment_group_id"] = experimentGroupID
        }
        let trainingMode = (values.single["--training-mode"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let validTrainingModes = allowAutoTrainingMode ? ["auto", "lora", "qlora", "dora"] : ["lora", "qlora", "dora"]
        if !trainingMode.isEmpty, validTrainingModes.contains(trainingMode) == false {
            if ["dpo", "orpo", "cpo", "grpo", "rlhf"].contains(trainingMode) {
                throw MelixCLIError.usage(
                    "Invalid value for --training-mode. For alignment training modes (dpo, orpo, cpo, grpo, rlhf), use `melix alignment train --algorithm <mode>`."
                )
            }
            let expected = allowAutoTrainingMode ? "auto, lora, qlora, dora" : "lora, qlora, dora"
            throw MelixCLIError.usage("Invalid value for --training-mode. Expected one of: \(expected).")
        }
        for flag in ["--response-only", "--mask-prompt", "--gradient-checkpointing"] where values.flags.contains(flag) {
            parameters[normalizedParameterKey(flag)] = "true"
        }
        return LoraTrainOptions(
            modelID: modelID,
            datasetSourceKind: datasetSourceKind,
            datasetURI: datasetURI,
            adapterName: adapterName,
            targetRepo: values.single["--target-repo"] ?? "",
            trainingMode: trainingMode,
            parameters: parameters,
            preflightFitCheck: values.flags.contains("--preflight-fit-check"),
            allowMemoryRisk: values.flags.contains("--allow-memory-risk"),
            json: jsonOverride ?? values.flags.contains("--json")
        )
    }

    private static func parseLoraRunEvaluationSourceConfiguration(
        _ values: ParsedArguments
    ) throws -> (
        source: ControlPlaneEvaluationRequest.Source,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping,
        profile: ControlPlaneEvaluationRequest.Profile
    ) {
        let localCSVPath = values.single["--source-csv"] ?? ""
        let localJSONLPath = values.single["--source-jsonl"] ?? ""
        guard [localCSVPath, localJSONLPath].filter({ $0.isEmpty == false }).count <= 1 else {
            throw MelixCLIError.usage("At most one of --source-csv or --source-jsonl may be provided for melix lora run.")
        }
        let fieldMapping = ControlPlaneEvaluationRequest.FieldMapping(
            systemPath: values.single["--field-system-path"] ?? "",
            inputTextPath: values.single["--field-input-text-path"] ?? "",
            targetPath: values.single["--field-target-path"] ?? "",
            sampleIDPath: values.single["--field-sample-id-path"] ?? ""
        )
        let outputSchemaJSON = try parseEvaluationOutputSchemaJSON(values)
        let profile = ControlPlaneEvaluationRequest.Profile(
            profileType: values.single["--profile-type"] ?? "final_result",
            resultKind: values.single["--result-kind"] ?? "text",
            extractionMode: values.single["--extraction-mode"] ?? "heuristic_final",
            scoringMode: values.single["--scoring-mode"] ?? "",
            threshold: try parseDoubleValue(values.single["--threshold"], option: "--threshold", defaultValue: 1.0) ?? 1.0,
            outputSchemaJSON: outputSchemaJSON,
            ignoredPaths: values.multi["--ignored-path"] ?? []
        )
        let source: ControlPlaneEvaluationRequest.Source
        if localCSVPath.isEmpty == false {
            source = .localCSV(path: localCSVPath)
        } else if localJSONLPath.isEmpty == false {
            source = .localJSONL(path: localJSONLPath)
        } else {
            source = .builtinPackage
        }
        if source.kind != .builtinPackage {
            if values.single["--dataset-root"]?.isEmpty == false || values.single["--eval-dataset-root"]?.isEmpty == false {
                throw MelixCLIError.usage("--dataset-root is only supported for builtin evaluation datasets.")
            }
            if isDedicatedEvaluationScoringMode(profile.scoringMode) {
                return (source, fieldMapping, profile)
            }
            guard fieldMapping.inputTextPath.isEmpty == false else {
                throw MelixCLIError.missingRequired("--field-input-text-path is required when using a custom evaluation dataset source.")
            }
            guard fieldMapping.targetPath.isEmpty == false else {
                throw MelixCLIError.missingRequired("--field-target-path is required when using a custom evaluation dataset source.")
            }
        }
        return (source, fieldMapping, profile)
    }

    private static func normalizedParameterKey(_ option: String) -> String {
        option
            .replacingOccurrences(of: "--", with: "")
            .replacingOccurrences(of: "-", with: "_")
    }

    private static func parseDatasetReference(_ datasetRef: String) throws -> (repoID: String, revision: String) {
        let trimmed = datasetRef.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let separator = trimmed.lastIndex(of: "@") else {
            guard trimmed.isEmpty == false else {
                throw MelixCLIError.usage("Invalid --dataset-ref: expected format is repo/name[@revision].")
            }
            return (trimmed, "main")
        }
        let repoID = String(trimmed[..<separator]).trimmingCharacters(in: .whitespacesAndNewlines)
        let revision = String(trimmed[trimmed.index(after: separator)...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard repoID.isEmpty == false, repoID.contains("@") == false else {
            throw MelixCLIError.usage("Invalid --dataset-ref: '\(repoID)' is not a valid repo id; expected format is repo/name[@revision].")
        }
        return (repoID, revision.isEmpty ? "main" : revision)
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

    private static func parseBenchmarkRepeatValue(
        _ value: String?,
        option: String,
        defaultValue: UInt32? = nil
    ) throws -> UInt32? {
        guard let parsed = try parseUInt32Value(value, option: option, defaultValue: defaultValue) else {
            return nil
        }
        guard (ControlPlaneBenchRequest.minRepeats...ControlPlaneBenchRequest.maxRepeats).contains(parsed) else {
            throw MelixCLIError.usage("Invalid value for \(option): \(parsed). Expected an integer between \(ControlPlaneBenchRequest.minRepeats) and \(ControlPlaneBenchRequest.maxRepeats).")
        }
        return parsed
    }

    private static func parseDoubleValue(
        _ value: String?,
        option: String,
        defaultValue: Double? = nil
    ) throws -> Double? {
        guard let value else {
            return defaultValue
        }
        guard let parsed = Double(value) else {
            throw MelixCLIError.usage("Invalid value for \(option). Expected a numeric value.")
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

    private static func parseRequiredBooleanValue(
        _ value: String?,
        option: String,
        defaultValue: Bool
    ) throws -> Bool {
        guard let value else {
            return defaultValue
        }
        guard let parsed = parseBooleanValue(value, option: option) else {
            throw MelixCLIError.usage("Invalid value for \(option). Expected true or false.")
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

    private static func parseNonNegativeIntValue(
        _ value: String?,
        option: String,
        defaultValue: Int
    ) throws -> Int {
        guard let parsed = try parseIntValue(value, option: option, defaultValue: defaultValue) else {
            return defaultValue
        }
        guard parsed >= 0 else {
            throw MelixCLIError.usage("Invalid value for \(option). Expected a non-negative integer.")
        }
        return parsed
    }

    private static func trimmedOption(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private static func nonEmpty(_ value: String?) -> String? {
        let trimmed = trimmedOption(value)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func normalizedServingDefaultsAccelerationMode(
        _ value: String?,
        defaultValue: String,
        allowEmpty: Bool = false
    ) throws -> String {
        guard let value else {
            return defaultValue
        }
        let trimmed = trimmedOption(value)
        if trimmed.isEmpty {
            guard allowEmpty else {
                throw MelixCLIError.usage(
                    "Invalid value for --acceleration-mode. Expected baseline or speculative_decode."
                )
            }
            return defaultValue
        }
        switch trimmed.lowercased() {
        case "baseline", "speculative_decode":
            return trimmed.lowercased()
        default:
            throw MelixCLIError.usage(
                "Invalid value for --acceleration-mode. Expected baseline or speculative_decode."
            )
        }
    }

    private static func normalizedServingDefaultsAccelerationProfile(
        _ value: String?,
        defaultValue: String,
        allowEmpty: Bool = false
    ) throws -> String {
        guard let value else {
            return defaultValue
        }
        let trimmed = trimmedOption(value)
        if trimmed.isEmpty {
            guard allowEmpty else {
                throw MelixCLIError.usage(
                    "Invalid value for --acceleration-profile. Expected \(ServingAccelerationProfiles.allowedProfileList)."
                )
            }
            return defaultValue
        }
        if let normalized = ServingAccelerationProfiles.normalizeProfileID(trimmed) {
            return normalized
        }
        throw MelixCLIError.usage(
            "Invalid value for --acceleration-profile. Expected \(ServingAccelerationProfiles.allowedProfileList)."
        )
    }
}

private struct ParsedArguments {
    var single: [String: String] = [:]
    var multi: [String: [String]] = [:]
    var flags: Set<String> = []
}

private struct ArgumentCursor {
    static let defaultValueLessFlags: Set<String> = [
        "--json",
        "--response-only",
        "--mask-prompt",
        "--gradient-checkpointing",
        "--allow-large-matrix",
        "--preflight-fit-check",
        "--allow-memory-risk",
        "--no-live",
        "--resume",
        "--dry-run",
        "--follow",
        "--eval-only",
    ]

    let arguments: [String]

    func parse(
        multiValueOptions: Set<String> = ["--suite"],
        valueLessFlags: Set<String> = Self.defaultValueLessFlags
    ) throws -> ParsedArguments {
        var result = ParsedArguments()
        var index = 0
        while index < arguments.count {
            let token = arguments[index]
            if valueLessFlags.contains(token) {
                result.flags.insert(token)
                index += 1
                continue
            }
            if let equalsIndex = token.firstIndex(of: "="), token.hasPrefix("--") {
                let option = String(token[..<equalsIndex])
                let value = String(token[token.index(after: equalsIndex)...])
                guard valueLessFlags.contains(option) == false else {
                    throw MelixCLIError.usage(MelixCLIParser.usageText)
                }
                if multiValueOptions.contains(option) {
                    result.multi[option, default: []].append(value)
                } else {
                    result.single[option] = value
                }
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

public typealias MelixCLICommandExecutor = @Sendable ([String]) async throws -> String

public struct MelixCLIProcessResult: Equatable, Sendable {
    public let stdout: String
    public let stderr: String
    public let exitCode: Int32

    public init(stdout: String, stderr: String, exitCode: Int32) {
        self.stdout = stdout
        self.stderr = stderr
        self.exitCode = exitCode
    }
}

public enum MelixCLIProcessFailureMessage {
    public static func make(stdout: String, stderr: String, exitCode: Int32) -> String {
        let stderrMessage = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        if !stderrMessage.isEmpty {
            return stderrMessage
        }
        let stdoutMessage = stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        if !stdoutMessage.isEmpty {
            return stdoutMessage
        }
        return "Subprocess exited with status \(exitCode)."
    }
}

public struct MelixCLIProcessExecutor: Sendable {
    public let baseCommand: [String]
    public let environment: [String: String]
    public let workingDirectory: String

    public init(
        baseCommand: [String],
        environment: [String: String] = ProcessInfo.processInfo.environment,
        workingDirectory: String = FileManager.default.currentDirectoryPath
    ) {
        self.baseCommand = baseCommand
        self.environment = environment
        self.workingDirectory = workingDirectory
    }

    public func run(arguments: [String]) async throws -> String {
        let result = try await runDetailed(arguments: arguments)
        guard result.exitCode == 0 else {
            let message = MelixCLIProcessFailureMessage.make(
                stdout: result.stdout,
                stderr: result.stderr,
                exitCode: result.exitCode
            )
            throw MelixCLIError.runtime(message)
        }
        return result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public func runDetailed(arguments: [String]) async throws -> MelixCLIProcessResult {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    continuation.resume(returning: try runDetailedSync(arguments: arguments))
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func runDetailedSync(arguments: [String]) throws -> MelixCLIProcessResult {
        guard let executable = baseCommand.first else {
            throw MelixCLIError.runtime("The melix subprocess command is not configured.")
        }
        let process = Process()
        if executable.contains("/") {
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = Array(baseCommand.dropFirst()) + arguments
        } else {
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [executable] + Array(baseCommand.dropFirst()) + arguments
        }
        process.environment = environment
        process.currentDirectoryURL = URL(fileURLWithPath: workingDirectory)

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        let stdoutData = stdout.fileHandleForReading.readDataToEndOfFile()
        let stderrData = stderr.fileHandleForReading.readDataToEndOfFile()
        let stdoutText = String(data: stdoutData, encoding: .utf8) ?? ""
        let stderrText = String(data: stderrData, encoding: .utf8) ?? ""
        return MelixCLIProcessResult(stdout: stdoutText, stderr: stderrText, exitCode: process.terminationStatus)
    }
}

public actor MelixCLIRunner {
    private static let defaultSpeculativeNumDraftTokens = 4
    private static let memoryFitSafetyThresholdFraction = 0.60
    private static let memoryFitSchemaVersion = "melix.memory_fit_receipt.v1"
    private static let diskFitSafetyMultiplier = 1.10

    private let client: any ControlPlaneXPCClient
    private let operatorSessionStore: any MelixOperatorSessionStoring
    /// Package-visible so the pipeline extension can derive MELIX_HOME-compatible receipt roots.
    let environment: [String: String]
    private let commandExecutor: MelixCLICommandExecutor?
    private let terminalCapabilities: MelixCLITerminalCapabilities
    private let terminalWriter: @Sendable (String) -> Void

    public init(
        client: (any ControlPlaneXPCClient)? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        operatorSessionStore: (any MelixOperatorSessionStoring)? = nil,
        commandExecutor: MelixCLICommandExecutor? = nil,
        serviceBuilder: (@Sendable ([String: String]) -> any ControlPlaneExecuting)? = nil,
        terminalCapabilities: MelixCLITerminalCapabilities? = nil,
        terminalWriter: @escaping @Sendable (String) -> Void = { text in
            FileHandle.standardOutput.write(Data(text.utf8))
        }
    ) {
        self.environment = environment
        self.commandExecutor = commandExecutor
        self.terminalCapabilities = terminalCapabilities ?? MelixCLITerminalCapabilities.detect(environment: environment)
        self.terminalWriter = terminalWriter
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
        if let commandExecutor, let arguments = Self.modelOperationArguments(
            modelID: modelID,
            operation: operation,
            outputDir: outputDir,
            quantProfileID: quantProfileID,
            weightQuant: weightQuant,
            kvQuant: kvQuant,
            ext: ext
        ) {
            let output = try await commandExecutor(arguments)
            return try Self.decodeSubprocessModelOperationResult(
                operation: operation,
                output: output
            )
        }
        return try await client.runModelOperation(
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

    private func runWorkspacePreflight(_ options: WorkspacePreflightOptions) async throws -> String {
        let manifestPath = options.manifestPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard manifestPath.isEmpty == false else {
            throw MelixCLIError.missingRequired("--manifest is required for melix workspace preflight.")
        }
        let arguments = Self.workspacePreflightScriptArguments(options)
        let output: String
        if let commandExecutor {
            output = try await commandExecutor(arguments)
        } else {
            let uvExecutable = environment["MELIX_UV"]?.trimmingCharacters(in: .whitespacesAndNewlines)
            let executor = MelixCLIProcessExecutor(
                baseCommand: [uvExecutable?.isEmpty == false ? uvExecutable! : "uv"],
                environment: ProcessInfo.processInfo.environment.merging(environment) { _, new in new },
                workingDirectory: Self.workspacePreflightWorkingDirectory(environment: environment)
            )
            let result = try await executor.runDetailed(arguments: arguments)
            guard result.exitCode == 0 || result.exitCode == 1 else {
                throw MelixCLIError.runtime(
                    MelixCLIProcessFailureMessage.make(
                        stdout: result.stdout,
                        stderr: result.stderr,
                        exitCode: result.exitCode
                    )
                )
            }
            output = result.stdout
        }
        return options.json ? output.trimmingCharacters(in: .whitespacesAndNewlines) : Self.renderWorkspacePreflightReceipt(output)
    }

    private static func workspacePreflightScriptArguments(_ options: WorkspacePreflightOptions) -> [String] {
        var arguments = [
            "run",
            "--project",
            "services/mlx-worker-python",
            "--extra",
            "mlx",
            "python",
            "scripts/workspace_manifest_preflight.py",
            "--manifest",
            options.manifestPath,
        ]
        appendOption("--output", value: options.outputPath, into: &arguments)
        return arguments
    }

    private static func workspacePreflightWorkingDirectory(environment: [String: String]) -> String {
        let explicit = environment["MELIX_REPO_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return explicit.isEmpty ? FileManager.default.currentDirectoryPath : explicit
    }

    private func runDatasetPrepareIngest(_ options: DatasetPrepareIngestOptions) async throws -> String {
        guard options.workspaceProjectID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            throw MelixCLIError.missingRequired("--workspace-project-id is required for melix dataset prepare ingest.")
        }
        let arguments = Self.datasetPrepareIngestScriptArguments(options)
        let output: String
        if let commandExecutor {
            output = try await commandExecutor(arguments)
        } else {
            let uvExecutable = environment["MELIX_UV"]?.trimmingCharacters(in: .whitespacesAndNewlines)
            let executor = MelixCLIProcessExecutor(
                baseCommand: [uvExecutable?.isEmpty == false ? uvExecutable! : "uv"],
                environment: ProcessInfo.processInfo.environment.merging(environment) { _, new in new },
                workingDirectory: Self.workspacePreflightWorkingDirectory(environment: environment)
            )
            let result = try await executor.runDetailed(arguments: arguments)
            guard result.exitCode == 0 || result.exitCode == 1 else {
                throw MelixCLIError.runtime(
                    MelixCLIProcessFailureMessage.make(
                        stdout: result.stdout,
                        stderr: result.stderr,
                        exitCode: result.exitCode
                    )
                )
            }
            output = result.stdout
        }
        return options.json ? output.trimmingCharacters(in: .whitespacesAndNewlines) : Self.renderDatasetIngestReceipt(output)
    }

    private func runDatasetPrepareVersion(_ options: DatasetPrepareVersionOptions) async throws -> String {
        let output = try await runDatasetPreparationVersionScript(
            Self.datasetPrepareVersionScriptArguments(options)
        )
        return options.json ? output.trimmingCharacters(in: .whitespacesAndNewlines) : Self.renderDatasetVersionReceipt(output)
    }

    private func runDatasetPrepareRetryFailed(_ options: DatasetPrepareRetryFailedOptions) async throws -> String {
        let output = try await runDatasetPreparationVersionScript(
            Self.datasetPrepareRetryFailedScriptArguments(options)
        )
        return options.json ? output.trimmingCharacters(in: .whitespacesAndNewlines) : Self.renderDatasetRetryReceipt(output)
    }

    private func runDatasetPrepareListVersions(_ options: DatasetPrepareListVersionsOptions) async throws -> String {
        let output = try await runDatasetPreparationVersionScript(
            Self.datasetPrepareListVersionsScriptArguments(options)
        )
        return options.json ? output.trimmingCharacters(in: .whitespacesAndNewlines) : Self.renderDatasetVersionList(output)
    }

    private func runDatasetPreparationVersionScript(_ arguments: [String]) async throws -> String {
        if let commandExecutor {
            return try await commandExecutor(arguments)
        }
        let uvExecutable = environment["MELIX_UV"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        let executor = MelixCLIProcessExecutor(
            baseCommand: [uvExecutable?.isEmpty == false ? uvExecutable! : "uv"],
            environment: ProcessInfo.processInfo.environment.merging(environment) { _, new in new },
            workingDirectory: Self.workspacePreflightWorkingDirectory(environment: environment)
        )
        let result = try await executor.runDetailed(arguments: arguments)
        guard result.exitCode == 0 || result.exitCode == 1 else {
            throw MelixCLIError.runtime(
                MelixCLIProcessFailureMessage.make(
                    stdout: result.stdout,
                    stderr: result.stderr,
                    exitCode: result.exitCode
                )
            )
        }
        return result.stdout
    }

    private static func datasetPrepareIngestScriptArguments(_ options: DatasetPrepareIngestOptions) -> [String] {
        var arguments = [
            "run",
            "--project",
            "services/mlx-worker-python",
            "--extra",
            "mlx",
            "python",
            "scripts/dataset_preparation_ingest.py",
            "--workspace-project-id",
            options.workspaceProjectID,
            "--workspace-manifest",
            options.workspaceManifestPath,
            "--input",
            options.inputPath,
            "--output-dir",
            options.outputDir,
            "--dataset-preparation-id",
            options.datasetPreparationID,
        ]
        appendOption("--output", value: options.receiptOutputPath, into: &arguments)
        arguments.append(contentsOf: ["--pii-mask", options.piiMask ? "true" : "false"])
        arguments.append(contentsOf: ["--exact-dedup", options.exactDedup ? "true" : "false"])
        arguments.append(contentsOf: ["--fuzzy-dedup", options.fuzzyDedup ? "true" : "false"])
        arguments.append(contentsOf: ["--segmentation", options.segmentation ? "true" : "false"])
        appendOption("--segmentation-strategy", value: options.segmentationStrategy, into: &arguments)
        return arguments
    }

    private static func datasetPrepareVersionScriptArguments(_ options: DatasetPrepareVersionOptions) -> [String] {
        var arguments = datasetPreparationVersionScriptPrefix(command: "version")
        appendOption("--workspace-manifest", value: options.workspaceManifestPath, into: &arguments)
        appendOption("--ingest-receipt", value: options.ingestReceiptPath, into: &arguments)
        appendOption("--output-root", value: options.outputRoot, into: &arguments)
        appendOption("--dataset-id", value: options.datasetID, into: &arguments)
        appendOption("--version-id", value: options.versionID, into: &arguments)
        appendOption("--created-at", value: options.createdAt, into: &arguments)
        appendOption("--mode", value: options.mode, into: &arguments)
        appendOption("--generator-model", value: options.generatorModel, into: &arguments)
        appendOption("--output-kind", value: options.outputKind, into: &arguments)
        appendOption("--output-format", value: options.outputFormat, into: &arguments)
        appendOption("--validation-ratio", value: options.validationRatio, into: &arguments)
        appendMultiOption("--fail-segment-id", values: options.failSegmentIDs, into: &arguments)
        return arguments
    }

    private static func datasetPrepareRetryFailedScriptArguments(_ options: DatasetPrepareRetryFailedOptions) -> [String] {
        var arguments = datasetPreparationVersionScriptPrefix(command: "retry-failed")
        appendOption("--workspace-manifest", value: options.workspaceManifestPath, into: &arguments)
        appendOption("--dataset-version", value: options.datasetVersionPath, into: &arguments)
        appendOption("--output-root", value: options.outputRoot, into: &arguments)
        appendOption("--version-id", value: options.versionID, into: &arguments)
        appendOption("--created-at", value: options.createdAt, into: &arguments)
        appendOption("--generator-model", value: options.generatorModel, into: &arguments)
        return arguments
    }

    private static func datasetPrepareListVersionsScriptArguments(_ options: DatasetPrepareListVersionsOptions) -> [String] {
        var arguments = datasetPreparationVersionScriptPrefix(command: "list-versions")
        appendOption("--workspace-manifest", value: options.workspaceManifestPath, into: &arguments)
        appendOption("--output-root", value: options.outputRoot, into: &arguments)
        appendOption("--dataset-id", value: options.datasetID, into: &arguments)
        return arguments
    }

    private static func datasetPreparationVersionScriptPrefix(command: String) -> [String] {
        [
            "run",
            "--project",
            "services/mlx-worker-python",
            "--extra",
            "mlx",
            "python",
            "scripts/dataset_preparation_version.py",
            command,
        ]
    }

    private static func renderDatasetIngestReceipt(_ output: String) -> String {
        guard let payload = jsonObject(from: output) else {
            return output.hasSuffix("\n") ? output : output + "\n"
        }
        let status = stringValue("status", from: payload)
        let projectID = stringValue("workspace_project_id", from: payload)
        let metrics = payload["metrics"] as? [String: Any] ?? [:]
        let sourceFiles = metrics["source_file_count"] as? NSNumber
        let segments = metrics["segment_count"] as? NSNumber
        var lines = [
            "Dataset ingest \(status.isEmpty ? "unknown" : status)\(projectID.isEmpty ? "" : " for \(projectID)")",
        ]
        if let sourceFiles, let segments {
            lines.append("Sources: \(sourceFiles.intValue), segments: \(segments.intValue)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private static func renderWorkspacePreflightReceipt(_ output: String) -> String {
        guard let payload = jsonObject(from: output) else {
            return output.hasSuffix("\n") ? output : output + "\n"
        }
        let status = stringValue("status", from: payload)
        let projectID = stringValue("project_id", from: payload)
        let checks = payload["checks"] as? [[String: Any]] ?? []
        let blocking = checks.filter { check in
            let checkStatus = (check["status"] as? String ?? "").lowercased()
            return checkStatus == "error" || checkStatus == "blocked"
        }
        var lines = [
            "Workspace preflight \(status.isEmpty ? "unknown" : status)\(projectID.isEmpty ? "" : " for \(projectID)")",
        ]
        for check in blocking {
            let code = check["code"] as? String ?? "WORKSPACE_PREFLIGHT_CHECK"
            let title = check["title"] as? String ?? code
            let detail = check["detail"] as? String ?? ""
            lines.append("- \(code): \(title)")
            if detail.isEmpty == false {
                lines.append("  \(detail)")
            }
        }
        return lines.joined(separator: "\n") + "\n"
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

    private static func renderDatasetVersionReceipt(_ output: String) -> String {
        guard let payload = jsonObject(from: output) else {
            return output.hasSuffix("\n") ? output : output + "\n"
        }
        let datasetID = stringValue("dataset_id", from: payload)
        let versionID = stringValue("version_id", from: payload)
        let trainCount = intValue("train_count", from: payload)
        let validationCount = intValue("validation_count", from: payload)
        let failedCount = intValue("failed_count", from: payload)
        return "Dataset version \(versionID) for \(datasetID)\nSamples: train \(trainCount), validation \(validationCount), failed \(failedCount)\n"
    }

    private static func renderDatasetRetryReceipt(_ output: String) -> String {
        guard let payload = jsonObject(from: output) else {
            return output.hasSuffix("\n") ? output : output + "\n"
        }
        let baseVersionID = stringValue("base_version_id", from: payload)
        let retryVersionID = stringValue("retry_version_id", from: payload)
        let retrySuccessCount = intValue("retry_success_count", from: payload)
        let retryFailedCount = intValue("retry_failed_count", from: payload)
        let rewrittenCount = intValue("rewritten_successful_sample_count", from: payload)
        return "Dataset retry \(baseVersionID) -> \(retryVersionID)\nRetry success: \(retrySuccessCount), failed: \(retryFailedCount), rewritten successful samples: \(rewrittenCount)\n"
    }

    private static func renderDatasetVersionList(_ output: String) -> String {
        guard let payload = jsonObject(from: output) else {
            return output.hasSuffix("\n") ? output : output + "\n"
        }
        let versions = payload["versions"] as? [[String: Any]] ?? []
        var lines = ["dataset_id\tversion_id\tcreated_at\ttrain_count\tvalidation_count\tfailed_count"]
        for version in versions {
            lines.append([
                stringValue("dataset_id", from: payload),
                stringValue("version_id", from: version),
                stringValue("created_at", from: version),
                String(intValue("train_count", from: version)),
                String(intValue("validation_count", from: version)),
                String(intValue("failed_count", from: version)),
            ].joined(separator: "\t"))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    public func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        try await client.getHubModelCard(repoID: repoID)
    }

    private func makeMemoryFitReceipt(
        repoID: String,
        targetKind: String,
        targetInputs: [String: String] = [:]
    ) async throws -> MemoryFitReceipt {
        let hubCardStart = DispatchTime.now()
        let card = try await getHubModelCard(repoID: repoID)
        let hubCardElapsedMS = elapsedMilliseconds(since: hubCardStart)
        let receiptStart = DispatchTime.now()
        let normalizedRepoID = card.repoID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? repoID.trimmingCharacters(in: .whitespacesAndNewlines)
            : card.repoID.trimmingCharacters(in: .whitespacesAndNewlines)
        let fitStatus = normalizedFitStatus(card.localFitStatus)
        let totalUnifiedMemoryBytes = ProcessInfo.processInfo.physicalMemory
        let safetyThresholdFraction = Self.memoryFitSafetyThresholdFraction
        let safetyThresholdBytes = UInt64(Double(totalUnifiedMemoryBytes) * safetyThresholdFraction)
        let availableDiskBytes = availableDiskCapacityBytes(near: MelixHome(environment: environment).managedModelRootURL)
        let diskFitStatus = memoryFitDiskStatus(
            estimatedDiskUsageBytes: card.estimatedArtifactBytes,
            availableDiskBytes: availableDiskBytes
        )
        let unknownFields = orderedUnique(memoryFitUnknownFields(card) + memoryFitRunUnknownFields(for: targetKind))
        let assumptions = memoryFitAssumptions(targetKind: targetKind)
        let receiptElapsedMS = elapsedMilliseconds(since: receiptStart)
        let probe: [String: Any] = [
            "name": "cli.memory_fit.\(targetKind)",
            "hub_card_elapsed_ms": NSNumber(value: hubCardElapsedMS),
            "receipt_elapsed_ms": NSNumber(value: receiptElapsedMS),
        ]
        let safetyThreshold: [String: Any] = [
            "safety_threshold_fraction": NSNumber(value: safetyThresholdFraction),
            "safety_threshold_bytes": NSNumber(value: safetyThresholdBytes),
        ]
        let payload: [String: Any] = [
            "schema_version": Self.memoryFitSchemaVersion,
            "target_kind": targetKind,
            "repo_id": normalizedRepoID,
            "pipeline_tag": card.pipelineTag,
            "mlx_compatible": card.mlxCompatible,
            "fit_status": fitStatus,
            "reasons": card.localFitReasons,
            "recommended_action": card.recommendedAction,
            "total_unified_memory_bytes": NSNumber(value: totalUnifiedMemoryBytes),
            "estimated_active_memory_bytes": NSNumber(value: card.estimatedResidentBytes),
            "estimated_disk_usage_bytes": NSNumber(value: card.estimatedArtifactBytes),
            "available_disk_bytes": NSNumber(value: availableDiskBytes),
            "disk_fit_status": diskFitStatus,
            "safety_threshold": safetyThreshold,
            "assumptions": assumptions,
            "unknown_fields": unknownFields,
            "target_inputs": targetInputs,
            "parameter_count": NSNumber(value: card.parameterCount),
            "quantization_summary": card.quantizationSummary,
            "probe": probe,
        ]
        return MemoryFitReceipt(
            payload: payload,
            targetKind: targetKind,
            repoID: normalizedRepoID,
            fitStatus: fitStatus,
            reasons: card.localFitReasons,
            recommendedAction: card.recommendedAction,
            totalUnifiedMemoryBytes: totalUnifiedMemoryBytes,
            estimatedActiveMemoryBytes: card.estimatedResidentBytes,
            estimatedDiskUsageBytes: card.estimatedArtifactBytes,
            availableDiskBytes: availableDiskBytes,
            diskFitStatus: diskFitStatus,
            safetyThresholdFraction: safetyThresholdFraction,
            unknownFields: unknownFields,
            assumptions: assumptions
        )
    }

    private func availableDiskCapacityBytes(near url: URL) -> UInt64 {
        let fileManager = FileManager.default
        var probeURL = url
        while fileManager.fileExists(atPath: probeURL.path) == false {
            let parentURL = probeURL.deletingLastPathComponent()
            if parentURL.path == probeURL.path {
                probeURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                break
            }
            probeURL = parentURL
        }
        if let values = try? probeURL.resourceValues(forKeys: [
            .volumeAvailableCapacityForImportantUsageKey,
            .volumeAvailableCapacityKey,
        ]) {
            if let importantCapacity = values.volumeAvailableCapacityForImportantUsage, importantCapacity > 0 {
                return UInt64(importantCapacity)
            }
            if let volumeCapacity = values.volumeAvailableCapacity, volumeCapacity > 0 {
                return UInt64(volumeCapacity)
            }
        }
        if let attributes = try? fileManager.attributesOfFileSystem(forPath: probeURL.path),
           let systemFreeSize = attributes[.systemFreeSize] as? NSNumber,
           systemFreeSize.int64Value > 0
        {
            return UInt64(systemFreeSize.int64Value)
        }
        return 0
    }

    private func memoryFitDiskStatus(estimatedDiskUsageBytes: UInt64, availableDiskBytes: UInt64) -> String {
        guard estimatedDiskUsageBytes > 0, availableDiskBytes > 0 else {
            return "unknown"
        }
        return Double(availableDiskBytes) >= Double(estimatedDiskUsageBytes) * Self.diskFitSafetyMultiplier
            ? "good"
            : "blocked"
    }

    private func memoryFitAssumptions(targetKind: String) -> [String] {
        var assumptions = [
            "ProcessInfo.physicalMemory is treated as Apple Silicon total unified memory.",
            "estimated_active_memory_bytes reuses Hub estimated_resident_bytes.",
            "estimated_disk_usage_bytes reuses Hub estimated_artifact_bytes.",
            "fit_status and recommended_action reuse the model-ops Hub local-fit policy.",
        ]
        switch targetKind {
        case "benchmark":
            assumptions.append("Benchmark KV-cache and activation overhead are not separately modeled yet.")
        case "eval":
            assumptions.append("Evaluation context, KV-cache, dataset-cache, and judge overhead are not separately modeled yet.")
        case "train":
            assumptions.append("Training optimizer state, LoRA adapter memory, activations, and dataset-cache overhead are not separately modeled yet.")
        default:
            break
        }
        return assumptions
    }

    private func memoryFitUnknownFields(_ card: Melix_Controlplane_V1_HubModelCard) -> [String] {
        var fields: [String] = []
        if card.estimatedResidentBytes == 0 {
            fields.append("estimated_active_memory_bytes")
        }
        if card.estimatedArtifactBytes == 0 {
            fields.append("estimated_disk_usage_bytes")
        }
        if normalizedFitStatus(card.localFitStatus) == "unknown" {
            fields.append("fit_status")
        }
        if card.parameterCount == 0 {
            fields.append("parameter_count")
        }
        if card.quantizationSummary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            fields.append("quantization_summary")
        }
        return fields
    }

    private func memoryFitRunUnknownFields(for targetKind: String) -> [String] {
        switch targetKind {
        case "benchmark":
            return ["kv_cache_bytes", "activation_bytes"]
        case "eval":
            return ["kv_cache_bytes", "activation_bytes", "dataset_cache_bytes", "judge_memory_bytes"]
        case "train":
            return ["optimizer_state_bytes", "lora_adapter_bytes", "activation_bytes", "dataset_cache_bytes"]
        default:
            return []
        }
    }

    private func orderedUnique(_ values: [String]) -> [String] {
        var seen: Set<String> = []
        var result: [String] = []
        for value in values where seen.insert(value).inserted {
            result.append(value)
        }
        return result
    }

    private func normalizedFitStatus(_ status: String) -> String {
        let trimmed = status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return trimmed.isEmpty ? "unknown" : trimmed
    }

    private func enforceMemoryFitPreflight(
        _ receipt: MemoryFitReceipt,
        allowMemoryRisk: Bool,
        commandName: String
    ) throws {
        guard ["blocked", "heavy"].contains(receipt.fitStatus), !allowMemoryRisk else {
            return
        }
        let reasons = receipt.reasons.isEmpty ? "No reason was provided." : receipt.reasons.joined(separator: " ")
        throw MelixCLIError.runtime(
            "Memory fit preflight blocked \(commandName) for \(receipt.repoID): fit_status=\(receipt.fitStatus), estimated_active_memory_bytes=\(formatBinaryBytes(receipt.estimatedActiveMemoryBytes)), estimated_disk_usage_bytes=\(formatBinaryBytes(receipt.estimatedDiskUsageBytes)). Pass --allow-memory-risk to run anyway. Reasons: \(reasons)"
        )
    }

    public func downloadHubModel(
        repoID: String,
        revision: String = "main",
        hfToken: String = ""
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        let tokenStore = HuggingFaceTokenStore(melixHome: MelixHome(environment: environment))
        let providedToken = hfToken.trimmingCharacters(in: .whitespacesAndNewlines)
        let effectiveToken: String
        if providedToken.isEmpty == false {
            _ = try tokenStore.saveToken(providedToken)
            effectiveToken = providedToken
        } else {
            effectiveToken = (try tokenStore.loadToken()?.token ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var ext: [String: String] = [
            "melix.source_kind": "hub_repo",
            "melix.source_locator": repoID,
            "melix.hf_repo_id": repoID,
            "melix.hf_revision": revision.isEmpty ? "main" : revision,
            "melix.managed_import": "true",
        ]
        if effectiveToken.isEmpty == false {
            ext["melix.hf_token"] = effectiveToken
        }
        ext["melix.managed_root"] = MelixHome(environment: environment).managedModelRootURL.path
        return try await performModelOperation(
            modelID: repoID,
            operation: "download",
            outputDir: "",
            ext: ext
        )
    }

    public func datasetRegistrySnapshot() async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await performModelOperation(
            modelID: "melix-datasets",
            operation: "dataset_snapshot",
            outputDir: "",
            ext: [:]
        )
    }

    public func downloadHubDataset(
        repoID: String,
        revision: String = "main",
        hfToken: String = ""
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        let tokenStore = HuggingFaceTokenStore(melixHome: MelixHome(environment: environment))
        let providedToken = hfToken.trimmingCharacters(in: .whitespacesAndNewlines)
        let effectiveToken: String
        if providedToken.isEmpty == false {
            _ = try tokenStore.saveToken(providedToken)
            effectiveToken = providedToken
        } else {
            effectiveToken = (try tokenStore.loadToken()?.token ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var ext: [String: String] = [
            "melix.source_kind": "hf_dataset",
            "melix.source_locator": repoID,
            "melix.hf_dataset_repo_id": repoID,
            "melix.hf_revision": revision.isEmpty ? "main" : revision,
            "melix.managed_import": "true",
        ]
        if effectiveToken.isEmpty == false {
            ext["melix.hf_token"] = effectiveToken
        }
        return try await performModelOperation(
            modelID: repoID,
            operation: "dataset_download",
            outputDir: "",
            ext: ext
        )
    }

    public func removeDataset(
        repoID: String,
        revision: String = "main",
        snapshotID: String = ""
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        var ext: [String: String] = [
            "melix.hf_dataset_repo_id": repoID,
            "melix.hf_revision": revision.isEmpty ? "main" : revision,
        ]
        if snapshotID.isEmpty == false {
            ext["melix.hf_snapshot_id"] = snapshotID
        }
        return try await performModelOperation(
            modelID: repoID,
            operation: "dataset_remove",
            outputDir: "",
            ext: ext
        )
    }

    public func generateSyntheticDataset(
        options: DatasetSyntheticOptions
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await performModelOperation(
            modelID: "melix-datasets",
            operation: "generate_synthetic_dataset",
            outputDir: options.outputDir,
            ext: try syntheticDatasetExt(from: options)
        )
    }

    private func syntheticDatasetExt(from options: DatasetSyntheticOptions) throws -> [String: String] {
        var ext: [String: String] = [
            "synthetic_mode": options.mode,
            "synthetic_dataset_id": options.datasetID,
            "synthetic_dataset_name": options.datasetName,
            "synthetic_num_records": String(options.numRecords),
            "synthetic_output_kind": options.outputKind,
            "synthetic_output_format": options.outputFormat,
            "provider_endpoint": options.providerEndpoint,
            "provider_name": options.providerName,
            "provider_type": options.providerType,
            "model_alias": options.modelAlias,
            "model": options.model,
            "preview_count": String(options.previewCount),
            "resume": options.resume,
            "disable_datadesigner_telemetry": options.enableDataDesignerTelemetry ? "false" : "true",
        ]
        if options.apiKey.isEmpty == false {
            ext["api_key"] = options.apiKey
        }
        if options.headers.isEmpty == false {
            ext["headers_json"] = try Self.canonicalJSONStringArray(options.headers)
        }
        if options.temperature.isEmpty == false {
            ext["temperature"] = options.temperature
        }
        if options.topP.isEmpty == false {
            ext["top_p"] = options.topP
        }
        if options.maxTokens > 0 {
            ext["max_tokens"] = String(options.maxTokens)
        }
        if options.timeoutSeconds.isEmpty == false {
            ext["timeout_seconds"] = options.timeoutSeconds
        }
        if options.maxParallelRequests > 0 {
            ext["max_parallel_requests"] = String(options.maxParallelRequests)
        }
        if options.extraBodyJSON.isEmpty == false {
            ext["extra_body_json"] = options.extraBodyJSON
        }
        if options.columns.isEmpty == false {
            ext["columns_json"] = try Self.canonicalJSONStringArray(options.columns)
        }
        if options.seedSourceKind.isEmpty == false {
            ext["seed_source_kind"] = options.seedSourceKind
            ext["seed_source_path"] = options.seedSourcePath
        }
        if options.validationRatio.isEmpty == false {
            ext["validation_ratio"] = options.validationRatio
        }
        if let randomSeed = options.randomSeed {
            ext["random_seed"] = String(randomSeed)
        }
        return ext
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

    public func importModel(
        path: String,
        modelID: String,
        modelKind: String = "text",
        revision: String = "main"
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        let canonicalPath = canonicalRootPath(path)
        var ext: [String: String] = [
            "source_path": canonicalPath,
            "melix.source_kind": "local_path",
            "melix.source_locator": canonicalPath,
            "melix.model_kind": modelKind.isEmpty ? "text" : modelKind,
            "melix.revision": revision.isEmpty ? "main" : revision,
        ]
        ext["melix.managed_root"] = MelixHome(environment: environment).managedModelRootURL.path
        return try await performModelOperation(
            modelID: modelID,
            operation: "local_import",
            outputDir: "",
            ext: ext
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
            defaultModelID: configuredSession.defaultModelID,
            servedModelIDs: configuredSession.servedModelIDs,
            rateLimitPerMinute: configuredSession.rateLimitPerMinute,
            timeoutSeconds: configuredSession.timeoutSeconds,
            modelIdleTimeoutSeconds: configuredSession.modelIdleTimeoutSeconds,
            allowedHosts: configuredSession.allowedHosts,
            allowedOrigins: configuredSession.allowedOrigins
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
            numDraftTokens: configuredSession.servingDefaults.numDraftTokens,
            accelerationProfile: configuredSession.servingDefaults.accelerationProfile
        )
    }

    public func runBenchmark(_ options: BenchRunOptions) async throws -> ControlPlaneBenchResult {
        var parameters = options.parameters
        if options.preflightFitCheck {
            guard options.hfRepoID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
                throw MelixCLIError.runtime("--preflight-fit-check is currently supported for melix bench run --repo-id targets.")
            }
            let receipt = try await makeMemoryFitReceipt(repoID: options.hfRepoID, targetKind: "benchmark")
            try enforceMemoryFitPreflight(
                receipt,
                allowMemoryRisk: options.allowMemoryRisk,
                commandName: "benchmark"
            )
            parameters.merge(try receipt.benchmarkParameters(schemaVersion: Self.memoryFitSchemaVersion)) { _, new in new }
        }
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
                parameters: parameters
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

    public func runEvaluationCompare(_ options: EvalCompareOptions) async throws -> [ControlPlaneEvaluationResult] {
        // Module 2 admits either registered-model targets or
        // adapter-manifest targets (or both). Reject only if both are empty.
        guard !options.targetModelIDs.isEmpty || !options.targetAdapterManifestPaths.isEmpty else {
            throw MelixCLIError.missingRequired(
                "At least one --target-model-id or --target-adapter is required for melix eval compare."
            )
        }
        if let commandExecutor {
            let output = try await commandExecutor(Self.evalCompareArguments(options))
            return try Self.decodeSubprocessEvaluationResults(output)
        }
        let baseModelID = options.modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        if baseModelID.isEmpty == false {
            _ = try await client.loadModel(modelID: baseModelID)
        }
        for targetModelID in options.targetModelIDs {
            _ = try await client.loadModel(modelID: targetModelID)
        }
        // Adapter targets are materialized ephemerally by the worker — no
        // client-side load here; the worker's _run_compare_suite handles
        // load + unload via the adapter manifest paths in `parameters`.
        var parameters = options.parameters
        parameters["compare_mode"] = "base_vs_targets"
        if !options.targetModelIDs.isEmpty {
            parameters["compare_target_model_ids"] = options.targetModelIDs.joined(separator: ",")
        }
        if !options.targetAdapterManifestPaths.isEmpty {
            parameters["compare_target_adapter_manifest_paths"] = options.targetAdapterManifestPaths.joined(separator: ",")
        }
        return try await runEvaluations(
            EvalRunOptions(
                modelID: options.modelID,
                hfRepoID: options.hfRepoID,
                suites: options.suites,
                datasetID: options.datasetID,
                sampleSize: options.sampleSize,
                source: options.source,
                fieldMapping: options.fieldMapping,
                profile: options.profile,
                parameters: parameters,
                evalPromptID: options.evalPromptID,
                evalPromptRevisionID: options.evalPromptRevisionID,
                evalPrompt: options.evalPrompt,
                evalPromptFile: options.evalPromptFile,
                semanticJudgeRemoteServerID: options.semanticJudgeRemoteServerID,
                semanticJudgeModelID: options.semanticJudgeModelID,
                json: options.json,
                liveProgress: options.liveProgress
            )
        )
    }

    private func runLoraTrainOperation(
        _ options: LoraTrainOptions,
        outputDir: String = "",
        trainingModeOverride: String = ""
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        var ext = options.parameters
        if options.preflightFitCheck {
            guard options.modelID.trimmingCharacters(in: .whitespacesAndNewlines).contains("/") else {
                throw MelixCLIError.runtime("--preflight-fit-check is currently supported for melix lora train --model-id Hugging Face repo targets.")
            }
            let receipt = try await makeMemoryFitReceipt(repoID: options.modelID, targetKind: "train")
            try enforceMemoryFitPreflight(
                receipt,
                allowMemoryRisk: options.allowMemoryRisk,
                commandName: "training"
            )
            ext.merge(try receipt.runParameters(schemaVersion: Self.memoryFitSchemaVersion)) { _, new in new }
        }
        ext["adapter_name"] = options.adapterName
        ext["dataset_source_kind"] = options.datasetSourceKind
        if !options.datasetURI.isEmpty {
            ext["dataset_uri"] = options.datasetURI
        }
        if !options.targetRepo.isEmpty {
            ext["target_repo"] = options.targetRepo
        }
        let trainingMode = trainingModeOverride.isEmpty ? options.trainingMode : trainingModeOverride
        if !trainingMode.isEmpty {
            ext["training_mode"] = trainingMode
        }
        let queue = localTrainingQueueStore()
        let admitted = try queue.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: options.modelID,
                datasetURI: options.datasetURI,
                adapterName: options.adapterName,
                trainingMode: trainingMode,
                runDirectory: outputDir,
                parameters: ext
            )
        )
        ext["training_queue_job_id"] = admitted.jobID
        ext["training_queue_schema_version"] = LocalTrainingQueueStore.schemaVersion
        ext["training_queue_path"] = MelixHome(environment: environment).localTrainingQueueFileURL.path
        do {
            _ = try queue.markRunning(jobID: admitted.jobID)
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "train_lora",
                outputDir: outputDir,
                ext: ext
            )
            _ = try? queue.markSucceeded(jobID: admitted.jobID)
            return result
        } catch let error as MelixCLIError {
            _ = try? queue.markFailed(
                jobID: admitted.jobID,
                code: queueErrorCode(for: error),
                message: error.errorDescription ?? "\(error)"
            )
            throw error
        } catch {
            _ = try? queue.markFailed(
                jobID: admitted.jobID,
                code: "training_queue_worker_failed",
                message: "\(error)"
            )
            throw error
        }
    }

    private func runLoraActivateOperation(
        _ options: LoraActivateOptions,
        outputDir: String = ""
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        var ext = ["artifact_path": options.adapterPath]
        if !options.derivedModelAlias.isEmpty {
            ext["derived_model_alias"] = options.derivedModelAlias
        }
        if !options.activationMode.isEmpty {
            ext["activation_mode"] = options.activationMode
        }
        return try await performModelOperation(
            modelID: options.modelID,
            operation: "activate_adapter",
            outputDir: outputDir,
            ext: ext
        )
    }

    private func runLoraRun(_ options: LoraRunOptions) async throws -> String {
        let outputRoot = try loraRunOutputRoot(options)
        let trainOutputDir = outputRoot.appendingPathComponent("train", isDirectory: true)
        let activationOutputDir = outputRoot.appendingPathComponent("activate", isDirectory: true)
        let evaluationOutputDir = outputRoot.appendingPathComponent("evaluation", isDirectory: true)
        try FileManager.default.createDirectory(at: evaluationOutputDir, withIntermediateDirectories: true)

        let resolvedTrainingMode = Self.resolvedLoraRunTrainingMode(
            requested: options.training.trainingMode,
            modelID: options.training.modelID,
            parameters: options.training.parameters
        )
        let trainResult = try await runLoraTrainOperation(
            options.training,
            outputDir: trainOutputDir.path,
            trainingModeOverride: resolvedTrainingMode
        )
        let adapterManifestPath = try Self.resolveLoraAdapterManifestPath(
            from: trainResult,
            fallbackOutputDir: trainOutputDir.path
        )
        let alias = options.training.parameters["derived_model_alias"].flatMap { $0.isEmpty ? nil : $0 }
            ?? "\(options.training.adapterName)-runtime"
        let activationResult = try await runLoraActivateOperation(
            LoraActivateOptions(
                modelID: options.training.modelID,
                adapterPath: adapterManifestPath,
                derivedModelAlias: alias,
                activationMode: options.activationMode
            ),
            outputDir: activationOutputDir.path
        )
        let compareOptions = EvalCompareOptions(
            modelID: options.evaluation.modelID,
            hfRepoID: options.evaluation.hfRepoID,
            targetModelIDs: options.evaluation.targetModelIDs,
            targetAdapterManifestPaths: [adapterManifestPath] + options.evaluation.targetAdapterManifestPaths,
            suites: options.evaluation.suites,
            datasetID: options.evaluation.datasetID,
            sampleSize: options.evaluation.sampleSize,
            source: options.evaluation.source,
            fieldMapping: options.evaluation.fieldMapping,
            profile: options.evaluation.profile,
            parameters: options.evaluation.parameters,
            json: true
        )
        let compareResults = try await runEvaluationCompare(compareOptions)
        let compareJobID = compareResults.first?.job.jobID ?? ""
        let summaryPath = evaluationOutputDir.appendingPathComponent("compare-summary.csv").path
        let samplesPath = evaluationOutputDir.appendingPathComponent("compare-samples.jsonl").path
        var exportedSummaryPath = ""
        var exportedSamplesPath = ""
        if compareJobID.isEmpty == false {
            _ = try await exportEvaluationArtifact(
                options: EvalExportOptions(jobID: compareJobID, outputPath: summaryPath, json: false),
                missingRowsMessage: "No evaluation compare summary rows were found for job \(compareJobID).",
                rowCount: { bundle in bundle.evaluationCompareSummaryRows(jobID: compareJobID).count },
                contents: { bundle in bundle.evaluationCompareSummaryCSV(jobID: compareJobID) }
            )
            exportedSummaryPath = summaryPath
            _ = try await exportEvaluationArtifact(
                options: EvalExportOptions(jobID: compareJobID, outputPath: samplesPath, json: false),
                missingRowsMessage: "No evaluation compare sample rows were found for job \(compareJobID).",
                rowCount: { bundle in bundle.evaluationCompareSampleRows(jobID: compareJobID).count },
                contents: { bundle in try bundle.evaluationCompareSamplesJSONL(jobID: compareJobID) }
            )
            exportedSamplesPath = samplesPath
        }

        let activationPayload = Self.jsonObject(from: activationResult.manifestJson) ?? [:]
        let receipt: [String: Any] = [
            "schema_version": "melix.lora_run_receipt.v1",
            "status": "completed",
            "model_id": options.training.modelID,
            "adapter_name": options.training.adapterName,
            "training_mode": resolvedTrainingMode,
            "activation_mode": options.activationMode,
            "output_dir": outputRoot.path,
            "adapter_manifest_path": adapterManifestPath,
            "activation_manifest_path": Self.resolveLoraActivationManifestPath(
                from: activationResult,
                fallbackOutputDir: activationOutputDir.path
            ),
            "derived_model_id": Self.stringValue("derived_model_id", from: activationPayload),
            "train": Self.modelOperationPayload(trainResult),
            "activation": Self.modelOperationPayload(activationResult),
            "evaluation": [
                "job_ids": compareResults.map(\.job.jobID),
                "summary_csv_path": exportedSummaryPath,
                "samples_jsonl_path": exportedSamplesPath,
                "results": compareResults.map(makeEvaluationPayload),
            ],
        ]
        if options.json {
            return try prettyJSON(receipt)
        }
        var lines = [
            "LoRA run completed.",
            "output_dir: \(outputRoot.path)",
            "training_mode: \(resolvedTrainingMode)",
            "adapter_manifest: \(adapterManifestPath)",
            "activation_manifest: \(receipt["activation_manifest_path"] as? String ?? "")",
        ]
        if compareJobID.isEmpty == false {
            lines.append("evaluation_job: \(compareJobID)")
            lines.append("summary_csv: \(exportedSummaryPath)")
            lines.append("samples_jsonl: \(exportedSamplesPath)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func runBenchmarkWithLiveDisplay(_ options: BenchRunOptions) async throws -> ControlPlaneBenchResult {
        guard shouldUseLiveDisplay(json: options.json, enabled: options.liveProgress) else {
            return try await runBenchmark(options)
        }
        let startedAt = Date()
        let display = makeLiveRunDisplay()
        var state = MelixCLILiveRunState(
            title: "Benchmark",
            targetText: runTargetText(modelID: options.modelID, hfRepoID: options.hfRepoID),
            suiteText: options.suites.isEmpty ? "default" : options.suites.joined(separator: ", "),
            steps: [
                .init(id: "validate", title: "Validate Target"),
                .init(id: "prepare", title: "Prepare Benchmark"),
                .init(id: "run", title: "Run Suites"),
                .init(id: "report", title: "Write Report"),
            ],
            detailText: benchmarkLiveDetail(options)
        )
        state.move(to: "validate", detailText: "Checking benchmark target and options", elapsedSeconds: elapsedSeconds(since: startedAt))
        display.render(state)
        do {
            state.move(to: "prepare", detailText: benchmarkLiveDetail(options), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.move(to: "run", detailText: "Benchmark suites are running", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            let result = try await withLiveRunTicker(state: state, display: display, startedAt: startedAt) {
                try await runBenchmark(options)
            }
            state.move(to: "report", detailText: "Collecting report and metrics", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.finish(
                primaryMetricText: Self.livePrimaryMetricText(result.metrics),
                artifactText: result.reportPath,
                detailText: result.job.map { "job \($0.jobID)" } ?? "benchmark completed",
                elapsedSeconds: elapsedSeconds(since: startedAt)
            )
            display.render(state, final: true)
            return result
        } catch {
            state.fail(detailText: String(describing: error), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state, final: true)
            throw error
        }
    }

    private func runBenchmarkMatrixWithLiveDisplay(_ options: BenchMatrixRunOptions) async throws -> ControlPlaneBenchMatrixResult {
        guard shouldUseLiveDisplay(json: options.json, enabled: options.liveProgress) else {
            return try await runBenchmarkMatrix(options)
        }
        let startedAt = Date()
        let display = makeLiveRunDisplay()
        var state = MelixCLILiveRunState(
            title: "Benchmark Matrix",
            targetText: runTargetText(modelID: options.modelID, hfRepoID: options.hfRepoID),
            suiteText: options.suites.joined(separator: ", "),
            steps: [
                .init(id: "validate", title: "Validate Matrix"),
                .init(id: "expand", title: "Expand Cells"),
                .init(id: "run", title: "Run Matrix"),
                .init(id: "summary", title: "Load Summary"),
            ],
            detailText: benchmarkMatrixLiveDetail(options)
        )
        state.move(to: "validate", detailText: "Checking matrix target and load budget", elapsedSeconds: elapsedSeconds(since: startedAt))
        display.render(state)
        do {
            state.move(to: "expand", detailText: benchmarkMatrixLiveDetail(options), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.move(to: "run", detailText: "Matrix cells are running", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            let result = try await withLiveRunTicker(state: state, display: display, startedAt: startedAt) {
                try await runBenchmarkMatrix(options)
            }
            state.move(to: "summary", detailText: "Loading matrix summary rows", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.finish(
                primaryMetricText: Self.livePrimaryMetricText(Self.benchmarkMatrixLiveMetrics(from: result.summaryRows)),
                artifactText: result.job.outputDir,
                detailText: "job \(result.job.jobID) • \(result.summaryRows.count) rows",
                elapsedSeconds: elapsedSeconds(since: startedAt)
            )
            display.render(state, final: true)
            return result
        } catch {
            state.fail(detailText: String(describing: error), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state, final: true)
            throw error
        }
    }

    private func runEvaluationsWithLiveDisplay(_ options: EvalRunOptions) async throws -> [ControlPlaneEvaluationResult] {
        guard shouldUseLiveDisplay(json: options.json, enabled: options.liveProgress) else {
            return try await runEvaluations(options)
        }
        let suites = options.suites.isEmpty ? ["mmlu"] : options.suites
        let startedAt = Date()
        let display = makeLiveRunDisplay()
        var state = MelixCLILiveRunState(
            title: "Evaluation",
            targetText: evaluationTargetText(options),
            suiteText: suites.joined(separator: ", "),
            steps: [
                .init(id: "validate", title: "Validate Target"),
                .init(id: "prepare", title: "Prepare Suites"),
                .init(id: "run", title: "Run Evaluation"),
                .init(id: "score", title: "Collect Scores"),
            ],
            detailText: evaluationLiveDetail(options)
        )
        state.move(to: "validate", detailText: "Checking evaluation target and dataset", elapsedSeconds: elapsedSeconds(since: startedAt))
        display.render(state)
        do {
            state.move(to: "prepare", detailText: evaluationLiveDetail(options), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.move(to: "run", detailText: "Evaluation suites are running", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            let results = try await withLiveRunTicker(state: state, display: display, startedAt: startedAt) {
                try await runEvaluations(options)
            }
            state.move(to: "score", detailText: "Collecting scores and artifacts", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.finish(
                primaryMetricText: Self.livePrimaryMetricText(Self.evaluationLiveMetrics(from: results)),
                artifactText: results.first?.job.outputDir ?? "",
                detailText: evaluationCompletionDetail(results),
                elapsedSeconds: elapsedSeconds(since: startedAt)
            )
            display.render(state, final: true)
            return results
        } catch {
            state.fail(detailText: String(describing: error), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state, final: true)
            throw error
        }
    }

    private func runEvaluationCompareWithLiveDisplay(_ options: EvalCompareOptions) async throws -> [ControlPlaneEvaluationResult] {
        guard shouldUseLiveDisplay(json: options.json, enabled: options.liveProgress) else {
            return try await runEvaluationCompare(options)
        }
        let startedAt = Date()
        let display = makeLiveRunDisplay()
        var state = MelixCLILiveRunState(
            title: "Evaluation Compare",
            targetText: runTargetText(modelID: options.modelID, hfRepoID: options.hfRepoID),
            suiteText: options.suites.isEmpty ? "default" : options.suites.joined(separator: ", "),
            steps: [
                .init(id: "baseline", title: "Load Baseline"),
                .init(id: "candidate", title: "Load Candidate"),
                .init(id: "compare", title: "Compare Metrics"),
                .init(id: "report", title: "Render Report"),
            ],
            detailText: evaluationCompareLiveDetail(options)
        )
        state.move(to: "baseline", detailText: "Checking base model", elapsedSeconds: elapsedSeconds(since: startedAt))
        display.render(state)
        do {
            state.move(to: "candidate", detailText: evaluationCompareLiveDetail(options), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.move(to: "compare", detailText: "Compare evaluation is running", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            let results = try await withLiveRunTicker(state: state, display: display, startedAt: startedAt) {
                try await runEvaluationCompare(options)
            }
            state.move(to: "report", detailText: "Rendering comparison report", elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state)
            state.finish(
                primaryMetricText: Self.livePrimaryMetricText(Self.evaluationLiveMetrics(from: results)),
                artifactText: results.first?.job.outputDir ?? "",
                detailText: evaluationCompletionDetail(results),
                elapsedSeconds: elapsedSeconds(since: startedAt)
            )
            display.render(state, final: true)
            return results
        } catch {
            state.fail(detailText: String(describing: error), elapsedSeconds: elapsedSeconds(since: startedAt))
            display.render(state, final: true)
            throw error
        }
    }

    private func shouldUseLiveDisplay(json: Bool, enabled: Bool) -> Bool {
        enabled && json == false && terminalCapabilities.isInteractive
    }

    private func makeLiveRunDisplay() -> MelixCLILiveRunDisplay {
        MelixCLILiveRunDisplay(capabilities: terminalCapabilities, write: terminalWriter)
    }

    private func withLiveRunTicker<T: Sendable>(
        state: MelixCLILiveRunState,
        display: MelixCLILiveRunDisplay,
        startedAt: Date,
        operation: @Sendable () async throws -> T
    ) async throws -> T {
        guard display.supportsContinuousRefresh else {
            return try await operation()
        }
        let ticker = Task<Void, Never> {
            var tickState = state
            while Task.isCancelled == false {
                do {
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                } catch {
                    return
                }
                guard Task.isCancelled == false else {
                    return
                }
                tickState.elapsedSeconds = Date().timeIntervalSince(startedAt)
                display.render(tickState)
            }
        }
        do {
            let result = try await operation()
            ticker.cancel()
            await ticker.value
            return result
        } catch {
            ticker.cancel()
            await ticker.value
            throw error
        }
    }

    private func elapsedSeconds(since startedAt: Date) -> Double {
        Date().timeIntervalSince(startedAt)
    }

    private func runTargetText(modelID: String, hfRepoID: String) -> String {
        if modelID.isEmpty == false {
            return modelID
        }
        if hfRepoID.isEmpty == false {
            return hfRepoID
        }
        return "n/a"
    }

    private func evaluationTargetText(_ options: EvalRunOptions) -> String {
        if options.modelID.isEmpty == false || options.hfRepoID.isEmpty == false {
            return runTargetText(modelID: options.modelID, hfRepoID: options.hfRepoID)
        }
        if options.remoteTargets.isEmpty == false {
            return options.remoteTargets.map {
                [$0.remoteServerID, $0.remoteModelID].filter { $0.isEmpty == false }.joined(separator: " / ")
            }.joined(separator: ", ")
        }
        if options.remoteServerID.isEmpty == false {
            return [options.remoteServerID, options.remoteModelID].filter { $0.isEmpty == false }.joined(separator: " / ")
        }
        return "n/a"
    }

    private func benchmarkLiveDetail(_ options: BenchRunOptions) -> String {
        let contexts = options.contextLengths.isEmpty ? "default" : options.contextLengths.map(String.init).joined(separator: ",")
        let batches = options.batchSizes.isEmpty ? "default" : options.batchSizes.map(String.init).joined(separator: ",")
        return "ctx \(contexts) • batch \(batches) • \(options.repeats)x repeats"
    }

    private func benchmarkMatrixLiveDetail(_ options: BenchMatrixRunOptions) -> String {
        let budget = options.requests > 0 ? "\(options.requests) requests" : "\(options.durationSeconds)s duration"
        let cells = max(1, options.suites.count)
            * max(1, options.contextLengths.count)
            * max(1, options.generationLengths.count)
            * max(1, options.batchSizes.count)
            * max(1, options.cacheProfiles.count)
            * max(1, options.reasoningModes.count)
            * max(1, options.structuredOutputModes.count)
            * max(1, options.concurrencyLevels.count)
        return "\(cells) cells • \(budget) • \(options.repeats)x repeats"
    }

    private func evaluationLiveDetail(_ options: EvalRunOptions) -> String {
        let samples = options.sampleSize > 0 ? "\(options.sampleSize)" : "default"
        if options.semanticJudgeRemoteServerID.isEmpty == false {
            return "sample \(samples) • semantic judge \(options.semanticJudgeRemoteServerID)"
        }
        return "sample \(samples)"
    }

    private func evaluationCompareLiveDetail(_ options: EvalCompareOptions) -> String {
        let registered = options.targetModelIDs.count
        let adapters = options.targetAdapterManifestPaths.count
        let samples = options.sampleSize > 0 ? "\(options.sampleSize)" : "default"
        return "\(registered) model targets • \(adapters) adapter targets • sample \(samples)"
    }

    private func evaluationCompletionDetail(_ results: [ControlPlaneEvaluationResult]) -> String {
        let rowCount = results.reduce(0) { $0 + $1.results.count }
        let jobText = results.first?.job.jobID ?? "evaluation"
        return "job \(jobText) • \(rowCount) result rows"
    }

    private static func livePrimaryMetricText(_ metrics: [String: Double]) -> String {
        guard metrics.isEmpty == false else {
            return ""
        }
        let preferredKeys = [
            "bench.smoke.ttft_ms",
            "bench.smoke.tokens_per_second",
            "matrix.throughput_tokens_per_second",
            "matrix.decode_tokens_per_second",
            "matrix.ttft_mean_ms",
            "eval.compare.win_rate",
            "event_extraction_weighted_f1",
            "mmlu.accuracy",
        ]
        let key = preferredKeys.first(where: { metrics[$0] != nil }) ?? metrics.keys.sorted().first
        guard let key, let value = metrics[key] else {
            return ""
        }
        return "\(key)=\(liveMetricValueText(value))"
    }

    private static func liveMetricValueText(_ value: Double) -> String {
        let format = abs(value) >= 100 ? "%.1f" : "%.3f"
        return String(format: format, value)
            .replacingOccurrences(of: #"\.?0+$"#, with: "", options: .regularExpression)
    }

    private static func benchmarkMatrixLiveMetrics(
        from rows: [Melix_Controlplane_V1_BenchmarkMatrixSummaryRow]
    ) -> [String: Double] {
        guard rows.isEmpty == false else {
            return [:]
        }
        return [
            "matrix.ttft_mean_ms": average(rows.map(\.ttftMeanMs)),
            "matrix.decode_tokens_per_second": average(rows.map(\.decodeTokensPerSecondMean)),
            "matrix.throughput_tokens_per_second": average(rows.map(\.throughputTokensPerSecond)),
        ]
    }

    private static func evaluationLiveMetrics(from results: [ControlPlaneEvaluationResult]) -> [String: Double] {
        var valuesByName: [String: [Double]] = [:]
        for result in results {
            for summary in result.results {
                for metric in summary.metrics where metric.name.isEmpty == false {
                    valuesByName[metric.name, default: []].append(metric.value)
                }
            }
        }
        return valuesByName.mapValues(average)
    }

    private static func average(_ values: [Double]) -> Double {
        guard values.isEmpty == false else {
            return 0
        }
        return values.reduce(0, +) / Double(values.count)

    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        if commandExecutor == nil, commandRequiresConfiguredRegistryRootPriming(command) {
            try await primeConfiguredRegistryRootsIfNeeded()
        }
        switch command {
        case .settingsShow(let options):
            let store = MelixRuntimeSettingsStore(
                melixHome: MelixHome(environment: environment),
                environment: environment
            )
            let payload = try store.effectiveSettings(overrides: options.overrides)
            return try prettyJSON(payload)
        case .settingsSet(let options):
            let store = MelixRuntimeSettingsStore(
                melixHome: MelixHome(environment: environment),
                environment: environment
            )
            let payload = try store.set(key: options.key, value: options.value)
            return options.json ? try prettyJSON(payload) : "Updated \(options.key).\n"
        case .settingsValidate(let options):
            let store = MelixRuntimeSettingsStore(
                melixHome: MelixHome(environment: environment),
                environment: environment
            )
            let payload = store.validate()
            return options.json ? try prettyJSON(payload) : ((payload["valid"] as? Bool) == true ? "Runtime settings are valid.\n" : "Runtime settings are invalid.\n")
        case .settingsReset(let options):
            let store = MelixRuntimeSettingsStore(
                melixHome: MelixHome(environment: environment),
                environment: environment
            )
            let payload = try store.reset(key: options.key)
            return options.json ? try prettyJSON(payload) : "Reset \(options.key).\n"
        case .info:
            let payload = MelixRuntimeDiscoveryBuilder(environment: environment).infoPayload()
            return try prettyJSON(payload)
        case .capabilities(let options):
            let payload = MelixRuntimeDiscoveryBuilder(environment: environment)
                .capabilitiesPayload(modelQuery: options.modelQuery)
            return try prettyJSON(payload)
        case .instructions:
            let payload = MelixRuntimeDiscoveryBuilder(environment: environment).instructionsPayload()
            return try prettyJSON(payload)
        case .schema:
            let payload = MelixRuntimeDiscoveryBuilder(environment: environment).schemaPayload()
            return try prettyJSON(payload)
        case .configMetadata:
            let payload = MelixRuntimeDiscoveryBuilder(environment: environment).configMetadataPayload()
            return try prettyJSON(payload)
        case .workspacePreflight(let options):
            return try await runWorkspacePreflight(options)
        case .uriInspect(let options):
            return try runURIInspect(options)
        case .uriImport(let options):
            return try await runURIImport(options)
        case .recipesList(let options):
            return try runRecipesList(options)
        case .recipesShow(let options):
            return try runRecipesShow(options)
        case .recipesValidate(let options):
            return try runRecipesValidate(options)
        case .recipesPlan(let options):
            return try runRecipesPlan(options)
        case .recipesApply(let options):
            return try await runRecipesApply(options)
        case .recipesInit(let options):
            return try runRecipesInit(options)
        case .cookbookRecommend(let options):
            return try runCookbookRecommend(options)
        case .pipelineRun(let options):
            return try await runPipeline(options)
        case .batchRun(let options):
            return try await runBatch(options)
        case .batchStatus(let options):
            return try runBatchStatus(options)
        case .batchResume(let options):
            return try await runBatchResume(options)
        case .doctor(let options):
            let report = try await client.runDoctor()
            let systemPayload = makeSystemPayload()
            if options.json {
                return try prettyJSON(makeDoctorPayload(report, systemPayload: systemPayload))
            }
            return report.markdown.isEmpty ? "# Melix Doctor\n" : report.markdown
        case .system(let options):
            let payload = makeSystemPayload()
            if options.json {
                return try prettyJSON(payload)
            }
            return renderSystemPayload(payload)
        case .monitor(let options):
            let records = try runRecordStore().loadRecords(sourcePath: options.sourcePath)
            let payload = diagnosticsStore().monitorPayload(records: records)
            if options.json {
                return try prettyJSON(payload)
            }
            return renderMonitorPayload(payload)
        case .logs(let options):
            let record = try runRecordStore().findRecord(runID: options.jobID, sourcePath: options.sourcePath)
            let snapshot = try diagnosticsStore().logSnapshot(record: record, follow: options.follow)
            if options.json {
                return try prettyJSON(snapshot.payload)
            }
            return snapshot.text.hasSuffix("\n") ? snapshot.text : snapshot.text + "\n"
        case .jobsList(let options):
            let jobs = try jobStatusStore().list(sourcePath: options.sourcePath)
            if options.json {
                return try prettyJSON(jobs)
            }
            return renderJobList(jobs)
        case .jobsShow(let options):
            let payload = try jobStatusStore().show(jobID: options.jobID, sourcePath: options.sourcePath)
            if options.json {
                return try prettyJSON(payload)
            }
            return renderJobStatus(payload)
        case .jobsLogs(let options):
            let snapshot = try jobStatusStore().logSnapshot(
                jobID: options.jobID,
                sourcePath: options.sourcePath,
                follow: options.follow
            )
            if options.json {
                return try prettyJSON(snapshot.payload)
            }
            return snapshot.text.hasSuffix("\n") ? snapshot.text : snapshot.text + "\n"
        case .jobsArtifacts(let options):
            let payload = try jobStatusStore().artifacts(jobID: options.jobID, sourcePath: options.sourcePath)
            if options.json {
                return try prettyJSON(payload)
            }
            return renderJobArtifacts(payload)
        case .jobsCancel(let options):
            let result = try jobStatusStore().cancel(jobID: options.jobID, sourcePath: options.sourcePath)
            if options.json {
                return try prettyJSON(result.payload)
            }
            let requested = (result.payload["cancel_requested"] as? Bool) == true
            let reason = stringField(result.payload, "reason")
            if requested {
                return "Cancel requested for \(options.jobID).\n"
            }
            return reason.isEmpty
                ? "Cancel was not requested for \(options.jobID).\n"
                : "Cancel was not requested for \(options.jobID): \(reason).\n"
        case .debugBundle(let options):
            let record = try runRecordStore().findRecord(runID: options.runID, sourcePath: options.sourcePath)
            let result = try diagnosticsStore().writeDebugBundle(record: record, outputPath: options.outputPath)
            if options.json {
                var payload = result.manifest
                payload["bundle_path"] = MelixDiagnosticsRedaction.redactString(result.bundleRoot.path)
                return try prettyJSON(payload)
            }
            return result.bundleRoot.path + "\n"
        case .estimateImport(let options):
            let receipt = try await makeMemoryFitReceipt(
                repoID: options.repoID,
                targetKind: options.targetKind,
                targetInputs: options.targetInputs
            )
            return options.json ? try prettyJSON(receipt.payload) : renderMemoryFitReceipt(receipt)
        case .convert(let options):
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "convert",
                outputDir: options.outputDir,
                ext: ["target_format": options.targetFormat]
            )
            return options.json ? result.manifestJson : result.outputPath + "\n"
        case .quantize(let options):
            var ext: [String: String] = [:]
            if !options.quantizationMode.isEmpty {
                ext["quantization_mode"] = options.quantizationMode
            }
            if !options.sourceArtifactKind.isEmpty {
                ext["source_artifact_kind"] = options.sourceArtifactKind
            }
            if !options.sourceArtifactPath.isEmpty {
                ext["source_artifact_path"] = options.sourceArtifactPath
            }
            if !options.quantizationBackend.isEmpty {
                ext["quantization_backend"] = options.quantizationBackend
            }
            if !options.mlxLMQBits.isEmpty {
                ext["mlx_lm_q_bits"] = options.mlxLMQBits
            }
            if !options.mlxLMQGroupSize.isEmpty {
                ext["mlx_lm_q_group_size"] = options.mlxLMQGroupSize
            }
            if !options.mlxLMQMode.isEmpty {
                ext["mlx_lm_q_mode"] = options.mlxLMQMode
            }
            if !options.calibrationDatasetURI.isEmpty {
                ext["calibration_dataset_uri"] = options.calibrationDatasetURI
            }
            if !options.qualityDelta.isEmpty {
                ext["quality_delta"] = options.qualityDelta
            }
            if !options.latencyDelta.isEmpty {
                ext["latency_delta"] = options.latencyDelta
            }
            if !options.localInferenceSmokeMode.isEmpty {
                ext["local_inference_smoke_mode"] = options.localInferenceSmokeMode
            }
            if !options.localInferenceSmokePrompt.isEmpty {
                ext["local_inference_smoke_prompt"] = options.localInferenceSmokePrompt
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "quantize",
                outputDir: options.outputDir,
                quantProfileID: options.quantProfileID,
                weightQuant: options.weightQuant,
                kvQuant: options.kvQuant,
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath + "\n"
        case .upload(let options):
            var ext = ["target_repo": options.targetRepo]
            if !options.artifactPath.isEmpty {
                ext["artifact_path"] = options.artifactPath
            }
            if !options.artifactKind.isEmpty {
                ext["artifact_kind"] = options.artifactKind
            }
            if !options.artifactManifestPath.isEmpty {
                ext["artifact_manifest_path"] = options.artifactManifestPath
            }
            if !options.publishBackend.isEmpty {
                ext["publish_backend"] = options.publishBackend
            }
            if !options.localPublishRoot.isEmpty {
                ext["local_publish_root"] = options.localPublishRoot
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "upload",
                outputDir: options.outputDir,
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath + "\n"
        case .modelList(let options):
            let snapshot = try await client.serverSnapshot()
            if options.json {
                return try prettyJSON(makeModelListPayload(snapshot.models))
            }
            return renderModelList(snapshot.models)
        case .modelInspect(let options):
            let snapshot = try? await client.serverSnapshot()
            let snapshotModel = snapshot?.models.first { $0.modelID == options.modelID }
            let info = try await client.modelInfo(modelID: options.modelID)
            if options.json {
                return try prettyJSON(makeModelInfoPayload(
                    info,
                    modelID: options.modelID,
                    snapshotModel: snapshotModel
                ))
            }
            return renderModelInfo(info, modelID: options.modelID, snapshotModel: snapshotModel)
        case .modelLoad(let options):
            let model: Melix_Controlplane_V1_ModelSummary
            do {
                model = try await client.loadModel(
                    modelID: options.modelID,
                    memoryBudgetBytes: options.memoryBudgetBytes
                )
            } catch {
                throw userFacingRequestError(from: error)
            }
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
        case .modelImport(let options):
            let result = try await importModel(
                path: options.path,
                modelID: options.modelID,
                modelKind: options.modelKind,
                revision: options.revision
            )
            let receipt = try makeManagedModelReceipt(from: result)
            return options.json ? try prettyJSON(receipt) : receipt.managedModelPath + "\n"
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
            let result = try await downloadHubModel(repoID: options.repoID, revision: options.revision, hfToken: options.hfToken)
            let receipt = try makeManagedModelReceipt(from: result)
            return options.json ? try prettyJSON(receipt) : receipt.managedModelPath + "\n"
        case .datasetList(let options):
            let result = try await datasetRegistrySnapshot()
            if options.json {
                return try prettyJSON(
                    try filterManifestKeys(
                        fromManifestJson: result.manifestJson,
                        defaults: datasetRegistrySnapshotDefaults()
                    )
                )
            }
            return try renderDatasetRegistrySnapshot(result.manifestJson)
        case .datasetHubDownload(let options):
            let result = try await downloadHubDataset(repoID: options.repoID, revision: options.revision, hfToken: options.hfToken)
            let receipt = try makeManagedDatasetReceipt(from: result)
            return options.json ? try prettyJSON(receipt) : receipt.managedDatasetPath + "\n"
        case .datasetRemove(let options):
            let result = try await removeDataset(
                repoID: options.repoID,
                revision: options.revision,
                snapshotID: options.snapshotID
            )
            return options.json ? result.manifestJson : renderDatasetRemoveResult(result)
        case .datasetPrepareIngest(let options):
            return try await runDatasetPrepareIngest(options)
        case .datasetPrepareVersion(let options):
            return try await runDatasetPrepareVersion(options)
        case .datasetPrepareRetryFailed(let options):
            return try await runDatasetPrepareRetryFailed(options)
        case .datasetPrepareListVersions(let options):
            return try await runDatasetPrepareListVersions(options)
        case .datasetSynthetic(let options):
            let result = try await generateSyntheticDataset(options: options)
            return options.json ? result.manifestJson : renderSyntheticDatasetResult(result)
        case .modelRootsList(let options):
            let state = try loadOperatorState()
            if options.json {
                return try prettyJSON(state.registryRoots)
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
                return try prettyJSON(state.registryRoots)
            }
            return renderRegistryRoots(state.registryRoots)
        case .modelRootsRemove(let options):
            let state = try mutateOperatorState { current in
                let canonical = canonicalRootPath(options.path)
                current.registryRoots.removeAll { $0 == canonical }
            }
            if options.json {
                return try prettyJSON(state.registryRoots)
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
                return try prettyJSON(state.registryRoots)
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
            if options.json {
                return try prettyJSON(
                    try filterManifestKeys(
                        fromManifestJson: result.manifestJson,
                        defaults: modelRegistrySnapshotDefaults()
                    )
                )
            }
            return result.outputPath + "\n"
        case .serverSnapshot(let options):
            let snapshot = try await client.serverSnapshot()
            return try renderServerSnapshot(snapshot, json: options.json)
        case .serverSessionList(let options):
            let state = try loadOperatorState()
            if options.json {
                return try prettyJSON(ServerSessionListResponse(
                    serverSessions: state.serverSessions,
                    selectedServerSessionID: state.selectedServerSessionID
                ))
            }
            return renderServerSessions(state)
        case .serverSessionCreate(let options):
            var createdID = ""
            let state = try mutateOperatorState { current in
                let created = MelixOperatorServerSessionState(
                    id: nextGeneratedServerSessionID(in: current.serverSessions),
                    title: options.title,
                    defaultModelID: options.defaultModelID,
                    servedModelIDs: options.servedModelIDs,
                    host: options.host,
                    port: options.port,
                    allowedHosts: options.allowedHosts,
                    allowedOrigins: options.allowedOrigins,
                    rateLimitPerMinute: options.rateLimitPerMinute,
                    timeoutSeconds: options.timeoutSeconds,
                    modelIdleTimeoutSeconds: options.modelIdleTimeoutSeconds,
                    servingDefaults: try servingDefaults(for: options),
                    lifecycle: .draft
                )
                current.serverSessions.append(created)
                current.selectedServerSessionID = created.id
                createdID = created.id
            }
            if options.json {
                guard let created = state.serverSessions.first(where: { $0.id == createdID }) else {
                    throw MelixCLIError.runtime("Created server session \(createdID) was not found in persisted state.")
                }
                return try prettyJSON(created)
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
                if options.defaultModelID.isEmpty == false {
                    session.defaultModelID = options.defaultModelID
                }
                if options.servedModelIDs.isEmpty == false {
                    session.servedModelIDs = normalizedServedModelIDs(
                        options.servedModelIDs,
                        defaultModelID: session.defaultModelID
                    )
                } else if options.defaultModelID.isEmpty == false {
                    session.servedModelIDs = normalizedServedModelIDs(
                        session.servedModelIDs,
                        defaultModelID: options.defaultModelID
                    )
                }
                if options.host.isEmpty == false {
                    session.host = options.host
                }
                if options.port > 0 {
                    session.port = options.port
                }
                if options.allowedHosts.isEmpty == false {
                    session.allowedHosts = options.allowedHosts
                } else if options.clearAllowedHosts {
                    session.allowedHosts = []
                }
                if options.allowedOrigins.isEmpty == false {
                    session.allowedOrigins = options.allowedOrigins
                } else if options.clearAllowedOrigins {
                    session.allowedOrigins = []
                }
                if options.rateLimitPerMinute > 0 {
                    session.rateLimitPerMinute = options.rateLimitPerMinute
                }
                if options.timeoutSeconds > 0 {
                    session.timeoutSeconds = options.timeoutSeconds
                }
                if options.modelIdleTimeoutSeconds > 0 {
                    session.modelIdleTimeoutSeconds = options.modelIdleTimeoutSeconds
                }
                try applyServingDefaultsUpdate(options, to: &session)
                session.updatedAt = Date()
                current.serverSessions[index] = session
            }
            if options.json {
                guard let updated = state.serverSessions.first(where: { $0.id == options.serverSessionID }) else {
                    throw MelixCLIError.runtime("Server session \(options.serverSessionID) was not found.")
                }
                return try prettyJSON(updated)
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
                return try prettyJSON([
                    "removed_id": options.serverSessionID,
                    "selected_server_session_id": state.selectedServerSessionID,
                ])
            }
            return renderServerSessions(state)
        case .serverSessionSelect(let options):
            let state = try mutateOperatorState { current in
                if current.serverSessions.contains(where: { $0.id == options.serverSessionID }) {
                    current.selectedServerSessionID = options.serverSessionID
                }
            }
            if options.json {
                return try prettyJSON([
                    "selected_server_session_id": state.selectedServerSessionID,
                ])
            }
            return renderServerSessions(state)
        case .serverStart(let options):
            let targetServerSessionID = try upsertServerSessionForStartIfNeeded(options)
            guard let configuredSession = try configuredServerSessionIfAvailable(id: targetServerSessionID) else {
                let snapshot = try await client.startServerSession(serverSessionID: targetServerSessionID)
                return try renderServerSnapshot(snapshot, json: options.json)
            }
            let serverSnapshot = try await client.serverSnapshot()
            for modelID in configuredSession.servedModelIDs {
                guard try await boundServerStartModelIsAvailable(
                    modelID: modelID,
                    serverSnapshot: serverSnapshot
                ) else {
                    try markServerSessionUnavailable(
                        id: configuredSession.id,
                        message: "Unavailable",
                        lastError: "Bound model \(modelID) is missing."
                    )
                    throw MelixCLIError.runtime("Bound model \(modelID) is missing.")
                }
                guard try await boundServerStartModelIsServeable(
                    modelID: modelID,
                    serverSnapshot: serverSnapshot
                ) else {
                    try markServerSessionUnavailable(
                        id: configuredSession.id,
                        message: "Unavailable",
                        lastError: "Bound model \(modelID) is not serveable."
                    )
                    throw MelixCLIError.runtime("Bound model \(modelID) is not serveable.")
                }
            }
            _ = try await client.applyServerSessionGatewayConfig(
                serverSessionID: configuredSession.id,
                host: configuredSession.host,
                port: configuredSession.port,
                defaultModelID: configuredSession.defaultModelID,
                servedModelIDs: configuredSession.servedModelIDs,
                rateLimitPerMinute: configuredSession.rateLimitPerMinute,
                timeoutSeconds: configuredSession.timeoutSeconds,
                modelIdleTimeoutSeconds: configuredSession.modelIdleTimeoutSeconds,
                allowedHosts: configuredSession.allowedHosts,
                allowedOrigins: configuredSession.allowedOrigins
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
                numDraftTokens: configuredSession.servingDefaults.numDraftTokens,
                accelerationProfile: configuredSession.servingDefaults.accelerationProfile
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
        case .remoteServerList(let options):
            let servers = try remoteServerStore().list()
            if options.json {
                return try prettyJSON(servers)
            }
            return renderRemoteServers(servers)
        case .remoteServerAdd(let options):
            let server = try remoteServerStore().save(
                RemoteServerMutation(
                    id: options.remoteServerID,
                    title: options.title,
                    providerPreset: options.providerPreset ?? .custom,
                    providerKind: options.providerKind,
                    baseURL: options.baseURL,
                    defaultModelID: options.defaultModelID,
                    timeoutSeconds: options.timeoutSeconds,
                    rateLimitPerMinute: options.rateLimitPerMinute,
                    apiKey: options.apiKey
                )
            )
            if options.json {
                return try prettyJSON(server)
            }
            return renderRemoteServers([server])
        case .remoteServerUpdate(let options):
            let store = remoteServerStore()
            guard let existing = try store.get(id: options.remoteServerID) else {
                throw MelixCLIError.runtime("Remote server \(options.remoteServerID) was not found.")
            }
            if options.providerPreset == nil,
               options.baseURL.isEmpty == false,
               let fixedBaseURL = existing.providerPreset.fixedBaseURL
            {
                throw MelixCLIError.runtime(
                    "--base-url cannot be used with remote server \(existing.id) because provider \(existing.providerPreset.rawValue) uses \(fixedBaseURL)."
                )
            }
            let server = try store.save(
                RemoteServerMutation(
                    id: existing.id,
                    title: options.title.isEmpty ? existing.title : options.title,
                    providerPreset: options.providerPreset ?? existing.providerPreset,
                    providerKind: options.providerKind.isEmpty ? existing.providerKind : options.providerKind,
                    baseURL: options.baseURL.isEmpty ? existing.baseURL : options.baseURL,
                    defaultModelID: options.defaultModelID.isEmpty ? existing.defaultModelID : options.defaultModelID,
                    timeoutSeconds: options.timeoutSeconds == 0 ? existing.timeoutSeconds : options.timeoutSeconds,
                    rateLimitPerMinute: options.rateLimitPerMinute == 0 ? existing.rateLimitPerMinute : options.rateLimitPerMinute,
                    apiKey: options.apiKey
                )
            )
            if options.json {
                return try prettyJSON(server)
            }
            return renderRemoteServers([server])
        case .remoteServerRemove(let options):
            try remoteServerStore().remove(id: options.remoteServerID)
            if options.json {
                return try prettyJSON(["removed_id": options.remoteServerID])
            }
            return "Removed remote server \(options.remoteServerID).\n"
        case .remoteServerTest(let options):
            let target = try remoteChatTarget(remoteServerID: options.remoteServerID, remoteModelID: options.remoteModelID)
            let execution = try await client.startChat(
                ControlPlaneChatRequest(
                    modelID: "",
                    messages: [.init(role: "user", content: "Reply with OK.")],
                    remoteTarget: target
                )
            )
            let result = try await collectChatResult(from: execution)
            let payload: [String: Any] = [
                "remote_server_id": target.serverID,
                "remote_model_id": target.modelID,
                "ok": true,
                "finish_reason": result.finishReason,
            ]
            if options.json {
                return try prettyJSON(payload)
            }
            return "Remote server \(target.serverID) responded with \(result.finishReason).\n"
        case .chatRun(let options):
            let execution: ControlPlaneChatExecution
            do {
                let remoteTarget = options.remoteServerID.isEmpty
                    ? nil
                    : try remoteChatTarget(
                        remoteServerID: options.remoteServerID,
                        remoteModelID: options.remoteModelID
                    )
                execution = try await client.startChat(
                    ControlPlaneChatRequest(
                        modelID: options.modelID,
                        messages: buildChatMessages(options: options),
                        remoteTarget: remoteTarget
                    )
                )
            } catch {
                throw userFacingRequestError(from: error)
            }
            let result = try await collectChatResult(from: execution)
            let receipt = ChatRunReceipt(
                modelID: execution.modelID,
                serverSessionID: options.serverSessionID,
                assistantText: result.assistantText,
                finishReason: result.finishReason,
                requestID: execution.requestID
            )
            if options.json {
                return try prettyJSON(receipt)
            }
            return receipt.assistantText + "\n"
        case .loraList(let options):
            let modelID = try await resolveModelID(preferred: options.modelID)
            let result = try await performModelOperation(
                modelID: modelID,
                operation: "registry_snapshot",
                outputDir: "",
                ext: [:]
            )
            if options.json {
                return try prettyJSON(
                    try filterManifestKeys(
                        fromManifestJson: result.manifestJson,
                        defaults: loraRegistryDefaults()
                    )
                )
            }
            return renderRegistrySnapshot(result.manifestJson)
        case .loraRun(let options):
            return try await runLoraRun(options)
        case .loraTrain(let options):
            let result = try await runLoraTrainOperation(options)
            return options.json ? result.manifestJson : result.outputPath
        case .alignmentTrain(let options):
            var ext = options.parameters
            ext["adapter_name"] = options.adapterName
            ext["dataset_source_kind"] = options.datasetSourceKind
            ext["training_mode"] = options.algorithm
            ext["alignment_algorithm"] = options.algorithm
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
        case .loraDatasetInspect(let options):
            var ext = options.parameters
            ext["dataset_source_kind"] = options.datasetSourceKind
            ext["inspect_only"] = "true"
            if !options.datasetURI.isEmpty {
                ext["dataset_uri"] = options.datasetURI
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "build_training_dataset",
                outputDir: "",
                ext: ext
            )
            return options.json ? result.manifestJson : renderTrainingDatasetManifest(result.manifestJson)
        case .loraDatasetBuild(let options):
            var ext = options.parameters
            ext["dataset_source_kind"] = options.datasetSourceKind
            if !options.datasetURI.isEmpty {
                ext["dataset_uri"] = options.datasetURI
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "build_training_dataset",
                outputDir: options.outputDir,
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .loraActivate(let options):
            let result = try await runLoraActivateOperation(options)
            return options.json ? result.manifestJson : result.outputPath
        case .loraRemoveDerived(let options):
            var ext: [String: String] = [:]
            if !options.derivedModelID.isEmpty {
                ext["derived_model_id"] = options.derivedModelID
            }
            if !options.manifestPath.isEmpty {
                ext["manifest_path"] = options.manifestPath
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "remove_derived_model",
                outputDir: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .loraPublish(let options):
            let resolvedKind = try resolveLoraPublishExportKind(options: options)
            var ext = [
                "target_repo": options.targetRepo,
                "artifact_path": options.artifactPath,
                "artifact_kind": resolvedKind.rawValue,
            ]
            if !options.artifactManifestPath.isEmpty {
                ext["artifact_manifest_path"] = options.artifactManifestPath
            }
            if !options.publishBackend.isEmpty {
                ext["publish_backend"] = options.publishBackend
            }
            if !options.localPublishRoot.isEmpty {
                ext["local_publish_root"] = options.localPublishRoot
            }
            let result = try await performModelOperation(
                modelID: options.modelID,
                operation: "upload",
                outputDir: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .loraExperimentsList(let options):
            return try await runLoraExperimentsList(options)
        case .loraExperimentsShow(let options):
            return try await runLoraExperimentsShow(options)
        case .loraPublishesList(let options):
            return try await runLoraPublishesList(options)
        case .loraPublishesShow(let options):
            return try await runLoraPublishesShow(options)
        case .loraResume(let options):
            return try await runLoraResume(options)
        case .benchRun(let options):
            let result = try await runBenchmarkWithLiveDisplay(options)
            if options.json {
                var payload: [String: Any] = [
                    "report_path": result.reportPath,
                    "report_markdown": result.reportMarkdown,
                    "metrics": result.metrics,
                ]
                if let job = result.job {
                    payload["job"] = makeBenchmarkJobPayload(job)
                }
                return try prettyJSON(payload)
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
        case .benchReport(let options):
            return try renderRunReport(kind: "benchmark", options: options)
        case .benchMatrixRun(let options):
            let result = try await runBenchmarkMatrixWithLiveDisplay(options)
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
            let results = try await runEvaluationsWithLiveDisplay(options)
            if options.json {
                return try prettyJSON(results.map(makeEvaluationPayload))
            }
            return renderEvaluationRuns(results)
        case .evalPromptList(let options):
            let prompts = try evaluationPromptStore().list()
            if options.json {
                return try prettyJSON(prompts)
            }
            return renderEvaluationPrompts(prompts)
        case .evalPromptShow(let options):
            let snapshot = try evaluationPromptSnapshot(promptID: options.promptID, revisionID: options.revisionID)
            if options.json {
                return try prettyJSON(snapshot)
            }
            return renderEvaluationPromptSnapshot(snapshot)
        case .evalPromptCreate(let options):
            let systemPrompt = try String(contentsOfFile: options.systemPromptFile, encoding: .utf8)
            let prompt = try evaluationPromptStore().create(
                promptID: options.promptID,
                title: options.title,
                systemPrompt: systemPrompt
            )
            if options.json {
                return try prettyJSON(prompt)
            }
            return renderEvaluationPrompts([prompt])
        case .evalPromptUpdate(let options):
            let systemPrompt = try String(contentsOfFile: options.systemPromptFile, encoding: .utf8)
            let prompt = try evaluationPromptStore().update(promptID: options.promptID, systemPrompt: systemPrompt)
            if options.json {
                return try prettyJSON(prompt)
            }
            return renderEvaluationPrompts([prompt])
        case .evalPromptFreeze(let options):
            let prompt = try evaluationPromptStore().freeze(promptID: options.promptID, revisionID: options.revisionID)
            if options.json {
                return try prettyJSON(prompt)
            }
            return renderEvaluationPrompts([prompt])
        case .evalPromptArchive(let options):
            let prompt = try evaluationPromptStore().archive(promptID: options.promptID)
            if options.json {
                return try prettyJSON(prompt)
            }
            return "Archived evaluation prompt \(prompt.id).\n"
        case .evalCompare(let options):
            let results = try await runEvaluationCompareWithLiveDisplay(options)
            if options.json {
                return try prettyJSON(results.map(makeEvaluationPayload))
            }
            if let bundle = try? await fetchBenchmarkExportBundle(),
               let compareText = renderEvaluationCompareRuns(results, bundle: bundle) {
                return compareText
            }
            return renderEvaluationRuns(results)
        case .evalList(let options):
            let bundle = try await fetchBenchmarkExportBundle()
            let entries = bundle.evaluationHistoryEntries()
            if options.json {
                return try prettyJSON(entries)
            }
            return renderEvaluationHistory(entries)
        case .evalCompareExportSummaryCSV(let options):
            return try await exportEvaluationArtifact(
                options: options,
                missingRowsMessage: "No evaluation compare summary rows were found for job \(options.jobID).",
                rowCount: { bundle in bundle.evaluationCompareSummaryRows(jobID: options.jobID).count },
                contents: { bundle in bundle.evaluationCompareSummaryCSV(jobID: options.jobID) }
            )
        case .evalCompareExportSamplesCSV(let options):
            return try await exportEvaluationArtifact(
                options: options,
                missingRowsMessage: "No evaluation compare sample rows were found for job \(options.jobID).",
                rowCount: { bundle in bundle.evaluationCompareSampleRows(jobID: options.jobID).count },
                contents: { bundle in bundle.evaluationCompareSamplesCSV(jobID: options.jobID) }
            )
        case .evalCompareExportSamplesJSONL(let options):
            return try await exportEvaluationArtifact(
                options: options,
                missingRowsMessage: "No evaluation compare sample rows were found for job \(options.jobID).",
                rowCount: { bundle in bundle.evaluationCompareSampleRows(jobID: options.jobID).count },
                contents: { bundle in try bundle.evaluationCompareSamplesJSONL(jobID: options.jobID) }
            )
        case .evalExportSummaryCSV(let options):
            return try await exportEvaluationArtifact(
                options: options,
                missingRowsMessage: "No evaluation rows were found for job \(options.jobID).",
                rowCount: { bundle in bundle.evaluationSummaryCSVRows(jobID: options.jobID).count },
                contents: { bundle in bundle.evaluationSummaryCSV(jobID: options.jobID) }
            )
        case .evalExportSamplesCSV(let options):
            return try await exportEvaluationArtifact(
                options: options,
                missingRowsMessage: "No evaluation rows were found for job \(options.jobID).",
                rowCount: { bundle in bundle.evaluationSampleRows(jobID: options.jobID).count },
                contents: { bundle in bundle.evaluationSamplesCSV(jobID: options.jobID) }
            )
        case .evalExportSamplesJSONL(let options):
            return try await exportEvaluationArtifact(
                options: options,
                missingRowsMessage: "No evaluation rows were found for job \(options.jobID).",
                rowCount: { bundle in bundle.evaluationSampleRows(jobID: options.jobID).count },
                contents: { bundle in try bundle.evaluationSamplesJSONL(jobID: options.jobID) }
            )
        case .evalReport(let options):
            return try renderRunReport(kind: "evaluation", options: options)
        case .runsList(let options):
            let records = try runRecordStore().loadRecords(sourcePath: options.sourcePath)
            if options.json {
                return try runRecordJSONString(records.map { $0.summaryPayload() })
            }
            return renderRunRecordList(records)
        case .runsShow(let options):
            let record = try runRecordStore().findRecord(runID: options.runID, sourcePath: options.sourcePath)
            if options.json {
                return try runRecordJSONString(record.payload)
            }
            return renderRunRecordMarkdown(record)
        case .runsExport(let options):
            let record = try runRecordStore().findRecord(runID: options.runID, sourcePath: options.sourcePath)
            let output: String
            switch options.format.lowercased() {
            case "json":
                output = try runRecordJSONString(record.payload)
            case "md", "markdown":
                output = renderRunRecordMarkdown(record)
            default:
                throw MelixCLIError.usage("Invalid value for --format. Expected json or md.")
            }
            return try writeRunRecordOutput(output, outputPath: options.outputPath)
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

    private static func modelOperationArguments(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) -> [String]? {
        switch operation {
        case "train_lora":
            let trainingMode = ext["training_mode"] ?? ext["alignment_algorithm"] ?? ""
            // Older desktop drafts and direct model-operation calls persisted
            // alignment algorithms under training_mode while still using the
            // train_lora operation; route those through the public alignment
            // command so saved GRPO/RLHF/etc. jobs stay forward-compatible.
            if ["dpo", "orpo", "cpo", "grpo", "rlhf"].contains(trainingMode) {
                var arguments = ["alignment", "train", "--model-id", modelID]
                let datasetSourceKind = ext["dataset_source_kind"] ?? "local_package"
                if datasetSourceKind == "hf_dataset" {
                    appendOption("--hf-dataset-path", value: ext["hf_dataset_path"], into: &arguments)
                } else {
                    appendOption("--dataset-uri", value: ext["dataset_uri"], into: &arguments)
                }
                appendOption("--adapter-name", value: ext["adapter_name"], into: &arguments)
                appendOption("--algorithm", value: trainingMode, into: &arguments)
                appendOption("--target-repo", value: ext["target_repo"], into: &arguments)
                appendOption("--preset", value: ext["preset_id"], into: &arguments)
                appendOption("--experiment-group", value: ext["experiment_group_id"], into: &arguments)
                appendOption("--hf-dataset-name", value: ext["hf_dataset_name"], into: &arguments)
                appendOption("--hf-dataset-revision", value: ext["hf_dataset_revision"], into: &arguments)
                appendOption("--hf-train-split", value: ext["hf_train_split"], into: &arguments)
                appendOption("--hf-valid-split", value: ext["hf_valid_split"], into: &arguments)
                appendOption("--text-feature", value: ext["text_feature"], into: &arguments)
                appendOption("--prompt-feature", value: ext["prompt_feature"], into: &arguments)
                appendOption("--completion-feature", value: ext["completion_feature"], into: &arguments)
                appendOption("--chat-feature", value: ext["chat_feature"], into: &arguments)
                appendOption("--rank", value: ext["rank"], into: &arguments)
                appendOption("--alpha", value: ext["alpha"], into: &arguments)
                appendOption("--dropout", value: ext["dropout"], into: &arguments)
                appendOption("--target-modules", value: ext["target_modules"], into: &arguments)
                appendOption("--num-layers", value: ext["num_layers"], into: &arguments)
                appendOption("--batch-size", value: ext["batch_size"], into: &arguments)
                appendOption("--epochs", value: ext["epochs"], into: &arguments)
                appendOption("--max-steps", value: ext["max_steps"], into: &arguments)
                appendOption("--learning-rate", value: ext["learning_rate"], into: &arguments)
                appendOption("--max-seq-length", value: ext["max_seq_length"], into: &arguments)
                appendOption("--sample-limit", value: ext["sample_limit"], into: &arguments)
                appendOption("--gradient-accumulation", value: ext["gradient_accumulation"], into: &arguments)
                appendOption("--grpo-candidate-count", value: ext["grpo_candidate_count"], into: &arguments)
                appendOption("--candidate-generation-mode", value: ext["candidate_generation_mode"], into: &arguments)
                appendOption("--candidate-scoring-mode", value: ext["candidate_scoring_mode"], into: &arguments)
                appendOption("--candidate-generation-max-tokens", value: ext["candidate_generation_max_tokens"], into: &arguments)
                appendOption("--source-adapter-path", value: ext["source_adapter_path"], into: &arguments)
                appendOption("--reference-model-path", value: ext["reference_model_path"], into: &arguments)
                appendOption("--reward-model-manifest-path", value: ext["reward_model_manifest_path"], into: &arguments)
                appendOption("--kl-penalty", value: ext["kl_penalty"], into: &arguments)
                arguments.append("--json")
                return arguments
            }
            var arguments = ["lora", "train", "--model-id", modelID]
            let datasetSourceKind = ext["dataset_source_kind"] ?? "local_package"
            if datasetSourceKind == "hf_dataset" {
                appendOption("--hf-dataset-path", value: ext["hf_dataset_path"], into: &arguments)
            } else {
                appendOption("--dataset-uri", value: ext["dataset_uri"], into: &arguments)
            }
            appendOption("--adapter-name", value: ext["adapter_name"], into: &arguments)
            appendOption("--target-repo", value: ext["target_repo"], into: &arguments)
            appendOption("--training-mode", value: ext["training_mode"], into: &arguments)
            appendOption("--preset", value: ext["preset_id"], into: &arguments)
            appendOption("--experiment-group", value: ext["experiment_group_id"], into: &arguments)
            appendOption("--hf-dataset-name", value: ext["hf_dataset_name"], into: &arguments)
            appendOption("--hf-dataset-revision", value: ext["hf_dataset_revision"], into: &arguments)
            appendOption("--hf-train-split", value: ext["hf_train_split"], into: &arguments)
            appendOption("--hf-valid-split", value: ext["hf_valid_split"], into: &arguments)
            appendOption("--text-feature", value: ext["text_feature"], into: &arguments)
            appendOption("--prompt-feature", value: ext["prompt_feature"], into: &arguments)
            appendOption("--completion-feature", value: ext["completion_feature"], into: &arguments)
            appendOption("--chat-feature", value: ext["chat_feature"], into: &arguments)
            appendOption("--rank", value: ext["rank"], into: &arguments)
            appendOption("--alpha", value: ext["alpha"], into: &arguments)
            appendOption("--dropout", value: ext["dropout"], into: &arguments)
            appendOption("--target-modules", value: ext["target_modules"], into: &arguments)
            appendOption("--num-layers", value: ext["num_layers"], into: &arguments)
            appendOption("--batch-size", value: ext["batch_size"], into: &arguments)
            appendOption("--epochs", value: ext["epochs"], into: &arguments)
            appendOption("--max-steps", value: ext["max_steps"], into: &arguments)
            appendOption("--learning-rate", value: ext["learning_rate"], into: &arguments)
            appendOption("--max-seq-length", value: ext["max_seq_length"], into: &arguments)
            appendOption("--sample-limit", value: ext["sample_limit"], into: &arguments)
            appendOption("--gradient-accumulation", value: ext["gradient_accumulation"], into: &arguments)
            appendOption("--resume-adapter", value: ext["resume_source_path"], into: &arguments)
            appendOption("--resume-from-manifest", value: ext["resume_manifest_path"], into: &arguments)
            appendOption("--derived-model-alias", value: ext["derived_model_alias"], into: &arguments)
            appendBooleanFlag("--response-only", value: ext["response_only"], into: &arguments)
            appendBooleanFlag("--mask-prompt", value: ext["mask_prompt"], into: &arguments)
            appendBooleanFlag("--gradient-checkpointing", value: ext["gradient_checkpointing"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "build_training_dataset":
            let inspectOnly = (ext["inspect_only"] ?? "").lowercased()
            var arguments = ["lora", "dataset", inspectOnly == "true" ? "inspect" : "build", "--model-id", modelID]
            let datasetSourceKind = ext["dataset_source_kind"] ?? "local_path"
            if datasetSourceKind == "hf_dataset" {
                appendOption("--hf-dataset-path", value: ext["hf_dataset_path"], into: &arguments)
            } else {
                appendOption("--dataset-uri", value: ext["dataset_uri"], into: &arguments)
            }
            if inspectOnly != "true" {
                appendOption("--output-dir", value: outputDir, into: &arguments)
            }
            appendOption("--hf-dataset-name", value: ext["hf_dataset_name"], into: &arguments)
            appendOption("--hf-dataset-revision", value: ext["hf_dataset_revision"], into: &arguments)
            appendOption("--hf-train-split", value: ext["hf_train_split"], into: &arguments)
            appendOption("--hf-valid-split", value: ext["hf_valid_split"], into: &arguments)
            appendOption("--text-feature", value: ext["text_feature"], into: &arguments)
            appendOption("--prompt-feature", value: ext["prompt_feature"], into: &arguments)
            appendOption("--completion-feature", value: ext["completion_feature"], into: &arguments)
            appendOption("--chat-feature", value: ext["chat_feature"], into: &arguments)
            appendOption("--template", value: ext["template"], into: &arguments)
            appendOption("--dataset-id", value: ext["dataset_id"], into: &arguments)
            appendOption("--validation-ratio", value: ext["validation_ratio"], into: &arguments)
            appendOption("--sample-limit", value: ext["sample_limit"], into: &arguments)
            appendOption("--preview-count", value: ext["preview_count"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "activate_adapter":
            var arguments = ["lora", "activate", "--model-id", modelID]
            appendOption("--adapter-path", value: ext["artifact_path"], into: &arguments)
            appendOption("--activation-mode", value: ext["activation_mode"], into: &arguments)
            appendOption("--alias", value: ext["derived_model_alias"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "remove_derived_model":
            var arguments = ["lora", "remove-derived", "--model-id", modelID]
            appendOption("--derived-model-id", value: ext["derived_model_id"], into: &arguments)
            appendOption("--manifest-path", value: ext["manifest_path"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "dataset_snapshot":
            return ["dataset", "list", "--json"]
        case "dataset_download":
            var arguments = ["dataset", "hub", "download", "--repo-id", modelID]
            appendOption("--revision", value: ext["melix.hf_revision"], into: &arguments)
            appendOption("--hf-token", value: ext["melix.hf_token"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "dataset_remove":
            var arguments = ["dataset", "remove", "--repo-id", modelID]
            appendOption("--revision", value: ext["melix.hf_revision"], into: &arguments)
            appendOption("--snapshot-id", value: ext["melix.hf_snapshot_id"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "generate_synthetic_dataset":
            var arguments = [
                "dataset",
                "synthetic",
                ext["synthetic_mode"] ?? "create",
            ]
            appendOption("--dataset-id", value: ext["synthetic_dataset_id"], into: &arguments)
            appendOption("--dataset-name", value: ext["synthetic_dataset_name"], into: &arguments)
            appendOption("--num-records", value: ext["synthetic_num_records"], into: &arguments)
            appendOption("--output-kind", value: ext["synthetic_output_kind"], into: &arguments)
            appendOption("--output-format", value: ext["synthetic_output_format"], into: &arguments)
            appendOption("--output-dir", value: outputDir, into: &arguments)
            appendOption("--provider-endpoint", value: ext["provider_endpoint"], into: &arguments)
            appendOption("--provider-name", value: ext["provider_name"], into: &arguments)
            appendOption("--provider-type", value: ext["provider_type"], into: &arguments)
            appendOption("--api-key", value: ext["api_key"], into: &arguments)
            appendMultiOption("--header", values: Self.syntheticJSONArrayStrings(ext["headers_json"]), into: &arguments)
            appendOption("--model-alias", value: ext["model_alias"], into: &arguments)
            appendOption("--model", value: ext["model"], into: &arguments)
            appendOption("--temperature", value: ext["temperature"], into: &arguments)
            appendOption("--top-p", value: ext["top_p"], into: &arguments)
            appendOption("--max-tokens", value: ext["max_tokens"], into: &arguments)
            appendOption("--timeout-seconds", value: ext["timeout_seconds"], into: &arguments)
            appendOption("--max-parallel-requests", value: ext["max_parallel_requests"], into: &arguments)
            appendOption("--extra-body-json", value: ext["extra_body_json"], into: &arguments)
            appendMultiOption("--column", values: Self.syntheticJSONArrayStrings(ext["columns_json"]), into: &arguments)
            appendOption("--seed-source-kind", value: ext["seed_source_kind"], into: &arguments)
            appendOption("--seed-source-path", value: ext["seed_source_path"], into: &arguments)
            appendOption("--validation-ratio", value: ext["validation_ratio"], into: &arguments)
            appendOption("--preview-count", value: ext["preview_count"], into: &arguments)
            appendOption("--random-seed", value: ext["random_seed"], into: &arguments)
            appendOption("--resume", value: ext["resume"], into: &arguments)
            if ext["disable_datadesigner_telemetry"] == "false" {
                arguments.append("--enable-datadesigner-telemetry")
            }
            arguments.append("--json")
            return arguments
        case "registry_snapshot":
            return ["lora", "list", "--model-id", modelID, "--json"]
        case "download":
            if ext["melix.source_kind"] == "hub_repo" {
                var arguments = ["model", "hub", "download", "--repo-id", modelID]
                appendOption("--revision", value: ext["melix.hf_revision"], into: &arguments)
                appendOption("--hf-token", value: ext["melix.hf_token"], into: &arguments)
                arguments.append("--json")
                return arguments
            }
            var arguments = ["model", "download", "--model-id", modelID]
            if outputDir.isEmpty == false {
                arguments.append(contentsOf: ["--output-dir", outputDir])
            }
            arguments.append("--json")
            return arguments
        case "convert":
            var arguments = ["convert", "--model-id", modelID]
            if outputDir.isEmpty == false {
                arguments.append(contentsOf: ["--output-dir", outputDir])
            }
            appendOption("--target-format", value: ext["target_format"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "quantize":
            var arguments = ["quantize", "--model-id", modelID]
            if outputDir.isEmpty == false {
                arguments.append(contentsOf: ["--output-dir", outputDir])
            }
            appendOption("--quant-profile-id", value: quantProfileID, into: &arguments)
            appendOption("--weight-quant", value: weightQuant, into: &arguments)
            appendOption("--kv-quant", value: kvQuant, into: &arguments)
            appendOption("--quantization-mode", value: ext["quantization_mode"], into: &arguments)
            appendOption("--source-artifact-kind", value: ext["source_artifact_kind"], into: &arguments)
            appendOption("--source-artifact-path", value: ext["source_artifact_path"], into: &arguments)
            appendOption("--quantization-backend", value: ext["quantization_backend"], into: &arguments)
            appendOption("--mlx-lm-q-bits", value: ext["mlx_lm_q_bits"], into: &arguments)
            appendOption("--mlx-lm-q-group-size", value: ext["mlx_lm_q_group_size"], into: &arguments)
            appendOption("--mlx-lm-q-mode", value: ext["mlx_lm_q_mode"], into: &arguments)
            appendOption("--calibration-dataset-uri", value: ext["calibration_dataset_uri"], into: &arguments)
            appendOption("--quality-delta", value: ext["quality_delta"], into: &arguments)
            appendOption("--latency-delta", value: ext["latency_delta"], into: &arguments)
            appendOption("--local-inference-smoke-mode", value: ext["local_inference_smoke_mode"], into: &arguments)
            appendOption("--local-inference-smoke-prompt", value: ext["local_inference_smoke_prompt"], into: &arguments)
            arguments.append("--json")
            return arguments
        case "upload":
            let artifactKind = ext["artifact_kind"] ?? ""
            if let exportKind = LoraPublishExportKind(rawValue: artifactKind) {
                var arguments = ["lora", "publish", "--model-id", modelID]
                appendOption("--target-repo", value: ext["target_repo"], into: &arguments)
                switch exportKind {
                case .adapterExport:
                    appendOption("--adapter-path", value: ext["artifact_path"], into: &arguments)
                case .mergedExport:
                    let artifactPath = ext["artifact_path"] ?? ""
                    let manifestPath = ext["artifact_manifest_path"] ?? ""
                    if manifestPath.isEmpty == false {
                        appendOption("--manifest-path", value: manifestPath, into: &arguments)
                    } else {
                        appendOption("--merged-model-path", value: artifactPath, into: &arguments)
                    }
                }
                appendOption("--publish-backend", value: ext["publish_backend"], into: &arguments)
                appendOption("--local-publish-root", value: ext["local_publish_root"], into: &arguments)
                arguments.append("--json")
                return arguments
            }
            var arguments = ["upload", "--model-id", modelID]
            if outputDir.isEmpty == false {
                arguments.append(contentsOf: ["--output-dir", outputDir])
            }
            appendOption("--target-repo", value: ext["target_repo"], into: &arguments)
            appendOption("--artifact-path", value: ext["artifact_path"], into: &arguments)
            appendOption("--artifact-kind", value: ext["artifact_kind"], into: &arguments)
            appendOption("--artifact-manifest-path", value: ext["artifact_manifest_path"], into: &arguments)
            appendOption("--publish-backend", value: ext["publish_backend"], into: &arguments)
            appendOption("--local-publish-root", value: ext["local_publish_root"], into: &arguments)
            arguments.append("--json")
            return arguments
        default:
            return nil
        }
    }

    private static func evalCompareArguments(_ options: EvalCompareOptions) -> [String] {
        var arguments = ["eval", "compare"]
        if options.modelID.isEmpty == false {
            arguments.append(contentsOf: ["--model-id", options.modelID])
        } else if options.hfRepoID.isEmpty == false {
            arguments.append(contentsOf: ["--repo-id", options.hfRepoID])
        }
        for targetModelID in options.targetModelIDs {
            arguments.append(contentsOf: ["--target-model-id", targetModelID])
        }
        for adapterManifestPath in options.targetAdapterManifestPaths {
            arguments.append(contentsOf: ["--target-adapter", adapterManifestPath])
        }
        for suite in options.suites {
            arguments.append(contentsOf: ["--suite", suite])
        }
        appendOption("--dataset-id", value: options.datasetID, into: &arguments)
        if options.sampleSize > 0 {
            arguments.append(contentsOf: ["--sample-size", String(options.sampleSize)])
        }
        appendEvaluationSourceArguments(
            source: options.source,
            fieldMapping: options.fieldMapping,
            profile: options.profile,
            schemaPath: options.parameters["schema_path"],
            into: &arguments
        )
        appendOption("--batch-factor", value: options.parameters["batch_factor"], into: &arguments)
        appendOption("--dataset-root", value: options.parameters["dataset_root"], into: &arguments)
        appendOption("--seed", value: options.parameters["seed"], into: &arguments)
        appendOption("--few-shot", value: options.parameters["few_shot"], into: &arguments)
        appendOption("--scoring-mode", value: options.parameters["scoring_mode"], into: &arguments)
        appendOption("--code-exec-policy", value: options.parameters["code_exec_policy"], into: &arguments)
        appendOption("--hints", value: options.parameters["hints_path"], into: &arguments)
        appendOption("--eval-prompt-id", value: options.evalPromptID, into: &arguments)
        appendOption("--eval-prompt-revision", value: options.evalPromptRevisionID, into: &arguments)
        appendOption("--eval-prompt", value: options.evalPrompt, into: &arguments)
        appendOption("--eval-prompt-file", value: options.evalPromptFile, into: &arguments)
        appendOption("--semantic-judge-remote-server-id", value: options.semanticJudgeRemoteServerID, into: &arguments)
        appendOption("--semantic-judge-model", value: options.semanticJudgeModelID, into: &arguments)
        arguments.append("--json")
        return arguments
    }

    private static func appendEvaluationSourceArguments(
        source: ControlPlaneEvaluationRequest.Source,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping,
        profile: ControlPlaneEvaluationRequest.Profile,
        schemaPath: String? = nil,
        into arguments: inout [String]
    ) {
        switch source.kind {
        case .builtinPackage:
            break
        case .localCSV:
            appendOption("--source-csv", value: source.path, into: &arguments)
        case .localJSONL:
            appendOption("--source-jsonl", value: source.path, into: &arguments)
        case .huggingFaceDataset:
            appendOption("--hf-dataset-path", value: source.datasetPath, into: &arguments)
            appendOption("--hf-dataset-name", value: source.datasetName, into: &arguments)
            appendOption("--hf-dataset-revision", value: source.datasetRevision, into: &arguments)
            appendOption("--hf-dataset-split", value: source.split, into: &arguments)
        }
        appendOption("--field-system-path", value: fieldMapping.systemPath, into: &arguments)
        appendOption("--field-input-text-path", value: fieldMapping.inputTextPath, into: &arguments)
        appendOption("--field-target-path", value: fieldMapping.targetPath, into: &arguments)
        appendOption("--field-sample-id-path", value: fieldMapping.sampleIDPath, into: &arguments)
        appendOption("--profile-type", value: profile.profileType, into: &arguments)
        appendOption("--result-kind", value: profile.resultKind, into: &arguments)
        appendOption("--extraction-mode", value: profile.extractionMode, into: &arguments)
        appendOption("--threshold", value: String(profile.threshold), into: &arguments)
        if let schemaPath, schemaPath.isEmpty == false {
            appendOption("--schema", value: schemaPath, into: &arguments)
        } else {
            appendOption("--output-schema-json", value: profile.outputSchemaJSON, into: &arguments)
        }
        appendMultiOption("--ignored-path", values: profile.ignoredPaths, into: &arguments)
    }

    private static func appendOption(
        _ option: String,
        value: String?,
        into arguments: inout [String]
    ) {
        guard let value, value.isEmpty == false else {
            return
        }
        arguments.append(contentsOf: [option, value])
    }

    private static func appendMultiOption(
        _ option: String,
        values: [String],
        into arguments: inout [String]
    ) {
        for value in values where value.isEmpty == false {
            arguments.append(contentsOf: [option, value])
        }
    }

    private static func appendBooleanFlag(
        _ option: String,
        value: String?,
        into arguments: inout [String]
    ) {
        guard value == "true" else {
            return
        }
        arguments.append(option)
    }

    private static func syntheticJSONArrayStrings(_ raw: String?) -> [String] {
        guard
            let raw,
            let data = raw.data(using: .utf8),
            let values = try? JSONSerialization.jsonObject(with: data) as? [String]
        else {
            return []
        }
        return values
    }

    private static func canonicalJSONStringArray(_ values: [String]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: values, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }

    private static func decodeSubprocessModelOperationResult(
        operation: String,
        output: String
    ) throws -> Melix_Controlplane_V1_ModelOperationResult {
        var result = Melix_Controlplane_V1_ModelOperationResult()
        result.operation = operation
        result.manifestJson = output
        guard let payload = jsonObject(from: output) else {
            return result
        }
        let payloadOperation = stringValue("operation", from: payload)
        result.operation = payloadOperation.isEmpty ? operation : payloadOperation
        result.jobID = stringValue("job_id", from: payload)
        result.stage = stringValue("stage", from: payload)
        result.pct = Float(doubleValue("pct", from: payload))
        result.outputPath = stringValue("output_path", from: payload)
        if result.outputPath.isEmpty, result.operation == "dataset_download" {
            result.outputPath = stringValue("snapshot_path", from: payload)
        }
        return result
    }

    private static func decodeSubprocessEvaluationResults(
        _ output: String
    ) throws -> [ControlPlaneEvaluationResult] {
        guard let items = jsonArray(from: output) else {
            throw MelixCLIError.runtime("The melix eval compare subprocess did not return a JSON array.")
        }
        return items.compactMap { item in
            guard let payload = item as? [String: Any] else {
                return nil
            }
            let nestedJobPayload = dictionaryValue("job", from: payload)
            let jobPayload = nestedJobPayload.isEmpty ? payload : nestedJobPayload
            var job = Melix_Controlplane_V1_EvaluationJobSummary()
            job.jobID = stringValue("job_id", from: jobPayload)
            job.modelID = stringValue("model_id", from: jobPayload)
            job.taskKind = stringValue("task_kind", from: jobPayload)
            job.sourceRepo = stringValue("source_repo", from: jobPayload)
            job.suiteID = stringValue("suite_id", from: jobPayload)
            job.datasetID = stringValue("dataset_id", from: jobPayload)
            job.sampleSize = UInt32(intValue("sample_size", from: jobPayload))
            job.scoringMode = stringValue("scoring_mode", from: jobPayload)
            job.parameters = stringDictionaryValue("parameters", from: jobPayload)
            job.status = stringValue("status", from: jobPayload)
            job.outputDir = stringValue("output_dir", from: jobPayload)
            job.createdAtUnixMs = Int64(intValue("created_at_unix_ms", from: jobPayload))
            job.updatedAtUnixMs = Int64(intValue("updated_at_unix_ms", from: jobPayload))

            let results = (payload["results"] as? [[String: Any]] ?? []).map { row in
                var summary = Melix_Controlplane_V1_EvaluationResultSummary()
                summary.jobID = stringValue("job_id", from: row)
                summary.suiteID = stringValue("suite_id", from: row)
                summary.datasetID = stringValue("dataset_id", from: row)
                summary.sampleSize = UInt32(intValue("sample_size", from: row))
                summary.reportPath = stringValue("report_path", from: row)
                summary.metrics = (row["metrics"] as? [[String: Any]] ?? []).map { metricPayload in
                    var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
                    metric.name = stringValue("name", from: metricPayload)
                    metric.value = doubleValue("value", from: metricPayload)
                    metric.unit = stringValue("unit", from: metricPayload)
                    return metric
                }
                return summary
            }
            return ControlPlaneEvaluationResult(job: job, results: results)
        }
    }

    private func loraRunOutputRoot(_ options: LoraRunOptions) throws -> URL {
        if options.outputDir.isEmpty == false {
            return URL(fileURLWithPath: (options.outputDir as NSString).expandingTildeInPath)
        }
        let root = MelixHome(environment: environment).rootURL
            .appendingPathComponent("runs", isDirectory: true)
            .appendingPathComponent("lora-run", isDirectory: true)
        let timestamp = String(Int64(Date().timeIntervalSince1970 * 1000))
        let adapter = Self.sanitizedLoraRunPathComponent(options.training.adapterName)
        return root.appendingPathComponent("\(timestamp)-\(adapter)", isDirectory: true)
    }

    private static func sanitizedLoraRunPathComponent(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
        let scalars = value.unicodeScalars.map { scalar -> Character in
            allowed.contains(scalar) ? Character(scalar) : "-"
        }
        let candidate = String(scalars)
            .split(separator: "-", omittingEmptySubsequences: true)
            .joined(separator: "-")
        return candidate.isEmpty ? "adapter" : candidate
    }

    private static func resolvedLoraRunTrainingMode(
        requested: String,
        modelID: String,
        parameters: [String: String]
    ) -> String {
        let normalized = requested.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalized.isEmpty || normalized == "auto" else {
            return normalized
        }
        let evidence = ([modelID] + parameters.map { "\($0.key)=\($0.value)" })
            .joined(separator: " ")
            .lowercased()
        let quantizedMarkers = ["4bit", "8bit", "q4", "q8", "optiq", "quantized"]
        return quantizedMarkers.contains { evidence.contains($0) } ? "qlora" : "lora"
    }

    private static func resolveLoraAdapterManifestPath(
        from result: Melix_Controlplane_V1_ModelOperationResult,
        fallbackOutputDir: String
    ) throws -> String {
        let payload = jsonObject(from: result.manifestJson) ?? [:]
        for key in ["adapter_manifest_path", "manifest_path", "artifact_path"] {
            let value = stringValue(key, from: payload)
            if value.isEmpty == false {
                return value
            }
        }
        if result.outputPath.hasSuffix(".json") {
            return result.outputPath
        }
        if result.outputPath.isEmpty == false {
            return URL(fileURLWithPath: result.outputPath).appendingPathComponent("train_lora.adapter.json").path
        }
        if fallbackOutputDir.isEmpty == false {
            return URL(fileURLWithPath: fallbackOutputDir).appendingPathComponent("train_lora.adapter.json").path
        }
        throw MelixCLIError.runtime("LoRA training did not return an adapter manifest path.")
    }

    private static func resolveLoraActivationManifestPath(
        from result: Melix_Controlplane_V1_ModelOperationResult,
        fallbackOutputDir: String
    ) -> String {
        let payload = jsonObject(from: result.manifestJson) ?? [:]
        let manifestPath = stringValue("manifest_path", from: payload)
        if manifestPath.isEmpty == false {
            return manifestPath
        }
        if result.outputPath.hasSuffix(".json") {
            return result.outputPath
        }
        if result.outputPath.isEmpty == false {
            return URL(fileURLWithPath: result.outputPath).appendingPathComponent("manifest.json").path
        }
        if fallbackOutputDir.isEmpty == false {
            return URL(fileURLWithPath: fallbackOutputDir).appendingPathComponent("manifest.json").path
        }
        return ""
    }

    private static func modelOperationPayload(
        _ result: Melix_Controlplane_V1_ModelOperationResult
    ) -> [String: Any] {
        [
            "job_id": result.jobID,
            "operation": result.operation,
            "stage": result.stage,
            "pct": result.pct,
            "output_path": result.outputPath,
            "manifest": jsonObject(from: result.manifestJson) ?? [:],
        ]
    }

    private static func jsonObject(from text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8) else {
            return nil
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private static func jsonArray(from text: String) -> [Any]? {
        guard let data = text.data(using: .utf8) else {
            return nil
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [Any]
    }

    private static func dictionaryValue(_ key: String, from payload: [String: Any]) -> [String: Any] {
        payload[key] as? [String: Any] ?? [:]
    }

    private static func stringDictionaryValue(_ key: String, from payload: [String: Any]) -> [String: String] {
        payload[key] as? [String: String] ?? [:]
    }

    private static func stringValue(_ key: String, from payload: [String: Any]) -> String {
        payload[key] as? String ?? ""
    }

    private static func doubleValue(_ key: String, from payload: [String: Any]) -> Double {
        if let value = payload[key] as? Double {
            return value
        }
        if let value = payload[key] as? NSNumber {
            return value.doubleValue
        }
        return 0
    }

    private static func intValue(_ key: String, from payload: [String: Any]) -> Int {
        if let value = payload[key] as? Int {
            return value
        }
        if let value = payload[key] as? NSNumber {
            return value.intValue
        }
        return 0
    }

    private func loadOperatorState() throws -> MelixOperatorSessionState {
        try operatorSessionStore.load() ?? MelixOperatorSessionState(selectedServerSessionID: "", serverSessions: [])
    }

    private func commandRequiresConfiguredRegistryRootPriming(_ command: MelixCLICommand) -> Bool {
        switch command {
        case .convert,
             .quantize,
             .upload,
             .modelList,
             .modelInspect,
             .modelLoad,
             .modelUnload,
             .serverSnapshot,
             .serverStart,
             .loraList,
             .loraRun,
             .loraTrain,
             .alignmentTrain,
             .loraActivate,
             .loraRemoveDerived,
             .loraExperimentsList,
             .loraExperimentsShow,
             .loraPublishesList,
             .loraPublishesShow,
             .loraResume,
             .benchRun,
             .benchMatrixRun,
             .evalCompare:
            return true
        case .chatRun(let options):
            return options.remoteServerID.isEmpty
        case .evalRun(let options):
            return Self.effectiveRemoteTargetOptions(for: options).isEmpty
        case .batchRun, .batchStatus, .batchResume:
            return false
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

    private func runLoraTrain(_ options: LoraTrainOptions) async throws -> String {
        var ext = options.parameters
        if options.preflightFitCheck {
            guard options.modelID.trimmingCharacters(in: .whitespacesAndNewlines).contains("/") else {
                throw MelixCLIError.runtime("--preflight-fit-check is currently supported for melix lora train --model-id Hugging Face repo targets.")
            }
            let receipt = try await makeMemoryFitReceipt(repoID: options.modelID, targetKind: "train")
            try enforceMemoryFitPreflight(
                receipt,
                allowMemoryRisk: options.allowMemoryRisk,
                commandName: "training"
            )
            ext.merge(try receipt.runParameters(schemaVersion: Self.memoryFitSchemaVersion)) { _, new in new }
        }
        ext["adapter_name"] = options.adapterName
        ext["dataset_source_kind"] = options.datasetSourceKind
        if !options.datasetURI.isEmpty {
            ext["dataset_uri"] = options.datasetURI
        }
        if !options.targetRepo.isEmpty {
            ext["target_repo"] = options.targetRepo
        }
        if !options.trainingMode.isEmpty {
            ext["training_mode"] = options.trainingMode
        }
        let result = try await performModelOperation(
            modelID: options.modelID,
            operation: "train_lora",
            outputDir: "",
            ext: ext
        )
        return options.json ? result.manifestJson : result.outputPath
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

    private func remoteServerStore() -> RemoteServerStore {
        RemoteServerStore(melixHome: MelixHome(environment: environment))
    }

    private func remoteServerAPIKeyStore() -> RemoteServerAPIKeyStore {
        RemoteServerAPIKeyStore(melixHome: MelixHome(environment: environment))
    }

    private func evaluationPromptStore() -> EvaluationPromptStore {
        EvaluationPromptStore(melixHome: MelixHome(environment: environment))
    }

    private func runRecordStore() -> MelixRunRecordStore {
        MelixRunRecordStore(melixHome: MelixHome(environment: environment))
    }

    private func diagnosticsStore() -> MelixDiagnosticsStore {
        MelixDiagnosticsStore(
            melixHome: MelixHome(environment: environment),
            environment: environment
        )
    }

    private func jobStatusStore() -> MelixJobStatusStore {
        let melixHome = MelixHome(environment: environment)
        return MelixJobStatusStore(
            runRecordStore: runRecordStore(),
            diagnosticsStore: diagnosticsStore(),
            melixHome: melixHome
        )
    }

    private func localTrainingQueueStore() -> LocalTrainingQueueStore {
        LocalTrainingQueueStore(melixHome: MelixHome(environment: environment))
    }

    private func queueErrorCode(for error: MelixCLIError) -> String {
        switch error {
        case .requestFailed(let code, _):
            return code.isEmpty ? "training_queue_worker_failed" : code
        case .usage:
            return "training_queue_invalid_options"
        case .missingValue, .missingRequired:
            return "training_queue_missing_options"
        case .runtime:
            return "training_queue_worker_failed"
        }
    }

    private func renderRunReport(kind: String, options: RunReportOptions) throws -> String {
        let report = try runRecordStore().report(kind: kind, sourcePath: options.sourcePath)
        switch options.format.lowercased() {
        case "terminal", "text":
            return renderRunReportTerminal(report.payload)
        case "markdown", "md":
            return report.markdown
        case "json":
            return try runRecordJSONString(report.payload)
        default:
            throw MelixCLIError.usage("Invalid value for --format. Expected terminal, markdown, or json.")
        }
    }

    private func evaluationPromptSnapshot(promptID: String, revisionID: String) throws -> EvaluationPromptSnapshot {
        let prompt = try evaluationPromptStore().get(id: promptID)
        guard let prompt else {
            throw MelixCLIError.runtime("Evaluation prompt \(promptID) was not found.")
        }
        let normalizedRevisionID = revisionID.trimmingCharacters(in: .whitespacesAndNewlines)
        let revision = normalizedRevisionID.isEmpty
            ? prompt.latestRevision
            : prompt.revisions.first { $0.revisionID == normalizedRevisionID }
        guard let revision else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) revision \(normalizedRevisionID) was not found.")
        }
        return EvaluationPromptSnapshot(prompt: prompt, revision: revision)
    }

    private func remoteChatTarget(
        remoteServerID: String,
        remoteModelID: String
    ) throws -> ControlPlaneChatRequest.RemoteTarget {
        let normalizedRemoteServerID = remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let server = try remoteServerStore().get(id: normalizedRemoteServerID) else {
            throw MelixCLIError.runtime("Remote server \(normalizedRemoteServerID) was not found.")
        }
        let apiKey = try remoteServerAPIKeyStore()
            .loadAPIKey(remoteServerID: server.id)?
            .apiKey
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard apiKey.isEmpty == false else {
            throw MelixCLIError.runtime("Remote server \(server.id) has no API key configured.")
        }
        let modelID = remoteModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? server.defaultModelID
            : remoteModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard modelID.isEmpty == false else {
            throw MelixCLIError.runtime("Remote server \(server.id) has no model configured.")
        }
        return ControlPlaneChatRequest.RemoteTarget(
            serverID: server.id,
            providerKind: server.providerKind,
            baseURL: server.baseURL,
            apiKey: apiKey,
            modelID: modelID,
            timeoutSeconds: server.timeoutSeconds,
            rateLimitPerMinute: server.rateLimitPerMinute
        )
    }

    private func remoteEvaluationTarget(
        remoteServerID: String,
        remoteModelID: String
    ) throws -> ControlPlaneEvaluationRequest.RemoteTarget {
        let target = try remoteChatTarget(remoteServerID: remoteServerID, remoteModelID: remoteModelID)
        return ControlPlaneEvaluationRequest.RemoteTarget(
            remoteServerID: target.serverID,
            providerKind: target.providerKind,
            baseURL: target.baseURL,
            apiKey: target.apiKey,
            modelID: target.modelID,
            timeoutSeconds: target.timeoutSeconds,
            rateLimitPerMinute: target.rateLimitPerMinute
        )
    }

    private func semanticJudgeParameters(
        remoteServerID: String,
        remoteModelID: String
    ) throws -> [String: String] {
        let target = try remoteEvaluationTarget(remoteServerID: remoteServerID, remoteModelID: remoteModelID)
        return [
            "semantic_judge_remote_server_id": target.remoteServerID,
            "semantic_judge_provider_kind": target.providerKind,
            "semantic_judge_base_url": target.baseURL,
            "semantic_judge_api_key": target.apiKey,
            "semantic_judge_model_id": target.modelID,
            "semantic_judge_timeout_seconds": String(target.timeoutSeconds),
            "semantic_judge_rate_limit_per_minute": String(target.rateLimitPerMinute),
        ]
    }

    private func buildChatMessages(options: ChatRunOptions) -> [ControlPlaneChatRequest.Message] {
        var messages: [ControlPlaneChatRequest.Message] = []
        let systemPrompt = options.systemPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        if systemPrompt.isEmpty == false {
            messages.append(.init(role: "system", content: systemPrompt))
        }
        messages.append(.init(role: "user", content: options.message))
        return messages
    }

    private func collectChatResult(
        from execution: ControlPlaneChatExecution
    ) async throws -> (assistantText: String, finishReason: String) {
        var fallbackAssistant = ""
        for try await event in execution.stream {
            switch event {
            case .tokenDelta(let delta):
                fallbackAssistant += delta
            case .completed(let finishReason, let assistantText, _):
                let resolvedAssistant = assistantText.isEmpty ? fallbackAssistant : assistantText
                guard resolvedAssistant.isEmpty == false else {
                    throw MelixCLIError.runtime("melix chat run did not produce assistant text.")
                }
                return (resolvedAssistant, finishReason.isEmpty ? "unknown" : finishReason)
            case .failed(let code, let message):
                if code == ModelRuntimeAvailability.missingRuntimeCacheCode {
                    throw MelixCLIError.requestFailed(
                        code: code,
                        message: message.isEmpty ? ModelRuntimeAvailability.missingRuntimeCacheMessage : message
                    )
                }
                throw MelixCLIError.runtime("melix chat run failed [\(code)]: \(message)")
            default:
                continue
            }
        }

        guard fallbackAssistant.isEmpty == false else {
            throw MelixCLIError.runtime("melix chat run did not complete.")
        }
        return (fallbackAssistant, "unknown")
    }

    private func userFacingRequestError(from error: Error) -> Error {
        if let error = error as? ControlPlaneXPCClientError {
            switch error {
            case .requestFailed(let code, let message):
                return MelixCLIError.requestFailed(
                    code: code,
                    message: normalizedRequestFailureMessage(code: code, message: message)
                )
            }
        }
        if let error = error as? ControlPlaneChatExecutionError {
            switch error {
            case .requestFailed(let code, let message):
                return MelixCLIError.requestFailed(
                    code: code,
                    message: normalizedRequestFailureMessage(code: code, message: message)
                )
            case .unavailable, .unavailableReason:
                break
            }
        }
        return error
    }

    private func normalizedRequestFailureMessage(code: String, message: String) -> String {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        if code == ModelRuntimeAvailability.missingRuntimeCacheCode {
            return trimmed.isEmpty ? ModelRuntimeAvailability.missingRuntimeCacheMessage : trimmed
        }
        return trimmed.isEmpty ? code : trimmed
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

    private func applyServerControlOptions(
        _ options: ServerControlOptions,
        to session: inout MelixOperatorServerSessionState
    ) {
        if !options.defaultModelID.isEmpty {
            session.defaultModelID = options.defaultModelID
        }
        if !options.servedModelIDs.isEmpty {
            session.servedModelIDs = normalizedServedModelIDs(
                options.servedModelIDs,
                defaultModelID: session.defaultModelID
            )
        } else if !options.defaultModelID.isEmpty {
            session.servedModelIDs = normalizedServedModelIDs(
                session.servedModelIDs,
                defaultModelID: options.defaultModelID
            )
        }
        if options.modelIdleTimeoutSeconds > 0 {
            session.modelIdleTimeoutSeconds = options.modelIdleTimeoutSeconds
        }
        if options.allowedHosts.isEmpty == false {
            session.allowedHosts = options.allowedHosts
        }
        if options.allowedOrigins.isEmpty == false {
            session.allowedOrigins = options.allowedOrigins
        }
    }

    private func normalizedServedModelIDs(
        _ modelIDs: [String],
        defaultModelID: String
    ) -> [String] {
        MelixServerModelRosterNormalizer.normalized(
            modelIDs,
            defaultModelID: defaultModelID
        )
    }

    private func upsertServerSessionForStartIfNeeded(_ options: ServerControlOptions) throws -> String {
        let title = options.serverTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        let host = options.host.trimmingCharacters(in: .whitespacesAndNewlines)
        let titleSessionID = MelixServerStartShortcutName.sessionIDCandidate(for: title)
        let hasShortcutConfiguration = title.isEmpty == false
            || options.defaultModelID.isEmpty == false
            || options.servedModelIDs.isEmpty == false
            || host.isEmpty == false
            || options.port > 0
            || options.allowedHosts.isEmpty == false
            || options.allowedOrigins.isEmpty == false
            || options.rateLimitPerMinute > 0
            || options.timeoutSeconds > 0
            || options.modelIdleTimeoutSeconds > 0
        guard hasShortcutConfiguration else {
            return options.serverSessionID
        }
        guard title.isEmpty == false else {
            throw MelixCLIError.missingRequired("TITLE is required when passing --model, --models, --default-model, --host, --port, --allowed-host, --allowed-origin, --rate-limit-per-minute, --timeout-seconds, or --model-idle-timeout-seconds to melix server start.")
        }
        guard !options.defaultModelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model or --models is required when starting a titled server session.")
        }

        var resolvedID = ""
        let state = try mutateOperatorState { current in
            if let index = current.serverSessions.firstIndex(where: { session in
                session.id == title
                    || session.title == title
                    || titleSessionID.map { session.id == $0 } == true
            }) {
                var session = current.serverSessions[index]
                session.title = title
                applyServerControlOptions(options, to: &session)
                if host.isEmpty == false {
                    session.host = host
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
                current.selectedServerSessionID = session.id
                resolvedID = session.id
            } else {
                let createdID = nextServerStartShortcutSessionID(
                    options: options,
                    existingSessions: current.serverSessions
                )
                let created = MelixOperatorServerSessionState(
                    id: createdID,
                    title: title,
                    defaultModelID: options.defaultModelID,
                    servedModelIDs: options.servedModelIDs,
                    host: host.isEmpty ? "127.0.0.1" : host,
                    port: options.port > 0 ? options.port : 8080,
                    allowedHosts: options.allowedHosts,
                    allowedOrigins: options.allowedOrigins,
                    rateLimitPerMinute: options.rateLimitPerMinute > 0 ? options.rateLimitPerMinute : 120,
                    timeoutSeconds: options.timeoutSeconds > 0 ? options.timeoutSeconds : 120,
                    modelIdleTimeoutSeconds: options.modelIdleTimeoutSeconds > 0
                        ? options.modelIdleTimeoutSeconds
                        : 600,
                    lifecycle: .draft
                )
                current.serverSessions.append(created)
                current.selectedServerSessionID = created.id
                resolvedID = created.id
            }
        }
        guard resolvedID.isEmpty == false,
              state.serverSessions.contains(where: { $0.id == resolvedID }) else {
            throw MelixCLIError.runtime("Server session titled \(title) could not be created.")
        }
        return resolvedID
    }

    private func nextGeneratedServerSessionID(in sessions: [MelixOperatorServerSessionState]) -> String {
        let existingIDs = Set(sessions.map(\.id))
        var index = 1
        while existingIDs.contains("server-session-\(index)") {
            index += 1
        }
        return "server-session-\(index)"
    }

    private func nextServerStartShortcutSessionID(
        options: ServerControlOptions,
        existingSessions: [MelixOperatorServerSessionState]
    ) -> String {
        let id = options.serverSessionID
        guard id != ServerSessionRuntimeStore.defaultServerSessionID,
              !existingSessions.contains(where: { $0.id == id })
        else {
            return nextGeneratedServerSessionID(in: existingSessions)
        }
        return id
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

    private func applyAccelerationProfile(
        _ profileID: String,
        to defaults: inout MelixOperatorServerServingDefaultsState
    ) throws {
        let normalizedProfileID = profileID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedProfileID.isEmpty == false else {
            return
        }
        guard let profileID = ServingAccelerationProfiles.normalizeProfileID(normalizedProfileID) else {
            throw MelixCLIError.usage(
                "Invalid value for --acceleration-profile. Expected \(ServingAccelerationProfiles.allowedProfileList)."
            )
        }
        let profile = ServingAccelerationProfiles.profile(id: profileID)
        defaults.accelerationProfile = profileID
        defaults.concurrentProcessingEnabled = profile.concurrentProcessingEnabled
        defaults.maxConcurrentRequests = Int(profile.maxConcurrentRequests)
        defaults.prefillBatchSize = Int(profile.prefillBatchSize)
        defaults.completionBatchSize = Int(profile.completionBatchSize)
        defaults.accelerationMode = ServingAccelerationProfiles.controlPlaneRawValue(profile.accelerationMode)
        defaults.draftModelID = profile.draftModelID
        defaults.numDraftTokens = Int(profile.numDraftTokens)
    }

    private func servingDefaults(
        for options: ServerSessionCreateOptions
    ) throws -> MelixOperatorServerServingDefaultsState {
        var defaults = MelixOperatorServerServingDefaultsState()
        try applyAccelerationProfile(options.accelerationProfile, to: &defaults)
        let rawAccelerationMode = options.accelerationMode.trimmingCharacters(in: .whitespacesAndNewlines)
        let accelerationMode = normalizedServingDefaultsAccelerationMode(options.accelerationMode)
        if rawAccelerationMode.isEmpty == false && accelerationMode.isEmpty {
            throw MelixCLIError.usage(
                "Invalid value for --acceleration-mode. Expected baseline or speculative_decode."
            )
        }
        guard accelerationMode == "speculative_decode" else {
            if rawAccelerationMode.isEmpty == false {
                defaults.accelerationMode = "baseline"
                defaults.draftModelID = ""
                defaults.numDraftTokens = 0
            }
            return defaults
        }
        defaults.accelerationMode = accelerationMode
        let draftModelID = options.draftModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        if draftModelID.isEmpty == false {
            defaults.draftModelID = draftModelID
        }
        if options.numDraftTokens > 0 {
            defaults.numDraftTokens = options.numDraftTokens
        }
        if defaults.numDraftTokens <= 0 {
            defaults.numDraftTokens = Self.defaultSpeculativeNumDraftTokens
        }
        guard defaults.draftModelID.isEmpty == false else {
            throw MelixCLIError.missingRequired("--draft-model-id is required for speculative decode serving defaults.")
        }
        return defaults
    }

    private func applyServingDefaultsUpdate(
        _ options: ServerSessionUpdateOptions,
        to session: inout MelixOperatorServerSessionState
    ) throws {
        let rawAccelerationMode = options.accelerationMode.trimmingCharacters(in: .whitespacesAndNewlines)
        let accelerationMode = normalizedServingDefaultsAccelerationMode(options.accelerationMode)
        if rawAccelerationMode.isEmpty == false && accelerationMode.isEmpty {
            throw MelixCLIError.usage(
                "Invalid value for --acceleration-mode. Expected baseline or speculative_decode."
            )
        }
        let draftModelID = options.draftModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        try applyAccelerationProfile(options.accelerationProfile, to: &session.servingDefaults)
        let hasAccelerationMode = accelerationMode.isEmpty == false
        let hasDraftModelID = draftModelID.isEmpty == false
        let hasNumDraftTokens = options.numDraftTokens > 0
        let hasAccelerationProfile = options.accelerationProfile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        guard hasAccelerationMode || hasDraftModelID || hasNumDraftTokens || hasAccelerationProfile else {
            return
        }

        if accelerationMode == "baseline" {
            session.servingDefaults.accelerationMode = "baseline"
            session.servingDefaults.draftModelID = ""
            session.servingDefaults.numDraftTokens = 0
            return
        }

        session.servingDefaults.accelerationMode = "speculative_decode"
        if hasDraftModelID {
            session.servingDefaults.draftModelID = draftModelID
        }
        if hasNumDraftTokens {
            session.servingDefaults.numDraftTokens = options.numDraftTokens
        }
        if session.servingDefaults.numDraftTokens <= 0 {
            session.servingDefaults.numDraftTokens = Self.defaultSpeculativeNumDraftTokens
        }
        guard session.servingDefaults.draftModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            throw MelixCLIError.missingRequired("--draft-model-id is required for speculative decode serving defaults.")
        }
    }

    private func normalizedServingDefaultsAccelerationMode(_ rawValue: String) -> String {
        switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "baseline", "speculative_decode":
            return rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        default:
            return ""
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

        let sanitizedModelID = sanitizedDownloadPathComponent(modelID, fallback: "model")
        return MelixHome(environment: environment).modelOpsJobsRootURL
            .appendingPathComponent("downloads", isDirectory: true)
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
        ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: rawValue)
    }

    private func runtimeModeLabel(_ model: Melix_Controlplane_V1_ModelSummary) -> String {
        // Render the runtime_mode field as a short tag for the list column:
        // "adapter" for adapter-backed, "fused" for fused derived, "-" when
        // the field isn't populated (base models and legacy entries). Unknown
        // values fall through to a bounded-width sentinel ("?") so a future
        // backend that populates a longer string cannot blow out the
        // tab-column width that downstream tooling relies on.
        switch model.runtimeMode {
        case "adapter_backed_runtime":
            return "adapter"
        case "fused_derived_model":
            return "fused"
        case "":
            return "-"
        default:
            return "?"
        }
    }

    private func loadTrustListLabel(_ model: Melix_Controlplane_V1_ModelSummary) -> String {
        let policy = ModelCatalogPresentation.loadTrustPolicy(for: model)
        let label: String
        switch policy.effectiveMode {
        case .modelLoadTrustDefaultSafe:
            label = "safe"
        case .modelLoadTrustTrustRemoteCode:
            label = "trust"
        case .modelLoadTrustNotApplicable:
            label = "n/a"
        case .unspecified:
            label = "-"
        case .UNRECOGNIZED:
            label = "?"
        }
        return policy.requiresReloadForTrustChange ? "\(label)*" : label
    }

    private func loadTrustDetailLines(_ model: Melix_Controlplane_V1_ModelSummary) -> [String] {
        let policy = ModelCatalogPresentation.loadTrustPolicy(for: model)
        var lines = [
            "load_trust_requested=\(ModelCatalogPresentation.loadTrustModeIdentifier(policy.requestedMode))",
            "load_trust_effective=\(ModelCatalogPresentation.loadTrustModeIdentifier(policy.effectiveMode))",
            "load_trust_policy_source=\(policy.policySource)",
            "load_trust_custom_loader_required=\(policy.customLoaderRequired ? "true" : "false")",
            "load_trust_requires_reload=\(policy.requiresReloadForTrustChange ? "true" : "false")",
        ]
        let route = ModelCatalogPresentation.workerRouteIdentifier(for: policy.routeClass)
        if route != "unspecified" {
            lines.append("load_trust_route_class=\(route)")
        }
        if !policy.loaderFamily.isEmpty {
            lines.append("load_trust_loader_family=\(policy.loaderFamily)")
        }
        if !policy.customLoaderDetectionSource.isEmpty {
            lines.append("load_trust_detection=\(policy.customLoaderDetectionSource)")
        }
        if !policy.blockReason.isEmpty {
            lines.append("load_trust_block_reason=\(policy.blockReason)")
        }
        return lines
    }

    private func makeModelLoadTrustPayload(_ model: Melix_Controlplane_V1_ModelSummary) -> [String: Any] {
        let policy = ModelCatalogPresentation.loadTrustPolicy(for: model)
        var payload: [String: Any] = [
            "receipt_present": model.hasLoadTrust,
            "requested_mode": ModelCatalogPresentation.loadTrustModeIdentifier(policy.requestedMode),
            "effective_mode": ModelCatalogPresentation.loadTrustModeIdentifier(policy.effectiveMode),
            "policy_source": policy.policySource,
            "custom_loader_required": policy.customLoaderRequired,
            "requires_reload_for_trust_change": policy.requiresReloadForTrustChange,
        ]

        let route = ModelCatalogPresentation.workerRouteIdentifier(for: policy.routeClass)
        if route != "unspecified" {
            payload["route_class"] = route
        }
        if !policy.loaderFamily.isEmpty {
            payload["loader_family"] = policy.loaderFamily
        }
        if !policy.customLoaderDetectionSource.isEmpty {
            payload["custom_loader_detection_source"] = policy.customLoaderDetectionSource
        }
        if !policy.blockReason.isEmpty {
            payload["block_reason"] = policy.blockReason
        }
        return payload
    }

    private func renderModelList(_ models: [Melix_Controlplane_V1_ModelSummary]) -> String {
        guard models.isEmpty == false else {
            return "No models found.\n"
        }
        // Fixed-width table: each column padded to the max width of the
        // header + all rows in that column so the output aligns cleanly in
        // terminals. Columns separated by two spaces. Consumers that need
        // the column-boundary-stable JSON shape should pass ``--json``;
        // this renderer is for human reading.
        let header = ["MODEL_ID", "KIND", "STATE", "STATUS", "RUNTIME", "TRUST"]
        let dataRows = models
            .sorted { $0.modelID < $1.modelID }
            .map { model in
                [
                    model.modelID,
                    model.kind,
                    modelStateLabel(model.state),
                    ModelRuntimeAvailability.runtimeStatus(for: model),
                    runtimeModeLabel(model),
                    loadTrustListLabel(model),
                ]
            }
        let allRows = [header] + dataRows
        // allRows always has the header row so `.max()` is non-nil; we still
        // pass a 0 fallback to satisfy the compiler without a force-unwrap.
        let widths = (0..<header.count).map { columnIndex in
            allRows.map { $0[columnIndex].count }.max() ?? 0
        }
        let formatted = allRows.map { row -> String in
            row.enumerated()
                .map { index, cell in
                    // Grapheme-safe padding: ``String.count`` returns
                    // grapheme-cluster count but Foundation's
                    // ``padding(toLength:)`` operates on UTF‑16 code units,
                    // so they disagree for any non-BMP character (emoji) or
                    // multi-code-unit grapheme. Today every cell in this
                    // table is ASCII, but padding with
                    // ``String(repeating:)`` keeps the two length notions
                    // aligned so a future non-ASCII runtime tag (or an
                    // emoji-laden model_id) still produces correctly-aligned
                    // columns.
                    if index == row.count - 1 {
                        return cell
                    }
                    let padding = max(0, widths[index] - cell.count)
                    return cell + String(repeating: " ", count: padding)
                }
                .joined(separator: "  ")
        }
        return formatted.joined(separator: "\n") + "\n"
    }

    private func renderModelSummary(_ model: Melix_Controlplane_V1_ModelSummary) -> String {
        "\(model.modelID)\t\(model.kind)\t\(modelStateLabel(model.state))\t\(runtimeModeLabel(model))\t\(loadTrustListLabel(model))\n"
    }

    private func renderModelInfo(
        _ info: Melix_Controlplane_V1_ModelInfo,
        modelID: String,
        snapshotModel: Melix_Controlplane_V1_ModelSummary?
    ) -> String {
        var lines = [
            "model_id=\(modelID)",
            "model_kind=\(info.modelKind)",
            "backend_id=\(info.backendID)",
            "family_id=\(info.familyID)",
            "max_context=\(info.maxContext)",
            "supported_tasks=\(info.supportedTasks.joined(separator: ","))",
        ]
        if let snapshotModel {
            lines.append("runtime_status=\(ModelRuntimeAvailability.isRuntimeCacheMissing(snapshotModel) ? "missing cache" : "ok")")
            let runtimePath = ModelRuntimeAvailability.runtimePath(for: snapshotModel)
            if !runtimePath.isEmpty {
                lines.append("runtime_path=\(runtimePath)")
            }
            let descriptorPath = ModelRuntimeAvailability.descriptorPath(for: snapshotModel)
            if !descriptorPath.isEmpty {
                lines.append("descriptor_path=\(descriptorPath)")
            }
            let restoreCommand = ModelRuntimeAvailability.restoreCommand(for: snapshotModel)
            if !restoreCommand.isEmpty {
                lines.append("restore_command=\(restoreCommand)")
            }
            lines.append(contentsOf: loadTrustDetailLines(snapshotModel))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func renderHubSearch(_ result: Melix_Controlplane_V1_HubSearchResult) -> String {
        guard result.models.isEmpty == false else {
            return "No hub models found.\n"
        }
        let lines = result.models.map { model in
            [
                model.repoID,
                model.pipelineTag,
                model.mlxCompatible ? "mlx" : "generic",
                model.localFitStatus.isEmpty ? "unknown" : model.localFitStatus,
                formatBinaryBytes(model.estimatedResidentBytes),
                model.recommendedAction,
            ].joined(separator: "\t")
        }
        return (["repo_id\tpipeline_tag\tcompatibility\tlocal_fit_status\testimated_resident_bytes\trecommended_action"] + lines)
            .joined(separator: "\n") + "\n"
    }

    private func renderHubModelCard(_ card: Melix_Controlplane_V1_HubModelCard) -> String {
        [
            "repo_id=\(card.repoID)",
            "author=\(card.author)",
            "model_name=\(card.modelName)",
            "pipeline_tag=\(card.pipelineTag)",
            "mlx_compatible=\(card.mlxCompatible ? "true" : "false")",
            "local_fit_status=\(card.localFitStatus.isEmpty ? "unknown" : card.localFitStatus)",
            "local_fit_reasons=\(card.localFitReasons.joined(separator: " | "))",
            "estimated_artifact_bytes=\(card.estimatedArtifactBytes)",
            "estimated_resident_bytes=\(formatBinaryBytes(card.estimatedResidentBytes))",
            "parameter_count=\(card.parameterCount)",
            "quantization_summary=\(card.quantizationSummary)",
            "gated=\(card.gated ? "true" : "false")",
            "recommended_action=\(card.recommendedAction)",
        ].joined(separator: "\n") + "\n"
    }

    private func renderMemoryFitReceipt(_ receipt: MemoryFitReceipt) -> String {
        [
            "schema_version=\(Self.memoryFitSchemaVersion)",
            "target_kind=\(receipt.targetKind)",
            "repo_id=\(receipt.repoID)",
            "fit_status=\(receipt.fitStatus)",
            "total_unified_memory_bytes=\(formatBinaryBytes(receipt.totalUnifiedMemoryBytes))",
            "estimated_active_memory_bytes=\(formatBinaryBytes(receipt.estimatedActiveMemoryBytes))",
            "estimated_disk_usage_bytes=\(formatBinaryBytes(receipt.estimatedDiskUsageBytes))",
            "available_disk_bytes=\(formatBinaryBytes(receipt.availableDiskBytes))",
            "disk_fit_status=\(receipt.diskFitStatus)",
            "safety_threshold_fraction=\(String(format: "%.2f", locale: Locale(identifier: "en_US_POSIX"), receipt.safetyThresholdFraction))",
            "recommended_action=\(receipt.recommendedAction)",
            "reasons=\(receipt.reasons.joined(separator: " | "))",
            "unknown_fields=\(receipt.unknownFields.joined(separator: ","))",
        ].joined(separator: "\n") + "\n"
    }

    private func formatBinaryBytes(_ bytes: UInt64) -> String {
        let units = ["B", "KB", "MB", "GB", "TB"]
        var value = Double(bytes)
        var unitIndex = 0
        while value >= 1024.0 && unitIndex < units.count - 1 {
            value /= 1024.0
            unitIndex += 1
        }
        guard unitIndex > 0 else {
            return "\(bytes) B"
        }
        return String(format: "%.2f %@", locale: Locale(identifier: "en_US_POSIX"), value, units[unitIndex])
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
            let modelIDs = session.servedModelIDs.joined(separator: ",")
            return "\(selectedMarker)\(session.id)\t\(session.title)\t\(modelIDs)\t\(session.lifecycle.rawValue)"
        }
        return (["server_session_id\ttitle\tmodel_ids\tlifecycle"] + rows).joined(separator: "\n") + "\n"
    }

    private func renderRemoteServers(_ servers: [RemoteServer]) -> String {
        guard servers.isEmpty == false else {
            return "No remote servers configured.\n"
        }
        let rows = servers.map { server in
            "\(server.id)\t\(server.title)\t\(server.providerPreset.rawValue)\t\(server.providerKind)\t\(server.defaultModelID)\t\(server.healthStatus)\t\(server.apiKeyHint)"
        }
        return (["remote_server_id\ttitle\tprovider\tprovider_kind\tdefault_model_id\thealth\tapi_key"] + rows).joined(separator: "\n") + "\n"
    }

    private func renderEvaluationPrompts(_ prompts: [EvaluationPrompt]) -> String {
        guard prompts.isEmpty == false else {
            return "No evaluation prompts configured.\n"
        }
        let rows = prompts.map { prompt in
            let latest = prompt.latestRevision
            return [
                prompt.id,
                prompt.title,
                prompt.taskKind,
                prompt.scoringMode,
                prompt.latestRevisionID,
                latest?.status.rawValue ?? "",
                latest?.contentHash ?? "",
                prompt.readOnly ? "read-only" : (prompt.archived ? "archived" : "editable"),
            ].joined(separator: "\t")
        }
        return ([
            "prompt_id\ttitle\ttask_kind\tscoring_mode\tlatest_revision\tstatus\tcontent_hash\tstate",
        ] + rows).joined(separator: "\n") + "\n"
    }

    private func renderEvaluationPromptSnapshot(_ snapshot: EvaluationPromptSnapshot) -> String {
        [
            "prompt_id=\(snapshot.promptID)",
            "title=\(snapshot.title)",
            "revision_id=\(snapshot.revisionID)",
            "status=\(snapshot.status.rawValue)",
            "content_hash=\(snapshot.contentHash)",
            "system_prompt:",
            snapshot.systemPrompt,
        ].joined(separator: "\n") + "\n"
    }

    private func makeModelSummaryPayload(_ model: Melix_Controlplane_V1_ModelSummary) -> [String: Any] {
        var payload: [String: Any] = [
            "model_id": model.modelID,
            "kind": model.kind,
            "state": modelStateLabel(model.state),
            "features": model.features,
            // runtime_mode — "base", "fused_derived_model",
            // "adapter_backed_runtime", or "" when the backend didn't set
            // the field. Module 1 promotes this from ext[melix.activation_mode]
            // into a first-class summary field so operators see at a glance
            // whether a loaded model is fused or adapter-backed.
            "runtime_mode": model.runtimeMode,
            "load_trust": makeModelLoadTrustPayload(model),
            "media_route_receipt": ModelCatalogPresentation.publicMediaRoutePayload(for: model),
        ]
        let activationMode = model.settings.ext["melix.activation_mode"] ?? ""
        if !activationMode.isEmpty {
            payload["activation_mode"] = activationMode
        }
        let adapterManifestPath = model.settings.ext["melix.adapter_manifest_path"] ?? ""
        if !adapterManifestPath.isEmpty {
            payload["adapter_manifest_path"] = adapterManifestPath
        }
        let adapterWeightsPath = model.settings.ext["melix.adapter_weights_path"] ?? ""
        if !adapterWeightsPath.isEmpty {
            payload["adapter_weights_path"] = adapterWeightsPath
        }
        for (key, value) in ModelRuntimeAvailability.publicMetadata(for: model) {
            payload[key] = value
        }
        return payload
    }

    private func makeModelListPayload(_ models: [Melix_Controlplane_V1_ModelSummary]) -> [[String: Any]] {
        models.sorted { $0.modelID < $1.modelID }.map(makeModelSummaryPayload)
    }

    private func makeModelInfoPayload(
        _ info: Melix_Controlplane_V1_ModelInfo,
        modelID: String,
        snapshotModel: Melix_Controlplane_V1_ModelSummary?
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "model_id": modelID,
            "model_kind": info.modelKind,
            "backend_id": info.backendID,
            "family_id": info.familyID,
            "max_context": Int(info.maxContext),
            "supported_tasks": info.supportedTasks,
            "supported_modalities": info.supportedModalities,
            "supported_parsers": info.supportedParsers,
        ]
        if let snapshotModel {
            for (key, value) in ModelRuntimeAvailability.publicMetadata(for: snapshotModel) {
                payload[key] = value
            }
            payload["load_trust"] = makeModelLoadTrustPayload(snapshotModel)
            payload["media_route_receipt"] = ModelCatalogPresentation.publicMediaRoutePayload(for: snapshotModel)
        }
        return payload
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
                    "local_fit_status": model.localFitStatus,
                    "local_fit_reasons": model.localFitReasons,
                    "estimated_artifact_bytes": NSNumber(value: model.estimatedArtifactBytes),
                    "estimated_resident_bytes": NSNumber(value: model.estimatedResidentBytes),
                    "parameter_count": NSNumber(value: model.parameterCount),
                    "quantization_summary": model.quantizationSummary,
                    "gated": model.gated,
                    "recommended_action": model.recommendedAction,
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
            "local_fit_status": card.localFitStatus,
            "local_fit_reasons": card.localFitReasons,
            "estimated_artifact_bytes": NSNumber(value: card.estimatedArtifactBytes),
            "estimated_resident_bytes": NSNumber(value: card.estimatedResidentBytes),
            "parameter_count": NSNumber(value: card.parameterCount),
            "quantization_summary": card.quantizationSummary,
            "gated": card.gated,
            "recommended_action": card.recommendedAction,
        ]
    }

    private func makeDoctorPayload(
        _ report: Melix_Controlplane_V1_DoctorReport,
        systemPayload: [String: Any]? = nil
    ) -> [String: Any] {
        let melixHome = MelixHome(environment: environment)
        let resolvedSystemPayload = systemPayload ?? makeSystemPayload()
        let systemFindings = MelixSystemDiagnostics.missingDependencyFindings(melixHome: melixHome)
        let redactedReport = MelixDiagnosticsRedaction.redactMapping([
            "markdown": report.markdown,
            "findings": report.findings.map { finding -> [String: Any] in
                [
                    "code": finding.code,
                    "severity": doctorHealthStatusLabel(finding.severity),
                    "summary": finding.summary,
                    "detail": finding.detail,
                ]
            },
        ])
        var payload: [String: Any] = [
            "markdown": redactedReport.payload["markdown"] as? String ?? "",
            "health_status": doctorHealthStatusLabel(report.healthStatus),
            "diagnostics_consent_state": MelixSystemDiagnostics.diagnosticsConsentState,
            "redaction_schema_version": MelixDiagnosticsRedaction.schemaVersion,
            "redacted_field_count": (resolvedSystemPayload["redacted_field_count"] as? Int ?? 0)
                + redactedReport.redactedFieldCount,
            "system": resolvedSystemPayload,
            "findings": (redactedReport.payload["findings"] as? [[String: Any]] ?? []) + systemFindings,
        ]
        if report.markdown.isEmpty && systemFindings.isEmpty == false {
            payload["markdown"] = "# Melix Doctor\n"
        }
        return payload
    }

    private func makeSystemPayload() -> [String: Any] {
        let melixHome = MelixHome(environment: environment)
        let redactedEnvironment = MelixDiagnosticsRedaction.redactEnvironment(environment)
        return MelixSystemDiagnostics.payload(
            melixHome: melixHome,
            environment: environment,
            redactedFieldCount: redactedEnvironment.redactedFieldCount
        )
    }

    private func renderSystemPayload(_ payload: [String: Any]) -> String {
        let platform = payload["platform"] as? [String: Any] ?? [:]
        let melixHome = payload["melix_home"] as? [String: Any] ?? [:]
        let lines = [
            "# Melix System",
            "",
            "- Diagnostics consent: \(payload["diagnostics_consent_state"] ?? "unknown")",
            "- Redaction schema: \(payload["redaction_schema_version"] ?? MelixDiagnosticsRedaction.schemaVersion)",
            "- Redacted fields: \(payload["redacted_field_count"] ?? 0)",
            "- Operating system: \(platform["operating_system"] ?? "unknown")",
            "- Physical memory bytes: \(platform["physical_memory_bytes"] ?? 0)",
            "- MELIX_HOME: \(melixHome["root"] ?? "")",
            "- Logs: \(melixHome["logs"] ?? "")",
            "",
        ]
        return lines.joined(separator: "\n") + "\n"
    }

    private func renderMonitorPayload(_ payload: [String: Any]) -> String {
        let statusCounts = payload["status_counts"] as? [String: Any] ?? [:]
        let recentRuns = payload["recent_runs"] as? [[String: Any]] ?? []
        var lines = [
            "# Melix Monitor",
            "",
            "- Runs: \(payload["run_count"] ?? 0)",
            "- Status counts: \(statusCounts.map { "\($0.key)=\($0.value)" }.sorted().joined(separator: ", "))",
            "- Logs: \(payload["logs_directory"] ?? "")",
            "",
            "run_id\trun_kind\tstatus\tmodel_id\tstarted_at_unix_ms",
        ]
        lines.append(contentsOf: recentRuns.map { run in
            [
                stringField(run, "run_id"),
                stringField(run, "run_kind"),
                stringField(run, "status"),
                stringField(run, "model_id"),
                stringField(run, "started_at_unix_ms"),
            ].joined(separator: "\t")
        })
        return lines.joined(separator: "\n") + "\n"
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

    private func doctorHealthStatusLabel(_ value: Melix_Controlplane_V1_DoctorHealthStatus) -> String {
        switch value {
        case .healthy:
            return "healthy"
        case .warning:
            return "warning"
        case .degraded:
            return "degraded"
        case .failed:
            return "failed"
        default:
            return "unspecified"
        }
    }

    private func filterManifestKeys(
        fromManifestJson manifestJSON: String,
        defaults: [String: Any]
    ) throws -> [String: Any] {
        guard let data = manifestJSON.data(using: .utf8) else {
            throw MelixCLIError.runtime("Registry manifest could not be decoded as UTF-8.")
        }
        let object: Any
        do {
            object = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.runtime("Registry manifest is not valid JSON: \((error as NSError).localizedDescription)")
        }
        guard let payload = object as? [String: Any] else {
            throw MelixCLIError.runtime("Registry manifest must be a JSON object.")
        }
        var result = defaults
        for key in defaults.keys {
            if let value = payload[key] {
                result[key] = value
            }
        }
        return result
    }

    private func loraRegistryDefaults() -> [String: Any] {
        [
            "adapters": [] as [Any],
            "experiment_groups": [] as [Any],
            "derived_models": [] as [Any],
            "downloads": [] as [Any],
        ]
    }

    private func modelRegistrySnapshotDefaults() -> [String: Any] {
        [
            "adapters": [] as [Any],
            "derived_models": [] as [Any],
            "experiment_groups": [] as [Any],
            "downloads": [] as [Any],
            "model_registry": [:] as [String: Any],
            "warnings": [] as [Any],
        ]
    }

    private func datasetRegistrySnapshotDefaults() -> [String: Any] {
        [
            "dataset_registry": [
                "schema_version": "melix.dataset_registry_snapshot.v1",
                "roots": [] as [Any],
                "datasets": [] as [Any],
            ] as [String: Any],
            "warnings": [] as [Any],
        ]
    }

    private func renderDatasetRegistrySnapshot(_ manifestJSON: String) throws -> String {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let registry = payload["dataset_registry"] as? [String: Any]
        else {
            throw MelixCLIError.runtime("dataset_snapshot response did not include a dataset_registry JSON object.")
        }
        let datasets = registry["datasets"] as? [[String: Any]] ?? []
        if datasets.isEmpty {
            return "No managed datasets found.\n"
        }
        let lines = datasets.map { dataset in
            let repoID = (dataset["repo_id"] as? String) ?? ""
            let revision = (dataset["revision"] as? String) ?? ""
            let snapshotID = (dataset["snapshot_id"] as? String) ?? ""
            let totalBytes = formatBinaryBytes((dataset["total_bytes"] as? NSNumber)?.uint64Value ?? 0)
            let path = (dataset["snapshot_path"] as? String) ?? ""
            return "\(repoID)\t\(revision)\t\(snapshotID)\t\(totalBytes)\t\(path)"
        }
        return (["repo_id\trevision\tsnapshot_id\ttotal_bytes\tsnapshot_path"] + lines)
            .joined(separator: "\n") + "\n"
    }

    private func renderDatasetRemoveResult(_ result: Melix_Controlplane_V1_ModelOperationResult) -> String {
        let outputPath = result.outputPath.trimmingCharacters(in: .whitespacesAndNewlines)
        if outputPath.isEmpty == false {
            return outputPath + "\n"
        }
        guard
            let data = result.manifestJson.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return "Dataset removal completed.\n"
        }

        let repoID = (payload["repo_id"] as? String) ?? ""
        let revision = (payload["revision"] as? String) ?? ""
        let snapshotID = (payload["snapshot_id"] as? String)
            ?? (payload["removed_snapshot_id"] as? String)
            ?? ""
        let removedPath = (payload["removed_snapshot_path"] as? String) ?? ""
        let datasetLabel = [
            repoID,
            revision.isEmpty ? "" : "@\(revision)",
            snapshotID.isEmpty ? "" : " (\(snapshotID))",
        ].joined()
        let headline = datasetLabel.isEmpty
            ? "Removed dataset snapshot."
            : "Removed dataset snapshot \(datasetLabel)."
        if removedPath.isEmpty {
            return headline + "\n"
        }
        return headline + "\nRemoved path: \(removedPath)\n"
    }

    private func renderSyntheticDatasetResult(_ result: Melix_Controlplane_V1_ModelOperationResult) -> String {
        let outputPath = result.outputPath.trimmingCharacters(in: .whitespacesAndNewlines)
        if outputPath.isEmpty == false {
            return outputPath + "\n"
        }
        guard
            let data = result.manifestJson.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return "Synthetic dataset generation completed.\n"
        }
        let datasetID = (payload["dataset_id"] as? String) ?? ""
        let datasetName = (payload["dataset_name"] as? String) ?? ""
        let outputKind = (payload["output_kind"] as? String) ?? ""
        let rowCount = ((payload["row_count"] as? NSNumber)?.intValue)
            ?? ((payload["sample_count"] as? NSNumber)?.intValue)
            ?? 0
        let label = datasetID.isEmpty ? datasetName : datasetID
        let target = label.isEmpty ? "Synthetic dataset" : "Synthetic dataset \(label)"
        let suffix = outputKind.isEmpty ? "" : " (\(outputKind))"
        return "\(target)\(suffix) generated with \(rowCount) rows.\n"
    }

    private func renderRegistrySnapshot(_ manifestJSON: String) -> String {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return manifestJSON
        }

        let adapters = payload["adapters"] as? [[String: Any]] ?? []
        let derivedModels = payload["derived_models"] as? [[String: Any]] ?? []
        let experimentGroups = payload["experiment_groups"] as? [[String: Any]] ?? []
        if adapters.isEmpty && derivedModels.isEmpty && experimentGroups.isEmpty {
            return "No adapters or derived models found.\n"
        }

        var sections: [String] = []
        if adapters.isEmpty == false {
            let adapterLines = adapters.map { adapter in
                let name = (adapter["adapter_name"] as? String) ?? "adapter"
                let status = (adapter["status"] as? String) ?? "unknown"
                let sourceModel = (adapter["source_model"] as? String) ?? ""
                let activationMode = (adapter["activation_mode"] as? String) ?? ""
                let derivedModelID = (adapter["derived_model_id"] as? String) ?? ""
                let publishedRepo = (adapter["published_repo"] as? String) ?? ""
                let publishKind = (adapter["publish_artifact_kind"] as? String) ?? ""
                return "\(name)\t\(status)\t\(sourceModel)\t\(activationMode)\t\(derivedModelID)\t\(publishedRepo)\t\(publishKind)"
            }
            sections.append(
                (["adapter\tstatus\tsource_model\tactivation_mode\tderived_model_id\tpublished_repo\tpublish_artifact_kind"] + adapterLines)
                    .joined(separator: "\n")
            )
        }

        if derivedModels.isEmpty == false {
            let derivedLines = derivedModels.map { derivedModel in
                let modelID = (derivedModel["model_id"] as? String) ?? ""
                let alias = (derivedModel["derived_model_alias"] as? String) ?? ""
                let activationMode = (derivedModel["activation_mode"] as? String) ?? ""
                let activationBackend = (derivedModel["activation_backend"] as? String) ?? ""
                let sourceModel = (derivedModel["source_model"] as? String) ?? ""
                return "\(modelID)\t\(alias)\t\(activationMode)\t\(activationBackend)\t\(sourceModel)"
            }
            sections.append(
                (["derived_model_id\talias\tactivation_mode\tactivation_backend\tsource_model"] + derivedLines)
                    .joined(separator: "\n")
            )
        }

        if experimentGroups.isEmpty == false {
            let groupLines = experimentGroups.map { group in
                let groupID = (group["group_id"] as? String) ?? ""
                let runCount = (group["run_count"] as? Int) ?? 0
                let presetTitle = (group["latest_preset_title"] as? String) ?? ""
                let bestLoss = (group["best_loss"] as? Double) ?? 0.0
                let recommendedManifestPath = (group["recommended_manifest_path"] as? String) ?? ""
                return "\(groupID)\t\(runCount)\t\(presetTitle)\t\(String(format: "%.3f", bestLoss))\t\(recommendedManifestPath)"
            }
            sections.append(
                (["experiment_group\truns\tpreset\tbest_loss\trecommended_manifest"] + groupLines)
                    .joined(separator: "\n")
            )
        }

        return sections.joined(separator: "\n\n") + "\n"
    }

    private func runLoraExperimentsList(_ options: LoraExperimentsListOptions) async throws -> String {
        let modelID = try await resolveModelID(preferred: options.modelID)
        let result = try await performModelOperation(
            modelID: modelID,
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let groups = try extractExperimentGroups(fromManifestJson: result.manifestJson)
        if options.json {
            return try prettyJSON(["experiment_groups": groups])
        }
        return renderExperimentsList(groups)
    }

    private func runLoraExperimentsShow(_ options: LoraExperimentsShowOptions) async throws -> String {
        let modelID = try await resolveModelID(preferred: options.modelID)
        let result = try await performModelOperation(
            modelID: modelID,
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let groups = try extractExperimentGroups(fromManifestJson: result.manifestJson)
        guard let group = groups.first(where: { ($0["group_id"] as? String) == options.groupID }) else {
            throw MelixCLIError.missingRequired(experimentGroupNotFoundMessage(groupID: options.groupID, groups: groups))
        }
        if options.json {
            return try prettyJSON(group)
        }
        return renderExperimentsShow(group)
    }

    private func runLoraPublishesList(_ options: LoraPublishesListOptions) async throws -> String {
        let modelID = try await resolveModelID(preferred: options.modelID)
        let result = try await performModelOperation(
            modelID: modelID,
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let publishes = try extractPublishes(fromManifestJson: result.manifestJson)
        if options.json {
            return try prettyJSON(["publishes": publishes])
        }
        return renderPublishesList(publishes)
    }

    private func runLoraPublishesShow(_ options: LoraPublishesShowOptions) async throws -> String {
        let modelID = try await resolveModelID(preferred: options.modelID)
        let result = try await performModelOperation(
            modelID: modelID,
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let publishes = try extractPublishes(fromManifestJson: result.manifestJson)
        guard let publish = publishes.first(where: { ($0["job_id"] as? String) == options.jobID }) else {
            throw MelixCLIError.missingRequired(publishNotFoundMessage(jobID: options.jobID, publishes: publishes))
        }
        if options.json {
            return try prettyJSON(publish)
        }
        return renderPublishesShow(publish)
    }

    private func extractPublishes(fromManifestJson manifestJson: String) throws -> [[String: Any]] {
        guard let data = manifestJson.data(using: .utf8) else {
            throw MelixCLIError.runtime("registry_snapshot payload was not valid UTF-8.")
        }
        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.runtime("registry_snapshot payload was not valid JSON: \(error.localizedDescription)")
        }
        guard let payload = parsed as? [String: Any] else {
            throw MelixCLIError.runtime("registry_snapshot payload was not a JSON object.")
        }
        return payload["publishes"] as? [[String: Any]] ?? []
    }

    private func publishNotFoundMessage(jobID: String, publishes: [[String: Any]]) -> String {
        let knownIDs = publishes.compactMap { $0["job_id"] as? String }.filter { $0.isEmpty == false }
        if knownIDs.isEmpty {
            return "Unknown publish job \(jobID); no publishes are recorded yet."
        }
        return "Unknown publish job \(jobID). Known jobs: \(truncatedKnownIDList(knownIDs))."
    }

    private func truncatedKnownIDList(_ ids: [String], limit: Int = 10) -> String {
        if ids.count <= limit {
            return ids.joined(separator: ", ")
        }
        let shown = ids.prefix(limit).joined(separator: ", ")
        let remaining = ids.count - limit
        return "\(shown), … (\(remaining) more)"
    }

    private func renderPublishesList(_ publishes: [[String: Any]]) -> String {
        if publishes.isEmpty {
            return "No publishes recorded.\n"
        }
        let header = ["JOB_ID", "KIND", "TARGET_REPO", "SOURCE_JOB", "ADAPTER/DERIVED"]
        let rows: [[String]] = publishes.map { publish in
            let jobID = (publish["job_id"] as? String) ?? ""
            let exportKind = (publish["export_artifact_kind"] as? String) ?? ""
            let targetRepo = (publish["target_repo"] as? String) ?? ""
            let sourceJob = (publish["source_job_id"] as? String) ?? ""
            let adapterName = (publish["adapter_name"] as? String) ?? ""
            let derivedModelID = (publish["derived_model_id"] as? String) ?? ""
            let identity = derivedModelID.isEmpty ? adapterName : derivedModelID
            return [jobID, exportKind, targetRepo, sourceJob, identity]
        }
        return renderFixedWidthTable(header: header, rows: rows) + "\n"
    }

    private func renderPublishesShow(_ publish: [String: Any]) -> String {
        let jobID = (publish["job_id"] as? String) ?? ""
        let exportKind = (publish["export_artifact_kind"] as? String) ?? ""
        let distributionContract = (publish["distribution_contract"] as? String) ?? ""
        let targetRepo = (publish["target_repo"] as? String) ?? ""
        let publishedURL = (publish["published_url"] as? String) ?? ""
        let publishedRef = (publish["published_ref"] as? String) ?? ""
        let publishBackend = (publish["publish_backend"] as? String) ?? ""
        let sourceArtifactKind = (publish["source_artifact_kind"] as? String) ?? ""
        let sourceJobID = (publish["source_job_id"] as? String) ?? ""
        let sourceModel = (publish["source_model"] as? String) ?? ""
        let sourceArtifactPath = (publish["source_artifact_path"] as? String) ?? ""
        let sourceManifestPath = (publish["source_manifest_path"] as? String) ?? ""
        let adapterName = (publish["adapter_name"] as? String) ?? ""
        let derivedModelID = (publish["derived_model_id"] as? String) ?? ""
        let activationMode = (publish["activation_mode"] as? String) ?? ""
        let receiptPath = (publish["receipt_path"] as? String) ?? ""
        let publishedFiles = (publish["published_files"] as? [Any] ?? []).compactMap { $0 as? String }
        let processorConfigFiles = (publish["processor_config_files"] as? [Any] ?? []).compactMap { $0 as? String }

        var lines: [String] = []
        lines.append("Publish: \(jobID)")
        if !exportKind.isEmpty {
            lines.append("Export kind: \(exportKind)")
        }
        if !distributionContract.isEmpty {
            lines.append("Distribution contract: \(distributionContract)")
        }
        if !targetRepo.isEmpty {
            lines.append("Target repo: \(targetRepo)")
        }
        if !publishedURL.isEmpty {
            lines.append("Published URL: \(publishedURL)")
        }
        if !publishedRef.isEmpty {
            lines.append("Published ref: \(publishedRef)")
        }
        if !publishBackend.isEmpty {
            lines.append("Publish backend: \(publishBackend)")
        }
        lines.append("")
        lines.append("Source:")
        if !sourceArtifactKind.isEmpty {
            lines.append("  Artifact kind: \(sourceArtifactKind)")
        }
        if !sourceJobID.isEmpty {
            lines.append("  Source job: \(sourceJobID)")
        }
        if !sourceModel.isEmpty {
            lines.append("  Source model: \(sourceModel)")
        }
        if !sourceArtifactPath.isEmpty {
            lines.append("  Artifact path: \(sourceArtifactPath)")
        }
        if !sourceManifestPath.isEmpty, sourceManifestPath != sourceArtifactPath {
            lines.append("  Manifest path: \(sourceManifestPath)")
        }
        if !adapterName.isEmpty {
            lines.append("  Adapter name: \(adapterName)")
        }
        if !derivedModelID.isEmpty {
            lines.append("  Derived model id: \(derivedModelID)")
        }
        if !activationMode.isEmpty {
            lines.append("  Activation mode: \(activationMode)")
        }
        if !publishedFiles.isEmpty {
            lines.append("")
            lines.append("Published files (\(publishedFiles.count)):")
            for file in publishedFiles {
                lines.append("  \(file)")
            }
        }
        if !processorConfigFiles.isEmpty {
            lines.append("")
            lines.append("Processor configs (\(processorConfigFiles.count)):")
            for file in processorConfigFiles {
                lines.append("  \(file)")
            }
        }
        if !receiptPath.isEmpty {
            lines.append("")
            lines.append("Receipt: \(receiptPath)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func runLoraResume(_ options: LoraResumeOptions) async throws -> String {
        let modelID = try await resolveModelID(preferred: options.modelID)
        let snapshot = try await performModelOperation(
            modelID: modelID,
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let groups = try extractExperimentGroups(fromManifestJson: snapshot.manifestJson)
        guard let group = groups.first(where: { ($0["group_id"] as? String) == options.groupID }) else {
            throw MelixCLIError.missingRequired(experimentGroupNotFoundMessage(groupID: options.groupID, groups: groups))
        }
        let best = group["best_known_adapter"] as? [String: Any] ?? [:]
        let manifestPath = (best["manifest_path"] as? String) ?? ""
        guard !manifestPath.isEmpty else {
            throw MelixCLIError.missingRequired(
                "Group \(options.groupID) has no recommended adapter; use `melix lora experiments show --group-id \(options.groupID)` to inspect runs."
            )
        }
        let manifest = try readAdapterManifestPayload(at: manifestPath)
        let manifestDatasetURI = (manifest["dataset_uri"] as? String) ?? ""
        let manifestHFDatasetPath = (manifest["hf_dataset_path"] as? String) ?? ""
        let inheritedSourceKind = (manifest["dataset_source_kind"] as? String) ?? ""
        let resolvedAdapterName = options.adapterName.isEmpty
            ? ((manifest["adapter_name"] as? String) ?? "")
            : options.adapterName
        let resolvedPresetID = options.presetID.isEmpty
            ? ((manifest["preset_id"] as? String) ?? "")
            : options.presetID
        let resolvedDatasetURI: String
        let resolvedSourceKind: String
        if options.datasetURI.isEmpty == false {
            resolvedDatasetURI = options.datasetURI
            resolvedSourceKind = inheritedSourceKind.isEmpty ? "local_package" : inheritedSourceKind
        } else if manifestDatasetURI.isEmpty == false {
            resolvedDatasetURI = manifestDatasetURI
            resolvedSourceKind = inheritedSourceKind.isEmpty ? "local_package" : inheritedSourceKind
        } else if manifestHFDatasetPath.isEmpty == false {
            resolvedDatasetURI = manifestHFDatasetPath
            resolvedSourceKind = "hf_dataset"
        } else {
            throw MelixCLIError.missingRequired(
                "Recommended manifest for \(options.groupID) did not carry a dataset_uri or hf_dataset_path; pass --dataset-uri explicitly."
            )
        }
        guard !resolvedAdapterName.isEmpty else {
            throw MelixCLIError.missingRequired(
                "Recommended manifest for \(options.groupID) did not carry an adapter_name; pass --adapter-name explicitly."
            )
        }
        var ext: [String: String] = [
            "adapter_name": resolvedAdapterName,
            "dataset_source_kind": resolvedSourceKind,
            "dataset_uri": resolvedDatasetURI,
            "resume_manifest_path": manifestPath,
            "experiment_group_id": options.groupID,
        ]
        if !resolvedPresetID.isEmpty {
            ext["preset_id"] = resolvedPresetID
        }
        if let groupTitle = manifest["experiment_group_title"] as? String, !groupTitle.isEmpty {
            ext["experiment_group_title"] = groupTitle
        }
        if resolvedSourceKind == "hf_dataset" {
            for key in [
                "hf_dataset_path",
                "hf_dataset_name",
                "hf_dataset_revision",
                "hf_train_split",
                "hf_valid_split",
                "text_feature",
                "prompt_feature",
                "completion_feature",
                "chat_feature",
            ] {
                if let value = manifest[key] as? String, !value.isEmpty {
                    ext[key] = value
                }
            }
        }
        let result = try await performModelOperation(
            modelID: modelID,
            operation: "train_lora",
            outputDir: "",
            ext: ext
        )
        if options.json {
            return try prettyJSON([
                "group_id": options.groupID,
                "resume_manifest_path": manifestPath,
                "dataset_uri": resolvedDatasetURI,
                "adapter_name": resolvedAdapterName,
                "preset_id": resolvedPresetID,
                "training_manifest_path": result.outputPath,
                "training_manifest_json": result.manifestJson,
            ])
        }
        return result.outputPath
    }

    private func extractExperimentGroups(fromManifestJson manifestJson: String) throws -> [[String: Any]] {
        guard let data = manifestJson.data(using: .utf8) else {
            throw MelixCLIError.runtime("registry_snapshot payload was not valid UTF-8.")
        }
        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.runtime("registry_snapshot payload was not valid JSON: \(error.localizedDescription)")
        }
        guard let payload = parsed as? [String: Any] else {
            throw MelixCLIError.runtime("registry_snapshot payload was not a JSON object.")
        }
        return payload["experiment_groups"] as? [[String: Any]] ?? []
    }

    private func readAdapterManifestPayload(at path: String) throws -> [String: Any] {
        let url = URL(fileURLWithPath: path)
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw MelixCLIError.runtime("Unable to read adapter manifest at \(path): \(error.localizedDescription)")
        }
        guard let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MelixCLIError.runtime("Adapter manifest at \(path) was not a JSON object.")
        }
        return payload
    }

    private enum LoraPublishManifestClassification {
        case classified(LoraPublishExportKind)
        case unclassifiable
        case fileMissing
        case malformed(String)
    }

    private func resolveLoraPublishExportKind(options: LoraPublishOptions) throws -> LoraPublishExportKind {
        let classification = classifyLoraPublishManifest(at: options.artifactManifestPath)
        if let explicit = options.exportKind {
            // When both an explicit override and a *successfully-classified*
            // manifest are present, validate the override against the
            // manifest. Unreadable or unclassifiable manifests honor the
            // override — that's the documented escape hatch for
            // pre-schema-version manifests.
            if case .classified(let inferredKind) = classification, inferredKind != explicit {
                throw MelixCLIError.usage(
                    "--export-kind \(exportKindFlagValue(explicit)) does not match the manifest at \(options.artifactManifestPath) (classified as \(exportKindFlagValue(inferredKind))). Omit --export-kind to accept the manifest-inferred value or pass a matching manifest."
                )
            }
            return explicit
        }
        switch classification {
        case .classified(let kind):
            return kind
        case .unclassifiable:
            throw MelixCLIError.usage(
                "Unable to infer export kind from manifest at \(options.artifactManifestPath); pass --export-kind (adapter|merged) explicitly."
            )
        case .fileMissing:
            // Distinct error so a typo'd path is obvious without re-running
            // with --export-kind to mask the read failure.
            throw MelixCLIError.usage(
                "Manifest not found at \(options.artifactManifestPath); check the path or pass --export-kind (adapter|merged) explicitly."
            )
        case .malformed(let detail):
            throw MelixCLIError.usage(
                "Manifest at \(options.artifactManifestPath) is not valid JSON (\(detail)); fix the file or pass --export-kind (adapter|merged) explicitly."
            )
        }
    }

    private func classifyLoraPublishManifest(at manifestPath: String) -> LoraPublishManifestClassification {
        guard !manifestPath.isEmpty else {
            return .fileMissing
        }
        let url = URL(fileURLWithPath: manifestPath)
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            // Both ENOENT and EACCES land here; treat them uniformly as
            // "file unavailable" — the operator's recovery path is the same
            // (fix the path / permissions, or pass --export-kind to skip the
            // manifest read entirely).
            return .fileMissing
        }
        let payload: Any
        do {
            payload = try JSONSerialization.jsonObject(with: data)
        } catch {
            return .malformed(error.localizedDescription)
        }
        guard let object = payload as? [String: Any] else {
            return .malformed("top-level value was not a JSON object")
        }
        let schemaVersion = (object["schema_version"] as? String) ?? ""
        let artifactKind = (object["artifact_kind"] as? String) ?? ""
        let activationMode = (object["activation_mode"] as? String) ?? ""
        if artifactKind == "adapter" || schemaVersion == "melix.lora_adapter_package.v1" {
            return .classified(.adapterExport)
        }
        if schemaVersion == "melix.derived_text_model.v1" || activationMode == "fused_derived_model" {
            return .classified(.mergedExport)
        }
        if artifactKind == "converted_model_bundle" || artifactKind == "quantized_model_bundle" {
            return .classified(.mergedExport)
        }
        return .unclassifiable
    }

    private func exportKindFlagValue(_ kind: LoraPublishExportKind) -> String {
        switch kind {
        case .adapterExport:
            return "adapter"
        case .mergedExport:
            return "merged"
        }
    }

    private func experimentGroupNotFoundMessage(groupID: String, groups: [[String: Any]]) -> String {
        let knownIDs = groups.compactMap { $0["group_id"] as? String }.filter { $0.isEmpty == false }
        if knownIDs.isEmpty {
            return "Unknown experiment group \(groupID); no groups are recorded yet."
        }
        return "Unknown experiment group \(groupID). Known groups: \(truncatedKnownIDList(knownIDs))."
    }

    private func renderExperimentsList(_ groups: [[String: Any]]) -> String {
        if groups.isEmpty {
            return "No experiment groups found.\n"
        }
        let header = ["GROUP_ID", "TITLE", "RUNS", "BEST_LOSS", "RESUME_READY"]
        let rows: [[String]] = groups.map { group in
            let groupID = (group["group_id"] as? String) ?? ""
            let title = (group["title"] as? String) ?? ""
            let runCount = (group["run_count"] as? Int) ?? 0
            let bestLossText = coerceDouble(group["best_loss"]).map { String(format: "%.4f", $0) } ?? "n/a"
            let resumeReadyCount = (group["resume_ready_run_ids"] as? [Any] ?? []).count
            return [
                groupID,
                title,
                String(runCount),
                bestLossText,
                "\(resumeReadyCount) of \(runCount)",
            ]
        }
        return renderFixedWidthTable(header: header, rows: rows) + "\n"
    }

    private func renderExperimentsShow(_ group: [String: Any]) -> String {
        let groupID = (group["group_id"] as? String) ?? ""
        let title = (group["title"] as? String) ?? ""
        let sourceModel = (group["source_model"] as? String) ?? ""
        let adapterName = (group["adapter_name"] as? String) ?? ""
        let runCount = (group["run_count"] as? Int) ?? 0
        let resumeReadyIDs = (group["resume_ready_run_ids"] as? [Any] ?? []).compactMap { $0 as? String }
        let lineage = (group["checkpoint_lineage"] as? [[String: Any]]) ?? []
        let best = group["best_known_adapter"] as? [String: Any] ?? [:]

        var lines: [String] = []
        lines.append("Group: \(groupID)")
        if !title.isEmpty {
            lines.append("Title: \(title)")
        }
        if !sourceModel.isEmpty {
            lines.append("Source model: \(sourceModel)")
        }
        if !adapterName.isEmpty {
            lines.append("Adapter name: \(adapterName)")
        }
        lines.append("")
        lines.append("Runs (\(runCount)):")
        if lineage.isEmpty {
            lines.append("  (no per-run detail available)")
        } else {
            let lineageHeader = ["RUN_ID", "CHECKPOINTS", "RESUME_READY"]
            let lineageRows: [[String]] = lineage.map { entry in
                let runID = (entry["run_id"] as? String) ?? ""
                let checkpointCount = (entry["checkpoint_count"] as? Int) ?? 0
                let resumeReady = (entry["resume_ready"] as? Bool) ?? false
                return [runID, String(checkpointCount), resumeReady ? "yes" : "no"]
            }
            let table = renderFixedWidthTable(header: lineageHeader, rows: lineageRows)
            for tableLine in table.split(separator: "\n", omittingEmptySubsequences: false) {
                lines.append("  " + String(tableLine))
            }
        }
        if !resumeReadyIDs.isEmpty {
            lines.append("")
            lines.append("Resume-ready runs: \(resumeReadyIDs.joined(separator: ", "))")
        }

        let bestRunID = (best["run_id"] as? String) ?? ""
        let bestManifestPath = (best["manifest_path"] as? String) ?? ""
        let bestLossText = coerceDouble(best["loss_best"]).map { String(format: "%.4f", $0) } ?? "n/a"
        if !bestRunID.isEmpty, !bestManifestPath.isEmpty {
            lines.append("")
            lines.append("Best known adapter:")
            lines.append("  Run \(bestRunID) (loss \(bestLossText))")
            lines.append("  Manifest: \(bestManifestPath)")
            lines.append("  Resume via: melix lora resume --group-id \(groupID)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func renderFixedWidthTable(header: [String], rows: [[String]]) -> String {
        let columnCount = header.count
        var widths = header.map { $0.count }
        for row in rows {
            for (index, cell) in row.enumerated() where index < columnCount {
                widths[index] = max(widths[index], cell.count)
            }
        }
        func pad(_ row: [String]) -> String {
            var segments: [String] = []
            for index in 0..<columnCount {
                let value = index < row.count ? row[index] : ""
                if index == columnCount - 1 {
                    segments.append(value)
                } else {
                    segments.append(value.padding(toLength: widths[index], withPad: " ", startingAt: 0))
                }
            }
            return segments.joined(separator: "  ")
        }
        var lines = [pad(header)]
        for row in rows {
            lines.append(pad(row))
        }
        return lines.joined(separator: "\n")
    }

    private func coerceDouble(_ value: Any?) -> Double? {
        if let number = value as? Double {
            return number
        }
        if let number = value as? Int {
            return Double(number)
        }
        if let string = value as? String, let number = Double(string) {
            return number
        }
        return nil
    }

    private func renderTrainingDatasetManifest(_ manifestJSON: String) -> String {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return manifestJSON
        }

        let quality = payload["quality"] as? [String: Any] ?? [:]
        let tokenStats = payload["token_stats"] as? [String: Any] ?? [:]
        let lines = [
            "dataset_id=\((payload["dataset_id"] as? String) ?? "")",
            "format=\((payload["format"] as? String) ?? "")",
            "sample_count=\((payload["sample_count"] as? Int) ?? 0)",
            "validation_sample_count=\((payload["validation_sample_count"] as? Int) ?? 0)",
            "duplicate_count=\((quality["duplicate_count"] as? Int) ?? 0)",
            "dirty_count=\((quality["dirty_count"] as? Int) ?? 0)",
            "prompt_tokens_p95=\((tokenStats["prompt_tokens_p95"] as? Int) ?? 0)",
        ]
        return lines.joined(separator: "\n") + "\n"
    }

    private func makeManagedModelReceipt(
        from result: Melix_Controlplane_V1_ModelOperationResult
    ) throws -> ManagedModelReceipt {
        guard let data = result.manifestJson.data(using: .utf8) else {
            throw MelixCLIError.runtime("Managed model operations must return a JSON manifest.")
        }
        let payloadObject: Any
        do {
            payloadObject = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.runtime("Managed model operations must return a JSON manifest.")
        }
        guard let payload = payloadObject as? [String: Any] else {
            throw MelixCLIError.runtime("Managed model operations must return a JSON manifest.")
        }

        let ext = payload["ext"] as? [String: Any] ?? [:]
        let warnings = (payload["warnings"] as? [String]) ?? []
        let modelID = (payload["model_id"] as? String)
            ?? (payload["source_model"] as? String)
            ?? ""
        let managedModelPath = (payload["managed_model_path"] as? String)
            ?? (payload["output_path"] as? String)
            ?? result.outputPath
        let sourceKind = (ext["melix.source_kind"] as? String)
            ?? (payload["source_kind"] as? String)
            ?? ""
        let sourceLocator = (ext["melix.source_locator"] as? String)
            ?? (ext["melix.hf_repo_id"] as? String)
            ?? (payload["source_path"] as? String)
            ?? ""

        guard modelID.isEmpty == false, managedModelPath.isEmpty == false else {
            throw MelixCLIError.runtime("Managed model manifest did not include a model identifier and output path.")
        }

        return ManagedModelReceipt(
            modelID: modelID,
            managedModelPath: managedModelPath,
            sourceKind: sourceKind,
            sourceLocator: sourceLocator,
            warnings: warnings
        )
    }

    private func makeManagedDatasetReceipt(
        from result: Melix_Controlplane_V1_ModelOperationResult
    ) throws -> ManagedDatasetReceipt {
        guard let data = result.manifestJson.data(using: .utf8) else {
            throw MelixCLIError.runtime("Managed dataset operations must return a JSON manifest.")
        }
        let payloadObject: Any
        do {
            payloadObject = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.runtime("Managed dataset operations must return a JSON manifest.")
        }
        guard let payload = payloadObject as? [String: Any] else {
            throw MelixCLIError.runtime("Managed dataset operations must return a JSON manifest.")
        }
        let datasetID = (payload["dataset_id"] as? String) ?? ""
        let repoID = (payload["repo_id"] as? String) ?? ""
        let revision = (payload["revision"] as? String) ?? ""
        let snapshotID = (payload["snapshot_id"] as? String) ?? ""
        // snapshot_path is the canonical worker field; output_path and the
        // stream output path cover older or newer worker versions during skew.
        let managedDatasetPath = (payload["snapshot_path"] as? String)
            ?? (payload["output_path"] as? String)
            ?? result.outputPath
        let sourceKind = (payload["source_kind"] as? String) ?? "hf_cache_snapshot"

        guard repoID.isEmpty == false, managedDatasetPath.isEmpty == false else {
            throw MelixCLIError.runtime("Managed dataset manifest did not include a repo identifier and snapshot path.")
        }

        return ManagedDatasetReceipt(
            datasetID: datasetID.isEmpty ? "\(repoID)@\(revision.isEmpty ? "main" : revision)" : datasetID,
            repoID: repoID,
            revision: revision.isEmpty ? "main" : revision,
            snapshotID: snapshotID,
            managedDatasetPath: managedDatasetPath,
            sourceKind: sourceKind
        )
    }

    private func runEvaluationSuites(
        options: EvalRunOptions,
        suites: [String]
    ) async throws -> [ControlPlaneEvaluationResult] {
        var baseParameters = options.parameters
        if options.preflightFitCheck {
            guard options.hfRepoID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
                throw MelixCLIError.runtime("--preflight-fit-check is currently supported for melix eval run --repo-id targets.")
            }
            let receipt = try await makeMemoryFitReceipt(repoID: options.hfRepoID, targetKind: "eval")
            try enforceMemoryFitPreflight(
                receipt,
                allowMemoryRisk: options.allowMemoryRisk,
                commandName: "evaluation"
            )
            baseParameters.merge(try receipt.runParameters(schemaVersion: Self.memoryFitSchemaVersion)) { _, new in new }
        }
        let effectiveOptions = EvalRunOptions(
            modelID: options.modelID,
            hfRepoID: options.hfRepoID,
            remoteServerID: options.remoteServerID,
            remoteModelID: options.remoteModelID,
            remoteTargets: options.remoteTargets,
            suites: options.suites,
            datasetID: options.datasetID,
            sampleSize: options.sampleSize,
            source: options.source,
            fieldMapping: options.fieldMapping,
            profile: options.profile,
            parameters: baseParameters,
            evalPromptID: options.evalPromptID,
            evalPromptRevisionID: options.evalPromptRevisionID,
            evalPrompt: options.evalPrompt,
            evalPromptFile: options.evalPromptFile,
            semanticJudgeRemoteServerID: options.semanticJudgeRemoteServerID,
            semanticJudgeModelID: options.semanticJudgeModelID,
            remoteParallelism: options.remoteParallelism,
            preflightFitCheck: options.preflightFitCheck,
            allowMemoryRisk: options.allowMemoryRisk,
            json: options.json,
            liveProgress: options.liveProgress
        )
        let adHocPrompt = try adHocEvaluationPromptSystemPrompt(effectiveOptions)
        let remoteTargetOptions = Self.effectiveRemoteTargetOptions(for: effectiveOptions)
        let resolvedRemoteTargets: [ControlPlaneEvaluationRequest.RemoteTarget?] = try remoteTargetOptions.isEmpty
            ? [nil]
            : remoteTargetOptions.map {
                try remoteEvaluationTarget(
                    remoteServerID: $0.remoteServerID,
                    remoteModelID: $0.remoteModelID
                )
            }
        var suiteParameters: [String: [String: String]] = [:]
        for suiteID in suites {
            suiteParameters[suiteID] = try evaluationParameters(options: effectiveOptions, suiteID: suiteID, adHocPrompt: adHocPrompt)
        }

        var plannedRequests: [PlannedEvaluationRequest] = []
        for remoteTarget in resolvedRemoteTargets {
            for suiteID in suites {
                let usesCustomSource = effectiveOptions.source.kind != .builtinPackage
                let parameters = suiteParameters[suiteID] ?? effectiveOptions.parameters
                let request = ControlPlaneEvaluationRequest(
                    modelID: effectiveOptions.modelID,
                    hfRepoID: effectiveOptions.hfRepoID,
                    suiteID: suiteID,
                    datasetID: usesCustomSource
                        ? effectiveOptions.datasetID
                        : (effectiveOptions.datasetID.isEmpty ? Self.defaultEvaluationDatasetID(for: suiteID) : effectiveOptions.datasetID),
                    sampleSize: effectiveOptions.sampleSize,
                    source: effectiveOptions.source,
                    fieldMapping: effectiveOptions.fieldMapping,
                    profile: effectiveOptions.profile,
                    parameters: parameters,
                    remoteTarget: remoteTarget
                )
                plannedRequests.append(
                    PlannedEvaluationRequest(index: plannedRequests.count, request: request)
                )
            }
        }

        guard remoteTargetOptions.count > 1 else {
            var collected: [ControlPlaneEvaluationResult] = []
            for plannedRequest in plannedRequests {
                collected.append(try await client.runEvaluation(plannedRequest.request))
            }
            return collected
        }

        let requestedParallelism = Int(effectiveOptions.remoteParallelism)
        let maxParallelism = requestedParallelism > 0 ? requestedParallelism : plannedRequests.count
        return try await runEvaluationRequestsConcurrently(
            plannedRequests,
            maxParallelism: maxParallelism
        )
    }

    private func evaluationParameters(options: EvalRunOptions, suiteID: String, adHocPrompt: String) throws -> [String: String] {
        var parameters = options.parameters
        if adHocPrompt.isEmpty == false {
            parameters.merge(
                try adHocEvaluationPromptParameters(systemPrompt: adHocPrompt, suiteID: suiteID, options: options)
            ) { _, new in new }
        }
        let effectiveScoringMode = options.parameters["scoring_mode"]?.isEmpty == false
            ? options.parameters["scoring_mode"] ?? ""
            : options.profile.scoringMode
        let usesEventPrompt = suiteID == "event_extraction"
            || effectiveScoringMode == EvaluationPromptStore.eventExtractionScoringMode
            || options.evalPromptID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        if usesEventPrompt && adHocPrompt.isEmpty {
            guard suiteID == "event_extraction"
                || effectiveScoringMode == EvaluationPromptStore.eventExtractionScoringMode
            else {
                throw MelixCLIError.runtime("Evaluation prompts are only supported for event_extraction_weighted_f1.")
            }
            parameters.merge(
                try evaluationPromptParameters(
                    promptID: options.evalPromptID,
                    revisionID: options.evalPromptRevisionID
                )
            ) { _, new in new }
        }
        if options.semanticJudgeRemoteServerID.isEmpty == false {
            guard suiteID == "event_extraction"
                || effectiveScoringMode == EvaluationPromptStore.eventExtractionScoringMode
                || effectiveScoringMode == EvaluationPromptStore.topicMembershipSemanticScoringMode
            else {
                throw MelixCLIError.runtime("Semantic judge scoring is only supported for event_extraction_weighted_f1 or topic_membership_semantic_micro_f1.")
            }
            parameters.merge(
                try semanticJudgeParameters(
                    remoteServerID: options.semanticJudgeRemoteServerID,
                    remoteModelID: options.semanticJudgeModelID
                )
            ) { _, new in new }
        }
        return parameters
    }

    private static func effectiveRemoteTargetOptions(for options: EvalRunOptions) -> [EvalRemoteTargetOptions] {
        guard options.modelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              options.hfRepoID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return []
        }
        if options.remoteTargets.isEmpty == false {
            return options.remoteTargets.filter { $0.remoteServerID.isEmpty == false }
        }
        if options.remoteServerID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false {
            return [
                EvalRemoteTargetOptions(
                    remoteServerID: options.remoteServerID,
                    remoteModelID: options.remoteModelID
                ),
            ]
        }
        return []
    }

    private func runEvaluationRequestsConcurrently(
        _ plannedRequests: [PlannedEvaluationRequest],
        maxParallelism: Int
    ) async throws -> [ControlPlaneEvaluationResult] {
        guard plannedRequests.isEmpty == false else {
            return []
        }
        let boundedParallelism = max(1, min(maxParallelism, plannedRequests.count))
        let client = self.client
        var results = Array<ControlPlaneEvaluationResult?>(repeating: nil, count: plannedRequests.count)
        try await withThrowingTaskGroup(of: (Int, ControlPlaneEvaluationResult).self) { group in
            var nextIndex = 0
            for _ in 0..<boundedParallelism {
                let plannedRequest = plannedRequests[nextIndex]
                nextIndex += 1
                group.addTask {
                    (plannedRequest.index, try await client.runEvaluation(plannedRequest.request))
                }
            }
            while let (index, result) = try await group.next() {
                results[index] = result
                if nextIndex < plannedRequests.count {
                    let plannedRequest = plannedRequests[nextIndex]
                    nextIndex += 1
                    group.addTask {
                        (plannedRequest.index, try await client.runEvaluation(plannedRequest.request))
                    }
                }
            }
        }
        return try results.enumerated().map { index, result in
            guard let result else {
                throw MelixCLIError.runtime("Evaluation request \(index) did not return a result.")
            }
            return result
        }
    }

    private func evaluationPromptParameters(promptID: String, revisionID: String) throws -> [String: String] {
        let snapshot = try evaluationPromptStore().resolveForRun(promptID: promptID, revisionID: revisionID)
        return [
            "prompt_id": snapshot.promptID,
            "prompt_revision_id": snapshot.revisionID,
            "prompt_content_hash": snapshot.contentHash,
            "prompt_title": snapshot.title,
            "eval_prompt_id": snapshot.promptID,
            "eval_prompt_revision_id": snapshot.revisionID,
            "eval_prompt_content_hash": snapshot.contentHash,
            "eval_prompt_title": snapshot.title,
            "eval_prompt_system_prompt": snapshot.systemPrompt,
            "eval_prompt_examples_json": try EvaluationPromptStore.examplesJSONString(snapshot.examples),
        ]
    }

    private func adHocEvaluationPromptSystemPrompt(_ options: EvalRunOptions) throws -> String {
        let hasInlinePrompt = options.evalPrompt.isEmpty == false
        let hasPromptFile = options.evalPromptFile.isEmpty == false
        let inlinePrompt = options.evalPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        let promptFile = options.evalPromptFile.trimmingCharacters(in: .whitespacesAndNewlines)
        guard hasInlinePrompt == false || hasPromptFile == false else {
            throw MelixCLIError.usage("--eval-prompt and --eval-prompt-file are mutually exclusive.")
        }
        guard hasInlinePrompt || hasPromptFile else {
            return ""
        }
        if hasInlinePrompt {
            guard inlinePrompt.isEmpty == false else {
                throw MelixCLIError.usage("--eval-prompt must contain non-empty text.")
            }
        }
        if hasPromptFile {
            guard promptFile.isEmpty == false else {
                throw MelixCLIError.usage("--eval-prompt-file must be a non-empty path.")
            }
        }
        guard options.evalPromptID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw MelixCLIError.usage("--eval-prompt and --eval-prompt-file cannot be combined with --eval-prompt-id.")
        }
        guard options.evalPromptRevisionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw MelixCLIError.usage("--eval-prompt-revision requires --eval-prompt-id.")
        }
        if promptFile.isEmpty == false {
            let prompt = try String(contentsOfFile: promptFile, encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard prompt.isEmpty == false else {
                throw MelixCLIError.usage("--eval-prompt-file must contain non-empty UTF-8 text.")
            }
            return prompt
        }
        return inlinePrompt
    }

    private func adHocEvaluationPromptParameters(
        systemPrompt: String,
        suiteID: String,
        options: EvalRunOptions
    ) throws -> [String: String] {
        let scoringMode = options.parameters["scoring_mode"]?.isEmpty == false
            ? options.parameters["scoring_mode"] ?? ""
            : options.profile.scoringMode
        let contentHash = try EvaluationPromptStore.contentHash(
            taskKind: suiteID,
            scoringMode: scoringMode,
            systemPrompt: systemPrompt
        )
        return [
            "prompt_id": "ad-hoc.evaluation.prompt",
            "prompt_revision_id": "ad-hoc",
            "prompt_content_hash": contentHash,
            "prompt_title": "Ad Hoc Evaluation Prompt",
            "eval_prompt_id": "ad-hoc.evaluation.prompt",
            "eval_prompt_revision_id": "ad-hoc",
            "eval_prompt_content_hash": contentHash,
            "eval_prompt_title": "Ad Hoc Evaluation Prompt",
            "eval_prompt_system_prompt": systemPrompt,
            "eval_prompt_examples_json": "[]",
        ]
    }

    private func exportEvaluationArtifact(
        options: EvalExportOptions,
        missingRowsMessage: String,
        rowCount: (ControlPlaneBenchmarkExportBundle) throws -> Int,
        contents: (ControlPlaneBenchmarkExportBundle) throws -> String
    ) async throws -> String {
        let bundle = try await fetchBenchmarkExportBundle()
        let rows = try rowCount(bundle)
        guard rows > 0 else {
            throw MelixCLIError.runtime(missingRowsMessage)
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
        let lines = runs.flatMap { run in
            let resultRows = run.results.isEmpty ? [nil] : run.results.map(Optional.some)
            return resultRows.map { result in
                let metrics = (result?.metrics ?? [])
                .map { metric in
                    metric.unit.isEmpty ? "\(metric.name)=\(metric.value)" : "\(metric.name)=\(metric.value)\(metric.unit)"
                }
                .joined(separator: ", ")
                return [
                    run.job.jobID,
                    result?.suiteID ?? run.job.suiteID,
                    result?.datasetID ?? run.job.datasetID,
                    run.job.status,
                    metrics,
                ].joined(separator: "\t")
            }
        }
        return (["job_id\tsuite\tdataset\tstatus\tmetrics"] + lines).joined(separator: "\n") + "\n"
    }

    private func renderEvaluationCompareRuns(
        _ runs: [ControlPlaneEvaluationResult],
        bundle: ControlPlaneBenchmarkExportBundle
    ) -> String? {
        let statusByJobID = runs.reduce(into: [String: String]()) { partialResult, run in
            partialResult[run.job.jobID] = run.job.status
        }
        var seenJobIDs = Set<String>()
        let orderedJobIDs = runs.compactMap { run in
            seenJobIDs.insert(run.job.jobID).inserted ? run.job.jobID : nil
        }
        let rows = orderedJobIDs.flatMap { jobID in
            bundle.evaluationSummaryCSVRows(jobID: jobID).filter { row in
                row.verdict.isEmpty == false
                    || row.effectThreshold != nil
                    || row.bootstrapLowerBound != nil
                    || row.bootstrapUpperBound != nil
                    || row.analyticalLowerBound != nil
                    || row.analyticalUpperBound != nil
            }
        }
        guard rows.isEmpty == false else {
            return nil
        }
        let lines = rows.map { row in
            [
                row.jobID,
                compareSuiteLabel(for: row),
                row.datasetID,
                statusByJobID[row.jobID] ?? "completed",
                row.verdict.isEmpty ? "-" : row.verdict,
                signedDecimalText(row.primaryScoreValue),
                intervalText(lower: row.bootstrapLowerBound, upper: row.bootstrapUpperBound),
                intervalText(lower: row.analyticalLowerBound, upper: row.analyticalUpperBound),
                decimalText(row.effectThreshold),
            ].joined(separator: "\t")
        }
        return ([
            "job_id\tsuite\tdataset\tstatus\tverdict\tdelta\tbootstrap_ci\tanalytical_ci\tthreshold",
        ] + lines).joined(separator: "\n") + "\n"
    }

    private func compareSuiteLabel(for row: ControlPlaneEvaluationSummaryCSVRow) -> String {
        guard row.modelID.isEmpty == false else {
            return row.suiteID
        }
        return "\(row.suiteID):\(row.modelID)"
    }

    private func signedDecimalText(_ value: Double) -> String {
        return String(format: "%+.4f", value)
    }

    private func decimalText(_ value: Double?) -> String {
        guard let value else {
            return "-"
        }
        return String(format: "%.4f", value)
    }

    private func intervalText(lower: Double?, upper: Double?) -> String {
        guard let lower, let upper else {
            return "-"
        }
        return "[\(signedDecimalText(lower)), \(signedDecimalText(upper))]"
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

    private func makeBenchmarkJobPayload(_ job: Melix_Controlplane_V1_BenchmarkJobSummary) -> [String: Any] {
        [
            "schema_version": job.schemaVersion,
            "job_id": job.jobID,
            "model_id": job.modelID,
            "task_kind": job.taskKind,
            "source_repo": job.sourceRepo,
            "suites": job.suites,
            "benchmark_mode": job.benchmarkMode,
            "status": job.status,
            "output_dir": job.outputDir,
            "created_at_unix_ms": job.createdAtUnixMs,
            "updated_at_unix_ms": job.updatedAtUnixMs,
            "parameters": job.parameters,
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

    private func runBatch(_ options: BatchRunOptions) async throws -> String {
        let plan = try BatchRunPlanner.makePlan(options: options, environment: environment)
        try BatchRunArtifacts.writeFoundationArtifacts(plan: plan)
        if plan.config.preflight {
            let report = try await buildBatchPreflightReport(plan: plan)
            try BatchRunArtifacts.writePreflightReport(report, plan: plan)
            if !report.blockers.isEmpty {
                let blockerList = report.blockers.map { "\($0.name): \($0.detail)" }.joined(separator: "; ")
                throw MelixCLIError.runtime(
                    "Batch preflight blocked run \(plan.config.runID) before execution. \(blockerList)"
                )
            }
            if options.dryRun, options.json {
                var payload = BatchRunArtifacts.effectiveConfigPayload(plan: plan)
                payload["preflight_result"] = report.payload(plan: plan)
                return try prettyJSON(payload)
            }
            if options.dryRun {
                return BatchRunArtifacts.renderPreflightTextSummary(plan: plan, report: report)
            }
        }
        if options.dryRun, options.json {
            return try prettyJSON(BatchRunArtifacts.effectiveConfigPayload(plan: plan))
        }
        if options.dryRun {
            return BatchRunArtifacts.renderTextSummary(plan: plan)
        }
        let executor = BatchRunExecutor(plan: plan, commandExecutor: makeBatchSubprocessExecutor(plan: plan))
        let result = try await executor.execute()
        if options.json {
            return try prettyJSON(result.summary.payload())
        }
        return BatchRunReporter.renderRunText(summary: result.summary, progressLines: result.progressLines)
    }

    private func runBatchStatus(_ options: BatchStatusOptions) throws -> String {
        let resolution = try BatchRunStatusResolver.resolve(options: options, environment: environment)
        let records = try BatchRunManifestStore.loadRecords(manifestPath: resolution.manifestPath)
        let summary = BatchRunManifestStore.summarize(
            records: records,
            runID: resolution.runID,
            tempRoot: resolution.tempRoot,
            outputRoot: resolution.outputRoot,
            manifestPath: resolution.manifestPath
        )
        if options.json {
            return try prettyJSON(summary.payload())
        }
        return BatchRunReporter.renderStatusText(summary: summary)
    }

    private func runBatchResume(_ options: BatchResumeOptions) async throws -> String {
        let (plan, records) = try BatchRunResumePlanner.makePlan(options: options, environment: environment)
        let mode = BatchRunResumeMode(evalOnly: options.evalOnly, missingOnly: options.missingOnly)
        if options.dryRun {
            return try BatchRunResumePlanner.renderDryRun(plan: plan, records: records, mode: mode, json: options.json)
        }
        let executor = BatchRunExecutor(plan: plan, commandExecutor: makeBatchSubprocessExecutor(plan: plan))
        let result = try await executor.execute(existingRecords: records, resumeMode: mode)
        if options.json {
            return try prettyJSON(result.summary.payload())
        }
        return BatchRunReporter.renderRunText(summary: result.summary, progressLines: result.progressLines)
    }

    private func makeBatchSubprocessExecutor(plan: BatchRunPlan) -> BatchRunSubprocessExecutor {
        { arguments, extraEnvironment, workingDirectory in
            let baseCommand = plan.config.cliPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? ["melix"]
                : [plan.config.cliPath]
            let executor = MelixCLIProcessExecutor(
                baseCommand: baseCommand,
                environment: ProcessInfo.processInfo.environment
                    .merging(self.environment) { _, new in new }
                    .merging(extraEnvironment) { _, new in new },
                workingDirectory: workingDirectory
            )
            do {
                let result = try await executor.runDetailed(arguments: arguments)
                return BatchRunSubprocessResult(stdout: result.stdout, stderr: result.stderr, exitCode: result.exitCode)
            } catch {
                return BatchRunSubprocessResult(stdout: "", stderr: error.localizedDescription, exitCode: -1)
            }
        }
    }

    private func buildBatchPreflightReport(plan: BatchRunPlan) async throws -> BatchRunPreflightReport {
        var checks: [BatchRunPreflightCheck] = []
        let fileManager = FileManager.default
        let config = plan.config

        checks.append(directoryCheck(
            name: "repo_root",
            path: config.repoRoot,
            blockedDetail: "Melix repository root does not exist: \(config.repoRoot).",
            readyDetail: "Melix repository root exists.",
            category: "runtime_config"
        ))
        checks.append(executableCheck(
            name: "cli",
            path: config.cliPath,
            blockedDetail: "Melix CLI build artifact is missing or not executable: \(config.cliPath). Build with xcrun swift build --product melix or set MELIX_CLI.",
            readyDetail: "Melix CLI build artifact is executable."
        ))
        checks.append(contentsOf: stackProductChecks(config: config))
        checks.append(isolatedRuntimeConfigCheck(config: config))
        checks.append(portCheck(config.httpPort))
        checks.append(directoryWritableCheck(name: "melix_home", path: config.melixHome))
        checks.append(directoryWritableCheck(name: "runtime_dir", path: config.runtimeDir))
        checks.append(directoryWritableCheck(name: "temp_root", path: config.tempRoot))
        checks.append(directoryWritableCheck(name: "output_root", path: config.outputRoot))
        checks.append(diskCheck(path: config.outputRoot, fileManager: fileManager))
        checks.append(preflightCacheCheck(config: config))
        checks.append(contentsOf: preflightModelChecks(plan: plan))
        checks.append(preflightCheck(name: "dataset") {
            try preflightDatasetCheck(config: config)
        })
        checks.append(preflightCheck(name: "judge") {
            try preflightJudgeCheck(config: config)
        })

        let status = checks.contains(where: \.isBlocking) ? "blocked" : "ready"
        return BatchRunPreflightReport(
            schemaVersion: "melix.batch.preflight_report.v1",
            status: status,
            checks: checks
        )
    }

    private func directoryCheck(
        name: String,
        path: String,
        blockedDetail: String,
        readyDetail: String,
        category: String = "filesystem"
    ) -> BatchRunPreflightCheck {
        var isDirectory = ObjCBool(false)
        if FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue {
            return .init(
                name: name,
                status: "ready",
                detail: readyDetail,
                actionable: "",
                category: category,
                metadata: ["path": path]
            )
        }
        return .init(
            name: name,
            status: "blocked",
            detail: blockedDetail,
            actionable: "Create the directory or provide the correct path.",
            category: category,
            metadata: ["path": path]
        )
    }

    private func directoryWritableCheck(name: String, path: String) -> BatchRunPreflightCheck {
        let url = URL(fileURLWithPath: path)
        var isDirectory = ObjCBool(false)
        if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) {
            if isDirectory.boolValue {
                let status = FileManager.default.isWritableFile(atPath: url.path) ? "ready" : "blocked"
                return .init(
                    name: name,
                    status: status,
                    detail: "\(name) exists at \(path).",
                    actionable: status == "ready" ? "" : "Fix permissions or choose a writable directory.",
                    category: "runtime_config",
                    metadata: ["path": path]
                )
            }
            return .init(
                name: name,
                status: "blocked",
                detail: "\(name) is not a directory: \(path).",
                actionable: "Choose a directory path.",
                category: "runtime_config",
                metadata: ["path": path]
            )
        }

        var ancestor = url.deletingLastPathComponent()
        while true {
            var ancestorIsDirectory = ObjCBool(false)
            if FileManager.default.fileExists(atPath: ancestor.path, isDirectory: &ancestorIsDirectory) {
                if !ancestorIsDirectory.boolValue {
                    return .init(
                        name: name,
                        status: "blocked",
                        detail: "\(name) cannot be created because an ancestor is not a directory: \(ancestor.path).",
                        actionable: "Choose a path under an existing writable directory.",
                        category: "runtime_config",
                        metadata: ["path": path, "ancestor": ancestor.path]
                    )
                }
                let status = FileManager.default.isWritableFile(atPath: ancestor.path) ? "ready" : "blocked"
                return .init(
                    name: name,
                    status: status,
                    detail: "\(name) does not exist yet; nearest existing directory is \(ancestor.path).",
                    actionable: status == "ready" ? "The batch runner will create this directory when it writes artifacts." : "Fix ancestor permissions or choose a writable directory.",
                    category: "runtime_config",
                    metadata: ["path": path, "ancestor": ancestor.path]
                )
            }
            let next = ancestor.deletingLastPathComponent()
            guard next.path != ancestor.path else {
                break
            }
            ancestor = next
        }
        return .init(
            name: name,
            status: "blocked",
            detail: "\(name) does not exist and no parent directory could be found for \(path).",
            actionable: "Create the parent directory or choose a path under an existing writable directory.",
            category: "runtime_config",
            metadata: ["path": path]
        )
    }

    private func executableCheck(
        name: String,
        path: String,
        blockedDetail: String,
        readyDetail: String
    ) -> BatchRunPreflightCheck {
        if FileManager.default.isExecutableFile(atPath: path) {
            return .init(
                name: name,
                status: "ready",
                detail: readyDetail,
                actionable: "",
                category: "runtime_products",
                metadata: ["path": path]
            )
        }
        return .init(
            name: name,
            status: "blocked",
            detail: blockedDetail,
            actionable: "Build or point to the executable before launching a sweep.",
            category: "runtime_products",
            metadata: ["path": path]
        )
    }

    private func stackProductChecks(config: BatchRunEffectiveConfig) -> [BatchRunPreflightCheck] {
        let repoRoot = URL(fileURLWithPath: config.repoRoot)
        let products = [
            ("control_plane", ".build/debug/MelixControlPlaneService", true),
            ("python_worker_entrypoint", "services/mlx-worker-python/worker", false),
        ]
        return products.map { name, relativePath, requiresExecutable in
            let path = repoRoot.appendingPathComponent(relativePath).path
            var isDirectory = ObjCBool(false)
            let exists = FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
            let isUsable = exists && (!requiresExecutable || FileManager.default.isExecutableFile(atPath: path))
            if isUsable {
                return .init(
                    name: name,
                    status: "ready",
                    detail: "Required stack product \(relativePath) is present.",
                    actionable: "",
                    category: "runtime_products",
                    metadata: [
                        "path": path,
                        "requires_executable": String(requiresExecutable),
                    ]
                )
            }
            return .init(
                name: name,
                status: "warning",
                detail: "Required stack product \(relativePath) is not present yet.",
                actionable: "Build runtime prerequisites before execution, for example with make bootstrap or xcrun swift build --product melix.",
                category: "runtime_products",
                metadata: [
                    "path": path,
                    "exists": String(exists),
                    "requires_executable": String(requiresExecutable),
                ]
            )
        }
    }

    private func isolatedRuntimeConfigCheck(config: BatchRunEffectiveConfig) -> BatchRunPreflightCheck {
        let defaultRuntimeDir = URL(fileURLWithPath: config.repoRoot)
            .appendingPathComponent(".runtime/sidecars/\(config.serviceInstanceName)", isDirectory: true)
            .path
        let defaultHome = URL(fileURLWithPath: config.repoRoot)
            .appendingPathComponent(".runtime/home-\(config.serviceInstanceName)", isDirectory: true)
            .path
        var blockers: [String] = []
        if config.serviceInstanceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            blockers.append("service instance name is empty")
        }
        let bareDefaultPorts = Set(["11434", "12436"])
        if config.serviceInstanceName == "default" || bareDefaultPorts.contains(config.httpPort) {
            blockers.append("batch mode must not use the bare default Melix stack")
        }
        if config.runtimeDir == config.repoRoot || config.runtimeDir == "." || config.runtimeDir == "/" {
            blockers.append("runtime dir is not isolated")
        }
        if config.melixHome == FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".melix", isDirectory: true)
            .path
        {
            blockers.append("MELIX_HOME points at shared operator state")
        }
        let metadata = [
            "service_instance_name": config.serviceInstanceName,
            "http_port": config.httpPort,
            "bare_default_ports": bareDefaultPorts.sorted().joined(separator: ","),
            "runtime_dir": config.runtimeDir,
            "melix_home": config.melixHome,
            "default_runtime_dir": defaultRuntimeDir,
            "default_melix_home": defaultHome,
        ]
        if blockers.isEmpty {
            return .init(
                name: "isolated_runtime_config",
                status: "ready",
                detail: "Batch runtime config uses named instance \(config.serviceInstanceName), port \(config.httpPort), isolated runtime dir, and isolated MELIX_HOME.",
                actionable: "",
                category: "runtime_config",
                metadata: metadata
            )
        }
        return .init(
            name: "isolated_runtime_config",
            status: "blocked",
            detail: blockers.joined(separator: "; "),
            actionable: "Use a named batch instance, non-default HTTP port, worktree-local runtime dir, and worktree-local MELIX_HOME.",
            category: "runtime_config",
            metadata: metadata
        )
    }

    private func portCheck(_ value: String) -> BatchRunPreflightCheck {
        guard let port = Int(value), (1024...65535).contains(port) else {
            return .init(
                name: "http_port",
                status: "blocked",
                detail: "Invalid MELIX_HTTP_PORT value: \(value).",
                actionable: "Use a TCP port between 1024 and 65535.",
                category: "runtime_config",
                metadata: ["http_port": value]
            )
        }
        if isTCPPortListening(port) {
            return .init(
                name: "http_port",
                status: "blocked",
                detail: "HTTP port \(port) is already in use.",
                actionable: "Choose an unused MELIX_HTTP_PORT for this batch instance.",
                category: "runtime_config",
                metadata: ["http_port": value]
            )
        }
        return .init(
            name: "http_port",
            status: "ready",
            detail: "HTTP port \(port) is valid and no listener is currently detected.",
            actionable: "",
            category: "runtime_config",
            metadata: ["http_port": value]
        )
    }

    private func isTCPPortListening(_ port: Int) -> Bool {
        let socketFD = socket(AF_INET, SOCK_STREAM, 0)
        guard socketFD >= 0 else {
            return false
        }
        defer { close(socketFD) }

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = UInt16(port).bigEndian
        address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

        let result = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                Darwin.connect(socketFD, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return result == 0
    }

    private func diskCheck(path: String, fileManager: FileManager) -> BatchRunPreflightCheck {
        let url = URL(fileURLWithPath: path)
        do {
            let values = try url.resourceValues(forKeys: [
                .volumeAvailableCapacityForImportantUsageKey,
                .volumeAvailableCapacityKey,
            ])
            let available: Int64?
            if let importantCapacity = values.volumeAvailableCapacityForImportantUsage,
               importantCapacity > 0
            {
                available = importantCapacity
            } else if let volumeCapacity = values.volumeAvailableCapacity,
                      volumeCapacity > 0
            {
                available = Int64(volumeCapacity)
            } else if let fileSystemAttributes = try? fileManager.attributesOfFileSystem(forPath: url.path),
                      let fileSystemAvailable = fileSystemAttributes[.systemFreeSize] as? NSNumber
            {
                available = fileSystemAvailable.int64Value
            } else {
                available = nil
            }
            guard let available, available > 0 else {
            return .init(
                name: "disk",
                status: "warning",
                detail: "Could not determine available disk capacity near \(path).",
                actionable: "Confirm there is enough free disk before a long sweep.",
                category: "resource",
                metadata: ["path": path]
            )
        }
            let availableBytes = UInt64(max(0, available))
            let detail = "Available capacity near \(path): \(formatBinaryBytes(availableBytes))."
            return .init(
                name: "disk",
                status: "ready",
                detail: detail,
                actionable: "",
                category: "resource",
                metadata: [
                    "path": path,
                    "available_bytes": String(availableBytes),
                    "available_gib": String(format: "%.2f", Double(availableBytes) / 1_073_741_824.0),
                ]
            )
        } catch {
            return .init(
                name: "disk",
                status: "warning",
                detail: "Could not read available disk capacity near \(path): \(error.localizedDescription)",
                actionable: "Confirm there is enough free disk before a long sweep.",
                category: "resource",
                metadata: ["path": path]
            )
        }
    }

    private func preflightCacheCheck(config: BatchRunEffectiveConfig) -> BatchRunPreflightCheck {
        let melixHome = isolatedMelixHome(config: config)
        let modelCacheRoot = melixHome.managedModelRootURL
        let datasetCacheRoot = melixHome.rootURL.appendingPathComponent("datasets", isDirectory: true)
        let modelCacheExists = FileManager.default.fileExists(atPath: modelCacheRoot.path)
        let datasetCacheExists = FileManager.default.fileExists(atPath: datasetCacheRoot.path)
        let status = modelCacheExists || datasetCacheExists ? "ready" : "warning"
        let detail = [
            "model_cache=\(modelCacheRoot.path) \(modelCacheExists ? "exists" : "missing")",
            "dataset_cache=\(datasetCacheRoot.path) \(datasetCacheExists ? "exists" : "missing")",
        ].joined(separator: "; ")
        let actionable = status == "ready"
            ? ""
            : "Confirm required models and datasets can be downloaded or materialized before a long sweep."
        return .init(
            name: "cache_state",
            status: status,
            detail: detail,
            actionable: actionable,
            category: "cache",
            metadata: [
                "model_cache": modelCacheRoot.path,
                "model_cache_exists": String(modelCacheExists),
                "dataset_cache": datasetCacheRoot.path,
                "dataset_cache_exists": String(datasetCacheExists),
            ]
        )
    }

    private func preflightModelChecks(plan: BatchRunPlan) -> [BatchRunPreflightCheck] {
        let duplicateCounts = Dictionary(grouping: plan.models, by: \.repoID)
            .mapValues(\.count)
        return plan.selectedModels.map { model -> BatchRunPreflightCheck in
            if model.repoID.contains("/") {
                return .init(
                    name: "model_repo:\(model.index)",
                    status: "ready",
                    detail: "\(model.repoID) has a Hugging Face repo-shaped id.",
                    actionable: "",
                    category: "model_resolution",
                    metadata: [
                        "repo_id": model.repoID,
                        "source_line": String(model.sourceLine),
                        "duplicate_count": String(duplicateCounts[model.repoID, default: 1]),
                    ]
                )
            }
            return .init(
                name: "model_repo:\(model.index)",
                status: "blocked",
                detail: "\(model.repoID) is not a Hugging Face repo id.",
                actionable: "Use owner/repo model ids in the model list.",
                category: "model_resolution",
                metadata: [
                    "repo_id": model.repoID,
                    "source_line": String(model.sourceLine),
                ]
            )
        }
    }

    private func preflightDatasetCheck(config: BatchRunEffectiveConfig) throws -> BatchRunPreflightCheck {
        let datasetID = config.evalDatasetID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !datasetID.isEmpty else {
            return .init(
                name: "dataset",
                status: "blocked",
                detail: "Evaluation dataset id is empty.",
                actionable: "Set --eval-dataset-id or eval_dataset_id.",
                category: "dataset",
                metadata: ["dataset_id": datasetID]
            )
        }
        let repoRootFixture = URL(fileURLWithPath: config.repoRoot)
            .appendingPathComponent("services/mlx-worker-python/fixtures/evaluation", isDirectory: true)
            .appendingPathComponent(datasetID, isDirectory: true)
        if FileManager.default.fileExists(atPath: repoRootFixture.appendingPathComponent("manifest.json").path),
           FileManager.default.fileExists(atPath: repoRootFixture.appendingPathComponent("samples.jsonl").path)
        {
            return .init(
                name: "dataset",
                status: "ready",
                detail: "Fixture dataset \(datasetID) is packaged at \(repoRootFixture.path).",
                actionable: "",
                category: "dataset",
                metadata: [
                    "dataset_id": datasetID,
                    "fixture_path": repoRootFixture.path,
                    "source": "repo_fixture",
                ]
            )
        }

        let managedRoot = isolatedMelixHome(config: config).rootURL
            .appendingPathComponent("datasets", isDirectory: true)
        if FileManager.default.fileExists(atPath: managedRoot.path) {
            return .init(
                name: "dataset",
                status: "warning",
                detail: "Dataset \(datasetID) was not found in repo fixtures; managed dataset cache exists at \(managedRoot.path).",
                actionable: "Confirm the dataset is materialized before a long sweep.",
                category: "dataset",
                metadata: [
                    "dataset_id": datasetID,
                    "managed_cache": managedRoot.path,
                    "source": "managed_cache",
                ]
            )
        }
        return .init(
            name: "dataset",
            status: "blocked",
            detail: "Dataset \(datasetID) was not found in repo fixtures or managed dataset cache.",
            actionable: "Download or package the evaluation dataset before running the sweep.",
            category: "dataset",
            metadata: [
                "dataset_id": datasetID,
                "fixture_path": repoRootFixture.path,
                "managed_cache": managedRoot.path,
            ]
        )
    }

    private func preflightJudgeCheck(config: BatchRunEffectiveConfig) throws -> BatchRunPreflightCheck {
        let judgeID = config.judgeRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !judgeID.isEmpty else {
            return .init(
                name: "judge",
                status: "blocked",
                detail: "Semantic judge remote-server id is empty.",
                actionable: "Set --judge-remote-server-id or judge_remote_server_id.",
                category: "judge",
                metadata: ["remote_server_id": judgeID]
            )
        }
        let melixHome = isolatedMelixHome(config: config)
        guard let server = try RemoteServerStore(melixHome: melixHome).get(id: judgeID) else {
            return .init(
                name: "judge",
                status: "blocked",
                detail: "Remote server \(judgeID) was not found in MELIX_HOME=\(config.melixHome).",
                actionable: "Configure the judge with melix remote-server add before launching a long run.",
                category: "judge",
                metadata: [
                    "remote_server_id": judgeID,
                    "melix_home": config.melixHome,
                ]
            )
        }
        let apiKey = try RemoteServerAPIKeyStore(melixHome: melixHome)
            .loadAPIKey(remoteServerID: server.id)?
            .apiKey
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !apiKey.isEmpty else {
            return .init(
                name: "judge",
                status: "blocked",
                detail: "Remote server \(judgeID) has no API key configured.",
                actionable: "Store the judge API key with melix remote-server add/update.",
                category: "judge",
                metadata: ["remote_server_id": judgeID]
            )
        }
        let modelID = config.judgeModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? server.defaultModelID
            : config.judgeModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !modelID.isEmpty else {
            return .init(
                name: "judge",
                status: "blocked",
                detail: "Remote server \(judgeID) has no judge model configured.",
                actionable: "Set --judge-model or configure a default remote model.",
                category: "judge",
                metadata: ["remote_server_id": judgeID]
            )
        }
        return .init(
            name: "judge",
            status: "ready",
            detail: "Remote server \(judgeID) is configured for model \(modelID).",
            actionable: "",
            category: "judge",
            metadata: [
                "remote_server_id": judgeID,
                "model_id": modelID,
                "provider_kind": server.providerKind,
            ]
        )
    }

    private func preflightCheck(
        name: String,
        _ run: () throws -> BatchRunPreflightCheck
    ) -> BatchRunPreflightCheck {
        do {
            return try run()
        } catch {
            return .init(
                name: name,
                status: "blocked",
                detail: "\(name) preflight check failed: \(error.localizedDescription)",
                actionable: "Fix the reported configuration or state and rerun preflight.",
                category: "preflight_exception"
            )
        }
    }

    private func isolatedMelixHome(config: BatchRunEffectiveConfig) -> MelixHome {
        MelixHome(environment: environment.merging([
            "MELIX_HOME": config.melixHome,
            "MELIX_RUNTIME_DIR": config.runtimeDir,
        ]) { _, new in new })
    }

    private static func defaultEvaluationDatasetID(for suiteID: String) -> String {
        if suiteID == "event_extraction" {
            return "top200.event-extraction.top20.v1"
        }
        return "\(suiteID).dev.v1"
    }
}

private struct MemoryFitReceipt {
    let payload: [String: Any]
    let targetKind: String
    let repoID: String
    let fitStatus: String
    let reasons: [String]
    let recommendedAction: String
    let totalUnifiedMemoryBytes: UInt64
    let estimatedActiveMemoryBytes: UInt64
    let estimatedDiskUsageBytes: UInt64
    let availableDiskBytes: UInt64
    let diskFitStatus: String
    let safetyThresholdFraction: Double
    let unknownFields: [String]
    let assumptions: [String]

    func benchmarkParameters(schemaVersion: String) throws -> [String: String] {
        try runParameters(schemaVersion: schemaVersion)
    }

    func runParameters(schemaVersion: String) throws -> [String: String] {
        [
            "memory_fit_schema_version": schemaVersion,
            "memory_fit_target_kind": targetKind,
            "memory_fit_repo_id": repoID,
            "memory_fit_status": fitStatus,
            "memory_fit_estimated_active_memory_bytes": String(estimatedActiveMemoryBytes),
            "memory_fit_estimated_disk_usage_bytes": String(estimatedDiskUsageBytes),
            "memory_fit_available_disk_bytes": String(availableDiskBytes),
            "memory_fit_disk_status": diskFitStatus,
            "memory_fit_total_unified_memory_bytes": String(totalUnifiedMemoryBytes),
            "memory_fit_safety_threshold_fraction": String(
                format: "%.2f",
                locale: Locale(identifier: "en_US_POSIX"),
                safetyThresholdFraction
            ),
            "memory_fit_unknown_fields": unknownFields.joined(separator: ","),
            "memory_fit_receipt_json": try compactJSONString(),
        ]
    }

    private func compactJSONString() throws -> String {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }
}

private struct BenchExportCSVResponse: Encodable {
    let jobID: String
    let outputPath: String
    let rowCount: Int
}

private struct ServerSessionListResponse: Encodable {
    let serverSessions: [MelixOperatorServerSessionState]
    let selectedServerSessionID: String

    enum CodingKeys: String, CodingKey {
        case serverSessions = "server_sessions"
        case selectedServerSessionID = "selected_server_session_id"
    }
}

private struct EvalExportResponse: Encodable {
    let jobID: String
    let outputPath: String
    let rowCount: Int
}
