import Foundation
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol
import Observation
import Security

public actor MenuBarMetricsStore {
    private var values: [String: Double] = [:]

    public init() {}

    public func record(name: String, valueMs: Double) {
        values[name] = valueMs
    }

    public func snapshot() -> [String: Double] {
        values
    }
}

public struct RuntimeCLIWorkflowFailureState: Equatable, Sendable {
    public let commandID: String
    public let surface: MelixCLIWorkflowSurface
    public let failureKind: MelixCLIWorkflowFailureKind
    public let detail: String

    public init(
        commandID: String,
        surface: MelixCLIWorkflowSurface,
        failureKind: MelixCLIWorkflowFailureKind,
        detail: String
    ) {
        self.commandID = commandID
        self.surface = surface
        self.failureKind = failureKind
        self.detail = detail
    }
}

public struct RuntimeModelRow: Identifiable, Equatable, Sendable {
    public let modelID: String
    public let kind: String
    public let features: [String]
    public let supportedTasks: [String]
    public let state: Melix_Controlplane_V1_ModelState
    public let stateText: String
    public let actionTitle: String
    public let maxContext: UInt32
    public let alias: String
    public let typeOverrideText: String
    public let memoryPolicyText: String
    public let diskStreamingModeText: String
    public let adaptiveThinkingText: String
    public let accelerationModeText: String
    public let accelerationProfileID: String
    public let toolParserFallbackText: String
    public let residencyText: String
    public let memoryText: String
    public let memoryAlertText: String
    public let cachePolicyText: String
    public let cacheSettingsText: String
    public let imageFamilyID: String
    public let imageDefaultWorkflowRole: String
    public let imageSupportsGeneration: Bool
    public let imageSupportsEdit: Bool
    /// Short human-readable runtime-mode tag: "adapter", "fused", or "" for
    /// base/unknown. Mirrors the serving signal promoted in PR #52
    /// (issue #12 Module 1) so the menubar list distinguishes adapter-backed
    /// derived models from fused derived models at a glance.
    public let runtimeModeText: String
    /// VoiceOver-friendly phrasing paired with ``runtimeModeText``. Populated
    /// alongside the tag by the same mapper helper so a future rename of the
    /// short tag can't silently cause the a11y label to fall through to a
    /// generic default — both fields travel together through the view.
    public let runtimeModeAccessibilityLabel: String
    public let runtimeCacheMissing: Bool
    public let runtimeCacheStatusText: String
    public let runtimeCacheDetailText: String
    public let runtimePathText: String
    public let registryDescriptorPathText: String
    public let restoreCommandText: String
    public let restoreRepoID: String
    public let restoreRevision: String

    public init(
        modelID: String,
        kind: String,
        features: [String] = [],
        supportedTasks: [String] = [],
        state: Melix_Controlplane_V1_ModelState,
        stateText: String,
        actionTitle: String,
        maxContext: UInt32,
        alias: String,
        typeOverrideText: String = "",
        memoryPolicyText: String,
        diskStreamingModeText: String,
        adaptiveThinkingText: String,
        accelerationModeText: String,
        accelerationProfileID: String,
        toolParserFallbackText: String = "Off",
        residencyText: String,
        memoryText: String,
        memoryAlertText: String,
        cachePolicyText: String = "",
        cacheSettingsText: String = "",
        imageFamilyID: String = "",
        imageDefaultWorkflowRole: String = "",
        imageSupportsGeneration: Bool = false,
        imageSupportsEdit: Bool = false,
        runtimeModeText: String = "",
        runtimeModeAccessibilityLabel: String = "",
        runtimeCacheMissing: Bool = false,
        runtimeCacheStatusText: String = "",
        runtimeCacheDetailText: String = "",
        runtimePathText: String = "",
        registryDescriptorPathText: String = "",
        restoreCommandText: String = "",
        restoreRepoID: String = "",
        restoreRevision: String = "main"
    ) {
        self.modelID = modelID
        self.kind = kind
        self.features = features
        self.supportedTasks = supportedTasks
        self.state = state
        self.stateText = stateText
        self.actionTitle = actionTitle
        self.maxContext = maxContext
        self.alias = alias
        self.typeOverrideText = typeOverrideText
        self.memoryPolicyText = memoryPolicyText
        self.diskStreamingModeText = diskStreamingModeText
        self.adaptiveThinkingText = adaptiveThinkingText
        self.accelerationModeText = accelerationModeText
        self.accelerationProfileID = accelerationProfileID
        self.toolParserFallbackText = toolParserFallbackText
        self.residencyText = residencyText
        self.memoryText = memoryText
        self.memoryAlertText = memoryAlertText
        self.cachePolicyText = cachePolicyText
        self.cacheSettingsText = cacheSettingsText
        self.imageFamilyID = imageFamilyID
        self.imageDefaultWorkflowRole = imageDefaultWorkflowRole
        self.imageSupportsGeneration = imageSupportsGeneration
        self.imageSupportsEdit = imageSupportsEdit
        self.runtimeModeText = runtimeModeText
        self.runtimeModeAccessibilityLabel = runtimeModeAccessibilityLabel
        self.runtimeCacheMissing = runtimeCacheMissing
        self.runtimeCacheStatusText = runtimeCacheStatusText
        self.runtimeCacheDetailText = runtimeCacheDetailText
        self.runtimePathText = runtimePathText
        self.registryDescriptorPathText = registryDescriptorPathText
        self.restoreCommandText = restoreCommandText
        self.restoreRepoID = restoreRepoID
        self.restoreRevision = restoreRevision
    }

    public var id: String {
        modelID
    }

    public var displayName: String {
        let trimmedAlias = alias.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmedAlias.isEmpty ? modelID : trimmedAlias
    }

    public var displayNameWithID: String {
        let name = displayName
        return name == modelID ? modelID : "\(name) • \(modelID)"
    }

    public var isLoaded: Bool {
        switch state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }

    public var isServeableServerModel: Bool {
        MelixServeableModelRules.isServeable(kind: kind, features: features)
    }
}

public struct RuntimeModelInfoState: Equatable, Sendable {
    public let modelID: String
    public let modelKind: String
    public let maxContext: UInt32
    public let supportedParsers: [String]
    public let supportedModalities: [String]
    public let supportedTasks: [String]
    public let backendID: String
    public let familyID: String
    public let audioInstallProfileText: String
    public let audioLanguagesText: String
    public let audioVoiceModeText: String
    public let audioOutputFormatsText: String
    public let audioSupportsInstructionsText: String
    public let audioVoiceCatalogSummaryText: String
    public let audioVoiceLocalesText: String
    public let audioDefaultLocaleText: String
    public let audioPackagedDefaultLocaleText: String
    public let audioLocalePolicyText: String
    public let audioRuntimePackStateText: String
    public let audioRuntimePackIDText: String
    public let audioModelStateText: String
    public let runtimeStatusText: String
    public let runtimePathText: String
    public let registryDescriptorPathText: String
    public let restoreCommandText: String
    public let modelPath: String
    public let modelRevision: String
    public let defaultWorkflowRole: String
    public let detectedIdentitySource: String
    public let aliasText: String
    public let typeOverrideText: String
    public let ttlSeconds: UInt32
    public let pinOnLoad: Bool
    public let memoryPolicyText: String
    public let memoryBudgetText: String
    public let diskStreamingModeText: String
    public let adaptiveThinkingText: String
    public let accelerationModeText: String
    public let accelerationProfileID: String
    public let toolParserFallbackText: String
    public let ocrPromptProfileText: String
    public let ocrSamplingProfileText: String
    public let ocrTemperatureText: String
    public let ocrTopPText: String
    public let ocrMaxTokensText: String
    public let cacheModeText: String
    public let cacheCompatibilityText: String
    public let cacheCompatibilityReasonText: String
    public let cacheDirectoryText: String
    public let cacheBlockSizeText: String
    public let cacheBudgetText: String
    public let multimodalCacheBudgetText: String
    public let cacheRootText: String
    public let initialCacheBlocksText: String
    public let generationConfigSourceText: String
    public let generationConfigTemperatureText: String
    public let generationConfigTopPText: String
    public let generationConfigMaxTokensText: String
    public let ocrStopSequencesText: String

    public init(
        modelID: String,
        modelKind: String,
        maxContext: UInt32,
        supportedParsers: [String],
        supportedModalities: [String],
        supportedTasks: [String] = [],
        backendID: String = "",
        familyID: String = "",
        audioInstallProfileText: String = "",
        audioLanguagesText: String = "",
        audioVoiceModeText: String = "",
        audioOutputFormatsText: String = "",
        audioSupportsInstructionsText: String = "",
        audioVoiceCatalogSummaryText: String = "",
        audioVoiceLocalesText: String = "",
        audioDefaultLocaleText: String = "",
        audioPackagedDefaultLocaleText: String = "",
        audioLocalePolicyText: String = "",
        audioRuntimePackStateText: String = "",
        audioRuntimePackIDText: String = "",
        audioModelStateText: String = "",
        runtimeStatusText: String = "",
        runtimePathText: String = "",
        registryDescriptorPathText: String = "",
        restoreCommandText: String = "",
        modelPath: String = "",
        modelRevision: String = "",
        defaultWorkflowRole: String = "",
        detectedIdentitySource: String = "",
        aliasText: String = "",
        typeOverrideText: String = "",
        ttlSeconds: UInt32 = 0,
        pinOnLoad: Bool = false,
        memoryPolicyText: String = "Unspecified",
        memoryBudgetText: String = "",
        diskStreamingModeText: String = "Disabled",
        adaptiveThinkingText: String = "Off",
        accelerationModeText: String = "Unspecified",
        accelerationProfileID: String = "",
        toolParserFallbackText: String = "Off",
        ocrPromptProfileText: String = "",
        ocrSamplingProfileText: String = "",
        ocrTemperatureText: String = "",
        ocrTopPText: String = "",
        ocrMaxTokensText: String = "",
        cacheModeText: String = "",
        cacheCompatibilityText: String = "",
        cacheCompatibilityReasonText: String = "",
        cacheDirectoryText: String = "",
        cacheBlockSizeText: String = "",
        cacheBudgetText: String = "",
        multimodalCacheBudgetText: String = "",
        cacheRootText: String = "",
        initialCacheBlocksText: String = "",
        generationConfigSourceText: String = "",
        generationConfigTemperatureText: String = "",
        generationConfigTopPText: String = "",
        generationConfigMaxTokensText: String = "",
        ocrStopSequencesText: String = ""
    ) {
        self.modelID = modelID
        self.modelKind = modelKind
        self.maxContext = maxContext
        self.supportedParsers = supportedParsers
        self.supportedModalities = supportedModalities
        self.supportedTasks = supportedTasks
        self.backendID = backendID
        self.familyID = familyID
        self.audioInstallProfileText = audioInstallProfileText
        self.audioLanguagesText = audioLanguagesText
        self.audioVoiceModeText = audioVoiceModeText
        self.audioOutputFormatsText = audioOutputFormatsText
        self.audioSupportsInstructionsText = audioSupportsInstructionsText
        self.audioVoiceCatalogSummaryText = audioVoiceCatalogSummaryText
        self.audioVoiceLocalesText = audioVoiceLocalesText
        self.audioDefaultLocaleText = audioDefaultLocaleText
        self.audioPackagedDefaultLocaleText = audioPackagedDefaultLocaleText
        self.audioLocalePolicyText = audioLocalePolicyText
        self.audioRuntimePackStateText = audioRuntimePackStateText
        self.audioRuntimePackIDText = audioRuntimePackIDText
        self.audioModelStateText = audioModelStateText
        self.runtimeStatusText = runtimeStatusText
        self.runtimePathText = runtimePathText
        self.registryDescriptorPathText = registryDescriptorPathText
        self.restoreCommandText = restoreCommandText
        self.modelPath = modelPath
        self.modelRevision = modelRevision
        self.defaultWorkflowRole = defaultWorkflowRole
        self.detectedIdentitySource = detectedIdentitySource
        self.aliasText = aliasText
        self.typeOverrideText = typeOverrideText
        self.ttlSeconds = ttlSeconds
        self.pinOnLoad = pinOnLoad
        self.memoryPolicyText = memoryPolicyText
        self.memoryBudgetText = memoryBudgetText
        self.diskStreamingModeText = diskStreamingModeText
        self.adaptiveThinkingText = adaptiveThinkingText
        self.accelerationModeText = accelerationModeText
        self.accelerationProfileID = accelerationProfileID
        self.toolParserFallbackText = toolParserFallbackText
        self.ocrPromptProfileText = ocrPromptProfileText
        self.ocrSamplingProfileText = ocrSamplingProfileText
        self.ocrTemperatureText = ocrTemperatureText
        self.ocrTopPText = ocrTopPText
        self.ocrMaxTokensText = ocrMaxTokensText
        self.cacheModeText = cacheModeText
        self.cacheCompatibilityText = cacheCompatibilityText
        self.cacheCompatibilityReasonText = cacheCompatibilityReasonText
        self.cacheDirectoryText = cacheDirectoryText
        self.cacheBlockSizeText = cacheBlockSizeText
        self.cacheBudgetText = cacheBudgetText
        self.multimodalCacheBudgetText = multimodalCacheBudgetText
        self.cacheRootText = cacheRootText
        self.initialCacheBlocksText = initialCacheBlocksText
        self.generationConfigSourceText = generationConfigSourceText
        self.generationConfigTemperatureText = generationConfigTemperatureText
        self.generationConfigTopPText = generationConfigTopPText
        self.generationConfigMaxTokensText = generationConfigMaxTokensText
        self.ocrStopSequencesText = ocrStopSequencesText
    }
}

public struct RuntimeHubModelSearchResultState: Identifiable, Equatable, Sendable {
    public let id: String
    public let repoID: String
    public let author: String
    public let modelName: String
    public let pipelineTag: String
    public let compatibilityText: String
    public let downloadsText: String
    public let likesText: String
    public let localFitStatus: String
    public let runSuitabilityText: String
    public let localFitReasons: [String]
    public let estimatedArtifactBytesText: String
    public let estimatedResidentBytesText: String
    public let parameterCountText: String
    public let quantizationSummary: String
    public let gated: Bool
    public let recommendedAction: String

    public init(
        repoID: String,
        author: String,
        modelName: String,
        pipelineTag: String,
        compatibilityText: String,
        downloadsText: String,
        likesText: String,
        localFitStatus: String,
        runSuitabilityText: String,
        localFitReasons: [String],
        estimatedArtifactBytesText: String,
        estimatedResidentBytesText: String,
        parameterCountText: String,
        quantizationSummary: String,
        gated: Bool,
        recommendedAction: String
    ) {
        self.id = repoID
        self.repoID = repoID
        self.author = author
        self.modelName = modelName
        self.pipelineTag = pipelineTag
        self.compatibilityText = compatibilityText
        self.downloadsText = downloadsText
        self.likesText = likesText
        self.localFitStatus = localFitStatus
        self.runSuitabilityText = runSuitabilityText
        self.localFitReasons = localFitReasons
        self.estimatedArtifactBytesText = estimatedArtifactBytesText
        self.estimatedResidentBytesText = estimatedResidentBytesText
        self.parameterCountText = parameterCountText
        self.quantizationSummary = quantizationSummary
        self.gated = gated
        self.recommendedAction = recommendedAction
    }

    public var canDownload: Bool {
        localFitStatus.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() != "blocked"
    }

    public var sizeText: String {
        if estimatedArtifactBytesText == "0 B" && estimatedResidentBytesText == "0 B" {
            return ""
        }
        if estimatedResidentBytesText == "0 B" {
            return "\(estimatedArtifactBytesText) artifact"
        }
        if estimatedArtifactBytesText == "0 B" {
            return "\(estimatedResidentBytesText) resident"
        }
        return "\(estimatedArtifactBytesText) artifact • \(estimatedResidentBytesText) resident"
    }
}

public struct RuntimeHubModelCardState: Equatable, Sendable {
    public let repoID: String
    public let author: String
    public let modelName: String
    public let summary: String
    public let pipelineTag: String
    public let compatibilityText: String
    public let tags: [String]
    public let baseModels: [String]
    public let localFitStatus: String
    public let runSuitabilityText: String
    public let localFitReasons: [String]
    public let estimatedArtifactBytesText: String
    public let estimatedResidentBytesText: String
    public let parameterCountText: String
    public let quantizationSummary: String
    public let gated: Bool
    public let recommendedAction: String

    public init(
        repoID: String,
        author: String,
        modelName: String,
        summary: String,
        pipelineTag: String,
        compatibilityText: String,
        tags: [String],
        baseModels: [String],
        localFitStatus: String,
        runSuitabilityText: String,
        localFitReasons: [String],
        estimatedArtifactBytesText: String,
        estimatedResidentBytesText: String,
        parameterCountText: String,
        quantizationSummary: String,
        gated: Bool,
        recommendedAction: String
    ) {
        self.repoID = repoID
        self.author = author
        self.modelName = modelName
        self.summary = RichOutputSanitizer.sanitized(summary)
        self.pipelineTag = pipelineTag
        self.compatibilityText = compatibilityText
        self.tags = tags
        self.baseModels = baseModels
        self.localFitStatus = localFitStatus
        self.runSuitabilityText = runSuitabilityText
        self.localFitReasons = localFitReasons
        self.estimatedArtifactBytesText = estimatedArtifactBytesText
        self.estimatedResidentBytesText = estimatedResidentBytesText
        self.parameterCountText = parameterCountText
        self.quantizationSummary = quantizationSummary
        self.gated = gated
        self.recommendedAction = recommendedAction
    }

    public var canDownload: Bool {
        localFitStatus.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() != "blocked"
    }
}

public struct RuntimeRegistryEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let subtitleText: String
    public let sourceText: String
    public let statusText: String
    public let runSuitabilityText: String
    public let sizeText: String
    public let taskText: String
    public let repoID: String
    public let canInspect: Bool
    public let canDownload: Bool

    public init(
        id: String,
        title: String,
        subtitleText: String,
        sourceText: String,
        statusText: String,
        runSuitabilityText: String,
        sizeText: String,
        taskText: String,
        repoID: String = "",
        canInspect: Bool = false,
        canDownload: Bool = false
    ) {
        self.id = id
        self.title = title
        self.subtitleText = subtitleText
        self.sourceText = sourceText
        self.statusText = statusText
        self.runSuitabilityText = runSuitabilityText
        self.sizeText = sizeText
        self.taskText = taskText
        self.repoID = repoID
        self.canInspect = canInspect
        self.canDownload = canDownload
    }
}

public struct RuntimeModelOperationState: Equatable, Sendable {
    public let modelID: String
    public let operation: String
    public let jobID: String
    public let stage: String
    public let pct: Float
    public let outputPath: String
    public let manifestJson: String
    public let quantProfileID: String
    public let artifactKind: String
    public let manifestPath: String
    public let artifactBytes: UInt64
    public let artifactRuntime: String
    public let servingCompatible: Bool
    public let smokeTestRequested: Bool
    public let smokeTestPassed: Bool
    public let calibrationSampleCount: Int
    public let targetRepo: String
    public let sourceArtifactKind: String
    public let conversionTargetFormat: String
    public let linkedQuantizationProfileID: String
}

public enum RuntimeLoraWorkflowPhase: String, Equatable, Sendable {
    case running
    case succeeded
    case failed

    public var badgeTitle: String {
        switch self {
        case .running:
            return "Running"
        case .succeeded:
            return "Completed"
        case .failed:
            return "Needs Attention"
        }
    }

    public var symbolName: String {
        switch self {
        case .running:
            return "clock"
        case .succeeded:
            return "checkmark.circle.fill"
        case .failed:
            return "exclamationmark.triangle.fill"
        }
    }
}

public struct RuntimeLoraWorkflowStatusState: Equatable, Sendable {
    public let operation: String
    public let phase: RuntimeLoraWorkflowPhase
    public let title: String
    public let detail: String
}

public struct RuntimeDownloadQueueEntryState: Codable, Identifiable, Equatable, Sendable {
    public let jobID: String
    public let sourceModel: String
    public let status: String
    public let stage: String
    public let pct: Double
    public let outputDir: String
    public let outputPath: String
    public let partialPath: String
    public let statePath: String
    public let selectedMirror: String
    public let downloadedBytes: Int
    public let totalBytes: Int
    public let resumeUsed: Bool
    public let resumeFromBytes: Int
    public let retryCount: Int
    public let stallDetectionCount: Int
    public let stallReason: String
    public let resumeReady: Bool

    public var id: String {
        jobID
    }

    public var statusText: String {
        switch normalizedStatus {
        case "completed":
            "Completed"
        case "running":
            "Running"
        case "retrying":
            "Retrying"
        case "stalled":
            "Stalled"
        case "failed":
            "Failed"
        default:
            normalizedStatus.isEmpty ? "Unknown" : normalizedStatus.capitalized
        }
    }

    public var progressText: String {
        let percentText = "\(Int((pct * 100).rounded()))%"
        guard totalBytes > 0 else {
            return percentText
        }
        return "\(Self.formatBytes(downloadedBytes)) / \(Self.formatBytes(totalBytes)) • \(percentText)"
    }

    public var transferDetailText: String {
        var parts: [String] = []
        if !selectedMirror.isEmpty {
            parts.append(selectedMirror)
        }
        if retryCount > 0 {
            parts.append("retries \(retryCount)")
        }
        if stallDetectionCount > 0 {
            parts.append("stall detections \(stallDetectionCount)")
        }
        if !stallReason.isEmpty {
            parts.append(stallReason.replacingOccurrences(of: "_", with: " "))
        }
        if resumeUsed, resumeFromBytes > 0 {
            parts.append("resumed from \(Self.formatBytes(resumeFromBytes))")
        }
        return parts.joined(separator: " • ")
    }

    public var resumeActionTitle: String {
        "Resume Download"
    }

    public var isActive: Bool {
        ["running", "retrying"].contains(normalizedStatus)
    }

    private var normalizedStatus: String {
        status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private static func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useBytes, .useKB, .useMB, .useGB]
        formatter.countStyle = .binary
        formatter.includesUnit = true
        formatter.isAdaptive = true
        return formatter.string(fromByteCount: Int64(max(bytes, 0)))
    }

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case sourceModel = "source_model"
        case status
        case stage
        case pct
        case outputDir = "output_dir"
        case outputPath = "output_path"
        case partialPath = "partial_path"
        case statePath = "state_path"
        case selectedMirror = "selected_mirror"
        case downloadedBytes = "downloaded_bytes"
        case totalBytes = "total_bytes"
        case resumeUsed = "resume_used"
        case resumeFromBytes = "resume_from_bytes"
        case retryCount = "retry_count"
        case stallDetectionCount = "stall_detection_count"
        case stallReason = "stall_reason"
        case resumeReady = "resume_ready"
    }
}

public enum RuntimeAudioSetupActionKind: String, Equatable, Sendable {
    case installRuntime = "install_runtime"
    case downloadModel = "download_model"
}

public struct RuntimeAudioSetupActionState: Identifiable, Equatable, Sendable {
    public let modelID: String
    public let alias: String
    public let detail: String
    public let actionTitle: String
    public let kind: RuntimeAudioSetupActionKind

    public var id: String {
        "\(modelID):\(kind.rawValue)"
    }
}

public struct RuntimeAudioSetupPromptState: Identifiable, Equatable, Sendable {
    public let modelID: String
    public let alias: String
    public let detail: String
    public let primaryActionTitle: String
    public let kind: RuntimeAudioSetupActionKind

    public var id: String {
        "\(modelID):\(kind.rawValue)"
    }

    public var title: String {
        "Audio Support Required"
    }

    public var action: RuntimeAudioSetupActionState {
        RuntimeAudioSetupActionState(
            modelID: modelID,
            alias: alias,
            detail: detail,
            actionTitle: primaryActionTitle,
            kind: kind
        )
    }

    public init(action: RuntimeAudioSetupActionState) {
        self.modelID = action.modelID
        self.alias = action.alias
        self.detail = action.detail
        self.primaryActionTitle = action.actionTitle
        self.kind = action.kind
    }
}

public struct RuntimeDoctorFindingState: Equatable, Sendable, Identifiable {
    public let code: String
    public let severityText: String
    public let summary: String
    public let detail: String

    public var id: String {
        code
    }
}

public struct RuntimeDoctorReportState: Equatable, Sendable {
    public let markdown: String
    public let healthStatusText: String
    public let findings: [RuntimeDoctorFindingState]

    public init(
        markdown: String,
        healthStatusText: String = "",
        findings: [RuntimeDoctorFindingState] = []
    ) {
        self.markdown = RichOutputSanitizer.sanitized(markdown)
        self.healthStatusText = healthStatusText
        self.findings = findings
    }
}

public enum RuntimeBenchmarkTargetMode: String, CaseIterable, Identifiable, Sendable {
    case catalogModel = "catalog_model"
    case huggingFaceRepo = "hf_repo"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .catalogModel:
            return "Catalog Model"
        case .huggingFaceRepo:
            return "Hugging Face Repo"
        }
    }
}

public enum RuntimeImageWorkflowRole: String, CaseIterable, Sendable {
    case generate
    case edit
}

public enum RuntimeImageEditMode: String, CaseIterable, Identifiable, Sendable {
    case edit
    case variation
    case iterate

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .edit:
            return "Edit"
        case .variation:
            return "Variation"
        case .iterate:
            return "Iterate"
        }
    }

    var controlPlaneMode: ControlPlaneImageEditRequest.Mode {
        switch self {
        case .edit:
            return .edit
        case .variation:
            return .variation
        case .iterate:
            return .iterate
        }
    }
}

public enum RuntimeBenchmarkPresentationMode: String, CaseIterable, Identifiable, Sendable {
    case standard = "standard"
    case matrix = "matrix"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .standard:
            return "Standard"
        case .matrix:
            return "Matrix"
        }
    }
}

public enum RuntimeDiagnosticsStagePreference: String, Sendable {
    case benchmark
    case matrix
    case evaluation
}

public enum RuntimeBenchmarkMatrixLoadBudgetMode: String, CaseIterable, Identifiable, Sendable {
    case requests = "requests"
    case durationSeconds = "duration_seconds"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .requests:
            return "Requests"
        case .durationSeconds:
            return "Duration"
        }
    }
}

public enum RuntimeLoraDatasetSourceKind: String, CaseIterable, Identifiable, Sendable {
    case localPackage = "local_package"
    case huggingFaceDataset = "hf_dataset"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .localPackage:
            return "Local Package"
        case .huggingFaceDataset:
            return "Hugging Face"
        }
    }
}

public enum RuntimeLoraTrainingMode: String, CaseIterable, Identifiable, Sendable {
    case lora = "lora"
    case qlora = "qlora"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .lora:
            return "LoRA"
        case .qlora:
            return "QLoRA"
        }
    }
}

public enum RuntimeLoraTrainingPreset: String, CaseIterable, Identifiable, Sendable {
    case custom = ""
    case debugFast = "debug_fast"
    case balancedAdapter = "balanced_adapter"
    case qualityAdapter = "quality_adapter"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .custom:
            return "Custom"
        case .debugFast:
            return "Debug Fast"
        case .balancedAdapter:
            return "Balanced Adapter"
        case .qualityAdapter:
            return "Quality Adapter"
        }
    }

    public var isNamedPreset: Bool {
        self != .custom
    }
}

public enum RuntimeLoraActivationMode: String, CaseIterable, Identifiable, Sendable {
    case fusedDerivedModel = "fused_derived_model"
    case adapterBackedRuntime = "adapter_backed_runtime"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .fusedDerivedModel:
            return "Fused Derived Model"
        case .adapterBackedRuntime:
            return "Adapter-backed Runtime"
        }
    }
}

public enum RuntimeEvaluationMode: String, CaseIterable, Identifiable, Sendable {
    case standard = "standard"
    case compare = "compare"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .standard:
            return "Standard"
        case .compare:
            return "Compare"
        }
    }
}

public enum RuntimeEvaluationDatasetSourceKind: String, CaseIterable, Identifiable, Sendable {
    case builtinPackage = "builtin_package"
    case localCSV = "local_csv"
    case localJSONL = "local_jsonl"
    case huggingFaceDataset = "hf_dataset"

    public var id: String {
        rawValue
    }

    public var title: String {
        switch self {
        case .builtinPackage:
            return "Built-in Package"
        case .localCSV:
            return "Local CSV"
        case .localJSONL:
            return "Local JSONL"
        case .huggingFaceDataset:
            return "Hugging Face Dataset"
        }
    }
}

public struct RuntimeAdapterPackageState: Identifiable, Equatable, Sendable {
    public let id: String
    public let adapterName: String
    public let sourceModel: String
    public let datasetURI: String
    public let statusText: String
    public let activationStatusText: String
    public let exportabilityText: String
    public let publishedStateText: String
    public let outputPath: String
    public let derivedModelID: String
    public let derivedModelPath: String
    public let targetRepo: String
    public let publishedRepo: String
    public let responseOnlyEnabled: Bool
    public let gradientCheckpointingEnabled: Bool
    public let checkpointCount: Int
    public let resumeReady: Bool
    public let tokensPerSecond: Double
    public let peakMemoryGB: Double
    public let trainingDurationText: String
    public let activationDurationText: String
    public let publishDurationText: String

    public var experimentSummaryText: String {
        runtimeExperimentSummaryText(checkpointCount: checkpointCount, resumeReady: resumeReady)
    }

    public var performanceSummaryText: String {
        runtimeTrainingPerformanceText(tokensPerSecond: tokensPerSecond, peakMemoryGB: peakMemoryGB)
    }
}

public struct RuntimeTrainingHistoryEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let jobID: String
    public let modelID: String
    public let adapterName: String
    public let datasetURI: String
    public let statusText: String
    public let stageText: String
    public let outputPath: String
    public let targetRepo: String
    public let checkpointCount: Int
    public let resumeReady: Bool
    public let tokensPerSecond: Double
    public let peakMemoryGB: Double

    public var experimentSummaryText: String {
        runtimeExperimentSummaryText(checkpointCount: checkpointCount, resumeReady: resumeReady)
    }

    public var performanceSummaryText: String {
        runtimeTrainingPerformanceText(tokensPerSecond: tokensPerSecond, peakMemoryGB: peakMemoryGB)
    }
}

public struct RuntimeLoraCheckpointLineageEntry: Identifiable, Equatable, Sendable {
    public let id: String
    public let runID: String
    public let checkpointCount: Int
    public let resumeReady: Bool

    public init(runID: String, checkpointCount: Int, resumeReady: Bool) {
        self.id = runID
        self.runID = runID
        self.checkpointCount = checkpointCount
        self.resumeReady = resumeReady
    }
}

public struct RuntimeLoraExperimentGroupState: Identifiable, Equatable, Sendable {
    public let id: String
    public let groupID: String
    public let title: String
    public let adapterName: String
    public let sourceModel: String
    public let runCount: Int
    public let latestPresetTitle: String
    public let latestTokensPerSecond: Double
    public let latestPeakMemoryGB: Double
    public let latestCheckpointCount: Int
    public let latestResumeReady: Bool
    public let bestLoss: Double
    public let recommendedManifestPath: String
    public let bestRunID: String
    public let resumeReadyRunIDs: [String]
    public let checkpointLineage: [RuntimeLoraCheckpointLineageEntry]

    public var experimentSummaryText: String {
        runtimeExperimentSummaryText(
            checkpointCount: latestCheckpointCount,
            resumeReady: latestResumeReady
        )
    }

    public var performanceSummaryText: String {
        runtimeTrainingPerformanceText(
            tokensPerSecond: latestTokensPerSecond,
            peakMemoryGB: latestPeakMemoryGB
        )
    }

    public var resumeReadySummaryText: String {
        "\(resumeReadyRunIDs.count) of \(runCount) runs resume-ready"
    }
}

public struct RuntimeRegistryRootState: Identifiable, Equatable, Sendable {
    public let id: String
    public let rootPath: String
    public let rootOrder: Int
    public let accessible: Bool
    public let errorCode: String
    public let errorMessage: String
    public let discoveredModelIDs: [String]

    public var statusText: String {
        if accessible {
            return "Accessible"
        }
        if errorCode.isEmpty {
            return "Unavailable"
        }
        let normalized = errorCode.replacingOccurrences(of: "_", with: " ")
        guard let first = normalized.first else {
            return "Unavailable"
        }
        return String(first).uppercased() + normalized.dropFirst()
    }

    public var detailText: String {
        let discoveredCount = discoveredModelIDs.count
        let discoveredSummary = discoveredCount == 1 ? "1 model" : "\(discoveredCount) models"
        if errorMessage.isEmpty {
            return discoveredSummary
        }
        return "\(discoveredSummary) • \(errorMessage)"
    }
}

public struct RuntimeBenchMetricState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let value: String

    public init(name: String, value: String) {
        let sanitizedName = RichOutputSanitizer.sanitized(name)
        self.id = sanitizedName
        self.name = sanitizedName
        self.value = RichOutputSanitizer.sanitized(value)
    }
}

public struct RuntimeBenchReportState: Equatable, Sendable {
    public let reportPath: String
    public let markdown: String
    public let metrics: [RuntimeBenchMetricState]

    public init(reportPath: String, markdown: String, metrics: [RuntimeBenchMetricState]) {
        self.reportPath = reportPath
        self.markdown = RichOutputSanitizer.sanitized(markdown)
        self.metrics = metrics
    }
}

public struct RuntimeBenchmarkSuiteOptionState: Identifiable, Equatable, Sendable {
    public let id: String
    public let taskKind: String
    public let title: String
    public let datasetPath: String
    public let datasetName: String
    public let datasetSplit: String
    public let defaultSampleSize: Int
    public let defaultBatchFactor: Int

    public var datasetLabel: String {
        "\(datasetPath) • \(datasetSplit)"
    }

    public var defaultsText: String {
        "default \(defaultSampleSize)x sample • \(defaultBatchFactor)x batch"
    }
}

public struct RuntimeBenchmarkHistoryEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let taskTitle: String
    public let sourceRepo: String
    public let suiteID: String
    public let suiteTitle: String
    public let datasetLabel: String
    public let sampleSizeText: String
    public let batchFactorText: String
    public let statusText: String
    public let metricCountText: String
    public let createdAtText: String
    public let createdAtUnixMS: Int64
    public let reportPath: String
}

public struct RuntimeBenchmarkMetricCardState: Identifiable, Equatable, Sendable {
    public let id: String
    public let taskKind: String
    public let suiteTitle: String
    public let metricName: String
    public let metricLabel: String
    public let value: Double
    public let valueText: String
    public let unit: String
}

public struct RuntimeBenchmarkChartPointState: Identifiable, Equatable, Sendable {
    public let id: String
    public let jobID: String
    public let taskKind: String
    public let suiteTitle: String
    public let metricName: String
    public let value: Double
    public let unit: String
    public let createdAtLabel: String
    public let createdAtUnixMS: Int64
}

public struct RuntimeBenchmarkCSVExportState: Equatable, Sendable {
    public let outputPath: String
    public let rowCount: Int
}

public struct RuntimeBenchmarkMatrixHistoryEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let taskTitle: String
    public let sourceRepo: String
    public let suiteSummary: String
    public let cellCountText: String
    public let loadBudgetText: String
    public let statusText: String
    public let createdAtText: String
    public let createdAtUnixMS: Int64
}

public struct RuntimeBenchmarkMatrixSummaryCardState: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let valueText: String
    public let detail: String
}

public struct RuntimeBenchmarkMatrixSummaryRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let suiteTitle: String
    public let configurationSummary: String
    public let latencyText: String
    public let throughputText: String
    public let successRateText: String
    public let peakMemoryText: String
    public let createdAtText: String
    public let contextLength: Int
    public let batchSize: Int
    public let concurrencyLevel: Int
    public let ttftMeanMS: Double
    public let throughputTokensPerSecond: Double
}

public struct RuntimeBenchmarkMatrixChartPointState: Identifiable, Equatable, Sendable {
    public let id: String
    public let seriesTitle: String
    public let xLabel: String
    public let xValue: Int
    public let yValue: Double
    public let unit: String
}

public struct RuntimeBenchmarkMatrixExportState: Equatable, Sendable {
    public let outputPath: String
    public let rowCount: Int
    public let formatTitle: String
}

public struct RuntimeEvaluationSuiteOptionState: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let datasetID: String
    public let scoreLabel: String
    public let defaultSampleSize: Int
    public let defaultBatchFactor: Int

    public var defaultsText: String {
        "default \(defaultSampleSize)x sample • \(defaultBatchFactor)x batch"
    }
}

public struct RuntimeEvaluationHistoryEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let jobID: String
    public let modelID: String
    public let taskKind: String
    public let taskTitle: String
    public let sourceRepo: String
    public let suiteID: String
    public let suiteTitle: String
    public let datasetID: String
    public let sampleSizeText: String
    public let scoringModeText: String
    public let statusText: String
    public let metricCountText: String
    public let createdAtText: String
    public let createdAtUnixMS: Int64
    public let reportPath: String
}

public struct RuntimeEvaluationMetricCardState: Identifiable, Equatable, Sendable {
    public let id: String
    public let suiteTitle: String
    public let metricName: String
    public let metricLabel: String
    public let value: Double
    public let valueText: String
    public let unit: String
    public let verdictText: String
    public let thresholdText: String
    public let bootstrapCIText: String
    public let analyticalCIText: String
}

public struct RuntimeEvaluationSamplePreviewState: Identifiable, Equatable, Sendable {
    public let id: String
    public let sampleID: String
    public let inputText: String
    public let target: String
    public let extractedResult: String
    public let rawResponse: String
    public let typedScoreText: String
    public let statusText: String
    public let timeText: String
    public let categoryLabel: String
    public let subjectLabel: String

    public init(
        id: String,
        sampleID: String,
        inputText: String,
        target: String,
        extractedResult: String,
        rawResponse: String,
        typedScoreText: String,
        statusText: String,
        timeText: String,
        categoryLabel: String = "",
        subjectLabel: String = ""
    ) {
        self.id = id
        self.sampleID = RichOutputSanitizer.sanitized(sampleID)
        self.inputText = RichOutputSanitizer.sanitized(inputText)
        self.target = RichOutputSanitizer.sanitized(target)
        self.extractedResult = RichOutputSanitizer.sanitized(extractedResult)
        self.rawResponse = RichOutputSanitizer.sanitized(rawResponse)
        self.typedScoreText = RichOutputSanitizer.sanitized(typedScoreText)
        self.statusText = RichOutputSanitizer.sanitized(statusText)
        self.timeText = RichOutputSanitizer.sanitized(timeText)
        self.categoryLabel = RichOutputSanitizer.sanitized(categoryLabel)
        self.subjectLabel = RichOutputSanitizer.sanitized(subjectLabel)
    }
}

public struct RuntimeEvaluationExportState: Equatable, Sendable {
    public let outputPath: String
    public let rowCount: Int
    public let formatTitle: String
}

public struct DesktopChatTranscriptEntry: Identifiable, Equatable, Sendable {
    public enum Kind: String, Sendable {
        case user
        case assistant
        case reasoning
        case tool
        case error
    }

    public let id: String
    public let kind: Kind
    public let title: String
    public let body: String
    public let detail: String

    public init(id: String, kind: Kind, title: String, body: String, detail: String) {
        self.id = id
        self.kind = kind
        self.title = title
        self.body = body
        self.detail = detail
    }
}

public struct DesktopChatCapabilityRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let modelID: String
    public let detail: String
    public let isReady: Bool

    public var shortTitle: String {
        switch id {
        case "text":
            return "Text"
        case "ocr":
            return "OCR"
        case "vlm":
            return "Vision"
        case "transcription":
            return "Audio In"
        case "speech":
            return "Audio Out"
        default:
            return title
        }
    }

    public var systemImageName: String {
        switch id {
        case "text":
            return "text.bubble"
        case "ocr":
            return "doc.text.viewfinder"
        case "vlm":
            return "eye"
        case "transcription":
            return "waveform.badge.mic"
        case "speech":
            return "speaker.wave.2"
        default:
            return "square.grid.2x2"
        }
    }
}

private struct GatewayAccessProjection: Equatable, Sendable {
    let authMode: DesktopServerAuthMode
    let authTokenHint: String
    let sharedAccessState: DesktopSharedAccessState
    let accessKeyCount: Int
    let accessKeyHints: [String]
    let activeAuthSessionCount: Int
    let rememberedAuthSessionCount: Int
    let expiredRememberedSessionCount: Int
    let authSessionRetentionSeconds: Int
    let lastAuthSessionSignOutLatencyMs: Double
}

private struct GatewayConfigProjection: Equatable, Sendable {
    let host: String
    let port: Int
    let effectiveHost: String
    let effectivePort: Int
    let servedModelID: String
    let rateLimitPerMinute: Int
    let timeoutSeconds: Int
    let sourceText: String
    let activeBinding: Bool
    let requiresRestart: Bool
}

private struct ServingDefaultsProjection: Equatable, Sendable {
    let temperature: Double
    let topP: Double
    let maxTokens: Int
    let streamIntervalTokens: Int
    let maxConcurrentRequests: Int
    let concurrentProcessingEnabled: Bool
    let prefillBatchSize: Int
    let completionBatchSize: Int
    let accelerationMode: String
    let draftModelID: String
    let numDraftTokens: Int
    let effectiveTemperature: Double
    let effectiveTopP: Double
    let effectiveMaxTokens: Int
    let effectiveStreamIntervalTokens: Int
    let effectiveMaxConcurrentRequests: Int
    let effectiveConcurrentProcessingEnabled: Bool
    let effectivePrefillBatchSize: Int
    let effectiveCompletionBatchSize: Int
    let effectiveAccelerationMode: String
    let effectiveDraftModelID: String
    let effectiveNumDraftTokens: Int
    let sourceText: String
    let modelOverrideApplied: Bool
    let updatedAtUnixMS: Int64
}

private struct ImageDefaultsProjection: Equatable, Sendable {
    let generateModelID: String
    let editModelID: String
    let size: String
    let steps: Int
    let guidance: Double
    let strength: Double
    let negativePrompt: String
    let effectiveGenerateModelID: String
    let effectiveEditModelID: String
    let effectiveSize: String
    let effectiveSteps: Int
    let effectiveGuidance: Double
    let effectiveStrength: Double
    let effectiveNegativePrompt: String
    let requestTimeoutSeconds: UInt32
    let sourceText: String
    let updatedAtUnixMS: Int64
}

private struct ChatPresentationFragment: Sendable {
    let kind: DesktopChatTranscriptEntry.Kind
    let entryID: String
    let title: String
    let detail: String
    var remainingText: String
    let firstQueuedAt: Date
}

private enum RuntimeLoraWorkflowOperation: String, Sendable {
    case trainLoRA = "train_lora"
    case activateAdapter = "activate_adapter"
    case publishAdapter = "upload"
    case removeDerivedModel = "remove_derived_model"

    var runningTitle: String {
        switch self {
        case .trainLoRA:
            return "Training LoRA"
        case .activateAdapter:
            return "Activating Adapter"
        case .publishAdapter:
            return "Publishing Adapter"
        case .removeDerivedModel:
            return "Removing Derived Model"
        }
    }

    var successTitle: String {
        switch self {
        case .trainLoRA:
            return "LoRA Training Finished"
        case .activateAdapter:
            return "Adapter Activated"
        case .publishAdapter:
            return "Adapter Published"
        case .removeDerivedModel:
            return "Derived Model Removed"
        }
    }

    var failureTitle: String {
        switch self {
        case .trainLoRA:
            return "LoRA Training Failed"
        case .activateAdapter:
            return "Activation Failed"
        case .publishAdapter:
            return "Publish Failed"
        case .removeDerivedModel:
            return "Remove Failed"
        }
    }
}

@MainActor
@Observable
public final class RuntimeViewModel {
    public private(set) var statusTitle = "Melix Starting"
    public private(set) var serverStateText = "Starting"
    public private(set) var connectionStateText = "Connecting"
    public private(set) var connectionDetailText = "Awaiting handshake"
    public var selectedSurface: DesktopSurface = .chat
    public var selectedToolSection: DesktopToolSection = .modelsLibrary
    public private(set) var desktopPaneVisibility = DesktopPaneVisibilityState.defaultStates
    public private(set) var models: [RuntimeModelRow] = []
    public private(set) var serverSessions: [DesktopServerSessionState] = []
    public private(set) var remoteServers: [RemoteServer] = []
    public private(set) var chatSessions: [DesktopChatSessionState] = []
    public private(set) var lastError: String?
    public private(set) var lastCLIWorkflowFailure: RuntimeCLIWorkflowFailureState?
    public private(set) var productUpdateSummary: String?
    public private(set) var productUpdateDetail: String?
    public private(set) var productUpdateIsAvailable = false
    public private(set) var productUpdateCheckSucceeded = true
    public private(set) var protocolVersion = "melix.controlplane.v1"
    public private(set) var serverVersion = "0.1.0"
    public private(set) var daemonInstanceID = ""
    public private(set) var features: [String] = []
    public private(set) var selectedModelInfo: RuntimeModelInfoState?
    public private(set) var modelHubSearchResults: [RuntimeHubModelSearchResultState] = []
    public private(set) var selectedHubModelCard: RuntimeHubModelCardState?
    public private(set) var modelHubNextCursor = ""
    public private(set) var modelHubTokenHint = ""
    public private(set) var lastModelOperation: RuntimeModelOperationState?
    public private(set) var loraWorkflowStatus: RuntimeLoraWorkflowStatusState?
    public private(set) var downloadQueue: [RuntimeDownloadQueueEntryState] = []
    public var modelRegistryEntries: [RuntimeRegistryEntryState] {
        Self.makeModelRegistryEntries(
            models: models,
            downloadQueue: downloadQueue,
            hubResults: modelHubSearchResults
        )
    }
    public private(set) var lastDoctorReport: RuntimeDoctorReportState?
    public private(set) var lastBenchReport: RuntimeBenchReportState?
    public private(set) var benchmarkHistory: [RuntimeBenchmarkHistoryEntryState] = []
    public private(set) var benchmarkMetricCards: [RuntimeBenchmarkMetricCardState] = []
    public private(set) var benchmarkChartPoints: [RuntimeBenchmarkChartPointState] = []
    public private(set) var benchmarkMetricOptions: [String] = []
    public private(set) var lastBenchmarkCSVExport: RuntimeBenchmarkCSVExportState?
    public private(set) var benchmarkMatrixHistory: [RuntimeBenchmarkMatrixHistoryEntryState] = []
    public private(set) var benchmarkMatrixSummaryCards: [RuntimeBenchmarkMatrixSummaryCardState] = []
    public private(set) var benchmarkMatrixSummaryRows: [RuntimeBenchmarkMatrixSummaryRowState] = []
    public private(set) var benchmarkMatrixContextChartPoints: [RuntimeBenchmarkMatrixChartPointState] = []
    public private(set) var benchmarkMatrixThroughputChartPoints: [RuntimeBenchmarkMatrixChartPointState] = []
    public private(set) var lastBenchmarkMatrixExport: RuntimeBenchmarkMatrixExportState?
    public private(set) var evaluationPrompts: [EvaluationPrompt] = []
    public private(set) var evaluationHistory: [RuntimeEvaluationHistoryEntryState] = []
    public private(set) var evaluationMetricCards: [RuntimeEvaluationMetricCardState] = []
    public private(set) var evaluationSamplePreview: [RuntimeEvaluationSamplePreviewState] = []
    public private(set) var lastEvaluationExport: RuntimeEvaluationExportState?
    public private(set) var adapterPackages: [RuntimeAdapterPackageState] = []
    public private(set) var trainingHistory: [RuntimeTrainingHistoryEntryState] = []
    public private(set) var loraExperimentGroups: [RuntimeLoraExperimentGroupState] = []
    public private(set) var registryRoots: [RuntimeRegistryRootState] = []
    public private(set) var registryConfiguredRootPaths: [String] = []
    public private(set) var registryHasConfiguredRootOverride = false
    public private(set) var registryScannedAtText = "Never"
    public private(set) var chatTranscript: [DesktopChatTranscriptEntry] = []
    public private(set) var chatCapabilities: [DesktopChatCapabilityRow] = []
    public private(set) var agentIntegrationExports: [AgentIntegrationExport] = []
    public private(set) var pendingAudioSetupPrompt: RuntimeAudioSetupPromptState?
    public private(set) var chatStatusText = "Idle"
    public private(set) var lastChatUsageText = ""
    public private(set) var isChatStreaming = false
    public private(set) var lastChatRequestID = ""
    public private(set) var imageJobs: [Melix_Controlplane_V1_ImageJobSummary] = []
    public private(set) var imageStatusText = "Idle"
    public private(set) var selectedImageJobID = ""
    public private(set) var imageRequestTimeoutSeconds: UInt32 = 1_800

    public var isLoraWorkflowActionInProgress: Bool {
        loraWorkflowStatus?.phase == .running
    }
    public private(set) var selectedAgentIntegrationTarget: AgentIntegrationExportTarget = .openAICompatible
    public var selectedRemoteServerID = ""
    public var remoteServerIDDraft = "sub2api"
    public var remoteServerTitleDraft = "sub2api"
    public var remoteServerProviderPresetDraft: RemoteServerProviderPreset = .custom
    public var remoteServerProviderKindDraft = "openai-compatible"
    public var remoteServerBaseURLDraft = "" {
        didSet {
            if let fixedBaseURL = remoteServerProviderPresetDraft.fixedBaseURL,
               remoteServerBaseURLDraft != fixedBaseURL
            {
                remoteServerBaseURLDraft = fixedBaseURL
            }
        }
    }
    public var remoteServerDefaultModelIDDraft = "gemini-2.5-flash"
    public var remoteServerAPIKeyDraft = ""
    public var remoteServerTimeoutSecondsDraft: UInt32 = 120
    public var remoteServerRateLimitPerMinuteDraft: UInt32 = 0
    public var chatComposerText = ""
    public var selectedChatModelID = "melix-dev-text"
    public var selectedLoraModelID = "melix-dev-text"
    public var modelHubSearchQuery = ""
    public var modelHubSearchMLXOnly = true
    public var modelHubSelectedRevision = "main"
    public var modelHubTokenDraft = ""
    public var modelSettingsAliasDraft = ""
    public var modelSettingsTypeOverrideDraft = ""
    public var modelSettingsTTLDraft = ""
    public var modelSettingsPinOnLoadDraft = false
    public var modelSettingsMemoryPolicyDraft = "evictable"
    public var modelSettingsMemoryBudgetDraft = ""
    public var modelSettingsDiskStreamingModeDraft = "disabled"
    public var modelSettingsCacheModeDraft = "tiered"
    public var modelSettingsCacheMemoryBudgetDraft = ""
    public var modelSettingsCacheMemoryBudgetPctDraft = ""
    public var modelSettingsCacheBlockSizeTokensDraft = ""
    public var modelSettingsCacheDirectoryDraft = ""
    public var modelSettingsMultimodalCacheBudgetDraft = ""
    public var modelSettingsAccelerationModeDraft = "baseline"
    public var modelSettingsAccelerationProfileIDDraft = ""
    public var modelSettingsAdaptiveThinkingModeDraft = "off"
    public var modelSettingsAdaptiveThinkingBudgetDraft = ""
    public var modelSettingsToolParserXMLFallbackDraft = false
    public var modelSettingsOCRSamplingProfileDraft = ""
    public var modelSettingsOCRTemperatureDraft = ""
    public var modelSettingsOCRTopPDraft = ""
    public var modelSettingsOCRMaxTokensDraft = ""
    public var selectedBenchmarkModelID = "melix-dev-text"
    public var selectedBenchmarkPresentationMode: RuntimeBenchmarkPresentationMode = .standard
    public var preferredDiagnosticsStage: RuntimeDiagnosticsStagePreference?
    public var selectedBenchmarkTargetMode: RuntimeBenchmarkTargetMode = .catalogModel
    public var selectedBenchmarkSuiteIDs: Set<String> = ["smoke"]
    public var selectedBenchContextLengths: [UInt32] = [1024, 4096]
    public var selectedBenchBatchSizes: [UInt32] = [2, 4]
    public var benchRepeats = "3"
    public var benchCacheProfile = "partial_prefix"
    public var benchReasoningMode = "enabled"
    public var benchStructuredOutputMode = "json_schema"
    public var benchmarkSampleSize = ""
    public var benchmarkBatchFactor = ""
    public var benchmarkHFRepoID = ""
    public var selectedBenchmarkHistoryJobID = ""
    public var selectedBenchmarkMetricName = ""
    public var selectedBenchGenerationLengths: [UInt32] = [128, 256]
    public var selectedBenchMatrixCacheProfiles: [String] = ["cold", "partial_prefix"]
    public var selectedBenchMatrixReasoningModes: [String] = ["enabled"]
    public var selectedBenchMatrixStructuredOutputModes: [String] = ["json_schema"]
    public var selectedBenchMatrixConcurrencyLevels: [UInt32] = [1, 2]
    public var selectedBenchmarkMatrixLoadBudgetMode: RuntimeBenchmarkMatrixLoadBudgetMode = .requests
    public var benchMatrixRepeats = "3"
    public var benchMatrixRequests = "8"
    public var benchMatrixDurationSeconds = "60"
    public var benchMatrixAllowLargeMatrix = false
    public var selectedBenchmarkMatrixHistoryJobID = ""
    public var selectedEvaluationTargetMode: RuntimeBenchmarkTargetMode = .catalogModel
    public var selectedEvaluationModelID = "melix-dev-text"
    public var selectedEvaluationSuiteIDs: Set<String> = ["mmlu"]
    public var evaluationSampleSize = ""
    public var evaluationBatchFactor = ""
    public var evaluationSeed = ""
    public var evaluationFewShot = ""
    public var evaluationScoringMode = "multiple_choice_accuracy"
    public var evaluationCodeExecPolicy = "sandboxed"
    public var evaluationHFRepoID = ""
    public var evaluationDatasetSourceKind: RuntimeEvaluationDatasetSourceKind = .builtinPackage
    public var evaluationSourcePath = ""
    public var evaluationHFDatasetPath = ""
    public var evaluationHFDatasetName = ""
    public var evaluationHFDatasetRevision = "main"
    public var evaluationHFDatasetSplit = "train"
    public var evaluationFieldSystemPath = ""
    public var evaluationFieldInputTextPath = ""
    public var evaluationFieldTargetPath = ""
    public var evaluationFieldSampleIDPath = ""
    public var evaluationResultKind = "text"
    public var evaluationExtractionMode = "heuristic_final"
    public var evaluationThreshold = "1.0"
    public var evaluationOutputSchemaJSON = ""
    public var evaluationIgnoredPaths = ""
    public var selectedEvaluationPromptID = EvaluationPromptStore.builtInBaselinePromptID
    public var evaluationPromptIDDraft = "event-extraction-custom"
    public var evaluationPromptTitleDraft = "Event Extraction Prompt"
    public var evaluationPromptSystemPromptDraft = EvaluationPromptStore.builtInBaselineSystemPrompt
    public var selectedEvaluationSemanticJudgeRemoteServerID = ""
    public var evaluationSemanticJudgeModelID = ""
    public var selectedEvaluationMode: RuntimeEvaluationMode = .standard
    public var selectedEvaluationCompareTargetModelIDs: Set<String> = []
    public var selectedEvaluationHistoryJobID = ""
    public var loraDatasetSourceKind: RuntimeLoraDatasetSourceKind = .localPackage
    public var loraTrainingMode: RuntimeLoraTrainingMode = .lora
    public var selectedLoraTrainingPreset: RuntimeLoraTrainingPreset = .custom
    public var loraActivationMode: RuntimeLoraActivationMode = .fusedDerivedModel
    public var loraDatasetURI = "datasets/melix-dev"
    public var loraHFDatasetPath = ""
    public var loraHFDatasetName = ""
    public var loraHFDatasetRevision = ""
    public var loraHFTrainSplit = "train"
    public var loraHFValidSplit = ""
    public var loraChatFeature = ""
    public var loraPromptFeature = ""
    public var loraCompletionFeature = ""
    public var loraTextFeature = "text"
    public var loraAdapterName = "melix-dev-adapter"
    public var loraTargetRepo = "melix/adapters/melix-dev-adapter"
    public var loraExperimentGroupID = ""
    public var loraResumeFromManifestPath = ""
    public var loraRank = "8"
    public var loraAlpha = "16"
    public var loraDropout = "0.0"
    public var loraTargetModules = ""
    public var loraNumLayers = ""
    public var loraBatchSize = "1"
    public var loraEpochs = "1"
    public var loraLearningRate = "0.0001"
    public var loraMaxSeqLength = "2048"
    public var loraResponseOnly = true
    public var loraMaskPrompt = false
    public var loraGradientCheckpointing = false
    public var loraDerivedModelAlias = ""
    public var selectedAdapterPackageID = ""
    public var registryRootPathDraft = ""
    public var imagePromptText = ""
    public var imageEditMode: RuntimeImageEditMode = .edit
    public var imageEditSourceURL = ""
    public var imageEditMaskURL = ""
    public var imageEditSourceArtifactID = ""
    public var imageSize = "1024x1024"
    public var imageSteps = "28"
    public var imageGuidance = "7.5"
    public var imageStrength = "1.0"
    public var imageNegativePrompt = ""
    public var imageVariantCount: UInt32 = 1
    public var selectedImageGenerateModelID = "melix-dev-image"
    public var selectedImageEditModelID = "melix-dev-image"
    public private(set) var imageDefaultsSourceText = "Built-in Defaults"
    public private(set) var effectiveImageGenerateModelID = ""
    public private(set) var effectiveImageEditModelID = ""
    public private(set) var effectiveImageSize = "1024x1024"
    public private(set) var effectiveImageSteps = "28"
    public private(set) var effectiveImageGuidance = "7.5"
    public private(set) var effectiveImageStrength = "1.0"
    public private(set) var effectiveImageNegativePrompt = ""
    public private(set) var imageDefaultsUpdatedAtUnixMS: Int64 = 0
    public let availableQuantizationProfileIDs = ["q2", "q3", "q4", "q5", "q6", "q7", "q8"]
    public var selectedQuantizationProfileID = "q4"
    public var openCommandCenterAction: (@MainActor @Sendable () -> Void)?

    public var onStateChanged: (@MainActor @Sendable () -> Void)?

    public var serveableModels: [RuntimeModelRow] {
        models.filter(\.isServeableServerModel)
    }

    public func isPendingAssistantTranscriptEntry(_ entry: DesktopChatTranscriptEntry) -> Bool {
        isEmptyPendingAssistantEntry(entry)
    }

    private let client: any ControlPlaneXPCClient
    private let metrics: MenuBarMetricsStore
    private let operatorSessionStore: any OperatorSessionStoring
    private let cliWorkflowRunner: (any MelixCLIWorkflowRunning)?
    private let operatorCommandRunner: MelixCLIRunner?
    private let serverSessionAPIKeyStore: any ServerSessionAPIKeyStoring
    private let remoteServerStore: any RemoteServerStoring
    private let evaluationPromptStore: any EvaluationPromptStoring
    private let huggingFaceTokenStore: any HuggingFaceTokenStoring
    private let productInstallStateProvider: any ProductInstallStateProviding
    private var subscriptionTask: Task<Void, Never>?
    private var lastSeenSeq: UInt64 = 0
    private var latestSnapshot = Melix_Controlplane_V1_ServerSnapshot()
    private var recentEvents: [DesktopLogEntry] = []
    private var connectionStateTransitions = 0.0
    private var chatConversationMessages: [ControlPlaneChatRequest.Message] = []
    private var activeAssistantEntryID: String?
    private var activeReasoningEntryID: String?
    private var activeToolEntryIDs: [String: String] = [:]
    private var chatPresentationFragments: [ChatPresentationFragment] = []
    private var chatPresentationTask: Task<Void, Never>?
    private var chatPresentationMaxLagMs = 0.0
    private var chatPresentationFlushCount = 0.0
    private var persistedServerSessions: [DesktopServerSessionState] = []
    private var dismissedBannerIDs: Set<String> = []
    private var modelSettingsDraftModelID = ""
    private var operatorStateRestored = false
    private var lastPersistedOperatorSessionState: OperatorSessionState?
    private var gatewayAPIKeyPersistFailures = 0.0
    private var remoteServerPersistFailures = 0.0
    private var evaluationPromptPersistFailures = 0.0
    private var evaluationPromptEditingFrozenRevisionAsDraft = false
    private var lastAppliedGatewaySessionID = ""
    private var lastAppliedGatewayPrimaryKey = ""
    private var gatewayApplyTask: Task<Void, Never>?
    private var benchmarkExportBundle: ControlPlaneBenchmarkExportBundle?

    private static let benchmarkSuiteOptions = [
        RuntimeBenchmarkSuiteOptionState(
            id: "smoke",
            taskKind: "text-generation",
            title: "UltraChat Smoke",
            datasetPath: "HuggingFaceH4/ultrachat_200k",
            datasetName: "default",
            datasetSplit: "train_sft",
            defaultSampleSize: 1,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "latency",
            taskKind: "text-generation",
            title: "Dolly Latency",
            datasetPath: "databricks/databricks-dolly-15k",
            datasetName: "default",
            datasetSplit: "train",
            defaultSampleSize: 5,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "smoke",
            taskKind: "image-to-text",
            title: "Docs Images OCR Smoke",
            datasetPath: "huggingface/documentation-images",
            datasetName: "default",
            datasetSplit: "train",
            defaultSampleSize: 1,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "latency",
            taskKind: "image-to-text",
            title: "Docs Images OCR Latency",
            datasetPath: "huggingface/documentation-images",
            datasetName: "default",
            datasetSplit: "validation",
            defaultSampleSize: 4,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "smoke",
            taskKind: "image-text-to-text",
            title: "Docs Images VLM Smoke",
            datasetPath: "huggingface/documentation-images",
            datasetName: "default",
            datasetSplit: "train",
            defaultSampleSize: 1,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "latency",
            taskKind: "image-text-to-text",
            title: "Docs Images VLM Latency",
            datasetPath: "huggingface/documentation-images",
            datasetName: "default",
            datasetSplit: "validation",
            defaultSampleSize: 4,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "smoke",
            taskKind: "text-to-image",
            title: "Dolly Text-to-Image Smoke",
            datasetPath: "databricks/databricks-dolly-15k",
            datasetName: "default",
            datasetSplit: "train",
            defaultSampleSize: 1,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "latency",
            taskKind: "text-to-image",
            title: "UltraChat Text-to-Image Latency",
            datasetPath: "HuggingFaceH4/ultrachat_200k",
            datasetName: "default",
            datasetSplit: "train_sft",
            defaultSampleSize: 4,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "smoke",
            taskKind: "image-text-to-image",
            title: "Docs Images Edit Smoke",
            datasetPath: "huggingface/documentation-images",
            datasetName: "default",
            datasetSplit: "train",
            defaultSampleSize: 1,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "latency",
            taskKind: "image-text-to-image",
            title: "Docs Images Edit Latency",
            datasetPath: "huggingface/documentation-images",
            datasetName: "default",
            datasetSplit: "validation",
            defaultSampleSize: 4,
            defaultBatchFactor: 1
        ),
    ]

    static let benchmarkContextLengthOptions: [UInt32] = [1024, 4096, 8192]
    static let benchmarkBatchSizeOptions: [UInt32] = [1, 2, 4, 8]
    static let benchmarkGenerationLengthOptions: [UInt32] = [128, 256, 512]
    static let benchmarkConcurrencyOptions: [UInt32] = [1, 2, 4]
    static let benchmarkCacheProfileOptions = ControlPlaneBenchRequest.validCacheProfiles
    static let benchmarkReasoningModeOptions: [String] = ["off", "enabled", "deep_reasoning"]
    static let benchmarkStructuredOutputModeOptions: [String] = ["off", "json_object", "json_schema"]

    private static let evaluationSuiteOptions = [
        RuntimeEvaluationSuiteOptionState(
            id: "mmlu",
            title: "MMLU",
            datasetID: "mmlu.dev.v1",
            scoreLabel: "Multiple-choice accuracy",
            defaultSampleSize: 8,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "arc_challenge",
            title: "ARC Challenge",
            datasetID: "arc_challenge.dev.v1",
            scoreLabel: "Multiple-choice accuracy",
            defaultSampleSize: 8,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "hellaswag",
            title: "HellaSwag",
            datasetID: "hellaswag.dev.v1",
            scoreLabel: "Multiple-choice accuracy",
            defaultSampleSize: 8,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "winogrande",
            title: "Winogrande",
            datasetID: "winogrande.dev.v1",
            scoreLabel: "Multiple-choice accuracy",
            defaultSampleSize: 8,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "truthfulqa_mc",
            title: "TruthfulQA MC",
            datasetID: "truthfulqa_mc.dev.v1",
            scoreLabel: "Multiple-choice accuracy",
            defaultSampleSize: 8,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "gsm8k",
            title: "GSM8K",
            datasetID: "gsm8k.dev.v1",
            scoreLabel: "Exact match",
            defaultSampleSize: 8,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "humaneval",
            title: "HumanEval",
            datasetID: "humaneval.dev.v1",
            scoreLabel: "Pass@1",
            defaultSampleSize: 4,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "mbpp",
            title: "MBPP",
            datasetID: "mbpp.dev.v1",
            scoreLabel: "Pass@1",
            defaultSampleSize: 4,
            defaultBatchFactor: 1
        ),
        RuntimeEvaluationSuiteOptionState(
            id: "event_extraction",
            title: "Event Extraction",
            datasetID: "event_extraction.jsonl",
            scoreLabel: "Weighted F1",
            defaultSampleSize: 200,
            defaultBatchFactor: 1
        ),
    ]
    private static let chatPresentationFlushInterval: Duration = .milliseconds(24)
    private static let chatPresentationCharactersPerFlush = 8

    public init(
        client: any ControlPlaneXPCClient,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        operatorSessionStore: any OperatorSessionStoring = NullOperatorSessionStore(),
        cliWorkflowRunner: (any MelixCLIWorkflowRunning)? = nil,
        operatorCommandRunner: MelixCLIRunner? = nil,
        serverSessionAPIKeyStore: any ServerSessionAPIKeyStoring = NullServerSessionAPIKeyStore(),
        remoteServerStore: any RemoteServerStoring = NullRemoteServerStore(),
        evaluationPromptStore: any EvaluationPromptStoring = NullEvaluationPromptStore(),
        huggingFaceTokenStore: any HuggingFaceTokenStoring = NullHuggingFaceTokenStore(),
        productInstallStateProvider: any ProductInstallStateProviding = FilesystemProductInstallStateProvider()
    ) {
        self.client = client
        self.metrics = metrics
        self.operatorSessionStore = operatorSessionStore
        self.cliWorkflowRunner = cliWorkflowRunner
        self.operatorCommandRunner = operatorCommandRunner
        self.serverSessionAPIKeyStore = serverSessionAPIKeyStore
        self.remoteServerStore = remoteServerStore
        self.evaluationPromptStore = evaluationPromptStore
        self.huggingFaceTokenStore = huggingFaceTokenStore
        self.productInstallStateProvider = productInstallStateProvider
        reloadRemoteServers()
        reloadEvaluationPrompts()
        reloadHuggingFaceTokenHint()
    }

    var cliWorkflowRunnerSurface: MelixCLIWorkflowSurface? {
        cliWorkflowRunner?.surface
    }

    private var commandWorkflowRunner: (any MelixCLIWorkflowRunning)? {
        cliWorkflowRunner ?? operatorCommandRunner
    }

    private func reloadHuggingFaceTokenHint() {
        modelHubTokenHint = ((try? huggingFaceTokenStore.loadToken()?.maskedHint) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public func reloadRemoteServers() {
        do {
            let servers = try remoteServerStore.list()
            remoteServers = servers
            if selectedRemoteServerID.isEmpty || servers.contains(where: { $0.id == selectedRemoteServerID }) == false {
                selectedRemoteServerID = servers.first?.id ?? ""
            }
            if let selected = servers.first(where: { $0.id == selectedRemoteServerID }) {
                applyRemoteServerDraft(from: selected)
            }
            if selectedEvaluationSemanticJudgeRemoteServerID.isEmpty == false,
               servers.contains(where: { $0.id == selectedEvaluationSemanticJudgeRemoteServerID }) == false
            {
                selectedEvaluationSemanticJudgeRemoteServerID = ""
                evaluationSemanticJudgeModelID = ""
            }
        } catch {
            remoteServerPersistFailures += 1
            recordLocalError("Remote Server load failed: \(error)")
        }
    }

    deinit {
        MainActor.assumeIsolated {
            subscriptionTask?.cancel()
        }
    }

    public func selectSurface(_ surface: DesktopSurface) {
        selectedSurface = surface
        notifyStateChanged()
    }

    public func prepareNewRemoteServerDraft() {
        selectedRemoteServerID = ""
        remoteServerIDDraft = "sub2api"
        remoteServerTitleDraft = "sub2api"
        remoteServerProviderPresetDraft = .custom
        remoteServerProviderKindDraft = "openai-compatible"
        remoteServerBaseURLDraft = ""
        remoteServerDefaultModelIDDraft = "gemini-2.5-flash"
        remoteServerAPIKeyDraft = ""
        remoteServerTimeoutSecondsDraft = 120
        remoteServerRateLimitPerMinuteDraft = 0
        selectedSurface = .server
        notifyStateChanged()
    }

    public var isRemoteServerBaseURLEditable: Bool {
        remoteServerProviderPresetDraft.isBaseURLEditable
    }

    public var isRemoteServerIDEditable: Bool {
        selectedRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func selectRemoteServerProviderPreset(_ providerPreset: RemoteServerProviderPreset) {
        let previousFixedBaseURL = remoteServerProviderPresetDraft.fixedBaseURL
        remoteServerProviderPresetDraft = providerPreset
        remoteServerProviderKindDraft = providerPreset.providerKind
        if let fixedBaseURL = providerPreset.fixedBaseURL {
            remoteServerBaseURLDraft = fixedBaseURL
        } else if let previousFixedBaseURL,
                  remoteServerBaseURLDraft == previousFixedBaseURL
        {
            remoteServerBaseURLDraft = ""
        }
        notifyStateChanged()
    }

    public func selectRemoteServer(id: String) {
        selectedRemoteServerID = id
        if let server = remoteServers.first(where: { $0.id == id }) {
            applyRemoteServerDraft(from: server)
        }
        selectedSurface = .server
        notifyStateChanged()
    }

    public func saveRemoteServerDraft() {
        let id = remoteServerIDDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let title = remoteServerTitleDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let providerKind = remoteServerProviderKindDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let baseURL = remoteServerProviderPresetDraft.fixedBaseURL
            ?? remoteServerBaseURLDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let defaultModelID = remoteServerDefaultModelIDDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let selectedID = selectedRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        if selectedID.isEmpty == false, id != selectedID {
            remoteServerIDDraft = selectedID
            recordLocalError("Remote Server ID cannot be changed after creation. Use New to create another server.")
            notifyStateChanged()
            return
        }
        guard id.isEmpty == false,
              title.isEmpty == false,
              providerKind.isEmpty == false,
              baseURL.isEmpty == false,
              defaultModelID.isEmpty == false
        else {
            recordLocalError("Remote Server requires id, title, provider, base URL, and default model.")
            notifyStateChanged()
            return
        }

        do {
            let saved = try remoteServerStore.save(
                RemoteServerMutation(
                    id: id,
                    title: title,
                    providerPreset: remoteServerProviderPresetDraft,
                    providerKind: providerKind,
                    baseURL: baseURL,
                    defaultModelID: defaultModelID,
                    timeoutSeconds: remoteServerTimeoutSecondsDraft,
                    rateLimitPerMinute: remoteServerRateLimitPerMinuteDraft,
                    apiKey: remoteServerAPIKeyDraft
                )
            )
            remoteServerAPIKeyDraft = ""
            selectedRemoteServerID = saved.id
            remoteServers = try remoteServerStore.list()
            applyRemoteServerDraft(from: saved)
            notifyStateChanged()
        } catch {
            remoteServerPersistFailures += 1
            Task {
                await metrics.record(
                    name: "remote_server.persist_failures",
                    valueMs: remoteServerPersistFailures
                )
            }
            recordLocalError("Remote Server save failed: \(error)")
            notifyStateChanged()
        }
    }

    public func removeSelectedRemoteServer() {
        let targetID = selectedRemoteServerID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard targetID.isEmpty == false else {
            return
        }
        do {
            try remoteServerStore.remove(id: targetID)
            remoteServers = try remoteServerStore.list()
            if let first = remoteServers.first {
                selectedRemoteServerID = first.id
                applyRemoteServerDraft(from: first)
            } else {
                prepareNewRemoteServerDraft()
            }
            notifyStateChanged()
        } catch {
            remoteServerPersistFailures += 1
            Task {
                await metrics.record(
                    name: "remote_server.persist_failures",
                    valueMs: remoteServerPersistFailures
                )
            }
            recordLocalError("Remote Server remove failed: \(error)")
            notifyStateChanged()
        }
    }

    private func applyRemoteServerDraft(from server: RemoteServer) {
        remoteServerIDDraft = server.id
        remoteServerTitleDraft = server.title
        remoteServerProviderPresetDraft = server.providerPreset
        remoteServerProviderKindDraft = server.providerKind
        remoteServerBaseURLDraft = server.baseURL
        remoteServerDefaultModelIDDraft = server.defaultModelID
        remoteServerAPIKeyDraft = ""
        remoteServerTimeoutSecondsDraft = server.timeoutSeconds
        remoteServerRateLimitPerMinuteDraft = server.rateLimitPerMinute
    }

    public var selectedEvaluationPrompt: EvaluationPrompt? {
        evaluationPrompts.first { $0.id == selectedEvaluationPromptID }
    }

    public var selectedEvaluationPromptRevision: EvaluationPromptRevision? {
        selectedEvaluationPrompt?.latestRevision
    }

    public var selectedEvaluationPromptSummaryText: String {
        guard let prompt = selectedEvaluationPrompt,
              let revision = prompt.latestRevision
        else {
            return "New draft prompt"
        }
        let status = revision.status.rawValue.capitalized
        let shortHash = String(revision.contentHash.suffix(12))
        return "\(prompt.title) • \(revision.revisionID) • \(status) • \(shortHash)"
    }

    public var isEvaluationPromptIDEditable: Bool {
        selectedEvaluationPromptID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public var isEvaluationPromptDraftEditable: Bool {
        guard let prompt = selectedEvaluationPrompt else {
            return true
        }
        guard prompt.readOnly == false else {
            return false
        }
        return prompt.latestRevision?.status == .draft || evaluationPromptEditingFrozenRevisionAsDraft
    }

    public var canFreezeSelectedEvaluationPrompt: Bool {
        guard let prompt = selectedEvaluationPrompt,
              prompt.readOnly == false,
              prompt.latestRevision?.status == .draft
        else {
            return false
        }
        return true
    }

    public func reloadEvaluationPrompts() {
        do {
            let prompts = try evaluationPromptStore.list(includeArchived: false)
            evaluationPrompts = prompts
            if selectedEvaluationPromptID.isEmpty
                || prompts.contains(where: { $0.id == selectedEvaluationPromptID }) == false
            {
                selectedEvaluationPromptID = prompts.first(where: { $0.id == EvaluationPromptStore.builtInBaselinePromptID })?.id
                    ?? prompts.first?.id
                    ?? ""
            }
            if let selected = prompts.first(where: { $0.id == selectedEvaluationPromptID }) {
                applyEvaluationPromptDraft(from: selected)
            }
        } catch {
            evaluationPromptPersistFailures += 1
            recordLocalError("Evaluation prompt load failed: \(error)")
        }
    }

    public func selectEvaluationPrompt(id: String) {
        selectedEvaluationPromptID = id
        evaluationPromptEditingFrozenRevisionAsDraft = false
        if let prompt = evaluationPrompts.first(where: { $0.id == id }) {
            applyEvaluationPromptDraft(from: prompt)
        }
        notifyStateChanged()
    }

    public func prepareNewEvaluationPromptDraft() {
        selectedEvaluationPromptID = ""
        evaluationPromptIDDraft = "event-extraction-custom"
        evaluationPromptTitleDraft = "Event Extraction Prompt"
        evaluationPromptSystemPromptDraft = EvaluationPromptStore.builtInBaselineSystemPrompt
        evaluationPromptEditingFrozenRevisionAsDraft = false
        notifyStateChanged()
    }

    public func prepareEvaluationPromptDraftFromSelection() {
        guard let prompt = selectedEvaluationPrompt,
              prompt.readOnly == false
        else {
            recordLocalError("The built-in evaluation prompt is read-only. Create a new prompt to customize it.")
            notifyStateChanged()
            return
        }
        evaluationPromptEditingFrozenRevisionAsDraft = prompt.latestRevision?.status == .frozen
        applyEvaluationPromptDraft(from: prompt)
        notifyStateChanged()
    }

    public func saveEvaluationPromptDraft() {
        let id = evaluationPromptIDDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let title = evaluationPromptTitleDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let systemPrompt = evaluationPromptSystemPromptDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        let selectedID = selectedEvaluationPromptID.trimmingCharacters(in: .whitespacesAndNewlines)
        if selectedID.isEmpty == false, id != selectedID {
            evaluationPromptIDDraft = selectedID
            recordLocalError("Evaluation prompt ID cannot be changed after creation. Use New Prompt to create another prompt.")
            notifyStateChanged()
            return
        }
        guard id.isEmpty == false,
              title.isEmpty == false,
              systemPrompt.isEmpty == false
        else {
            recordLocalError("Evaluation prompt requires id, title, and system prompt.")
            notifyStateChanged()
            return
        }
        if selectedEvaluationPrompt?.readOnly == true {
            recordLocalError("The built-in evaluation prompt is read-only. Create a new prompt to customize it.")
            notifyStateChanged()
            return
        }

        do {
            let saved = selectedID.isEmpty
                ? try evaluationPromptStore.create(promptID: id, title: title, systemPrompt: systemPrompt)
                : try evaluationPromptStore.update(promptID: id, systemPrompt: systemPrompt)
            evaluationPromptEditingFrozenRevisionAsDraft = false
            selectedEvaluationPromptID = saved.id
            evaluationPrompts = try evaluationPromptStore.list(includeArchived: false)
            applyEvaluationPromptDraft(from: saved)
            notifyStateChanged()
        } catch {
            evaluationPromptPersistFailures += 1
            Task {
                await metrics.record(
                    name: "evaluation_prompt.persist_failures",
                    valueMs: evaluationPromptPersistFailures
                )
            }
            recordLocalError("Evaluation prompt save failed: \(error)")
            notifyStateChanged()
        }
    }

    public func freezeSelectedEvaluationPrompt() {
        let promptID = selectedEvaluationPromptID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard promptID.isEmpty == false else {
            recordLocalError("Save the evaluation prompt draft before freezing it.")
            notifyStateChanged()
            return
        }
        do {
            let frozen = try evaluationPromptStore.freeze(promptID: promptID, revisionID: "")
            evaluationPromptEditingFrozenRevisionAsDraft = false
            selectedEvaluationPromptID = frozen.id
            evaluationPrompts = try evaluationPromptStore.list(includeArchived: false)
            applyEvaluationPromptDraft(from: frozen)
            notifyStateChanged()
        } catch {
            evaluationPromptPersistFailures += 1
            Task {
                await metrics.record(
                    name: "evaluation_prompt.persist_failures",
                    valueMs: evaluationPromptPersistFailures
                )
            }
            recordLocalError("Evaluation prompt freeze failed: \(error)")
            notifyStateChanged()
        }
    }

    public func archiveSelectedEvaluationPrompt() {
        let promptID = selectedEvaluationPromptID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard promptID.isEmpty == false else {
            return
        }
        do {
            _ = try evaluationPromptStore.archive(promptID: promptID)
            evaluationPrompts = try evaluationPromptStore.list(includeArchived: false)
            selectedEvaluationPromptID = evaluationPrompts.first?.id ?? ""
            if let first = evaluationPrompts.first {
                applyEvaluationPromptDraft(from: first)
            }
            notifyStateChanged()
        } catch {
            evaluationPromptPersistFailures += 1
            Task {
                await metrics.record(
                    name: "evaluation_prompt.persist_failures",
                    valueMs: evaluationPromptPersistFailures
                )
            }
            recordLocalError("Evaluation prompt archive failed: \(error)")
            notifyStateChanged()
        }
    }

    private func applyEvaluationPromptDraft(from prompt: EvaluationPrompt) {
        evaluationPromptIDDraft = prompt.id
        evaluationPromptTitleDraft = prompt.title
        evaluationPromptSystemPromptDraft = prompt.latestRevision?.systemPrompt ?? ""
    }

    public func selectToolSection(_ section: DesktopToolSection) {
        selectedSurface = .tools
        selectedToolSection = section
        notifyStateChanged()
    }

    public func openPreferences() {
        selectedSurface = .tools
        selectedToolSection = .settings
        notifyStateChanged()
    }

    public func desktopPaneVisibilityState(for surface: DesktopSurface? = nil) -> DesktopPaneVisibilityState {
        let resolvedSurface = surface ?? selectedSurface
        return desktopPaneVisibility.first { $0.surface == resolvedSurface }
            ?? DesktopPaneVisibilityState.defaultState(for: resolvedSurface)
    }

    public func isDesktopPaneVisible(
        _ role: DesktopPaneRole,
        for surface: DesktopSurface? = nil
    ) -> Bool {
        let state = desktopPaneVisibilityState(for: surface)
        switch role {
        case .sidebar:
            return state.showsSidebar
        case .inspector:
            return state.showsInspector
        }
    }

    public func setDesktopPaneVisible(
        _ role: DesktopPaneRole,
        visible: Bool,
        for surface: DesktopSurface? = nil
    ) {
        updateDesktopPaneVisibility(role, visible: visible, for: surface ?? selectedSurface)
        notifyStateChanged()
    }

    public func toggleDesktopPane(_ role: DesktopPaneRole) {
        setDesktopPaneVisible(role, visible: isDesktopPaneVisible(role) == false)
    }

    private func updateDesktopPaneVisibility(
        _ role: DesktopPaneRole,
        visible: Bool,
        for surface: DesktopSurface
    ) {
        var states = DesktopPaneVisibilityState.mergedWithDefaults(desktopPaneVisibility)
        guard let index = states.firstIndex(where: { $0.surface == surface }) else {
            return
        }
        switch role {
        case .sidebar:
            states[index].showsSidebar = visible
        case .inspector:
            states[index].showsInspector = visible
        }
        desktopPaneVisibility = states
    }

    public func toggleBenchmarkSuite(_ suiteID: String) {
        if selectedBenchmarkSuiteIDs.contains(suiteID) {
            selectedBenchmarkSuiteIDs.remove(suiteID)
        } else {
            selectedBenchmarkSuiteIDs.insert(suiteID)
        }
        rebuildBenchmarkDerivedState()
        notifyStateChanged()
    }

    public func toggleBenchContextLength(_ contextLength: UInt32) {
        selectedBenchContextLengths = Self.toggledValues(
            contextLength,
            in: selectedBenchContextLengths
        )
        notifyStateChanged()
    }

    public func toggleBenchBatchSize(_ batchSize: UInt32) {
        selectedBenchBatchSizes = Self.toggledValues(
            batchSize,
            in: selectedBenchBatchSizes
        )
        notifyStateChanged()
    }

    public func toggleBenchGenerationLength(_ generationLength: UInt32) {
        selectedBenchGenerationLengths = Self.toggledValues(
            generationLength,
            in: selectedBenchGenerationLengths
        )
        notifyStateChanged()
    }

    public func toggleBenchMatrixCacheProfile(_ cacheProfile: String) {
        selectedBenchMatrixCacheProfiles = Self.toggledStrings(
            cacheProfile,
            in: selectedBenchMatrixCacheProfiles
        )
        notifyStateChanged()
    }

    public func toggleBenchMatrixReasoningMode(_ reasoningMode: String) {
        selectedBenchMatrixReasoningModes = Self.toggledStrings(
            reasoningMode,
            in: selectedBenchMatrixReasoningModes
        )
        notifyStateChanged()
    }

    public func toggleBenchMatrixStructuredOutputMode(_ structuredOutputMode: String) {
        selectedBenchMatrixStructuredOutputModes = Self.toggledStrings(
            structuredOutputMode,
            in: selectedBenchMatrixStructuredOutputModes
        )
        notifyStateChanged()
    }

    public func toggleBenchMatrixConcurrencyLevel(_ concurrencyLevel: UInt32) {
        selectedBenchMatrixConcurrencyLevels = Self.toggledValues(
            concurrencyLevel,
            in: selectedBenchMatrixConcurrencyLevels
        )
        notifyStateChanged()
    }

    public func selectBenchmarkHistory(jobID: String) {
        preferredDiagnosticsStage = .benchmark
        selectedBenchmarkHistoryJobID = jobID
        rebuildBenchmarkDerivedState()
        notifyStateChanged()
    }

    public func selectBenchmarkMetric(_ metricName: String) {
        selectedBenchmarkMetricName = metricName
        rebuildBenchmarkDerivedState()
        notifyStateChanged()
    }

    public func selectBenchmarkMatrixHistory(jobID: String) {
        preferredDiagnosticsStage = .matrix
        selectedBenchmarkMatrixHistoryJobID = jobID
        rebuildBenchmarkMatrixDerivedState()
        notifyStateChanged()
    }

    public func toggleEvaluationSuite(_ suiteID: String) {
        if selectedEvaluationSuiteIDs.contains(suiteID) {
            selectedEvaluationSuiteIDs.remove(suiteID)
        } else {
            selectedEvaluationSuiteIDs.insert(suiteID)
        }
        rebuildEvaluationDerivedState()
        notifyStateChanged()
    }

    public func selectEvaluationHistory(jobID: String) {
        preferredDiagnosticsStage = .evaluation
        selectedEvaluationHistoryJobID = jobID
        rebuildEvaluationDerivedState()
        notifyStateChanged()
    }

    public func openCommandCenter() {
        openCommandCenterAction?()
    }

    public func selectAgentIntegrationTarget(_ target: AgentIntegrationExportTarget) {
        selectedAgentIntegrationTarget = target
        notifyStateChanged()
    }

    public func createServerSession() {
        let modelID = serveableModels.first?.modelID ?? selectedChatModelID
        let nextIndex = serverSessions.count + 1
        let title = nextIndex == 1 ? "Primary Server" : "Server \(nextIndex)"
        let port = 8080 + max(0, serverSessions.count)
        if let commandWorkflowRunner {
            Task {
                do {
                    _ = try await commandWorkflowRunner.run(
                        .serverSessionCreate(
                            .init(title: title, modelID: modelID, host: "127.0.0.1", port: port, json: true)
                        )
                    )
                    restoreOperatorSessionState()
                    syncServerSessionsWithModels()
                    refreshAgentIntegrationExports()
                    selectedSurface = .server
                    if chatSessions.isEmpty {
                        createChatSession()
                    }
                } catch {
                    recordCLIWorkflowErrorIfNeeded(error)
                    recordLocalError(String(describing: error))
                }
                notifyStateChanged()
            }
            return
        }
        let session = DesktopServerSessionState(
            id: "server-session-\(UUID().uuidString)",
            title: title,
            modelID: modelID,
            port: port,
            lifecycle: .draft
        )
        persistedServerSessions.append(session)
        selectedServerSessionID = session.id
        syncServerSessionsWithModels()
        refreshAgentIntegrationExports()
        selectedSurface = .server
        if chatSessions.isEmpty {
            createChatSession()
        }
        notifyStateChanged()
    }

    public func selectServerSession(id: String) {
        guard serverSessions.contains(where: { $0.id == id }) else {
            return
        }
        if let commandWorkflowRunner {
            Task {
                do {
                    _ = try await commandWorkflowRunner.run(
                        .serverSessionSelect(.init(serverSessionID: id, json: true))
                    )
                    restoreOperatorSessionState()
                    syncServerSessionsWithModels()
                    refreshAgentIntegrationExports()
                } catch {
                    recordCLIWorkflowErrorIfNeeded(error)
                    recordLocalError(String(describing: error))
                }
                selectedChatModelID = selectedServerSession?.modelID ?? selectedChatModelID
                maybeApplyStoredGatewayAccessForSelectedRunningSession()
                notifyStateChanged()
            }
            return
        }
        selectedServerSessionID = id
        selectedChatModelID = selectedServerSession?.modelID ?? selectedChatModelID
        refreshAgentIntegrationExports()
        maybeApplyStoredGatewayAccessForSelectedRunningSession()
        notifyStateChanged()
    }

    public func updateSelectedServerSessionModelID(_ modelID: String) {
        updateSelectedServerSession { session in
            session.modelID = modelID
            session.updatedAt = Date()
        }
        if selectedChatSession == nil {
            selectedChatModelID = modelID
        }
    }

    public func updateSelectedServerSessionHost(_ host: String) {
        updateSelectedServerSession { session in
            session.host = host
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionPort(_ port: Int) {
        updateSelectedServerSession { session in
            session.port = max(1, port)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionAuthMode(_ authMode: DesktopServerAuthMode) {
        updateSelectedServerSession { session in
            session.authMode = authMode
            if authMode == .apiKeys {
                session.sharedAccessState = .enabled
            } else if session.sharedAccessState == .enabled {
                session.sharedAccessState = .localOnly
            }
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionAuthTokenHint(_ value: String) {
        updateSelectedServerSession { session in
            session.authTokenHint = value
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionRateLimit(_ value: Int) {
        updateSelectedServerSession { session in
            session.rateLimitPerMinute = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionTimeout(_ value: Int) {
        updateSelectedServerSession { session in
            session.timeoutSeconds = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionTemperature(_ value: Double) {
        updateSelectedServerSession { session in
            session.servingDefaults.temperature = max(0, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionTopP(_ value: Double) {
        updateSelectedServerSession { session in
            session.servingDefaults.topP = max(0, min(1, value))
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionMaxTokens(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.maxTokens = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionStreamIntervalTokens(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.streamIntervalTokens = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionMaxConcurrentRequests(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.maxConcurrentRequests = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionConcurrentProcessingEnabled(_ value: Bool) {
        updateSelectedServerSession { session in
            session.servingDefaults.concurrentProcessingEnabled = value
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionPrefillBatchSize(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.prefillBatchSize = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionCompletionBatchSize(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.completionBatchSize = max(1, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionAccelerationMode(_ value: String) {
        updateSelectedServerSession { session in
            session.servingDefaults.accelerationMode = value
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionDraftModelID(_ value: String) {
        updateSelectedServerSession { session in
            session.servingDefaults.draftModelID = value.trimmingCharacters(in: .whitespacesAndNewlines)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionNumDraftTokens(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.numDraftTokens = max(0, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionAutoSleepEnabled(_ value: Bool) {
        updateSelectedServerSession { session in
            session.autoSleepEnabled = value
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionLightSleepAfterSeconds(_ value: Int) {
        updateSelectedServerSession { session in
            session.lightSleepAfterSeconds = max(0, value)
            session.updatedAt = Date()
        }
    }

    public func updateSelectedServerSessionDeepSleepAfterSeconds(_ value: Int) {
        updateSelectedServerSession { session in
            session.deepSleepAfterSeconds = max(0, value)
            session.updatedAt = Date()
        }
    }

    @discardableResult
    public func generatePrimaryAPIKeyForSelectedServerSession() async -> String? {
        guard let selectedServerSession else {
            return nil
        }

        do {
            let primaryKey = try Self.makePrimaryAPIKey()
            let persistedRecord = try serverSessionAPIKeyStore.savePrimaryKey(
                serverSessionID: selectedServerSession.id,
                primaryKey: primaryKey,
                keyID: "primary"
            )

            replaceServerSession(id: selectedServerSession.id) { session in
                session.authMode = .apiKeys
                session.sharedAccessState = .enabled
                session.authTokenHint = persistedRecord.keyID
                session.accessKeyCount = 1
                session.accessKeyHints = [persistedRecord.keyID]
                session.updatedAt = Date()
            }
            syncServerSessionsWithModels()
            refreshAgentIntegrationExports()

            notifyStateChanged()
            return primaryKey
        } catch {
            gatewayAPIKeyPersistFailures += 1
            Task {
                await metrics.record(
                    name: "gateway.api_key_persist_failures",
                    valueMs: gatewayAPIKeyPersistFailures
                )
            }
            recordLocalError("Primary API key persistence failed: \(error)")
            notifyStateChanged()
            return nil
        }
    }

    public func startSelectedServerSession() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        await startServerSession(id: serverSession.id)
    }

    public func applySelectedServerGatewayConfig() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        _ = await persistGatewayConfig(for: serverSession.id)
    }

    public func applySelectedServerServingDefaults() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        _ = await persistServingDefaults(for: serverSession.id)
    }

    public func applySelectedServerServingDefaultsFromUI() {
        Task {
            await applySelectedServerServingDefaults()
        }
    }

    public func stopSelectedServerSession() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        await stopServerSession(id: serverSession.id)
    }

    public func pauseSelectedServerSession() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        await pauseServerSession(id: serverSession.id)
    }

    public func resumeSelectedServerSession() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        await resumeServerSession(id: serverSession.id)
    }

    public func wakeSelectedServerSession() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        await wakeServerSession(id: serverSession.id)
    }

    public func applySelectedServerIdlePolicy() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        if await executeServerLifecycleCommand(
            .serverSetIdlePolicy(
                .init(
                    serverSessionID: serverSession.id,
                    autoSleepEnabled: serverSession.autoSleepEnabled,
                    lightSleepAfterSeconds: UInt32(max(0, serverSession.lightSleepAfterSeconds)),
                    deepSleepAfterSeconds: UInt32(max(0, serverSession.deepSleepAfterSeconds)),
                    json: true
                )
            ),
            metricName: "menu.server_idle_policy_ms"
        ) {
            return
        }
        await performServerIdlePolicyUpdate(serverSessionID: serverSession.id)
    }

    public func startServerSession(id serverSessionID: String) async {
        if cliWorkflowRunner != nil {
            await startServerSessionViaCLI(serverSessionID: serverSessionID)
            return
        }
        if await executeServerLifecycleCommand(
            .serverStart(.init(serverSessionID: serverSessionID, json: true)),
            metricName: "menu.server_start_ms"
        ) {
            return
        }
        guard await persistGatewayConfig(for: serverSessionID) else {
            return
        }
        guard await persistServingDefaults(for: serverSessionID) else {
            return
        }
        await performServerLifecycleAction(
            serverSessionID: serverSessionID,
            metricName: "menu.server_start_ms"
        ) { [client] targetServerSessionID in
            try await client.startServerSession(serverSessionID: targetServerSessionID)
        }
    }

    public func pauseServerSession(id serverSessionID: String) async {
        if await executeServerLifecycleCommand(
            .serverPause(.init(serverSessionID: serverSessionID, json: true)),
            metricName: "menu.server_pause_ms"
        ) {
            return
        }
        await performServerLifecycleAction(
            serverSessionID: serverSessionID,
            metricName: "menu.server_pause_ms"
        ) { [client] targetServerSessionID in
            try await client.pauseServerSession(serverSessionID: targetServerSessionID)
        }
    }

    public func resumeServerSession(id serverSessionID: String) async {
        if await executeServerLifecycleCommand(
            .serverResume(.init(serverSessionID: serverSessionID, json: true)),
            metricName: "menu.server_resume_ms"
        ) {
            return
        }
        await performServerLifecycleAction(
            serverSessionID: serverSessionID,
            metricName: "menu.server_resume_ms"
        ) { [client] targetServerSessionID in
            try await client.resumeServerSession(serverSessionID: targetServerSessionID)
        }
    }

    public func wakeServerSession(id serverSessionID: String) async {
        if await executeServerLifecycleCommand(
            .serverWake(.init(serverSessionID: serverSessionID, json: true)),
            metricName: "menu.server_wake_ms"
        ) {
            return
        }
        await performServerLifecycleAction(
            serverSessionID: serverSessionID,
            metricName: "menu.server_wake_ms"
        ) { [client] targetServerSessionID in
            try await client.wakeServerSession(serverSessionID: targetServerSessionID)
        }
    }

    public func stopServerSession(id serverSessionID: String) async {
        if await executeServerLifecycleCommand(
            .serverStop(.init(serverSessionID: serverSessionID, json: true)),
            metricName: "menu.server_stop_ms"
        ) {
            return
        }
        await performServerLifecycleAction(
            serverSessionID: serverSessionID,
            metricName: "menu.server_stop_ms"
        ) { [client] targetServerSessionID in
            try await client.stopServerSession(serverSessionID: targetServerSessionID)
        }
    }

    public func createChatSession() {
        guard operatorStateRestored || serverSessions.isEmpty == false else {
            setLastError("Create a Server Session before opening chat.")
            chatStatusText = "No Server Session"
            selectedSurface = .server
            notifyStateChanged()
            return
        }

        let nextIndex = chatSessions.count + 1
        let session = DesktopChatSessionState(
            id: "chat-session-\(UUID().uuidString)",
            title: nextIndex == 1 ? "Chat 1" : "Chat \(nextIndex)",
            serverSessionID: "",
            statusText: "Choose Server"
        )
        chatSessions.append(session)
        loadChatSession(session)
        selectedSurface = .chat
        notifyStateChanged()
    }

    public func forkSelectedChatSession() {
        guard let source = selectedChatSession else {
            createChatSession()
            return
        }

        let nextIndex = chatSessions.count + 1
        let forked = DesktopChatSessionState(
            id: "chat-session-\(UUID().uuidString)",
            title: "\(source.title) Fork",
            serverSessionID: source.serverSessionID,
            branchID: "branch-\(nextIndex)",
            branchTitle: "Branch \(nextIndex)",
            transcript: source.transcript,
            statusText: source.statusText,
            usageText: source.usageText,
            requestID: source.requestID,
            isStreaming: false,
            exportPath: source.exportPath
        )
        chatSessions.append(forked)
        loadChatSession(forked)
        selectedSurface = .chat
        notifyStateChanged()
    }

    public func selectChatSession(id: String) {
        guard let session = chatSessions.first(where: { $0.id == id }) else {
            return
        }
        loadChatSession(session)
        notifyStateChanged()
    }

    public func deleteChatSession(id: String) {
        guard let index = chatSessions.firstIndex(where: { $0.id == id }) else {
            return
        }
        let deletingSelectedSession = selectedChatSession?.id == id
        chatSessions.remove(at: index)

        if chatSessions.isEmpty {
            selectedChatSessionID = ""
            chatTranscript = []
            chatConversationMessages = []
            chatComposerText = ""
            chatStatusText = "Idle"
            lastChatUsageText = ""
            lastChatRequestID = ""
            isChatStreaming = false
        } else if deletingSelectedSession {
            let nextIndex = min(index, chatSessions.count - 1)
            loadChatSession(chatSessions[nextIndex])
        }
        notifyStateChanged()
    }

    public func bindSelectedChatSessionToServer(serverSessionID: String) {
        guard
            let selectedChatSession,
            let serverSession = serverSession(id: serverSessionID)
        else {
            return
        }

        replaceChatSession(id: selectedChatSession.id) { session in
            session.serverSessionID = serverSession.id
            if session.statusText == "Choose Server" || session.statusText == "No Server Session" {
                session.statusText = "Idle"
            }
            session.updatedAt = Date()
        }
        selectedServerSessionID = serverSession.id
        selectedChatModelID = serverSession.modelID
        if selectedChatSessionID == selectedChatSession.id {
            chatStatusText = chatStatusText == "Choose Server" || chatStatusText == "No Server Session"
                ? "Idle"
                : chatStatusText
        }
        if let updatedSession = self.selectedChatSession {
            loadChatSession(updatedSession)
        }
        notifyStateChanged()
    }

    @discardableResult
    public func exportSelectedChatSession() -> String? {
        guard let session = selectedChatSession else {
            return nil
        }
        let sanitizedName = session.title.replacingOccurrences(of: " ", with: "-").lowercased()
        let exportURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(sanitizedName)-export.md")
        let lines = session.transcript.map { entry in
            "## \(sanitizedRichText(entry.title))\n\n\(sanitizedRichText(entry.body))\n"
        }
        let payload = """
        # \(sanitizedRichText(session.title))

        - Server Session: \(session.serverSessionID)
        - Branch: \(sanitizedRichText(session.branchTitle))
        - Status: \(sanitizedRichText(session.statusText))

        \(lines.joined(separator: "\n"))
        """

        do {
            try payload.write(to: exportURL, atomically: true, encoding: .utf8)
            replaceChatSession(id: session.id) { chat in
                chat.exportPath = exportURL.path
                chat.updatedAt = Date()
            }
            if selectedChatSessionID == session.id {
                lastChatRequestID = session.requestID
            }
            notifyStateChanged()
            return exportURL.path
        } catch {
            recordLocalError("Chat export failed: \(error)")
            notifyStateChanged()
            return nil
        }
    }

    public func serverSession(id: String) -> DesktopServerSessionState? {
        serverSessions.first(where: { $0.id == id })
    }

    public var primaryModel: RuntimeModelRow? {
        if let selectedModelID = selectedServerSession?.modelID,
           let selectedModel = models.first(where: { $0.modelID == selectedModelID })
        {
            return selectedModel
        }
        return models.first { $0.modelID == "melix-dev-text" } ?? models.first
    }

    public var desktopRuntimeEndpointState: DesktopRuntimeEndpointState {
        guard let session = selectedServerSession else {
            return .fallback
        }
        return DesktopRuntimeEndpointState(
            serverSessionID: session.id,
            serverTitle: session.title,
            modelID: session.modelID,
            requestedBaseURL: session.baseURL,
            effectiveBaseURL: session.effectiveBaseURL,
            sharedAccessSummaryText: session.sharedAccessSummaryText
        )
    }

    private var primaryModelSummary: Melix_Controlplane_V1_ModelSummary? {
        guard let modelID = primaryModel?.modelID else {
            return nil
        }
        return latestSnapshot.models.first(where: { $0.modelID == modelID })
    }

    public var selectedServerSession: DesktopServerSessionState? {
        guard !selectedServerSessionID.isEmpty else {
            return serverSessions.first
        }
        return serverSessions.first(where: { $0.id == selectedServerSessionID }) ?? serverSessions.first
    }

    public var selectedChatSession: DesktopChatSessionState? {
        guard !selectedChatSessionID.isEmpty else {
            return chatSessions.first
        }
        return chatSessions.first(where: { $0.id == selectedChatSessionID }) ?? chatSessions.first
    }

    public var selectedChatServerSession: DesktopServerSessionState? {
        guard
            let selectedChatSession,
            selectedChatSession.hasServerBinding
        else {
            return nil
        }
        return serverSession(id: selectedChatSession.serverSessionID)
    }

    public var selectedAgentIntegrationExport: AgentIntegrationExport? {
        agentIntegrationExports.first(where: { $0.target == selectedAgentIntegrationTarget })
        ?? agentIntegrationExports.first
    }

    public var desktopBannerState: DesktopBannerState? {
        desktopSignalStates.first { $0.priority >= .recovery }
    }

    public var desktopSignalStates: [DesktopBannerState] {
        resolvedDesktopSignals().filter { banner in
            banner.isDismissible == false || dismissedBannerIDs.contains(banner.id) == false
        }.sorted { lhs, rhs in
            if lhs.priority == rhs.priority {
                return lhs.title < rhs.title
            }
            return lhs.priority > rhs.priority
        }
    }

    public var recoverableDownloads: [RuntimeDownloadQueueEntryState] {
        downloadQueue.filter(\.resumeReady)
    }

    public var activeDownloads: [RuntimeDownloadQueueEntryState] {
        downloadQueue.filter(\.isActive)
    }

    public func dismissDesktopBanner(id: String? = nil) {
        let banner = desktopSignalStates.first { candidate in
            guard let id else {
                return true
            }
            return candidate.id == id
        }
        guard let banner, banner.isDismissible else {
            return
        }
        dismissedBannerIDs.insert(banner.id)
        notifyStateChanged()
    }

    private func resolvedDesktopSignals() -> [DesktopBannerState] {
        var signals: [DesktopBannerState] = []
        if let missingModel = models.first(where: \.runtimeCacheMissing) {
            signals.append(
                DesktopBannerState(
                    id: "model-runtime-cache-missing-\(missingModel.modelID)",
                    title: "Missing model cache: \(missingModel.modelID)",
                    detail: missingModel.runtimeCacheDetailText,
                    severity: .warning,
                    isRecoverable: true
                )
            )
        }
        if serverStateText == "Failed" || connectionStateText == "Degraded" {
            signals.append(
                DesktopBannerState(
                    id: "runtime-critical",
                    title: "Operator Attention Required",
                    detail: lastError ?? connectionDetailText,
                    severity: .critical
                )
            )
        }
        if let failingServer = serverSessions.first(where: { $0.lifecycle == .error }) {
            signals.append(
                DesktopBannerState(
                    id: "server-session-\(failingServer.id)-critical",
                    title: "\(failingServer.title) Needs Recovery",
                    detail: failingServer.lastError,
                    severity: .critical
                )
            )
        }
        if serverStateText == "Degraded" || serverStateText == "Draining" || connectionStateText == "Reconnecting" {
            signals.append(
                DesktopBannerState(
                    id: "runtime-monitoring",
                    title: "Runtime Needs Monitoring",
                    detail: connectionDetailText,
                    severity: .warning
                )
            )
        }
        if let selectedServerBanner = selectedServerSession?.lifecycleBannerState,
           selectedServerSession?.lifecycle != .unavailable
        {
            signals.append(selectedServerBanner)
        }
        if let recoverableDownload = recoverableDownloads.first {
            let detail = recoverableDownloads.count == 1
                ? "\(recoverableDownload.sourceModel) • \(recoverableDownload.progressText)"
                : "\(recoverableDownloads.count) downloads can resume • \(recoverableDownload.progressText)"
            signals.append(
                DesktopBannerState(
                    id: "download-recovery",
                    title: "Download Recovery Available",
                    detail: detail,
                    severity: .warning,
                    isRecoverable: true
                )
            )
        } else if let activeDownload = activeDownloads.first {
            let detail = activeDownloads.count == 1
                ? "\(activeDownload.sourceModel) • \(activeDownload.progressText)"
                : "\(activeDownloads.count) downloads in progress • \(activeDownload.progressText)"
            signals.append(
                DesktopBannerState(
                    id: "download-queue-active",
                    title: "Download Queue Active",
                    detail: detail,
                    severity: .info
                )
            )
        }
        if let updateBanner = productUpdateBannerState {
            signals.append(updateBanner)
        }
        return signals
    }

    public var audioSetupActions: [RuntimeAudioSetupActionState] {
        latestSnapshot.models.compactMap { model in
            let backendID = model.settings.ext["melix.audio.backend_id"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard backendID.hasPrefix("mlx_audio.") else {
                return nil
            }

            let alias = model.settings.alias.isEmpty ? model.modelID : model.settings.alias
            let runtimePackState = model.settings.ext["melix.audio.runtime_pack_state"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if runtimePackState != "installed" {
                let runtimePackID = model.settings.ext["melix.audio.runtime_pack_id"]?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? "melix-audio-runtime-pack"
                return RuntimeAudioSetupActionState(
                    modelID: model.modelID,
                    alias: alias,
                    detail: "Install \(runtimePackID) to enable audio requests for \(alias).",
                    actionTitle: "Install Audio Support",
                    kind: .installRuntime
                )
            }

            let modelState = model.settings.ext["melix.audio.model_state"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard modelState != "managed_local" else {
                return nil
            }
            return RuntimeAudioSetupActionState(
                modelID: model.modelID,
                alias: alias,
                detail: "Download \(alias) into Melix managed storage before serving audio requests.",
                actionTitle: "Download Audio Model",
                kind: .downloadModel
            )
        }
    }

    public var latestAdapterPackage: RuntimeAdapterPackageState? {
        adapterPackages.first
    }

    public var loraCapableModels: [RuntimeModelRow] {
        models.filter { $0.kind == "text" }
    }

    public var selectedLoraModel: RuntimeModelRow? {
        let modelID = resolvedLoraModelID()
        return loraCapableModels.first(where: { $0.modelID == modelID }) ?? loraCapableModels.first
    }

    public var selectedAdapterPackage: RuntimeAdapterPackageState? {
        guard !selectedAdapterPackageID.isEmpty else {
            return adapterPackages.first
        }
        return adapterPackages.first(where: { $0.id == selectedAdapterPackageID }) ?? adapterPackages.first
    }

    public var registryRootSummaryText: String {
        if registryHasConfiguredRootOverride {
            let count = registryConfiguredRootPaths.count
            return count == 0
                ? "Control-plane override active • no roots configured"
                : "Control-plane override active • \(count) roots configured"
        }
        if registryRoots.isEmpty {
            return "Using environment roots • no snapshot loaded yet"
        }
        return "Using environment roots • \(registryRoots.count) roots observed"
    }

    public var canAddRegistryRoot: Bool {
        Self.normalizedRegistryRootPath(registryRootPathDraft) != nil
    }

    public var imageModels: [RuntimeModelRow] {
        models.filter { $0.kind == "image" || $0.kind == "image_generation" }
    }

    public var selectedImageModelID: String {
        get { selectedImageGenerateModelID }
        set { selectedImageGenerateModelID = newValue }
    }

    public func imageModels(for role: RuntimeImageWorkflowRole) -> [RuntimeModelRow] {
        imageModels
            .filter { Self.imageModel($0, supports: role) }
            .sorted { lhs, rhs in
                let lhsPreferred = lhs.imageDefaultWorkflowRole == role.rawValue
                let rhsPreferred = rhs.imageDefaultWorkflowRole == role.rawValue
                if lhsPreferred != rhsPreferred {
                    return lhsPreferred && !rhsPreferred
                }
                return lhs.modelID < rhs.modelID
            }
    }

    public func selectedImageModelID(for role: RuntimeImageWorkflowRole) -> String {
        switch role {
        case .generate:
            return selectedImageGenerateModelID
        case .edit:
            return selectedImageEditModelID
        }
    }

    public func setSelectedImageModelID(_ modelID: String, for role: RuntimeImageWorkflowRole) {
        switch role {
        case .generate:
            selectedImageGenerateModelID = modelID
        case .edit:
            selectedImageEditModelID = modelID
        }
        notifyStateChanged()
    }

    public var selectedImageJob: Melix_Controlplane_V1_ImageJobSummary? {
        guard !selectedImageJobID.isEmpty else {
            return imageJobs.first
        }
        return imageJobs.first(where: { $0.jobID == selectedImageJobID }) ?? imageJobs.first
    }

    public var imageTimeoutPolicyText: String {
        let minutes = max(1, Int(imageRequestTimeoutSeconds) / 60)
        if minutes * 60 == Int(imageRequestTimeoutSeconds) {
            return "\(minutes)-minute creative workflow deadline"
        }
        return "\(imageRequestTimeoutSeconds)-second creative workflow deadline"
    }

    public var selectedImageJobTimeoutText: String {
        guard let job = selectedImageJob else {
            return imageTimeoutPolicyText
        }
        let timeoutSeconds = job.timeoutSeconds == 0 ? imageRequestTimeoutSeconds : job.timeoutSeconds
        let minutes = max(1, Int(timeoutSeconds) / 60)
        let policyText = minutes * 60 == Int(timeoutSeconds)
            ? "\(minutes)-minute deadline"
            : "\(timeoutSeconds)-second deadline"
        if job.error.code == "deadline_exceeded" {
            return "Timed out • \(policyText)"
        }
        return policyText
    }

    public var canRedoSelectedImageJob: Bool {
        selectedImageJob.map(Self.canRedoImageJob(_:)) ?? false
    }

    public var canPrepareReiterateFromSelectedImageJob: Bool {
        selectedImageJob.flatMap(Self.reiterateSourceArtifactID(from:)) != nil
    }

    public var imageEditSourceArtifactSummaryText: String? {
        let artifactID = imageEditSourceArtifactID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !artifactID.isEmpty else {
            return nil
        }
        if let artifact = selectedImageJob?.artifacts.first(where: { $0.artifactID == artifactID }) {
            return "\(artifactID) • \(artifact.storageUri)"
        }
        return artifactID
    }

    public var desktopFoundationState: DesktopFoundationState {
        DesktopFoundationState.build(
            statusTitle: statusTitle,
            serverStateText: serverStateText,
            connectionStateText: connectionStateText,
            connectionDetailText: connectionDetailText,
            snapshot: latestSnapshot,
            protocolVersion: protocolVersion,
            serverVersion: serverVersion,
            daemonInstanceID: daemonInstanceID,
            features: features,
            productUpdateSummary: productUpdateSummary,
            productUpdateDetail: productUpdateDetail,
            lastError: lastError,
            recentEvents: recentEvents
        )
    }

    public var benchmarkModels: [RuntimeModelRow] {
        models.filter(Self.isBenchmarkEligibleModel)
    }

    public var benchmarkSuites: [RuntimeBenchmarkSuiteOptionState] {
        Self.benchmarkSuiteOptions.filter { $0.taskKind == resolvedBenchmarkTaskKind() }
    }

    public var evaluationModels: [RuntimeModelRow] {
        models.filter { $0.kind == "text" }
    }

    public var evaluationCompareTargetModels: [RuntimeModelRow] {
        let baseModelID = selectedEvaluationTargetMode == .catalogModel ? resolvedEvaluationModelID() : ""
        return evaluationModels.filter { model in
            baseModelID.isEmpty || model.modelID != baseModelID
        }
    }

    public var evaluationSuites: [RuntimeEvaluationSuiteOptionState] {
        Self.evaluationSuiteOptions
    }

    public var benchmarkTargetTaskKind: String {
        resolvedBenchmarkTaskKind()
    }

    public var benchmarkTargetTaskTitle: String {
        Self.benchmarkTaskTitle(for: resolvedBenchmarkTaskKind())
    }

    public var benchmarkTargetSummaryText: String {
        switch selectedBenchmarkTargetMode {
        case .catalogModel:
            guard let model = latestSnapshot.models.first(where: { $0.modelID == resolvedBenchmarkModelID() }) else {
                return "Select a benchmark-capable catalog model."
            }
            let alias = model.settings.alias.trimmingCharacters(in: .whitespacesAndNewlines)
            let label = alias.isEmpty ? model.modelID : "\(alias) • \(model.modelID)"
            return "\(benchmarkTargetTaskTitle) • \(label)"
        case .huggingFaceRepo:
            let repoID = benchmarkHFRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
            if repoID.isEmpty {
                return "Enter a Hugging Face repo to detect a supported benchmark task."
            }
            return "\(benchmarkTargetTaskTitle) • \(repoID)"
        }
    }

    public var benchmarkMatrixCellCount: Int {
        ControlPlaneBenchMatrixRequest(
            suites: selectedBenchmarkSuiteIDs.sorted(),
            contextLengths: normalizedBenchContextLengths(),
            generationLengths: normalizedBenchGenerationLengths(),
            batchSizes: normalizedBenchBatchSizes(),
            cacheProfiles: normalizedBenchMatrixCacheProfiles(),
            reasoningModes: normalizedBenchMatrixReasoningModes(),
            structuredOutputModes: normalizedBenchMatrixStructuredOutputModes(),
            concurrencyLevels: normalizedBenchMatrixConcurrencyLevels()
        ).matrixCellCount
    }

    public var benchmarkMatrixCellCountText: String {
        "\(benchmarkMatrixCellCount) cells"
    }

    public var benchmarkMatrixLoadBudgetSummaryText: String {
        switch selectedBenchmarkMatrixLoadBudgetMode {
        case .requests:
            return "Requests • \(normalizedBenchMatrixRequests())"
        case .durationSeconds:
            return "Duration • \(normalizedBenchMatrixDurationSeconds())s"
        }
    }

    public var evaluationTargetTaskKind: String {
        "text-generation"
    }

    public var evaluationTargetTaskTitle: String {
        Self.benchmarkTaskTitle(for: evaluationTargetTaskKind)
    }

    public var evaluationTargetSummaryText: String {
        switch selectedEvaluationTargetMode {
        case .catalogModel:
            guard let model = latestSnapshot.models.first(where: { $0.modelID == resolvedEvaluationModelID() }) else {
                return "Select a text-generation model for Evaluation."
            }
            let alias = model.settings.alias.trimmingCharacters(in: .whitespacesAndNewlines)
            let label = alias.isEmpty ? model.modelID : "\(alias) • \(model.modelID)"
            return "\(evaluationTargetTaskTitle) • \(label)"
        case .huggingFaceRepo:
            let repoID = evaluationHFRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
            if repoID.isEmpty {
                return "Enter a Hugging Face text-generation repo for Evaluation."
            }
            return "\(evaluationTargetTaskTitle) • \(repoID)"
        }
    }

    public var selectedBenchmarkHistoryEntry: RuntimeBenchmarkHistoryEntryState? {
        benchmarkHistory.first(where: { $0.jobID == selectedBenchmarkHistoryJobID })
            ?? benchmarkHistory.first
    }

    public var selectedBenchmarkMatrixHistoryEntry: RuntimeBenchmarkMatrixHistoryEntryState? {
        benchmarkMatrixHistory.first(where: { $0.jobID == selectedBenchmarkMatrixHistoryJobID })
            ?? benchmarkMatrixHistory.first
    }

    public var selectedEvaluationHistoryEntry: RuntimeEvaluationHistoryEntryState? {
        evaluationHistory.first(where: { $0.jobID == selectedEvaluationHistoryJobID })
            ?? evaluationHistory.first
    }

    private var selectedServerSessionID = ""
    private var selectedChatSessionID = ""

    public func start() async {
        let restoreStartedAt = Date()
        restoreOperatorSessionState()
        operatorStateRestored = true
        await refreshProductSignals()
        await metrics.record(
            name: "operator.session_restore_ms",
            valueMs: Date().timeIntervalSince(restoreStartedAt) * 1_000
        )
        await metrics.record(
            name: "gateway.api_key_persist_failures",
            valueMs: gatewayAPIKeyPersistFailures
        )

        await transitionConnectionState(to: "Connecting", detail: "Awaiting handshake")
        let handshakeStartedAt = Date()

        do {
            let response = try await client.handshake()
            protocolVersion = response.protocolVersion
            serverVersion = response.serverVersion
            daemonInstanceID = response.daemonInstanceID
            features = response.features
            await metrics.record(
                name: "menu.handshake_ms",
                valueMs: Date().timeIntervalSince(handshakeStartedAt) * 1_000
            )

            let hydrationStartedAt = Date()
            apply(snapshot: response.snapshot)
            await metrics.record(
                name: "menu.hydration_ms",
                valueMs: Date().timeIntervalSince(hydrationStartedAt) * 1_000
            )
            await startSubscription(lastSeenSeq: lastSeenSeq, isReconnect: false)
        } catch {
            await transitionConnectionState(to: "Degraded", detail: "Handshake failed")
            if let diagnostic = productInstallStateProvider.startupFailureDiagnostic(for: error) {
                setLastError(diagnostic.userMessage)
                await metrics.record(name: "startup.failure_classification_count", valueMs: 1)
            } else {
                setLastError(startupFailureMessage(error))
                await metrics.record(name: "startup.failure_classification_count", valueMs: 0)
            }
            statusTitle = "Melix Error"
            notifyStateChanged()
        }
    }

    public func refreshDesktopFoundation() async {
        let startedAt = Date()

        do {
            let snapshot = try await client.serverSnapshot()
            apply(snapshot: snapshot)
            let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
            await metrics.record(
                name: "menu.foundation_refresh_ms",
                valueMs: elapsedMs
            )
            if snapshot.imageJobs.isEmpty == false {
                await metrics.record(name: "desktop.image_refresh_ms", valueMs: elapsedMs)
            }
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    public func loadModel(modelID: String) async {
        if let model = runtimeCacheMissingModel(for: modelID) {
            markServerSessions(for: modelID, lifecycle: .error, error: model.runtimeCacheDetailText)
            recordLocalError(model.runtimeCacheDetailText)
            notifyStateChanged()
            return
        }
        let startedAt = Date()
        do {
            let requestedMemoryBudgetBytes = resolvedModelLoadMemoryBudgetBytes(for: modelID)
            let model: Melix_Controlplane_V1_ModelSummary
            if let operatorCommandRunner {
                model = try await operatorCommandRunner.loadModel(
                    modelID: modelID,
                    memoryBudgetBytes: requestedMemoryBudgetBytes
                )
            } else {
                model = try await client.loadModel(
                    modelID: modelID,
                    memoryBudgetBytes: requestedMemoryBudgetBytes
                )
            }
            await metrics.record(
                name: "menu.model_load_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            markServerSessions(for: modelID, lifecycle: .error, error: String(describing: error))
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    private func runtimeCacheMissingModel(for modelID: String) -> RuntimeModelRow? {
        if let model = models.first(where: { $0.modelID == modelID && $0.runtimeCacheMissing }) {
            return model
        }
        if let model = latestSnapshot.models.first(where: { $0.modelID == modelID }),
           ModelRuntimeAvailability.isRuntimeCacheMissing(model) {
            return makeRuntimeModelRow(model)
        }
        return nil
    }

    public func submitChatPrompt() async {
        let prompt = chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            return
        }
        guard !isChatStreaming else {
            return
        }

        guard let serverSession = selectedChatServerSession else {
            guard selectedChatSession != nil || serverSessions.isEmpty == false else {
                chatStatusText = "No Server Session"
                setLastError("Create a Server Session before sending chat prompts.")
                selectedSurface = .server
                notifyStateChanged()
                return
            }
            chatStatusText = "Choose Server"
            setLastError("Choose a Server Session before sending chat prompts.")
            selectedSurface = .chat
            if let selectedChatSession {
                replaceChatSession(id: selectedChatSession.id) { session in
                    session.statusText = "Choose Server"
                    session.updatedAt = Date()
                }
            }
            notifyStateChanged()
            return
        }
        guard serverSession.isInteractiveReady else {
            chatStatusText = serverSession.lifecycle.rawValue
            setLastError(chatSubmissionBlockedMessage(for: serverSession))
            selectedSurface = .chat
            notifyStateChanged()
            return
        }

        let modelID = resolvedChatModelID()
        if models.contains(where: { $0.modelID == modelID }) == false {
            await refreshDesktopFoundation()
        }
        if let missingModel = runtimeCacheMissingModel(for: modelID) {
            chatComposerText = ""
            let userMessage = ControlPlaneChatRequest.Message(role: "user", content: prompt)
            chatConversationMessages.append(userMessage)
            resetChatPresentationState()
            appendChatEntry(
                id: "user-\(UUID().uuidString)",
                kind: .user,
                title: "User",
                body: prompt,
                detail: ""
            )
            chatStatusText = "Failed • \(ModelRuntimeAvailability.missingRuntimeCacheCode)"
            setLastError(missingModel.runtimeCacheDetailText)
            appendChatEntry(
                id: "error-\(UUID().uuidString)",
                kind: .error,
                title: "Error",
                body: missingModel.runtimeCacheDetailText,
                detail: ""
            )
            notifyStateChanged()
            return
        }
        chatComposerText = ""
        let startedAt = Date()
        let userMessage = ControlPlaneChatRequest.Message(role: "user", content: prompt)
        chatConversationMessages.append(userMessage)
        resetChatPresentationState()
        appendChatEntry(
            id: "user-\(UUID().uuidString)",
            kind: .user,
            title: "User",
            body: prompt,
            detail: ""
        )
        let pendingAssistantEntryID = "assistant-\(UUID().uuidString)"
        activeAssistantEntryID = pendingAssistantEntryID
        appendChatEntry(
            id: pendingAssistantEntryID,
            kind: .assistant,
            title: "Assistant",
            body: "",
            detail: ""
        )
        chatStatusText = "Preparing"
        lastChatUsageText = ""
        isChatStreaming = true
        notifyStateChanged()

        if shouldPreloadChatModel(modelID: modelID) {
            await loadModel(modelID: modelID)
        }

        do {
            let execution = try await client.startChat(
                ControlPlaneChatRequest(
                    modelID: modelID,
                    messages: chatConversationMessages
                )
            )
            lastChatRequestID = execution.requestID
            await metrics.record(
                name: "menu.chat_submit_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )

            var recordedFirstDelta = false
            var reasoningDeltaCount = 0
            var toolDeltaCount = 0

            for try await event in execution.stream {
                if recordedFirstDelta == false {
                    switch event {
                    case .tokenDelta, .reasoningDelta, .toolCallDelta:
                        recordedFirstDelta = true
                        await metrics.record(
                            name: "menu.chat_first_delta_ms",
                            valueMs: Date().timeIntervalSince(startedAt) * 1_000
                        )
                    default:
                        break
                    }
                }

                switch event {
                case .queued(let lane, let queuePosition, _):
                    chatStatusText = "Queued • \(lane) • #\(queuePosition)"
                case .admitted(let lane, let workerID, _):
                    chatStatusText = "Admitted • \(lane) • \(workerID)"
                case .prefillStarted(let inputTokens):
                    chatStatusText = "Prefill • \(inputTokens) tokens"
                case .decodeStarted(let decodeHandle, _):
                    chatStatusText = decodeHandle.isEmpty ? "Decode" : "Decode • \(decodeHandle)"
                case .tokenDelta(let text):
                    appendAssistantDelta(text, requestID: execution.requestID)
                    await Task.yield()
                case .reasoningDelta(let text):
                    reasoningDeltaCount += 1
                    appendReasoningDelta(text, requestID: execution.requestID)
                    await Task.yield()
                case .toolCallDelta(let callID, let toolName, let argumentsFragment):
                    toolDeltaCount += 1
                    appendToolDelta(callID: callID, toolName: toolName, argumentsFragment: argumentsFragment)
                    await Task.yield()
                case .usage(let promptTokens, let completionTokens):
                    lastChatUsageText = "\(promptTokens) prompt • \(completionTokens) completion"
                case .completed(let finishReason, let assistantText, let reasoningText):
                    flushPendingChatPresentation()
                    chatStatusText = finishReason.isEmpty ? "Completed" : "Completed • \(finishReason)"
                    finalizeAssistantText(assistantText, requestID: execution.requestID)
                    finalizeReasoningText(reasoningText, requestID: execution.requestID)
                    removeEmptyPendingAssistantEntryIfNeeded()
                case .failed(let code, let message):
                    flushPendingChatPresentation()
                    chatStatusText = code.isEmpty ? "Failed" : "Failed • \(code)"
                    let failureMessage = message.isEmpty ? "Chat request failed." : message
                    setLastError(failureMessage)
                    removeEmptyPendingAssistantEntryIfNeeded()
                    appendChatEntry(
                        id: "error-\(UUID().uuidString)",
                        kind: .error,
                        title: "Error",
                        body: failureMessage,
                        detail: code
                    )
                case .heartbeat:
                    chatStatusText = "Streaming"
                }

                notifyStateChanged()
            }

            flushPendingChatPresentation()
            removeEmptyPendingAssistantEntryIfNeeded()
            await metrics.record(
                name: "menu.chat_stream_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            await metrics.record(
                name: "menu.chat_reasoning_delta_count",
                valueMs: Double(reasoningDeltaCount)
            )
            await metrics.record(
                name: "menu.chat_tool_delta_count",
                valueMs: Double(toolDeltaCount)
            )
            await recordChatPresentationMetricsIfNeeded()
            commitAssistantMessageIfNeeded()
        } catch {
            flushPendingChatPresentation()
            let failure = chatFailureDisplay(for: error)
            setLastError(failure.message)
            chatStatusText = failure.code.isEmpty ? "Failed" : "Failed • \(failure.code)"
            removeEmptyPendingAssistantEntryIfNeeded()
            appendChatEntry(
                id: "error-\(UUID().uuidString)",
                kind: .error,
                title: "Error",
                body: failure.message,
                detail: failure.code
            )
        }

        isChatStreaming = false
        resetChatPresentationState()
        activeAssistantEntryID = nil
        activeReasoningEntryID = nil
        activeToolEntryIDs.removeAll()
        notifyStateChanged()
    }

    private func chatFailureDisplay(for error: Error) -> (code: String, message: String) {
        if let error = error as? ControlPlaneChatExecutionError {
            switch error {
            case .requestFailed(let code, let message):
                let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
                return (
                    code,
                    trimmed.isEmpty && code == ModelRuntimeAvailability.missingRuntimeCacheCode
                        ? ModelRuntimeAvailability.missingRuntimeCacheMessage
                        : (trimmed.isEmpty ? code : trimmed)
                )
            case .unavailable, .unavailableReason:
                break
            }
        }
        return ("", String(describing: error))
    }

    public func clearChatTranscript() {
        resetChatPresentationState()
        chatTranscript = []
        chatConversationMessages = []
        chatStatusText = "Idle"
        lastChatUsageText = ""
        lastChatRequestID = ""
        activeAssistantEntryID = nil
        activeReasoningEntryID = nil
        activeToolEntryIDs.removeAll()
        replaceChatSession(id: selectedChatSessionID) { session in
            session.transcript = []
            session.statusText = "Idle"
            session.usageText = ""
            session.requestID = ""
            session.updatedAt = Date()
        }
        notifyStateChanged()
    }

    private func shouldPreloadChatModel(modelID: String) -> Bool {
        guard let model = models.first(where: { $0.modelID == modelID }) else {
            return false
        }
        return model.isLoaded == false
    }

    public func selectImageJob(jobID: String) {
        selectedImageJobID = jobID
        notifyStateChanged()
    }

    public func submitImageGeneration() async {
        let prompt = imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            return
        }
        guard
            let imageSteps = normalizedOptionalUInt32Draft(imageSteps, fieldName: "Image steps"),
            let imageGuidance = normalizedOptionalDoubleDraft(imageGuidance, fieldName: "Image guidance")
        else {
            return
        }

        await submitImageGeneration(
            ControlPlaneImageGenerationRequest(
                modelID: resolvedImageModelID(for: .generate),
                prompt: prompt,
                size: imageSize,
                steps: imageSteps,
                guidance: Float(imageGuidance),
                negativePrompt: imageNegativePrompt.trimmingCharacters(in: .whitespacesAndNewlines),
                n: max(1, imageVariantCount)
            ),
            statusText: "Submitting",
            clearPromptOnSuccess: true
        )
    }

    public func submitImageEdit() async {
        let sourceURL = imageEditSourceURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let sourceArtifactID = imageEditSourceArtifactID.trimmingCharacters(in: .whitespacesAndNewlines)
        let selectedEditMode = imageEditMode
        let trimmedPrompt = imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines)
        let promptDelta = selectedEditMode == .iterate ? trimmedPrompt : ""

        if selectedEditMode == .variation || selectedEditMode == .iterate {
            guard !sourceArtifactID.isEmpty else {
                imageStatusText = "Failed"
                recordLocalError("Variation and iterate requests require a source artifact.")
                notifyStateChanged()
                return
            }
        }

        guard !sourceURL.isEmpty || !sourceArtifactID.isEmpty else {
            imageStatusText = "Failed"
            recordLocalError("Image edit source is required.")
            notifyStateChanged()
            return
        }
        if selectedEditMode == .iterate, promptDelta.isEmpty {
            imageStatusText = "Failed"
            recordLocalError("Iterate requests require a prompt delta.")
            notifyStateChanged()
            return
        }
        guard let imageSteps = normalizedOptionalUInt32Draft(imageSteps, fieldName: "Image steps"),
              let imageGuidance = normalizedOptionalDoubleDraft(imageGuidance, fieldName: "Image guidance"),
              let resolvedImageStrength = normalizedOptionalDoubleDraft(imageStrength, fieldName: "Image strength") else {
            return
        }
        guard resolvedImageStrength > 0, resolvedImageStrength <= 1 else {
            recordLocalError("Image strength must be between 0 and 1.")
            notifyStateChanged()
            return
        }

        await submitImageEdit(
            ControlPlaneImageEditRequest(
                modelID: resolvedImageModelID(for: .edit),
                prompt: selectedEditMode == .iterate ? "" : trimmedPrompt,
                imageURL: sourceArtifactID.isEmpty ? sourceURL : "",
                maskURL: imageEditMaskURL.trimmingCharacters(in: .whitespacesAndNewlines),
                sourceArtifactID: sourceArtifactID,
                promptDelta: promptDelta,
                mode: selectedEditMode.controlPlaneMode,
                strength: Float(resolvedImageStrength),
                size: imageSize,
                steps: imageSteps,
                guidance: Float(imageGuidance),
                negativePrompt: imageNegativePrompt.trimmingCharacters(in: .whitespacesAndNewlines),
                n: max(1, imageVariantCount)
            ),
            statusText: selectedEditMode == .iterate ? "Submitting Iterate" : "Submitting",
            clearPromptOnSuccess: true
        )
    }

    public func redoSelectedImageJob() async {
        guard let job = selectedImageJob, Self.canRedoImageJob(job) else {
            return
        }
        if job.operation == "image_generate" {
            await submitImageGeneration(Self.redoGenerationRequest(from: job), statusText: "Redoing", clearPromptOnSuccess: false)
            return
        }
        await submitImageEdit(Self.redoEditRequest(from: job), statusText: "Redoing", clearPromptOnSuccess: false)
    }

    public func prepareReiterateFromSelectedImageJob() {
        guard let job = selectedImageJob,
              let artifactID = Self.reiterateSourceArtifactID(from: job) else {
            return
        }
        if let imageModel = models.first(where: { $0.modelID == job.modelID && Self.imageModel($0, supports: .edit) }) {
            selectedImageEditModelID = imageModel.modelID
        }
        imageEditMode = .iterate
        imageEditSourceArtifactID = artifactID
        imageEditSourceURL = ""
        imageEditMaskURL = ""
        imagePromptText = ""
        if job.recipe.steps > 0 {
            imageSteps = String(job.recipe.steps)
        }
        if job.recipe.guidance > 0 {
            imageGuidance = Self.formatImageDefaultNumber(Double(job.recipe.guidance))
        }
        if job.recipe.strength > 0 {
            imageStrength = Self.formatImageDefaultNumber(Double(job.recipe.strength))
        }
        if job.recipe.size.isEmpty == false {
            imageSize = job.recipe.size
        }
        if job.recipe.negativePrompt.isEmpty == false {
            imageNegativePrompt = job.recipe.negativePrompt
        }
        imageStatusText = "Iterate draft seeded"
        notifyStateChanged()
    }

    private func submitImageGeneration(
        _ request: ControlPlaneImageGenerationRequest,
        statusText: String,
        clearPromptOnSuccess: Bool
    ) async {
        if models.contains(where: { $0.modelID == request.modelID && $0.isLoaded }) == false {
            await loadModel(modelID: request.modelID)
        }

        let startedAt = Date()
        imageStatusText = statusText
        notifyStateChanged()

        do {
            let job = try await client.generateImage(request)
            upsert(imageJob: job)
            imageStatusText = Self.imageStatusText(for: job)
            if clearPromptOnSuccess {
                imagePromptText = ""
            }
            await metrics.record(
                name: "desktop.image_action_latency_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            imageStatusText = "Failed"
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    private func submitImageEdit(
        _ request: ControlPlaneImageEditRequest,
        statusText: String,
        clearPromptOnSuccess: Bool
    ) async {
        if models.contains(where: { $0.modelID == request.modelID && $0.isLoaded }) == false {
            await loadModel(modelID: request.modelID)
        }

        let startedAt = Date()
        imageStatusText = statusText
        notifyStateChanged()

        do {
            let job = try await client.editImage(request)
            upsert(imageJob: job)
            imageStatusText = Self.imageStatusText(for: job)
            if clearPromptOnSuccess {
                imagePromptText = ""
            }
            if request.sourceArtifactID.isEmpty == false {
                imageEditSourceArtifactID = ""
                imageEditMode = .edit
            }
            await metrics.record(
                name: "desktop.image_action_latency_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            imageStatusText = "Failed"
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    public func applyImageDefaultsFromUI() {
        Task {
            await applyImageDefaults()
        }
    }

    public func applyImageDefaults() async {
        guard let imageSteps = normalizedOptionalUInt32Draft(imageSteps, fieldName: "Image steps"),
              let imageGuidance = normalizedOptionalDoubleDraft(imageGuidance, fieldName: "Image guidance"),
              let resolvedImageStrength = normalizedOptionalDoubleDraft(imageStrength, fieldName: "Image strength") else {
            return
        }
        guard resolvedImageStrength > 0, resolvedImageStrength <= 1 else {
            recordLocalError("Image strength must be between 0 and 1.")
            notifyStateChanged()
            return
        }

        let startedAt = Date()
        do {
            let summary = try await client.applyImageDefaults(
                ControlPlaneImageDefaultsRequest(
                    generateModelID: resolvedImageModelID(for: .generate),
                    editModelID: resolvedImageModelID(for: .edit),
                    size: imageSize.trimmingCharacters(in: .whitespacesAndNewlines),
                    steps: imageSteps,
                    guidance: Float(imageGuidance),
                    strength: Float(resolvedImageStrength),
                    negativePrompt: imageNegativePrompt.trimmingCharacters(in: .whitespacesAndNewlines)
                )
            )
            latestSnapshot.imageDefaults = summary
            applyImageDefaultsProjection()
            await metrics.record(
                name: "desktop.image_defaults_apply_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    public func cancelSelectedImageJob() async {
        guard let job = selectedImageJob, !job.requestID.isEmpty, job.cancelable else {
            return
        }

        let startedAt = Date()
        imageStatusText = "Canceling"
        notifyStateChanged()

        do {
            _ = try await client.cancelRequest(requestID: job.requestID)
            await metrics.record(
                name: "desktop.image_cancel_latency_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            imageStatusText = "Failed"
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    public func loadPrimaryModel() async {
        guard let primaryModel else {
            return
        }
        if primaryModel.runtimeCacheMissing {
            await restoreMissingRuntimeCache(modelID: primaryModel.modelID)
        } else {
            await loadModel(modelID: primaryModel.modelID)
        }
    }

    public func unloadModel(modelID: String) async {
        let startedAt = Date()
        do {
            let model: Melix_Controlplane_V1_ModelSummary
            if let operatorCommandRunner {
                model = try await operatorCommandRunner.unloadModel(modelID: modelID)
            } else {
                model = try await client.unloadModel(modelID: modelID)
            }
            await metrics.record(
                name: "menu.model_unload_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            markServerSessions(for: modelID, lifecycle: .error, error: String(describing: error))
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func unloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await unloadModel(modelID: modelID)
    }

    private func resolvedModelLoadMemoryBudgetBytes(for modelID: String) -> UInt64 {
        if modelSettingsDraftModelID == modelID,
           let draftValue = normalizedOptionalUInt64Draft(
               modelSettingsMemoryBudgetDraft,
               fieldName: "Memory budget bytes"
           ) {
            return draftValue
        }
        return primaryModelSummary?.modelID == modelID
            ? primaryModelSummary?.settings.memoryBudgetBytes ?? 0
            : latestSnapshot.models.first(where: { $0.modelID == modelID })?.settings.memoryBudgetBytes ?? 0
    }

    public func updateModelSettings(
        modelID: String,
        alias: String,
        typeOverride: String = "",
        ttlSeconds: String = "",
        pinOnLoad: Bool,
        memoryPolicy: String,
        memoryBudgetBytes: String = "",
        diskStreamingMode: String,
        cacheMode: String = "tiered",
        cacheMemoryBudgetBytes: String = "",
        cacheMemoryBudgetPct: String = "",
        cacheBlockSizeTokens: String = "",
        cacheDirectory: String = "",
        multimodalCacheBudgetBytes: String = "",
        accelerationMode: String,
        accelerationProfileID: String,
        adaptiveThinkingMode: String = "off",
        adaptiveThinkingBudgetTokens: String = "",
        toolParserXMLFallback: Bool = false,
        ocrSamplingProfileID: String = "",
        ocrDefaultTemperature: String = "",
        ocrDefaultTopP: String = "",
        ocrDefaultMaxTokens: String = "",
        includeOCRSettings: Bool = false
    ) async {
        let startedAt = Date()
        do {
            var values = [
                "alias": alias,
                "type_override": typeOverride,
                "ttl_seconds": ttlSeconds,
                "pin_on_load": pinOnLoad ? "true" : "false",
                "memory_policy": memoryPolicy,
                "memory_budget_bytes": memoryBudgetBytes,
                "disk_streaming_mode": diskStreamingMode,
                "cache_mode": cacheMode,
                "cache_memory_budget_bytes": cacheMemoryBudgetBytes,
                "cache_memory_budget_pct": cacheMemoryBudgetPct,
                "cache_block_size_tokens": cacheBlockSizeTokens,
                "cache_directory": cacheDirectory,
                "multimodal_cache_budget_bytes": multimodalCacheBudgetBytes,
                "default_acceleration_mode": accelerationMode,
                "acceleration_profile_id": accelerationProfileID,
                "adaptive_thinking_mode": adaptiveThinkingMode,
                "adaptive_thinking_budget_tokens": adaptiveThinkingBudgetTokens,
                "tool_parser_xml_fallback": toolParserXMLFallback ? "true" : "false",
            ]
            if includeOCRSettings {
                values["ocr_sampling_profile_id"] = ocrSamplingProfileID
                values["ocr_default_temperature"] = ocrDefaultTemperature
                values["ocr_default_top_p"] = ocrDefaultTopP
                values["ocr_default_max_tokens"] = ocrDefaultMaxTokens
            }
            let model = try await client.updateModelSettings(
                modelID: modelID,
                values: values
            )
            await metrics.record(
                name: "menu.model_settings_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
            synchronizeModelSettingsDrafts(force: true)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func applyPrimaryModelSettings() async {
        guard let model = primaryModelSummary else {
            return
        }

        guard
            normalizedOptionalUInt32Draft(
                modelSettingsTTLDraft,
                fieldName: "TTL seconds"
            ) != nil || modelSettingsTTLDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt32Draft(
                modelSettingsAdaptiveThinkingBudgetDraft,
                fieldName: "Adaptive thinking budget"
            ) != nil || modelSettingsAdaptiveThinkingBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt64Draft(
                modelSettingsMemoryBudgetDraft,
                fieldName: "Memory budget bytes"
            ) != nil || modelSettingsMemoryBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt64Draft(
                modelSettingsCacheMemoryBudgetDraft,
                fieldName: "Cache memory budget bytes"
            ) != nil || modelSettingsCacheMemoryBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt32Draft(
                modelSettingsCacheMemoryBudgetPctDraft,
                fieldName: "Cache memory budget percent"
            ) != nil || modelSettingsCacheMemoryBudgetPctDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt32Draft(
                modelSettingsCacheBlockSizeTokensDraft,
                fieldName: "Cache block size tokens"
            ) != nil || modelSettingsCacheBlockSizeTokensDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt64Draft(
                modelSettingsMultimodalCacheBudgetDraft,
                fieldName: "Multimodal cache budget bytes"
            ) != nil || modelSettingsMultimodalCacheBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalDoubleDraft(
                modelSettingsOCRTemperatureDraft,
                fieldName: "OCR temperature"
            ) != nil || modelSettingsOCRTemperatureDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalDoubleDraft(
                modelSettingsOCRTopPDraft,
                fieldName: "OCR top-p"
            ) != nil || modelSettingsOCRTopPDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        guard
            normalizedOptionalUInt32Draft(
                modelSettingsOCRMaxTokensDraft,
                fieldName: "OCR max tokens"
            ) != nil || modelSettingsOCRMaxTokensDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }

        await updateModelSettings(
            modelID: model.modelID,
            alias: modelSettingsAliasDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            typeOverride: modelSettingsTypeOverrideDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            ttlSeconds: modelSettingsTTLDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            pinOnLoad: modelSettingsPinOnLoadDraft,
            memoryPolicy: modelSettingsMemoryPolicyDraft,
            memoryBudgetBytes: modelSettingsMemoryBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            diskStreamingMode: modelSettingsDiskStreamingModeDraft,
            cacheMode: modelSettingsCacheModeDraft,
            cacheMemoryBudgetBytes: modelSettingsCacheMemoryBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            cacheMemoryBudgetPct: modelSettingsCacheMemoryBudgetPctDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            cacheBlockSizeTokens: modelSettingsCacheBlockSizeTokensDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            cacheDirectory: modelSettingsCacheDirectoryDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            multimodalCacheBudgetBytes: modelSettingsMultimodalCacheBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            accelerationMode: modelSettingsAccelerationModeDraft,
            accelerationProfileID: modelSettingsAccelerationProfileIDDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            adaptiveThinkingMode: modelSettingsAdaptiveThinkingModeDraft,
            adaptiveThinkingBudgetTokens: modelSettingsAdaptiveThinkingBudgetDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            toolParserXMLFallback: modelSettingsToolParserXMLFallbackDraft,
            ocrSamplingProfileID: modelSettingsOCRSamplingProfileDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            ocrDefaultTemperature: modelSettingsOCRTemperatureDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            ocrDefaultTopP: modelSettingsOCRTopPDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            ocrDefaultMaxTokens: modelSettingsOCRMaxTokensDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            includeOCRSettings: model.kind == "ocr"
        )
    }

    public func resetPrimaryModelSettingsDrafts() {
        synchronizeModelSettingsDrafts(force: true)
        notifyStateChanged()
    }

    public func updatePrimaryModelForLatency() async {
        guard let model = primaryModel else {
            return
        }
        await updateModelSettings(
            modelID: model.modelID,
            alias: model.alias.isEmpty ? "Melix Text Turbo" : model.alias,
            pinOnLoad: true,
            memoryPolicy: "pinned",
            diskStreamingMode: "disabled",
            accelerationMode: "speculative_decode",
            accelerationProfileID: "draft-q4"
        )
    }

    public func fetchModelInfo(modelID: String) async {
        let startedAt = Date()
        do {
            let info: Melix_Controlplane_V1_ModelInfo
            if let operatorCommandRunner {
                info = try await operatorCommandRunner.inspectModel(modelID: modelID)
            } else {
                info = try await client.modelInfo(modelID: modelID)
            }
            let snapshotModel = latestSnapshot.models.first(where: { $0.modelID == modelID })
            await metrics.record(
                name: "menu.model_info_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            let generationConfigSourceText = snapshotModel?.settings.ext["melix.generation_config.source"] ?? ""
            let generationConfigTemperatureText = snapshotModel?.settings.ext["melix.generation_config.temperature"] ?? ""
            let generationConfigTopPText = snapshotModel?.settings.ext["melix.generation_config.top_p"] ?? ""
            let generationConfigMaxTokensText = snapshotModel?.settings.ext["melix.generation_config.max_tokens"] ?? ""
            let audioInstallProfileText = snapshotModel?.settings.ext["melix.audio.install_profile"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioLanguagesText = snapshotModel?.settings.ext["melix.audio.languages"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioVoiceModeText = snapshotModel?.settings.ext["melix.audio.voice_mode"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioOutputFormatsText = snapshotModel?.settings.ext["melix.audio.output_formats"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let rawAudioSupportsInstructionsText = snapshotModel?.settings.ext["melix.audio.supports_instructions"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioSupportsInstructionsText = rawAudioSupportsInstructionsText.isEmpty
                ? ""
                : (rawAudioSupportsInstructionsText == "true" ? "Yes" : "No")
            let audioVoiceCatalogSummaryText = snapshotModel?.settings.ext["melix.audio.voice_catalog_summary"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioVoiceLocalesText = snapshotModel?.settings.ext["melix.audio.voice_locales"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioDefaultLocaleText = snapshotModel?.settings.ext["melix.audio.default_locale"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioPackagedDefaultLocaleText = snapshotModel?.settings.ext["melix.audio.packaged_default_locale"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioLocalePolicyText = snapshotModel?.settings.ext["melix.audio.locale_policy"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioRuntimePackStateText = snapshotModel?.settings.ext["melix.audio.runtime_pack_state"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioRuntimePackIDText = snapshotModel?.settings.ext["melix.audio.runtime_pack_id"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let audioModelStateText = snapshotModel?.settings.ext["melix.audio.model_state"]?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            selectedModelInfo = RuntimeModelInfoState(
                modelID: modelID,
                modelKind: info.modelKind,
                maxContext: info.maxContext,
                supportedParsers: info.supportedParsers,
                supportedModalities: info.supportedModalities,
                supportedTasks: info.supportedTasks,
                backendID: info.backendID,
                familyID: info.familyID,
                audioInstallProfileText: audioInstallProfileText,
                audioLanguagesText: audioLanguagesText,
                audioVoiceModeText: audioVoiceModeText,
                audioOutputFormatsText: audioOutputFormatsText,
                audioSupportsInstructionsText: audioSupportsInstructionsText,
                audioVoiceCatalogSummaryText: audioVoiceCatalogSummaryText,
                audioVoiceLocalesText: audioVoiceLocalesText,
                audioDefaultLocaleText: audioDefaultLocaleText,
                audioPackagedDefaultLocaleText: audioPackagedDefaultLocaleText,
                audioLocalePolicyText: audioLocalePolicyText,
                audioRuntimePackStateText: audioRuntimePackStateText,
                audioRuntimePackIDText: audioRuntimePackIDText,
                audioModelStateText: audioModelStateText,
                runtimeStatusText: snapshotModel.map {
                    ModelRuntimeAvailability.isRuntimeCacheMissing($0) ? "missing cache" : "ok"
                } ?? "",
                runtimePathText: snapshotModel.map {
                    ModelRuntimeAvailability.runtimePath(for: $0)
                } ?? "",
                registryDescriptorPathText: snapshotModel.map {
                    ModelRuntimeAvailability.descriptorPath(for: $0)
                } ?? "",
                restoreCommandText: snapshotModel.map {
                    ModelRuntimeAvailability.restoreCommand(for: $0)
                } ?? "",
                modelPath: info.modelPath,
                modelRevision: info.modelRevision,
                defaultWorkflowRole: info.defaultWorkflowRole,
                detectedIdentitySource: info.detectedIdentitySource,
                aliasText: snapshotModel?.settings.alias ?? "",
                typeOverrideText: snapshotModel?.settings.typeOverride ?? "",
                ttlSeconds: snapshotModel?.settings.ttlSeconds ?? 0,
                pinOnLoad: snapshotModel?.settings.pinOnLoad ?? false,
                memoryPolicyText: snapshotModel.map {
                    runtimeMemoryPolicyText(resolvedResidencyPolicy(for: $0))
                } ?? "Unspecified",
                memoryBudgetText: snapshotModel.map {
                    runtimeMemoryBudgetText($0.settings.memoryBudgetBytes)
                } ?? "",
                diskStreamingModeText: snapshotModel.map {
                    runtimeDiskStreamingModeText($0.settings.diskStreamingMode)
                } ?? "Disabled",
                adaptiveThinkingText: snapshotModel.map {
                    runtimeAdaptiveThinkingText($0.settings.adaptiveThinking)
                } ?? "Off",
                accelerationModeText: snapshotModel.map {
                    runtimeAccelerationModeText($0.settings.defaultAccelerationMode)
                } ?? "Unspecified",
                accelerationProfileID: snapshotModel?.settings.accelerationProfileID ?? "",
                toolParserFallbackText: snapshotModel.map(runtimeToolParserFallbackText) ?? "Off",
                ocrPromptProfileText: snapshotModel?.settings.ext["ocr_prompt_profile_id"] ?? "",
                ocrSamplingProfileText: snapshotModel.map {
                    runtimeEffectiveOCRSamplingProfileText(
                        for: $0,
                        generationConfigAvailable: !generationConfigTemperatureText.isEmpty
                            || !generationConfigTopPText.isEmpty
                            || !generationConfigMaxTokensText.isEmpty
                    )
                } ?? "",
                ocrTemperatureText: snapshotModel.map {
                    runtimeEffectiveOCRSamplingValue(
                        explicitValue: $0.settings.ext["ocr_default_temperature"] ?? "",
                        generationConfigValue: generationConfigTemperatureText
                    )
                } ?? "",
                ocrTopPText: snapshotModel.map {
                    runtimeEffectiveOCRSamplingValue(
                        explicitValue: $0.settings.ext["ocr_default_top_p"] ?? "",
                        generationConfigValue: generationConfigTopPText
                    )
                } ?? "",
                ocrMaxTokensText: snapshotModel.map {
                    runtimeEffectiveOCRSamplingValue(
                        explicitValue: $0.settings.ext["ocr_default_max_tokens"] ?? "",
                        generationConfigValue: generationConfigMaxTokensText
                    )
                } ?? "",
                cacheModeText: snapshotModel.map {
                    runtimeCacheModeText($0.cachePolicy.effectiveMode)
                } ?? "",
                cacheCompatibilityText: snapshotModel.map {
                    runtimeCacheCompatibilityText($0.cachePolicy.compatibility)
                } ?? "",
                cacheCompatibilityReasonText: snapshotModel?.cachePolicy.compatibilityReason ?? "",
                cacheDirectoryText: snapshotModel.map(runtimeCacheDirectoryText(for:)) ?? "",
                cacheBlockSizeText: snapshotModel.map(runtimeCacheBlockSizeText(for:)) ?? "",
                cacheBudgetText: snapshotModel.map(runtimeCacheBudgetText(for:)) ?? "",
                multimodalCacheBudgetText: snapshotModel.map(runtimeMultimodalCacheBudgetText(for:)) ?? "",
                cacheRootText: snapshotModel?.cachePolicy.effectiveDirectory ?? "",
                initialCacheBlocksText: snapshotModel.map(runtimeInitialCacheBlocksText(for:)) ?? "",
                generationConfigSourceText: generationConfigSourceText,
                generationConfigTemperatureText: generationConfigTemperatureText,
                generationConfigTopPText: generationConfigTopPText,
                generationConfigMaxTokensText: generationConfigMaxTokensText,
                ocrStopSequencesText: snapshotModel?.settings.ext["ocr_stop_sequences"] ?? ""
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func searchModelHub() async {
        let query = modelHubSearchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.isEmpty == false else {
            modelHubSearchResults = []
            modelHubNextCursor = ""
            selectedHubModelCard = nil
            notifyStateChanged()
            return
        }

        let startedAt = Date()
        do {
            let result: Melix_Controlplane_V1_HubSearchResult
            if let operatorCommandRunner {
                result = try await operatorCommandRunner.searchHubModels(
                    query: query,
                    mlxOnly: modelHubSearchMLXOnly
                )
            } else {
                result = try await client.searchHubModels(
                    query: query,
                    pageSize: 10,
                    cursor: "",
                    mlxOnly: modelHubSearchMLXOnly
                )
            }
            modelHubSearchResults = result.models.map { Self.makeHubModelSearchResultState(from: $0) }
            modelHubNextCursor = result.nextCursor
            let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
            await metrics.record(
                name: "menu.model_hub_search_ms",
                valueMs: elapsedMs
            )
            await metrics.record(name: "hub.metadata_enrichment_latency_ms", valueMs: elapsedMs)
            await recordRegistryProbeMetrics(
                maxHubResidentBytes: result.models.map(\.estimatedResidentBytes).max() ?? 0
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func inspectHubModel(repoID: String) async {
        let normalizedRepoID = repoID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedRepoID.isEmpty == false else {
            return
        }
        let startedAt = Date()
        do {
            let card: Melix_Controlplane_V1_HubModelCard
            if let operatorCommandRunner {
                card = try await operatorCommandRunner.getHubModelCard(repoID: normalizedRepoID)
            } else {
                card = try await client.getHubModelCard(repoID: normalizedRepoID)
            }
            selectedHubModelCard = Self.makeHubModelCardState(from: card)
            let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
            await metrics.record(
                name: "menu.model_hub_show_ms",
                valueMs: elapsedMs
            )
            await metrics.record(name: "hub.metadata_enrichment_latency_ms", valueMs: elapsedMs)
            if card.estimatedResidentBytes > 0 {
                await metrics.record(
                    name: "hub.local_fit_estimated_resident_bytes",
                    valueMs: Double(card.estimatedResidentBytes)
                )
            }
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func downloadHubModel(repoID: String) async {
        let revision = Self.normalizedOptionalString(modelHubSelectedRevision) ?? "main"
        await downloadHubModel(repoID: repoID, revision: revision)
    }

    public func restoreMissingRuntimeCache(modelID: String) async {
        guard let model = runtimeCacheMissingModel(for: modelID) else {
            return
        }
        guard !model.restoreRepoID.isEmpty else {
            recordLocalError(ModelRuntimeAvailability.missingRuntimeCacheMessage)
            notifyStateChanged()
            return
        }
        await downloadHubModel(repoID: model.restoreRepoID, revision: model.restoreRevision)
    }

    private func downloadHubModel(repoID: String, revision requestedRevision: String) async {
        let normalizedRepoID = repoID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedRepoID.isEmpty == false else {
            return
        }
        if let blockedReasons = blockedHubFitReasons(repoID: normalizedRepoID) {
            let reasonText = blockedReasons.isEmpty ? "" : " \(blockedReasons.joined(separator: " "))"
            recordLocalError("Download blocked: \(normalizedRepoID) is not suitable for local Melix runtime.\(reasonText)")
            await metrics.record(name: "registry.blocked_download_attempt_count", valueMs: 1)
            notifyStateChanged()
            return
        }
        let revision = Self.normalizedOptionalString(requestedRevision) ?? "main"
        let providedToken = Self.normalizedOptionalString(modelHubTokenDraft) ?? ""
        let effectiveToken: String
        if providedToken.isEmpty == false {
            do {
                let record = try huggingFaceTokenStore.saveToken(providedToken)
                modelHubTokenHint = record.maskedHint
                modelHubTokenDraft = ""
                effectiveToken = providedToken
            } catch {
                recordLocalError("Hugging Face token could not be saved: \(error)")
                notifyStateChanged()
                return
            }
        } else {
            effectiveToken = ((try? huggingFaceTokenStore.loadToken()?.token) ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            reloadHuggingFaceTokenHint()
        }
        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let receipt = try await cliWorkflowRunner.downloadHubModel(
                    repoID: normalizedRepoID,
                    revision: revision,
                    hfToken: effectiveToken
                )
                _ = try await cliWorkflowRunner.run(.modelRootsRescan(.init(json: true)))
                clearCLIWorkflowFailure()
                await applyManagedReceiptOperation(
                    receipt,
                    modelID: normalizedRepoID,
                    operation: "download",
                    startedAt: startedAt,
                    metricName: "menu.model_hub_download_ms"
                )
                await refreshDownloadQueueState(notify: false, surfaceErrors: false)
                await refreshDesktopFoundation()
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
                notifyStateChanged()
            }
            return
        }
        do {
            let result: Melix_Controlplane_V1_ModelOperationResult
            if let operatorCommandRunner {
                result = try await operatorCommandRunner.downloadHubModel(
                    repoID: normalizedRepoID,
                    revision: revision,
                    hfToken: effectiveToken
                )
            } else {
                var ext = [
                    "melix.source_kind": "hub_repo",
                    "melix.hf_repo_id": normalizedRepoID,
                    "melix.hf_revision": revision,
                    "melix.managed_import": "true",
                ]
                if effectiveToken.isEmpty == false {
                    ext["melix.hf_token"] = effectiveToken
                }
                result = try await client.runModelOperation(
                    modelID: normalizedRepoID,
                    operation: "download",
                    outputDir: "",
                    quantProfileID: "",
                    weightQuant: "",
                    kvQuant: "",
                    ext: ext
                )
            }
            await applyModelOperationResult(
                result,
                modelID: normalizedRepoID,
                startedAt: startedAt,
                metricName: "menu.model_hub_download_ms",
                refreshProductToolingState: false,
                loraWorkflowOperation: nil
            )
            await refreshDownloadQueueState(notify: false, surfaceErrors: false)
            await refreshDesktopFoundation()
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    private func recordRegistryProbeMetrics(maxHubResidentBytes: UInt64) async {
        await metrics.record(
            name: "registry.unified_entry_count",
            valueMs: Double(modelRegistryEntries.count)
        )
        if maxHubResidentBytes > 0 {
            await metrics.record(
                name: "hub.local_fit_estimated_resident_bytes",
                valueMs: Double(maxHubResidentBytes)
            )
        }
    }

    private func blockedHubFitReasons(repoID: String) -> [String]? {
        if let card = selectedHubModelCard, card.repoID == repoID, card.localFitStatus == "blocked" {
            return card.localFitReasons
        }
        if let result = modelHubSearchResults.first(where: { $0.repoID == repoID }),
           result.localFitStatus == "blocked" {
            return result.localFitReasons
        }
        return nil
    }

    public func inspectPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await fetchModelInfo(modelID: modelID)
    }

    public func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String = "",
        weightQuant: String = "",
        kvQuant: String = "",
        ext: [String: String] = [:],
        refreshProductToolingState: Bool = false
    ) async {
        let startedAt = Date()
        do {
            let result = try await performModelOperationRequest(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                quantProfileID: quantProfileID,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
            await applyModelOperationResult(
                result,
                modelID: modelID,
                startedAt: startedAt,
                metricName: "menu.model_operation_ms",
                refreshProductToolingState: refreshProductToolingState,
                loraWorkflowOperation: nil
            )
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    private func performModelOperationRequest(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        if let operatorCommandRunner {
            return try await operatorCommandRunner.performModelOperation(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                quantProfileID: quantProfileID,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
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

    private func runLoraModelOperation(
        modelID: String,
        workflowOperation: RuntimeLoraWorkflowOperation,
        outputDir: String,
        quantProfileID: String = "",
        weightQuant: String = "",
        kvQuant: String = "",
        ext: [String: String] = [:],
        refreshProductToolingState: Bool = false,
        runningDetail: String
    ) async {
        let startedAt = Date()
        beginLoraWorkflow(workflowOperation, detail: runningDetail)
        do {
            let result = try await performModelOperationRequest(
                modelID: modelID,
                operation: workflowOperation.rawValue,
                outputDir: outputDir,
                quantProfileID: quantProfileID,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
            await applyModelOperationResult(
                result,
                modelID: modelID,
                startedAt: startedAt,
                metricName: "menu.model_operation_ms",
                refreshProductToolingState: refreshProductToolingState,
                loraWorkflowOperation: workflowOperation
            )
        } catch {
            let errorMessage = workflowErrorMessage(error)
            recordLocalError(errorMessage)
            failLoraWorkflow(workflowOperation, detail: errorMessage)
            notifyStateChanged()
        }
    }

    private func applyModelOperationResult(
        _ result: Melix_Controlplane_V1_ModelOperationResult,
        modelID: String,
        startedAt: Date,
        metricName: String,
        refreshProductToolingState: Bool,
        loraWorkflowOperation: RuntimeLoraWorkflowOperation?
    ) async {
        await metrics.record(
            name: metricName,
            valueMs: Date().timeIntervalSince(startedAt) * 1_000
        )
        let manifestPayload = Self.jsonPayload(from: result.manifestJson)
        let compatibilityPayload = Self.dictionaryValue("compatibility", from: manifestPayload)
        lastModelOperation = RuntimeModelOperationState(
            modelID: modelID,
            operation: result.operation,
            jobID: result.jobID,
            stage: result.stage,
            pct: result.pct,
            outputPath: result.outputPath,
            manifestJson: result.manifestJson,
            quantProfileID: result.hasQuantProfile ? result.quantProfile.quantProfileID : "",
            artifactKind: result.hasArtifact ? result.artifact.artifactKind : "",
            manifestPath: result.hasArtifact ? result.artifact.manifestPath : "",
            artifactBytes: result.hasArtifact ? result.artifact.artifactBytes : 0,
            artifactRuntime: result.hasArtifact
                ? result.artifact.runtime
                : Self.stringValue("runtime", from: compatibilityPayload),
            servingCompatible: result.hasArtifact
                ? result.artifact.servingCompatible
                : Self.boolValue("serving_compatible", from: compatibilityPayload),
            smokeTestRequested: result.hasArtifact
                ? result.artifact.smokeTestRequested
                : Self.boolValue("smoke_test_requested", from: compatibilityPayload),
            smokeTestPassed: result.hasArtifact
                ? result.artifact.smokeTestPassed
                : Self.boolValue("smoke_test_passed", from: compatibilityPayload),
            calibrationSampleCount: calibrationSampleCount(from: manifestPayload),
            targetRepo: Self.stringValue("target_repo", from: manifestPayload),
            sourceArtifactKind: Self.stringValue("source_artifact_kind", from: manifestPayload),
            conversionTargetFormat: Self.stringValue("target_format", from: manifestPayload),
            linkedQuantizationProfileID: Self.stringValue(
                "quant_profile_id",
                from: Self.dictionaryValue("linked_quantization", from: manifestPayload)
            )
        )
        if let loraWorkflowOperation {
            completeLoraWorkflow(
                loraWorkflowOperation,
                outputPath: result.outputPath,
                fallbackDetail: result.jobID
            )
        }
        if refreshProductToolingState {
            await refreshModelOpsProductState(modelID: modelID, notify: false)
        }
        notifyStateChanged()
    }

    private func applyManagedReceiptOperation(
        _ receipt: ManagedModelReceipt,
        modelID: String,
        operation: String,
        startedAt: Date,
        metricName: String
    ) async {
        await metrics.record(
            name: metricName,
            valueMs: Date().timeIntervalSince(startedAt) * 1_000
        )
        let manifestJSON = (try? String(
            data: JSONEncoder().encode(receipt),
            encoding: .utf8
        )) ?? "{}"
        lastModelOperation = RuntimeModelOperationState(
            modelID: modelID,
            operation: operation,
            jobID: "",
            stage: "completed",
            pct: 1,
            outputPath: receipt.managedModelPath,
            manifestJson: manifestJSON,
            quantProfileID: "",
            artifactKind: "managed_model_receipt",
            manifestPath: "",
            artifactBytes: 0,
            artifactRuntime: "",
            servingCompatible: true,
            smokeTestRequested: false,
            smokeTestPassed: false,
            calibrationSampleCount: 0,
            targetRepo: "",
            sourceArtifactKind: "",
            conversionTargetFormat: "",
            linkedQuantizationProfileID: ""
        )
        notifyStateChanged()
    }

    private func applyCLIModelOperationManifest(
        _ manifest: MelixCLIModelOperationManifestPayload,
        modelID: String,
        operation: String,
        rawManifestJSON: String,
        startedAt: Date,
        metricName: String,
        refreshProductToolingState: Bool,
        loraWorkflowOperation: RuntimeLoraWorkflowOperation?
    ) async {
        await metrics.record(
            name: metricName,
            valueMs: Date().timeIntervalSince(startedAt) * 1_000
        )
        lastModelOperation = RuntimeModelOperationState(
            modelID: modelID,
            operation: operation,
            jobID: manifest.jobID ?? "",
            stage: "completed",
            pct: 1,
            outputPath: manifest.outputPath ?? manifest.derivedModelPath ?? "",
            manifestJson: rawManifestJSON,
            quantProfileID: "",
            artifactKind: operation == "activate_adapter" ? "derived_model_manifest" : "adapter_manifest",
            manifestPath: "",
            artifactBytes: 0,
            artifactRuntime: "",
            servingCompatible: true,
            smokeTestRequested: false,
            smokeTestPassed: false,
            calibrationSampleCount: 0,
            targetRepo: "",
            sourceArtifactKind: "",
            conversionTargetFormat: "",
            linkedQuantizationProfileID: ""
        )
        if let loraWorkflowOperation {
            completeLoraWorkflow(
                loraWorkflowOperation,
                outputPath: manifest.outputPath ?? manifest.derivedModelPath ?? "",
                fallbackDetail: manifest.jobID ?? ""
            )
        }
        if refreshProductToolingState {
            await refreshModelOpsProductState(modelID: modelID, notify: false)
        }
        notifyStateChanged()
    }

    public func refreshDownloadQueueState() async {
        await refreshDownloadQueueState(notify: true, surfaceErrors: true)
    }

    public func resumeDownload(jobID: String) async {
        guard let entry = downloadQueue.first(where: { $0.jobID == jobID }), entry.resumeReady else {
            return
        }
        var ext: [String: String] = [:]
        if !entry.selectedMirror.isEmpty {
            ext["mirror_url"] = entry.selectedMirror
        }
        await runModelOperation(
            modelID: entry.sourceModel,
            operation: "download",
            outputDir: entry.outputDir,
            ext: ext
        )
        await refreshDownloadQueueState(notify: true, surfaceErrors: false)
    }

    public func quantizePrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "quantize",
            outputDir: "/tmp/melix-quantize",
            quantProfileID: selectedQuantizationProfileID,
            weightQuant: selectedQuantizationProfileID,
            kvQuant: "q8"
        )
    }

    public func convertPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "convert",
            outputDir: "/tmp/melix-convert",
            ext: ["target_format": "melix_model_bundle"]
        )
    }

    public func downloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "download",
            outputDir: Self.defaultDownloadOutputDirectory(namespace: "melix-downloads", modelID: modelID)
        )
        await refreshDownloadQueueState(notify: true, surfaceErrors: false)
    }

    public func installAudioRuntime(modelID: String) async {
        guard !modelID.isEmpty else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "install_audio_runtime",
            outputDir: "/tmp/melix-audio-runtime-pack"
        )
        await refreshDesktopFoundation()
    }

    public func downloadAudioModel(modelID: String) async {
        guard !modelID.isEmpty else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "download",
            outputDir: Self.defaultDownloadOutputDirectory(namespace: "melix-audio-models", modelID: modelID)
        )
        await refreshDownloadQueueState(notify: false, surfaceErrors: false)
        await refreshDesktopFoundation()
    }

    public func performAudioSetupAction(_ action: RuntimeAudioSetupActionState) async {
        switch action.kind {
        case .installRuntime:
            await installAudioRuntime(modelID: action.modelID)
        case .downloadModel:
            await downloadAudioModel(modelID: action.modelID)
        }
    }

    public func presentAudioSetupPrompt(_ action: RuntimeAudioSetupActionState) {
        pendingAudioSetupPrompt = RuntimeAudioSetupPromptState(action: action)
        notifyStateChanged()
    }

    public func dismissAudioSetupPrompt() {
        pendingAudioSetupPrompt = nil
        notifyStateChanged()
    }

    public func performPendingAudioSetupAction() async {
        guard let prompt = pendingAudioSetupPrompt else {
            return
        }
        pendingAudioSetupPrompt = nil
        notifyStateChanged()
        await performAudioSetupAction(prompt.action)
    }

    public func uploadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        let linkedQuantizationExt = latestPackagedArtifactUploadExt()
        await runModelOperation(
            modelID: modelID,
            operation: "upload",
            outputDir: "/tmp/melix-upload",
            ext: linkedQuantizationExt.merging(["target_repo": "melix/upload-target"]) { current, _ in current }
        )
    }

    public func trainPrimaryModel() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty else {
            surfaceLoraWorkflowGuardFailure(
                .trainLoRA,
                message: "Select a base model before starting LoRA training."
            )
            return
        }
        if let cliWorkflowRunner {
            let startedAt = Date()
            beginLoraWorkflow(.trainLoRA, detail: loraTrainingWorkflowDetail())
            do {
                let output = try await cliWorkflowRunner.run(
                    .loraTrain(
                        .init(
                            modelID: modelID,
                            datasetSourceKind: loraTrainingExt()["dataset_source_kind"] ?? "local_package",
                            datasetURI: loraTrainingExt()["dataset_uri"] ?? "",
                            adapterName: loraTrainingExt()["adapter_name"] ?? "melix-dev-adapter",
                            targetRepo: loraTrainingExt()["target_repo"] ?? "",
                            trainingMode: loraTrainingExt()["training_mode"] ?? "",
                            parameters: loraTrainingCLIParameters(),
                            json: true
                        )
                    )
                )
                let manifest = try decodeMelixCLIJSON(
                    MelixCLIModelOperationManifestPayload.self,
                    output: output,
                    command: .loraTrain(.init(modelID: modelID, datasetURI: "", adapterName: "", json: true)),
                    surface: cliWorkflowRunner.surface
                )
                clearCLIWorkflowFailure()
                await applyCLIModelOperationManifest(
                    manifest,
                    modelID: modelID,
                    operation: "train_lora",
                    rawManifestJSON: output,
                    startedAt: startedAt,
                    metricName: "menu.model_operation_ms",
                    refreshProductToolingState: true,
                    loraWorkflowOperation: .trainLoRA
                )
                loraResumeFromManifestPath = ""
                return
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                let errorMessage = workflowErrorMessage(error)
                recordLocalError(errorMessage)
                failLoraWorkflow(.trainLoRA, detail: errorMessage)
                notifyStateChanged()
                return
            }
        }
        await runLoraModelOperation(
            modelID: modelID,
            workflowOperation: .trainLoRA,
            outputDir: "",
            ext: loraTrainingExt(),
            refreshProductToolingState: true,
            runningDetail: loraTrainingWorkflowDetail()
        )
        loraResumeFromManifestPath = ""
    }

    public func activateLatestAdapter() async {
        let modelID = resolvedLoraModelID()
        let adapterPath = selectedAdapterPackage?.outputPath.isEmpty == false
            ? selectedAdapterPackage?.outputPath ?? ""
            : latestCLITrainedAdapterPath()
        guard !modelID.isEmpty else {
            surfaceLoraWorkflowGuardFailure(
                .activateAdapter,
                message: "Select a base model before activating an adapter."
            )
            return
        }
        guard adapterPath.isEmpty == false else {
            surfaceLoraWorkflowGuardFailure(
                .activateAdapter,
                message: "Train or select an adapter before activating it."
            )
            return
        }

        if let cliWorkflowRunner {
            let startedAt = Date()
            beginLoraWorkflow(.activateAdapter, detail: loraActivationWorkflowDetail(adapterPath: adapterPath))
            do {
                let output = try await cliWorkflowRunner.run(
                    .loraActivate(
                        .init(
                            modelID: modelID,
                            adapterPath: adapterPath,
                            derivedModelAlias: Self.normalizedOptionalString(loraDerivedModelAlias) ?? "",
                            json: true
                        )
                    )
                )
                let manifest = try decodeMelixCLIJSON(
                    MelixCLIModelOperationManifestPayload.self,
                    output: output,
                    command: .loraActivate(.init(modelID: modelID, adapterPath: adapterPath, json: true)),
                    surface: cliWorkflowRunner.surface
                )
                clearCLIWorkflowFailure()
                await applyCLIModelOperationManifest(
                    manifest,
                    modelID: modelID,
                    operation: "activate_adapter",
                    rawManifestJSON: output,
                    startedAt: startedAt,
                    metricName: "menu.model_operation_ms",
                    refreshProductToolingState: true,
                    loraWorkflowOperation: .activateAdapter
                )
                return
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                let errorMessage = workflowErrorMessage(error)
                recordLocalError(errorMessage)
                failLoraWorkflow(.activateAdapter, detail: errorMessage)
                notifyStateChanged()
                return
            }
        }

        var ext: [String: String] = [
            "artifact_path": adapterPath,
        ]
        if let alias = Self.normalizedOptionalString(loraDerivedModelAlias) {
            ext["derived_model_alias"] = alias
        }
        ext["activation_mode"] = loraActivationMode.rawValue
        await runLoraModelOperation(
            modelID: modelID,
            workflowOperation: .activateAdapter,
            outputDir: "",
            ext: ext,
            refreshProductToolingState: true,
            runningDetail: loraActivationWorkflowDetail(adapterPath: adapterPath)
        )
        await refreshDesktopFoundation()
    }

    public func removeSelectedDerivedModel() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let adapter = selectedAdapterPackage else {
            surfaceLoraWorkflowGuardFailure(
                .removeDerivedModel,
                message: "Select an activated adapter before removing its derived model."
            )
            return
        }

        var ext: [String: String] = [:]
        if let derivedModelID = Self.normalizedOptionalString(adapter.derivedModelID) {
            ext["derived_model_id"] = derivedModelID
        } else if let manifestPath = Self.normalizedOptionalString(adapter.outputPath) {
            ext["manifest_path"] = manifestPath
        } else {
            surfaceLoraWorkflowGuardFailure(
                .removeDerivedModel,
                message: "Select an activated adapter before removing its derived model."
            )
            return
        }

        await runLoraModelOperation(
            modelID: modelID,
            workflowOperation: .removeDerivedModel,
            outputDir: "",
            ext: ext,
            refreshProductToolingState: true,
            runningDetail: loraRemoveWorkflowDetail(adapter: adapter)
        )
        await refreshDesktopFoundation()
    }

    public func refreshModelOpsProductState() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty else {
            return
        }
        await refreshModelOpsProductState(
            modelID: modelID,
            notify: true,
            rescan: false,
            registryRootsOverride: nil,
            refreshFoundationAfterSuccess: false
        )
    }

    public func rescanRegistryRoots() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty else {
            return
        }
        if let operatorCommandRunner {
            do {
                _ = try await operatorCommandRunner.run(.modelRootsRescan(.init()))
                restoreOperatorSessionState()
            } catch {
                recordLocalError(String(describing: error))
                notifyStateChanged()
                return
            }
        }
        await refreshModelOpsProductState(
            modelID: modelID,
            notify: true,
            rescan: true,
            registryRootsOverride: nil,
            refreshFoundationAfterSuccess: true
        )
    }

    public func addRegistryRoot() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let normalizedRoot = Self.normalizedRegistryRootPath(registryRootPathDraft) else {
            return
        }

        var updatedRoots = editableRegistryRootPaths()
        guard updatedRoots.contains(normalizedRoot) == false else {
            registryRootPathDraft = ""
            notifyStateChanged()
            return
        }
        if let operatorCommandRunner {
            do {
                _ = try await operatorCommandRunner.run(.modelRootsAdd(.init(path: normalizedRoot)))
                restoreOperatorSessionState()
            } catch {
                recordLocalError(String(describing: error))
                notifyStateChanged()
                return
            }
        }
        updatedRoots.append(normalizedRoot)
        await refreshModelOpsProductState(
            modelID: modelID,
            notify: true,
            rescan: true,
            registryRootsOverride: updatedRoots,
            refreshFoundationAfterSuccess: true
        )
        registryRootPathDraft = ""
        notifyStateChanged()
    }

    public func removeRegistryRoot(rootID: String) async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let index = editableRegistryRootIndex(for: rootID) else {
            return
        }

        var updatedRoots = editableRegistryRootPaths()
        if let operatorCommandRunner {
            do {
                _ = try await operatorCommandRunner.run(.modelRootsRemove(.init(path: updatedRoots[index])))
                restoreOperatorSessionState()
            } catch {
                recordLocalError(String(describing: error))
                notifyStateChanged()
                return
            }
        }
        updatedRoots.remove(at: index)
        await refreshModelOpsProductState(
            modelID: modelID,
            notify: true,
            rescan: true,
            registryRootsOverride: updatedRoots,
            refreshFoundationAfterSuccess: true
        )
    }

    public func moveRegistryRootUp(rootID: String) async {
        await moveRegistryRoot(rootID: rootID, offset: -1)
    }

    public func moveRegistryRootDown(rootID: String) async {
        await moveRegistryRoot(rootID: rootID, offset: 1)
    }

    public func publishLatestAdapter() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let adapter = selectedAdapterPackage else {
            surfaceLoraWorkflowGuardFailure(
                .publishAdapter,
                message: "Select an adapter package before publishing it."
            )
            return
        }

        await runLoraModelOperation(
            modelID: modelID,
            workflowOperation: .publishAdapter,
            outputDir: "/tmp/melix-upload-adapter",
            ext: [
                "target_repo": adapter.targetRepo.isEmpty ? "melix/adapters/\(adapter.adapterName)" : adapter.targetRepo,
                "artifact_kind": "adapter",
                "artifact_path": adapter.outputPath,
                "adapter_name": adapter.adapterName,
            ],
            refreshProductToolingState: true,
            runningDetail: loraPublishWorkflowDetail(adapter: adapter)
        )
    }

    private static func doctorHealthStatusText(
        _ status: Melix_Controlplane_V1_DoctorHealthStatus
    ) -> String {
        switch status {
        case .healthy:
            return "Healthy"
        case .warning:
            return "Warning"
        case .degraded:
            return "Degraded"
        case .failed:
            return "Failed"
        case .unspecified, .UNRECOGNIZED:
            return "Unknown"
        }
    }

    private func calibrationSampleCount(from payload: [String: Any]) -> Int {
        Self.intValue("sample_count", from: Self.dictionaryValue("calibration", from: payload))
    }

    private func latestPackagedArtifactUploadExt() -> [String: String] {
        guard
            let lastModelOperation,
            ["quantized_model_bundle", "converted_model_bundle"].contains(lastModelOperation.artifactKind)
        else {
            return [:]
        }
        var ext: [String: String] = [
            "artifact_kind": "model",
            "artifact_path": lastModelOperation.outputPath,
        ]
        if !lastModelOperation.manifestPath.isEmpty {
            if lastModelOperation.artifactKind == "quantized_model_bundle" {
                ext["quantization_manifest_path"] = lastModelOperation.manifestPath
            } else {
                ext["artifact_manifest_path"] = lastModelOperation.manifestPath
            }
        }
        if !lastModelOperation.quantProfileID.isEmpty {
            ext["quant_profile_id"] = lastModelOperation.quantProfileID
        }
        return ext
    }

    private func startupFailureMessage(_ error: Error) -> String {
        "Startup failed: \(error). Open Melix Console for details."
    }

    private func refreshProductSignals() async {
        guard let updateStatus = productInstallStateProvider.updateStatus() else {
            productUpdateSummary = nil
            productUpdateDetail = nil
            productUpdateIsAvailable = false
            productUpdateCheckSucceeded = true
            dismissedBannerIDs = dismissedBannerIDs.filter { $0.hasPrefix("product-update::") == false }
            return
        }
        productUpdateSummary = updateStatus.summary
        productUpdateDetail = updateStatus.detail
        productUpdateIsAvailable = updateStatus.isAvailable
        productUpdateCheckSucceeded = updateStatus.checkSucceeded
        let activeUpdateBannerID = Self.productUpdateBannerID(summary: updateStatus.summary, detail: updateStatus.detail)
        dismissedBannerIDs = dismissedBannerIDs.filter { bannerID in
            bannerID.hasPrefix("product-update::") == false || bannerID == activeUpdateBannerID
        }
        await metrics.record(
            name: "update.check_success_rate",
            valueMs: updateStatus.checkSucceeded ? 100 : 0
        )
    }

    public func runDoctor() async {
        let startedAt = Date()
        do {
            let report = try await client.runDoctor()
            await metrics.record(
                name: "menu.ops_doctor_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            lastDoctorReport = RuntimeDoctorReportState(
                markdown: report.markdown,
                healthStatusText: Self.doctorHealthStatusText(report.healthStatus),
                findings: report.findings.map {
                    RuntimeDoctorFindingState(
                        code: $0.code,
                        severityText: Self.doctorHealthStatusText($0.severity),
                        summary: $0.summary,
                        detail: $0.detail
                    )
                }
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func runBench() async {
        preferredDiagnosticsStage = .benchmark
        let modelID = resolvedBenchmarkModelID()
        let repoID = benchmarkHFRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
        switch selectedBenchmarkTargetMode {
        case .catalogModel:
            guard !modelID.isEmpty else {
                recordLocalError("Select a benchmark-capable model before running Benchmark.")
                notifyStateChanged()
                return
            }
        case .huggingFaceRepo:
            guard !repoID.isEmpty else {
                recordLocalError("Enter a Hugging Face repo before running Benchmark.")
                notifyStateChanged()
                return
            }
        }
        let suites = selectedBenchmarkSuiteIDs.sorted()
        guard suites.isEmpty == false else {
            recordLocalError("Select at least one benchmark dataset before running Benchmark.")
            notifyStateChanged()
            return
        }
        let contextLengths = normalizedBenchContextLengths()
        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let payload = try await cliWorkflowRunner.decodeJSON(
                    MelixCLIBenchRunPayload.self,
                    command: .benchRun(
                        .init(
                            modelID: selectedBenchmarkTargetMode == .catalogModel ? modelID : "",
                            hfRepoID: selectedBenchmarkTargetMode == .huggingFaceRepo ? repoID : "",
                            suites: suites,
                            contextLengths: contextLengths,
                            generationLength: normalizedBenchGenerationLengths().first ?? 0,
                            batchSizes: normalizedBenchBatchSizes(),
                            repeats: normalizedBenchRepeats(),
                            cacheProfile: normalizedBenchCacheProfile(),
                            reasoningMode: normalizedBenchReasoningMode(),
                            structuredOutputMode: normalizedBenchStructuredOutputMode(),
                            parameters: benchmarkParameters(),
                            json: true
                        )
                    )
                )
                clearCLIWorkflowFailure()
                await metrics.record(
                    name: "menu.ops_bench_ms",
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
                for (name, value) in payload.metrics {
                    latestSnapshot.metrics.values[name] = value
                }
                lastBenchReport = RuntimeBenchReportState(
                    reportPath: payload.reportPath,
                    markdown: payload.reportMarkdown,
                    metrics: payload.metrics.keys.sorted().map { key in
                        RuntimeBenchMetricState(name: key, value: String(format: "%.2f", payload.metrics[key] ?? 0))
                    }
                )
                await refreshBenchmarkHistory(notify: false)
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            let result: ControlPlaneBenchResult
            if let operatorCommandRunner {
                result = try await operatorCommandRunner.runBenchmark(
                    .init(
                        modelID: selectedBenchmarkTargetMode == .catalogModel ? modelID : "",
                        hfRepoID: selectedBenchmarkTargetMode == .huggingFaceRepo ? repoID : "",
                        suites: suites,
                        contextLengths: contextLengths,
                        batchSizes: normalizedBenchBatchSizes(),
                        repeats: normalizedBenchRepeats(),
                        cacheProfile: normalizedBenchCacheProfile(),
                        reasoningMode: normalizedBenchReasoningMode(),
                        structuredOutputMode: normalizedBenchStructuredOutputMode(),
                        parameters: benchmarkParameters()
                    )
                )
            } else {
                result = try await client.runBench(
                    ControlPlaneBenchRequest(
                        modelID: selectedBenchmarkTargetMode == .catalogModel ? modelID : "",
                        hfRepoID: selectedBenchmarkTargetMode == .huggingFaceRepo ? repoID : "",
                        suites: suites,
                        contextLengths: contextLengths,
                        batchSizes: normalizedBenchBatchSizes(),
                        repeats: normalizedBenchRepeats(),
                        cacheProfile: normalizedBenchCacheProfile(),
                        reasoningMode: normalizedBenchReasoningMode(),
                        structuredOutputMode: normalizedBenchStructuredOutputMode(),
                        parameters: benchmarkParameters()
                    )
                )
            }
            await metrics.record(
                name: "menu.ops_bench_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            for (name, value) in result.metrics {
                latestSnapshot.metrics.values[name] = value
            }
            lastBenchReport = RuntimeBenchReportState(
                reportPath: result.reportPath,
                markdown: result.reportMarkdown,
                metrics: result.metrics.keys.sorted().map { key in
                    RuntimeBenchMetricState(name: key, value: String(format: "%.2f", result.metrics[key] ?? 0))
                }
            )
            await refreshBenchmarkHistory(notify: false)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func refreshBenchmarkHistory() async {
        preferredDiagnosticsStage = selectedBenchmarkPresentationMode == .matrix ? .matrix : .benchmark
        await refreshBenchmarkHistory(notify: true)
    }

    public func exportSelectedBenchmarkCSV() async {
        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let selectedJobID = selectedBenchmarkHistoryJobID.isEmpty ? (selectedBenchmarkHistoryEntry?.jobID ?? "") : selectedBenchmarkHistoryJobID
                let exportDirectory = try Self.ensureBenchmarkExportDirectory()
                let outputPath = exportDirectory.appendingPathComponent(Self.benchmarkCSVFileName(jobID: selectedJobID)).path
                let response = try await cliWorkflowRunner.decodeJSON(
                    MelixCLIExportResponse.self,
                    command: .benchExportCSV(.init(jobID: selectedJobID, outputPath: outputPath, json: true))
                )
                clearCLIWorkflowFailure()
                lastBenchmarkCSVExport = RuntimeBenchmarkCSVExportState(
                    outputPath: response.outputPath,
                    rowCount: response.rowCount
                )
                await metrics.record(
                    name: "menu.bench_export_csv_ms",
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            let exportDirectory = try Self.ensureBenchmarkExportDirectory()
            let bundle: ControlPlaneBenchmarkExportBundle
            if let operatorCommandRunner {
                bundle = try await operatorCommandRunner.fetchBenchmarkExportBundle(outputDir: exportDirectory.path)
            } else {
                let export = try await client.exportResults(outputDir: exportDirectory.path)
                bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            }
            applyBenchmarkExportBundle(bundle)
            let selectedJobID = selectedBenchmarkHistoryJobID.isEmpty ? nil : selectedBenchmarkHistoryJobID
            let rows = bundle.benchmarkCSVRows(jobID: selectedJobID)
            guard rows.isEmpty == false else {
                recordLocalError("No benchmark rows are available for CSV export.")
                notifyStateChanged()
                return
            }
            let csv = bundle.benchmarkCSV(jobID: selectedJobID)
            let outputURL = exportDirectory.appendingPathComponent(
                Self.benchmarkCSVFileName(jobID: selectedJobID)
            )
            try csv.write(to: outputURL, atomically: true, encoding: .utf8)
            lastBenchmarkCSVExport = RuntimeBenchmarkCSVExportState(
                outputPath: outputURL.path,
                rowCount: rows.count
            )
            await metrics.record(
                name: "menu.bench_export_csv_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func runBenchMatrix() async {
        preferredDiagnosticsStage = .matrix
        let modelID = resolvedBenchmarkModelID()
        let repoID = benchmarkHFRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
        switch selectedBenchmarkTargetMode {
        case .catalogModel:
            guard !modelID.isEmpty else {
                recordLocalError("Select a benchmark-capable model before running Matrix.")
                notifyStateChanged()
                return
            }
        case .huggingFaceRepo:
            guard !repoID.isEmpty else {
                recordLocalError("Enter a Hugging Face repo before running Matrix.")
                notifyStateChanged()
                return
            }
        }

        let taskKind = resolvedBenchmarkTaskKind()
        guard ["text-generation", "image-to-text", "image-text-to-text"].contains(taskKind) else {
            recordLocalError("Benchmark matrix supports only text-generation, image-to-text, and image-text-to-text targets.")
            notifyStateChanged()
            return
        }

        let suites = selectedBenchmarkSuiteIDs.sorted()
        guard suites.isEmpty == false else {
            recordLocalError("Select at least one matrix benchmark suite before running Matrix.")
            notifyStateChanged()
            return
        }

        let request = ControlPlaneBenchMatrixRequest(
            modelID: selectedBenchmarkTargetMode == .catalogModel ? modelID : "",
            hfRepoID: selectedBenchmarkTargetMode == .huggingFaceRepo ? repoID : "",
            taskKind: taskKind,
            suites: suites,
            contextLengths: normalizedBenchContextLengths(),
            generationLengths: normalizedBenchGenerationLengths(),
            batchSizes: normalizedBenchBatchSizes(),
            cacheProfiles: normalizedBenchMatrixCacheProfiles(),
            reasoningModes: normalizedBenchMatrixReasoningModes(),
            structuredOutputModes: normalizedBenchMatrixStructuredOutputModes(),
            concurrencyLevels: normalizedBenchMatrixConcurrencyLevels(),
            repeats: normalizedBenchMatrixRepeats(),
            requests: selectedBenchmarkMatrixLoadBudgetMode == .requests ? normalizedBenchMatrixRequests() : 0,
            durationSeconds: selectedBenchmarkMatrixLoadBudgetMode == .durationSeconds ? normalizedBenchMatrixDurationSeconds() : 0,
            allowLargeMatrix: benchMatrixAllowLargeMatrix
        )

        guard request.requests > 0 || request.durationSeconds > 0 else {
            let modeTitle = selectedBenchmarkMatrixLoadBudgetMode == .requests ? "requests" : "duration_seconds"
            recordLocalError("Set a positive \(modeTitle) value before running Matrix.")
            notifyStateChanged()
            return
        }
        guard request.requests == 0 || request.durationSeconds == 0 else {
            recordLocalError("Exactly one of requests or duration_seconds must be set for matrix benchmarks.")
            notifyStateChanged()
            return
        }
        guard request.allowLargeMatrix || request.matrixCellCount <= ControlPlaneBenchMatrixRequest.maxMatrixCellCount else {
            recordLocalError("Matrix benchmark expands to \(request.matrixCellCount) cells; enable Allow Large Matrix to continue.")
            notifyStateChanged()
            return
        }

        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let payload = try await cliWorkflowRunner.decodeJSON(
                    MelixCLIBenchmarkMatrixRunPayload.self,
                    command: .benchMatrixRun(
                        .init(
                            modelID: request.modelID,
                            hfRepoID: request.hfRepoID,
                            taskKind: request.taskKind,
                            suites: request.suites,
                            contextLengths: request.contextLengths,
                            generationLengths: request.generationLengths,
                            batchSizes: request.batchSizes,
                            cacheProfiles: request.cacheProfiles,
                            reasoningModes: request.reasoningModes,
                            structuredOutputModes: request.structuredOutputModes,
                            concurrencyLevels: request.concurrencyLevels,
                            repeats: request.repeats,
                            requests: request.requests,
                            durationSeconds: request.durationSeconds,
                            allowLargeMatrix: request.allowLargeMatrix,
                            json: true
                        )
                    )
                )
                selectedBenchmarkMatrixHistoryJobID = payload.job.jobID
                clearCLIWorkflowFailure()
                await metrics.record(
                    name: "menu.ops_bench_matrix_ms",
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
                await refreshBenchmarkHistory(notify: false)
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            let result: ControlPlaneBenchMatrixResult
            if let operatorCommandRunner {
                result = try await operatorCommandRunner.runBenchmarkMatrix(
                    .init(
                        modelID: request.modelID,
                        hfRepoID: request.hfRepoID,
                        taskKind: request.taskKind,
                        suites: request.suites,
                        contextLengths: request.contextLengths,
                        generationLengths: request.generationLengths,
                        batchSizes: request.batchSizes,
                        cacheProfiles: request.cacheProfiles,
                        reasoningModes: request.reasoningModes,
                        structuredOutputModes: request.structuredOutputModes,
                        concurrencyLevels: request.concurrencyLevels,
                        repeats: request.repeats,
                        requests: request.requests,
                        durationSeconds: request.durationSeconds,
                        allowLargeMatrix: request.allowLargeMatrix
                    )
                )
            } else {
                result = try await client.runBenchMatrix(request)
            }
            selectedBenchmarkMatrixHistoryJobID = result.job.jobID
            await metrics.record(
                name: "menu.ops_bench_matrix_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            await refreshBenchmarkHistory(notify: false)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func exportSelectedBenchmarkMatrixSummaryCSV() async {
        await exportBenchmarkMatrixArtifact(
            formatTitle: "summary.csv",
            fileName: Self.benchmarkMatrixSummaryCSVFileName(jobID: selectedBenchmarkMatrixHistoryJobID),
            builder: { bundle, jobID in
                let rows = bundle.benchmarkMatrixSummaryCSVRows(jobID: jobID)
                return (rows.count, bundle.benchmarkMatrixSummaryCSV(jobID: jobID))
            },
            missingRowsMessage: "No matrix benchmark summary rows are available for CSV export."
        )
    }

    public func exportSelectedBenchmarkMatrixRequestsCSV() async {
        await exportBenchmarkMatrixArtifact(
            formatTitle: "requests.csv",
            fileName: Self.benchmarkMatrixRequestsCSVFileName(jobID: selectedBenchmarkMatrixHistoryJobID),
            builder: { bundle, jobID in
                let rows = bundle.benchmarkMatrixRequestRows(jobID: jobID)
                return (rows.count, bundle.benchmarkMatrixRequestsCSV(jobID: jobID))
            },
            missingRowsMessage: "No matrix benchmark request rows are available for CSV export."
        )
    }

    public func runEvaluation() async {
        preferredDiagnosticsStage = .evaluation
        let modelID = resolvedEvaluationModelID()
        let repoID = evaluationHFRepoID.trimmingCharacters(in: .whitespacesAndNewlines)
        let usesCustomSource = evaluationDatasetSourceKind != .builtinPackage
        switch selectedEvaluationTargetMode {
        case .catalogModel:
            guard !modelID.isEmpty else {
                recordLocalError("Select a text-generation model before running Evaluation.")
                notifyStateChanged()
                return
            }
        case .huggingFaceRepo:
            guard !repoID.isEmpty else {
                recordLocalError("Enter a Hugging Face repo before running Evaluation.")
                notifyStateChanged()
                return
            }
        }

        let suites = selectedEvaluationSuiteIDs.sorted()
        guard suites.isEmpty == false else {
            recordLocalError("Select at least one evaluation suite before running Evaluation.")
            notifyStateChanged()
            return
        }

        let compareTargetModelIDs = selectedEvaluationCompareTargetModelIDs.sorted()
        if selectedEvaluationMode == .compare, compareTargetModelIDs.isEmpty {
            recordLocalError("Select at least one compare target model before running Evaluation Compare.")
            notifyStateChanged()
            return
        }
        let usesEvaluationPrompt = shouldUseEvaluationPrompt(suites: suites)
        if usesEvaluationPrompt, suites.contains(where: { $0 != "event_extraction" }) {
            recordLocalError("Event extraction prompts require selecting only the Event Extraction suite.")
            notifyStateChanged()
            return
        }
        if selectedEvaluationMode == .compare, usesEvaluationPrompt {
            recordLocalError("Event extraction prompts are available for standard Evaluation runs.")
            notifyStateChanged()
            return
        }
        let usesSemanticJudge = selectedEvaluationSemanticJudgeRemoteServerID
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .isEmpty == false
        if usesSemanticJudge, selectedEvaluationMode == .compare {
            recordLocalError("Semantic judge scoring is available for standard Evaluation runs.")
            notifyStateChanged()
            return
        }
        if usesSemanticJudge, suites != ["event_extraction"] {
            recordLocalError("Semantic judge scoring requires selecting only the Event Extraction suite.")
            notifyStateChanged()
            return
        }

        if let sourceValidationError = validateEvaluationSourceConfiguration() {
            recordLocalError(sourceValidationError)
            notifyStateChanged()
            return
        }

        let evaluationPromptSnapshot: EvaluationPromptSnapshot?
        do {
            evaluationPromptSnapshot = usesEvaluationPrompt
                ? try evaluationPromptStore.resolveForRun(promptID: selectedEvaluationPromptID, revisionID: "")
                : nil
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
            return
        }
        let semanticJudgeParameters: [String: String]
        do {
            semanticJudgeParameters = try evaluationSemanticJudgeParameters()
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
            return
        }

        let startedAt = Date()
        if usesCustomSource == false, let cliWorkflowRunner {
            do {
                let payloads = try await cliWorkflowRunner.decodeJSON(
                    [MelixCLIEvaluationRunPayload].self,
                    command: .evalRun(
                        .init(
                            modelID: selectedEvaluationTargetMode == .catalogModel ? modelID : "",
                            hfRepoID: selectedEvaluationTargetMode == .huggingFaceRepo ? repoID : "",
                            suites: suites,
                            datasetID: "",
                            sampleSize: UInt32(evaluationSampleSize.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0,
                            parameters: evaluationParameters(
                                compareTargetModelIDs: selectedEvaluationMode == .compare ? compareTargetModelIDs : nil,
                                promptSnapshot: nil,
                                semanticJudgeParameters: [:]
                            ),
                            evalPromptID: evaluationPromptSnapshot?.promptID ?? "",
                            evalPromptRevisionID: evaluationPromptSnapshot?.revisionID ?? "",
                            semanticJudgeRemoteServerID: selectedEvaluationSemanticJudgeRemoteServerID,
                            semanticJudgeModelID: evaluationSemanticJudgeModelID,
                            json: true
                        )
                    )
                )
                selectedEvaluationHistoryJobID = payloads.first?.job.jobID ?? ""
                clearCLIWorkflowFailure()
                await metrics.record(
                    name: "menu.ops_eval_ms",
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
                await refreshEvaluationHistory(notify: false)
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            if usesCustomSource == false, let operatorCommandRunner {
                if selectedEvaluationMode == .compare {
                    _ = try await operatorCommandRunner.runEvaluationCompare(
                        EvalCompareOptions(
                            modelID: selectedEvaluationTargetMode == .catalogModel ? modelID : "",
                            hfRepoID: selectedEvaluationTargetMode == .huggingFaceRepo ? repoID : "",
                            targetModelIDs: compareTargetModelIDs,
                            suites: suites,
                            sampleSize: UInt32(evaluationSampleSize.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0,
                            parameters: evaluationParameters(
                                compareTargetModelIDs: compareTargetModelIDs,
                                promptSnapshot: nil,
                                semanticJudgeParameters: [:]
                            )
                        )
                    )
                } else {
                    _ = try await operatorCommandRunner.runEvaluations(
                        .init(
                            modelID: selectedEvaluationTargetMode == .catalogModel ? modelID : "",
                            hfRepoID: selectedEvaluationTargetMode == .huggingFaceRepo ? repoID : "",
                            suites: suites,
                            sampleSize: UInt32(evaluationSampleSize.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0,
                            parameters: evaluationParameters(
                                compareTargetModelIDs: nil,
                                promptSnapshot: nil,
                                semanticJudgeParameters: [:]
                            ),
                            evalPromptID: evaluationPromptSnapshot?.promptID ?? "",
                            evalPromptRevisionID: evaluationPromptSnapshot?.revisionID ?? "",
                            semanticJudgeRemoteServerID: selectedEvaluationSemanticJudgeRemoteServerID,
                            semanticJudgeModelID: evaluationSemanticJudgeModelID
                        )
                    )
                }
            } else {
                for suiteID in suites {
                    _ = try await client.runEvaluation(
                        makeEvaluationRequest(
                            suiteID: suiteID,
                            modelID: selectedEvaluationTargetMode == .catalogModel ? modelID : "",
                            hfRepoID: selectedEvaluationTargetMode == .huggingFaceRepo ? repoID : "",
                            compareTargetModelIDs: selectedEvaluationMode == .compare ? compareTargetModelIDs : nil,
                            promptSnapshot: evaluationPromptSnapshot,
                            semanticJudgeParameters: semanticJudgeParameters
                        )
                    )
                }
            }
            await metrics.record(
                name: "menu.ops_eval_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            await refreshEvaluationHistory(notify: false)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func refreshEvaluationHistory() async {
        preferredDiagnosticsStage = .evaluation
        await refreshEvaluationHistory(notify: true)
    }

    public func exportSelectedEvaluationSummaryCSV() async {
        await exportEvaluationArtifact(
            formatTitle: "summary.csv",
            fileName: Self.evaluationSummaryCSVFileName(jobID: selectedEvaluationHistoryJobID),
            builder: { bundle, jobID in
                let rows = bundle.evaluationSummaryCSVRows(jobID: jobID)
                return (rows.count, bundle.evaluationSummaryCSV(jobID: jobID))
            },
            missingRowsMessage: "No evaluation summary rows are available for CSV export."
        )
    }

    public func exportSelectedEvaluationSamplesCSV() async {
        await exportEvaluationArtifact(
            formatTitle: "samples.csv",
            fileName: Self.evaluationSamplesCSVFileName(jobID: selectedEvaluationHistoryJobID),
            builder: { bundle, jobID in
                let rows = bundle.evaluationSampleRows(jobID: jobID)
                return (rows.count, bundle.evaluationSamplesCSV(jobID: jobID))
            },
            missingRowsMessage: "No evaluation sample rows are available for CSV export."
        )
    }

    public func exportSelectedEvaluationSamplesJSONL() async {
        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let selectedJobID = selectedEvaluationHistoryJobID.isEmpty
                    ? (selectedEvaluationHistoryEntry?.jobID ?? "")
                    : selectedEvaluationHistoryJobID
                let exportDirectory = try Self.ensureEvaluationExportDirectory()
                let outputPath = exportDirectory.appendingPathComponent(
                    Self.evaluationSamplesJSONLFileName(jobID: selectedJobID)
                ).path
                let response = try await cliWorkflowRunner.decodeJSON(
                    MelixCLIExportResponse.self,
                    command: .evalExportSamplesJSONL(.init(jobID: selectedJobID, outputPath: outputPath, json: true))
                )
                clearCLIWorkflowFailure()
                lastEvaluationExport = RuntimeEvaluationExportState(
                    outputPath: response.outputPath,
                    rowCount: response.rowCount,
                    formatTitle: "samples.jsonl"
                )
                await metrics.record(
                    name: "menu.eval_export_jsonl_ms",
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            let exportDirectory = try Self.ensureEvaluationExportDirectory()
            let bundle: ControlPlaneBenchmarkExportBundle
            if let operatorCommandRunner {
                bundle = try await operatorCommandRunner.fetchBenchmarkExportBundle(outputDir: exportDirectory.path)
            } else {
                let export = try await client.exportResults(outputDir: exportDirectory.path)
                bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            }
            applyBenchmarkExportBundle(bundle)
            let selectedJobID = selectedEvaluationHistoryJobID.isEmpty ? nil : selectedEvaluationHistoryJobID
            let rows = bundle.evaluationSampleRows(jobID: selectedJobID)
            guard rows.isEmpty == false else {
                recordLocalError("No evaluation sample rows are available for JSONL export.")
                notifyStateChanged()
                return
            }
            let jsonl = try bundle.evaluationSamplesJSONL(jobID: selectedJobID)
            let outputURL = exportDirectory.appendingPathComponent(
                Self.evaluationSamplesJSONLFileName(jobID: selectedJobID)
            )
            try jsonl.write(to: outputURL, atomically: true, encoding: .utf8)
            lastEvaluationExport = RuntimeEvaluationExportState(
                outputPath: outputURL.path,
                rowCount: rows.count,
                formatTitle: "samples.jsonl"
            )
            await metrics.record(
                name: "menu.eval_export_jsonl_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    private func refreshModelOpsProductState(modelID: String, notify: Bool) async {
        await refreshModelOpsProductState(
            modelID: modelID,
            notify: notify,
            rescan: false,
            registryRootsOverride: nil,
            refreshFoundationAfterSuccess: false
        )
    }

    private func refreshModelOpsProductState(
        modelID: String,
        notify: Bool,
        rescan: Bool,
        registryRootsOverride: [String]?,
        refreshFoundationAfterSuccess: Bool
    ) async {
        let startedAt = Date()
        do {
            var ext: [String: String] = [:]
            let requestedRegistryRoots = resolvedRegistryRootOverride(registryRootsOverride)
            if let requestedRegistryRoots,
               let encodedRoots = Self.encodedRegistryRoots(requestedRegistryRoots) {
                ext["melix.registry_roots_json"] = encodedRoots
            }
            if rescan {
                ext["melix.registry_rescan"] = "true"
            }
            let result: Melix_Controlplane_V1_ModelOperationResult
            if let operatorCommandRunner {
                result = try await operatorCommandRunner.performModelOperation(
                    modelID: modelID,
                    operation: "registry_snapshot",
                    outputDir: "",
                    ext: ext
                )
            } else {
                result = try await client.runModelOperation(
                    modelID: modelID,
                    operation: "registry_snapshot",
                    outputDir: "",
                    quantProfileID: "",
                    weightQuant: "",
                    kvQuant: "",
                    ext: ext
                )
            }
            await metrics.record(
                name: "menu.model_ops_refresh_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            applyModelOpsSnapshot(manifestJSON: result.manifestJson)
            if let requestedRegistryRoots {
                registryHasConfiguredRootOverride = true
                registryConfiguredRootPaths = requestedRegistryRoots
            }
            if refreshFoundationAfterSuccess {
                await refreshDesktopFoundation()
            }
        } catch {
            recordLocalError(String(describing: error))
        }
        if notify {
            notifyStateChanged()
        }
    }

    private func refreshDownloadQueueState(
        notify: Bool,
        surfaceErrors: Bool
    ) async {
        guard let modelID = resolvedModelOpsRefreshModelID() else {
            if notify {
                notifyStateChanged()
            }
            return
        }

        do {
            let result: Melix_Controlplane_V1_ModelOperationResult
            if let operatorCommandRunner {
                result = try await operatorCommandRunner.performModelOperation(
                    modelID: modelID,
                    operation: "registry_snapshot",
                    outputDir: "",
                    ext: [:]
                )
            } else {
                result = try await client.runModelOperation(
                    modelID: modelID,
                    operation: "registry_snapshot",
                    outputDir: "",
                    quantProfileID: "",
                    weightQuant: "",
                    kvQuant: "",
                    ext: [:]
                )
            }
            applyModelOpsSnapshot(manifestJSON: result.manifestJson)
        } catch {
            if surfaceErrors {
                recordLocalError(String(describing: error))
            }
        }
        if notify {
            notifyStateChanged()
        }
    }

    private func applyModelOpsSnapshot(manifestJSON: String) {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            recordLocalError("Model operations registry snapshot could not be decoded.")
            return
        }

        let adapters = (payload["adapters"] as? [[String: Any]]) ?? []
        let jobs = (payload["jobs"] as? [[String: Any]]) ?? []
        let downloads = (payload["downloads"] as? [[String: Any]]) ?? []
        let experimentGroups = (payload["experiment_groups"] as? [[String: Any]]) ?? []
        adapterPackages = adapters.map(Self.makeAdapterPackageState)
        downloadQueue = downloads
            .compactMap(Self.makeDownloadQueueEntryState)
            .sorted { lhs, rhs in
                if lhs.resumeReady == rhs.resumeReady {
                    return lhs.jobID > rhs.jobID
                }
                return lhs.resumeReady && rhs.resumeReady == false
            }
        trainingHistory = jobs
            .filter { Self.stringValue("operation", from: $0) == "train_lora" }
            .map(Self.makeTrainingHistoryEntryState)
        loraExperimentGroups = experimentGroups.compactMap(Self.makeLoraExperimentGroupState)
        if let registryPayload = payload["model_registry"] as? [String: Any] {
            let roots = (registryPayload["roots"] as? [[String: Any]] ?? [])
                .compactMap(Self.makeRegistryRootState)
                .sorted { lhs, rhs in
                    if lhs.rootOrder == rhs.rootOrder {
                        return lhs.rootPath < rhs.rootPath
                    }
                    return lhs.rootOrder < rhs.rootOrder
                }
            registryRoots = roots
            if registryHasConfiguredRootOverride == false {
                registryConfiguredRootPaths = roots.map(\.rootPath)
            }
            let scannedAtUnixMS = Self.int64Value("scanned_at_unix_ms", from: registryPayload)
            registryScannedAtText = scannedAtUnixMS > 0
                ? Self.benchmarkTimestampLabel(scannedAtUnixMS)
                : "Unknown"
        }
        refreshLoraSelectionState()
    }

    private func resolvedModelOpsRefreshModelID() -> String? {
        if let modelID = primaryModel?.modelID, !modelID.isEmpty {
            return modelID
        }
        if let modelID = latestSnapshot.models.first?.modelID, !modelID.isEmpty {
            return modelID
        }
        return nil
    }

    private func latestCLITrainedAdapterPath() -> String {
        guard lastModelOperation?.operation == "train_lora" else {
            return ""
        }
        return Self.normalizedOptionalString(lastModelOperation?.outputPath ?? "") ?? ""
    }

    private func beginLoraWorkflow(
        _ operation: RuntimeLoraWorkflowOperation,
        detail: String
    ) {
        loraWorkflowStatus = RuntimeLoraWorkflowStatusState(
            operation: operation.rawValue,
            phase: .running,
            title: operation.runningTitle,
            detail: sanitizedRichText(detail)
        )
        notifyStateChanged()
    }

    private func completeLoraWorkflow(
        _ operation: RuntimeLoraWorkflowOperation,
        outputPath: String,
        fallbackDetail: String = ""
    ) {
        let normalizedOutputPath = Self.normalizedOptionalString(outputPath) ?? ""
        let normalizedFallback = Self.normalizedOptionalString(fallbackDetail) ?? ""
        loraWorkflowStatus = RuntimeLoraWorkflowStatusState(
            operation: operation.rawValue,
            phase: .succeeded,
            title: operation.successTitle,
            detail: sanitizedRichText(normalizedOutputPath.isEmpty ? normalizedFallback : normalizedOutputPath)
        )
    }

    private func failLoraWorkflow(
        _ operation: RuntimeLoraWorkflowOperation,
        detail: String
    ) {
        loraWorkflowStatus = RuntimeLoraWorkflowStatusState(
            operation: operation.rawValue,
            phase: .failed,
            title: operation.failureTitle,
            detail: sanitizedRichText(detail)
        )
    }

    private func surfaceLoraWorkflowGuardFailure(
        _ operation: RuntimeLoraWorkflowOperation,
        message: String
    ) {
        recordLocalError(message)
        failLoraWorkflow(operation, detail: message)
        notifyStateChanged()
    }

    private func workflowErrorMessage(_ error: Error) -> String {
        let localizedDescription = (error as NSError).localizedDescription
        if localizedDescription.isEmpty == false,
           localizedDescription != "The operation couldn’t be completed." {
            return localizedDescription
        }
        return String(describing: error)
    }

    private func loraTrainingWorkflowDetail() -> String {
        let datasetLabel: String
        switch loraDatasetSourceKind {
        case .localPackage:
            datasetLabel = Self.normalizedOptionalString(loraDatasetURI) ?? "Local package"
        case .huggingFaceDataset:
            datasetLabel = Self.normalizedOptionalString(loraHFDatasetPath) ?? "Hugging Face dataset"
        }
        let adapterName = Self.normalizedOptionalString(loraAdapterName) ?? "Unnamed adapter"
        return "\(adapterName) • \(datasetLabel)"
    }

    private func loraActivationWorkflowDetail(adapterPath: String) -> String {
        if let adapter = selectedAdapterPackage {
            return "\(adapter.adapterName) • \(loraActivationMode.title)"
        }
        let path = URL(fileURLWithPath: adapterPath)
        let adapterName = path.deletingPathExtension().lastPathComponent
        let title = adapterName.isEmpty ? "Selected adapter" : adapterName
        return "\(title) • \(loraActivationMode.title)"
    }

    private func loraPublishWorkflowDetail(adapter: RuntimeAdapterPackageState) -> String {
        let targetRepo = adapter.targetRepo.isEmpty ? "melix/adapters/\(adapter.adapterName)" : adapter.targetRepo
        return "\(adapter.adapterName) • \(targetRepo)"
    }

    private func loraRemoveWorkflowDetail(adapter: RuntimeAdapterPackageState) -> String {
        let derivedModelID = Self.normalizedOptionalString(adapter.derivedModelID) ?? "Derived model"
        return "\(adapter.adapterName) • \(derivedModelID)"
    }

    private func updateSelectedServerSession(
        _ update: (inout DesktopServerSessionState) -> Void
    ) {
        replaceServerSession(id: selectedServerSessionID, update)
        refreshAgentIntegrationExports()
        notifyStateChanged()
    }

    private func replaceServerSession(
        id: String,
        _ update: (inout DesktopServerSessionState) -> Void
    ) {
        if let index = persistedServerSessions.firstIndex(where: { $0.id == id }) {
            var session = persistedServerSessions[index]
            update(&session)
            persistedServerSessions[index] = session
        }
        if let index = serverSessions.firstIndex(where: { $0.id == id }) {
            var session = serverSessions[index]
            update(&session)
            serverSessions[index] = session
        }
    }

    private func performServerLifecycleAction(
        serverSessionID: String,
        metricName: String,
        action: @escaping @Sendable (String) async throws -> Melix_Controlplane_V1_ServerSnapshot
    ) async {
        guard !serverSessionID.isEmpty else {
            return
        }

        selectedServerSessionID = serverSessionID

        let startedAt = Date()
        do {
            let snapshot = try await action(serverSessionID)
            await metrics.record(
                name: metricName,
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            apply(snapshot: snapshot)
        } catch {
            replaceServerSession(id: serverSessionID) { session in
                session.lastError = String(describing: error)
                session.updatedAt = Date()
            }
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    private func performServerIdlePolicyUpdate(serverSessionID: String) async {
        guard let serverSession = serverSession(id: serverSessionID) else {
            return
        }

        let startedAt = Date()
        do {
            let snapshot = try await client.updateServerIdlePolicy(
                serverSessionID: serverSession.id,
                autoSleepEnabled: serverSession.autoSleepEnabled,
                lightSleepAfterSeconds: UInt32(max(0, serverSession.lightSleepAfterSeconds)),
                deepSleepAfterSeconds: UInt32(max(0, serverSession.deepSleepAfterSeconds))
            )
            await metrics.record(
                name: "menu.server_idle_policy_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            apply(snapshot: snapshot)
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    @discardableResult
    private func persistGatewayConfig(for serverSessionID: String) async -> Bool {
        guard let serverSession = serverSession(id: serverSessionID) else {
            return false
        }

        let startedAt = Date()
        do {
            let snapshot: Melix_Controlplane_V1_ServerSnapshot
            if let operatorCommandRunner {
                snapshot = try await operatorCommandRunner.applyConfiguredServerSessionGatewayConfig(
                    serverSessionID: serverSession.id
                )
            } else {
                snapshot = try await client.applyServerSessionGatewayConfig(
                    serverSessionID: serverSession.id,
                    host: serverSession.host,
                    port: serverSession.port,
                    servedModelID: serverSession.modelID,
                    rateLimitPerMinute: serverSession.rateLimitPerMinute,
                    timeoutSeconds: serverSession.timeoutSeconds
                )
            }
            await metrics.record(
                name: "menu.gateway_config_apply_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            apply(snapshot: snapshot)
            return true
        } catch {
            recordLocalError("Gateway config apply failed: \(error)")
            notifyStateChanged()
            return false
        }
    }

    @discardableResult
    private func persistServingDefaults(for serverSessionID: String) async -> Bool {
        guard let serverSession = serverSession(id: serverSessionID) else {
            return false
        }

        let startedAt = Date()
        do {
            let snapshot: Melix_Controlplane_V1_ServerSnapshot
            if let operatorCommandRunner {
                snapshot = try await operatorCommandRunner.applyConfiguredServerSessionServingDefaults(
                    serverSessionID: serverSession.id
                )
            } else {
                snapshot = try await client.applyServerSessionServingDefaults(
                    serverSessionID: serverSession.id,
                    temperature: serverSession.servingDefaults.temperature,
                    topP: serverSession.servingDefaults.topP,
                    maxTokens: serverSession.servingDefaults.maxTokens,
                    streamIntervalTokens: serverSession.servingDefaults.streamIntervalTokens,
                    maxConcurrentRequests: serverSession.servingDefaults.maxConcurrentRequests,
                    concurrentProcessingEnabled: serverSession.servingDefaults.concurrentProcessingEnabled,
                    prefillBatchSize: serverSession.servingDefaults.prefillBatchSize,
                    completionBatchSize: serverSession.servingDefaults.completionBatchSize,
                    accelerationMode: servingDefaultsAccelerationMode(
                        from: serverSession.servingDefaults.accelerationMode
                    ),
                    draftModelID: serverSession.servingDefaults.draftModelID,
                    numDraftTokens: serverSession.servingDefaults.numDraftTokens
                )
            }
            await metrics.record(
                name: "menu.serving_defaults_apply_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            apply(snapshot: snapshot)
            return true
        } catch {
            recordLocalError("Serving defaults apply failed: \(error)")
            notifyStateChanged()
            return false
        }
    }

    private func chatSubmissionBlockedMessage(for serverSession: DesktopServerSessionState) -> String {
        switch serverSession.lifecycle {
        case .paused:
            return "Resume the paused Server Session before sending chat prompts."
        case .starting:
            return "Wait for the Server Session to finish starting before sending chat prompts."
        case .stopping:
            return "Wait for the Server Session to finish stopping or start it again before sending chat prompts."
        case .stopped, .draft, .unavailable:
            return "Start the bound Server Session before sending chat prompts."
        case .error:
            return serverSession.lastError.isEmpty
                ? "Recover the failed Server Session before sending chat prompts."
                : "Recover the failed Server Session before sending chat prompts. \(serverSession.lastError)"
        case .running, .sleeping:
            return ""
        }
    }

    private func replaceChatSession(
        id: String,
        _ update: (inout DesktopChatSessionState) -> Void
    ) {
        guard let index = chatSessions.firstIndex(where: { $0.id == id }) else {
            return
        }
        var session = chatSessions[index]
        update(&session)
        chatSessions[index] = session
    }

    private func loadChatSession(_ session: DesktopChatSessionState) {
        selectedChatSessionID = session.id
        if session.hasServerBinding,
           (selectedServerSessionID.isEmpty || serverSession(id: session.serverSessionID) != nil) {
            selectedServerSessionID = session.serverSessionID
        }
        chatTranscript = session.transcript
        chatStatusText = session.statusText
        lastChatUsageText = session.usageText
        lastChatRequestID = session.requestID
        isChatStreaming = session.isStreaming
        chatConversationMessages = session.transcript.compactMap { entry in
            switch entry.kind {
            case .user:
                return ControlPlaneChatRequest.Message(role: "user", content: entry.body)
            case .assistant:
                return ControlPlaneChatRequest.Message(role: "assistant", content: entry.body)
            default:
                return nil
            }
        }
        if let boundServer = serverSession(id: session.serverSessionID) {
            selectedChatModelID = boundServer.modelID
        }
    }

    private func ensureChatSessionsBoundToServerSessions() {
        if selectedServerSession == nil {
            selectedServerSessionID = serverSessions.first?.id ?? ""
        }

        if chatSessions.isEmpty {
            let session = DesktopChatSessionState(
                id: "chat-session-\(UUID().uuidString)",
                title: "Chat 1",
                serverSessionID: "",
                statusText: "Choose Server"
            )
            chatSessions = [session]
            loadChatSession(session)
            return
        }

        chatSessions = chatSessions.map { session in
            guard session.hasServerBinding, serverSession(id: session.serverSessionID) == nil else {
                return session
            }
            var unbound = session
            unbound.serverSessionID = ""
            unbound.statusText = "Choose Server"
            unbound.updatedAt = Date()
            return unbound
        }

        if selectedChatSession == nil, let first = chatSessions.first {
            loadChatSession(first)
        } else if let selectedChatSession, isChatStreaming == false {
            loadChatSession(selectedChatSession)
        }
    }

    private func syncServerSessionsWithModels() {
        let textModels = serveableModels

        if persistedServerSessions.isEmpty, let firstTextModel = textModels.first {
            let seededServerSessionID = latestSnapshot.runtimeSessions.first?.serverSessionID ?? "server-session-1"
            let projectedConfig = Self.gatewayConfigProjection(
                from: latestSnapshot,
                serverSessionID: seededServerSessionID
            )
            let projectedServedModelID = projectedConfig?.servedModelID
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let seeded = makeServerSession(
                for: projectedConfig.flatMap { projection in
                    textModels.first { $0.modelID == projection.servedModelID }
                } ?? firstTextModel,
                title: "Primary Server",
                port: projectedConfig?.port ?? 8080,
                serverSessionID: seededServerSessionID,
                modelIDOverride: projectedServedModelID?.isEmpty == false ? projectedServedModelID : nil
            )
            if projectedConfig != nil {
                var projectedSeeded = seeded
                applyGatewayConfigProjection(to: &projectedSeeded)
                persistedServerSessions = [projectedSeeded]
            } else {
                persistedServerSessions = [seeded]
            }
            selectedServerSessionID = seeded.id
        }

        guard persistedServerSessions.isEmpty == false else {
            serverSessions = []
            return
        }

        serverSessions = persistedServerSessions.enumerated().map { offset, session in
            var updated = session
            applyGatewayConfigProjection(to: &updated)
            applyServingDefaultsProjection(to: &updated)
            let runtimeSession = runtimeSession(for: session.id, fallbackIndex: offset)
            if let model = models.first(where: { $0.modelID == session.modelID }) {
                updated.lastKnownModelStateText = model.stateText
                if runtimeSession == nil {
                    switch session.lifecycle {
                    case .draft, .running, .paused, .sleeping, .stopped, .error, .unavailable:
                        updated.lifecycle = session.lifecycle
                    case .starting:
                        updated.lifecycle = model.isLoaded ? .running : .starting
                    case .stopping:
                        updated.lifecycle = model.isLoaded ? .stopping : .stopped
                    }
                }
            } else {
                updated.lifecycle = .unavailable
                updated.lastKnownModelStateText = "Unavailable"
            }
            if let runtimeSession {
                applyRuntimeSessionProjection(to: &updated, runtimeSession: runtimeSession)
            }
            if updated.title.isEmpty {
                updated.title = offset == 0 ? "Primary Server" : "Server \(offset + 1)"
            }
            applyGatewayAccessProjection(to: &updated)
            return updated
        }

        if selectedServerSession == nil {
            selectedServerSessionID = serverSessions.first?.id ?? ""
        }

        maybeApplyStoredGatewayAccessForSelectedRunningSession()
    }

    private func makeServerSession(
        for model: RuntimeModelRow,
        title: String,
        port: Int,
        serverSessionID: String = "server-session-\(UUID().uuidString)",
        modelIDOverride: String? = nil
    ) -> DesktopServerSessionState {
        var session = DesktopServerSessionState(
            id: serverSessionID,
            title: title,
            modelID: modelIDOverride ?? model.modelID,
            port: port,
            lifecycle: .running,
            lastKnownModelStateText: model.stateText
        )
        applyGatewayConfigProjection(to: &session)
        applyServingDefaultsProjection(to: &session)
        applyGatewayAccessProjection(to: &session)
        return session
    }

    private func markServerSessions(
        for modelID: String,
        lifecycle: DesktopServerSessionLifecycle,
        error: String
    ) {
        serverSessions = serverSessions.map { session in
            guard session.modelID == modelID else {
                return session
            }
            var updated = session
            updated.lifecycle = lifecycle
            updated.lastError = sanitizedRichText(error)
            updated.updatedAt = Date()
            return updated
        }
    }

    private func restoreOperatorSessionState() {
        do {
            guard let restoredState = try operatorSessionStore.load() else {
                return
            }
            selectedSurface = restoredState.selectedSurface
            selectedToolSection = restoredState.selectedToolSection
            selectedServerSessionID = restoredState.selectedServerSessionID
            desktopPaneVisibility = DesktopPaneVisibilityState.mergedWithDefaults(restoredState.paneVisibility)
            dismissedBannerIDs = Set(restoredState.dismissedBannerIDs)
            registryConfiguredRootPaths = Self.normalizedRegistryRootPaths(restoredState.registryRoots)
            registryHasConfiguredRootOverride = registryConfiguredRootPaths.isEmpty == false
            if restoredState.serverSessions.isEmpty == false {
                persistedServerSessions = restoredState.serverSessions
                serverSessions = restoredState.serverSessions
            }
            downloadQueue = restoredState.downloadQueue
            lastPersistedOperatorSessionState = restoredState
        } catch {
            recordLocalError("Operator session restore failed: \(error)")
        }
    }

    private func currentOperatorSessionState() -> OperatorSessionState {
        OperatorSessionState(
            selectedSurface: selectedSurface,
            selectedToolSection: selectedToolSection,
            selectedServerSessionID: selectedServerSessionID,
            serverSessions: persistedServerSessions,
            dismissedBannerIDs: dismissedBannerIDs.sorted(),
            downloadQueue: downloadQueue,
            registryRoots: registryConfiguredRootPaths,
            paneVisibility: desktopPaneVisibility
        )
    }

    private func persistOperatorSessionState() {
        guard operatorStateRestored else {
            return
        }

        let state = currentOperatorSessionState()
        guard state != lastPersistedOperatorSessionState else {
            return
        }

        let startedAt = Date()
        do {
            try operatorSessionStore.save(state)
            lastPersistedOperatorSessionState = state
            let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
            Task {
                await metrics.record(name: "operator.session_persist_write_ms", valueMs: elapsedMs)
            }
        } catch {
            recordLocalError("Operator session persistence failed: \(error)")
        }
    }

    private func executeServerLifecycleCommand(
        _ command: MelixCLICommand,
        metricName: String
    ) async -> Bool {
        guard let commandWorkflowRunner else {
            return false
        }

        let startedAt = Date()
        do {
            let output = try await commandWorkflowRunner.run(command)
            restoreOperatorSessionState()
            if commandWorkflowRunner.surface == .subprocess {
                try applyCLIServerSnapshotIfPresent(output: output, command: command, surface: commandWorkflowRunner.surface)
            } else {
                await refreshDesktopFoundation()
            }
            clearCLIWorkflowFailure()
            await metrics.record(
                name: metricName,
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordCLIWorkflowErrorIfNeeded(error)
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
        return true
    }

    private func startServerSessionViaCLI(serverSessionID: String) async {
        guard let cliWorkflowRunner, let serverSession = serverSession(id: serverSessionID) else {
            return
        }

        let startedAt = Date()
        do {
            _ = try await cliWorkflowRunner.run(
                .serverSessionUpdate(
                    .init(
                        serverSessionID: serverSession.id,
                        title: serverSession.title,
                        modelID: serverSession.modelID,
                        host: serverSession.host,
                        port: serverSession.port,
                        rateLimitPerMinute: serverSession.rateLimitPerMinute,
                        timeoutSeconds: serverSession.timeoutSeconds,
                        accelerationMode: serverSession.servingDefaults.accelerationMode,
                        draftModelID: serverSession.servingDefaults.draftModelID,
                        numDraftTokens: serverSession.servingDefaults.numDraftTokens,
                        json: true
                    )
                )
            )
            restoreOperatorSessionState()
            _ = try await cliWorkflowRunner.run(
                .serverSessionSelect(.init(serverSessionID: serverSession.id, json: true))
            )
            restoreOperatorSessionState()
            let snapshotOutput = try await cliWorkflowRunner.run(
                .serverStart(.init(serverSessionID: serverSession.id, json: true))
            )
            try applyCLIServerSnapshotIfPresent(
                output: snapshotOutput,
                command: .serverStart(.init(serverSessionID: serverSession.id, json: true)),
                surface: cliWorkflowRunner.surface
            )
            clearCLIWorkflowFailure()
            await metrics.record(
                name: "menu.server_start_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordCLIWorkflowErrorIfNeeded(error)
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    private func maybeApplyStoredGatewayAccessForSelectedRunningSession() {
        guard let selectedServerSession else {
            scheduleGatewayAccessClear(serverSessionID: lastAppliedGatewaySessionID)
            return
        }
        guard selectedServerSession.retainsGatewayAccessConfiguration else {
            scheduleGatewayAccessClear(serverSessionID: selectedServerSession.id)
            return
        }

        do {
            guard
                let persistedRecord = try serverSessionAPIKeyStore.loadPrimaryKey(
                    serverSessionID: selectedServerSession.id
                )
            else {
                scheduleGatewayAccessClear(serverSessionID: selectedServerSession.id)
                return
            }
            guard persistedRecord.primaryKey.isEmpty == false else {
                scheduleGatewayAccessClear(serverSessionID: selectedServerSession.id)
                return
            }

            scheduleGatewayAccessApply(
                serverSessionID: selectedServerSession.id,
                primaryKey: persistedRecord.primaryKey,
                keyID: persistedRecord.keyID,
                label: persistedRecord.keyID,
                tokenHint: persistedRecord.keyID
            )
        } catch {
            recordLocalError("Gateway API key restore failed: \(error)")
        }
    }

    private func scheduleGatewayAccessClear(serverSessionID: String) {
        guard lastAppliedGatewaySessionID.isEmpty == false else {
            return
        }
        let targetServerSessionID = serverSessionID.isEmpty ? lastAppliedGatewaySessionID : serverSessionID
        gatewayApplyTask?.cancel()
        gatewayApplyTask = Task { @MainActor in
            do {
                try await client.clearServerSessionGatewayAccess(serverSessionID: targetServerSessionID)
                resetAppliedGatewayAccessState()
            } catch {
                recordLocalError("Gateway access clear failed: \(error)")
                notifyStateChanged()
            }
        }
    }

    private func scheduleGatewayAccessApply(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String,
        force: Bool = false
    ) {
        guard !primaryKey.isEmpty else {
            return
        }
        if force == false,
           lastAppliedGatewaySessionID == serverSessionID,
           lastAppliedGatewayPrimaryKey == primaryKey
        {
            return
        }

        gatewayApplyTask?.cancel()
        gatewayApplyTask = Task { @MainActor in
            do {
                try await client.applyServerSessionGatewayAccess(
                    serverSessionID: serverSessionID,
                    primaryKey: primaryKey,
                    keyID: keyID,
                    label: label,
                    tokenHint: tokenHint
                )
                lastAppliedGatewaySessionID = serverSessionID
                lastAppliedGatewayPrimaryKey = primaryKey
            } catch {
                recordLocalError("Gateway access apply failed: \(error)")
                notifyStateChanged()
            }
        }
    }

    private func persistSelectedChatSessionState() {
        guard let session = selectedChatSession else {
            return
        }
        replaceChatSession(id: session.id) { current in
            current.transcript = persistableChatTranscript()
            current.statusText = chatStatusText
            current.usageText = lastChatUsageText
            current.requestID = lastChatRequestID
            current.isStreaming = isChatStreaming
            current.updatedAt = Date()
        }
    }

    private func consume(event: Melix_Controlplane_V1_ControlPlaneEvent) async {
        handle(event: event)
    }

    private func handle(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        lastSeenSeq = max(lastSeenSeq, event.seq)
        record(event: event)

        switch event.payload {
        case .serverState(let serverStateChanged):
            latestSnapshot.serverState = serverStateChanged.state
            latestSnapshot.runtimeSessions = serverStateChanged.runtimeSessions
            serverStateText = Self.serverStateText(serverStateChanged.state)
            statusTitle = "Melix \(serverStateText)"
            syncServerSessionsWithModels()
        case .modelState(let stateChanged):
            var model = existingModelSummary(for: stateChanged.modelID)
            model.modelID = stateChanged.modelID
            model.state = stateChanged.state
            upsert(model: model)
        case .sessionState(let sessionStateChanged):
            upsert(session: sessionStateChanged.state)
        case .requestProgress(let progress):
            latestSnapshot.metrics.values["scheduler.prefill_progress_processed_tokens"] = Double(progress.prefillProcessedTokens)
            latestSnapshot.metrics.values["scheduler.prefill_progress_total_tokens"] = Double(progress.prefillTotalTokens)
            latestSnapshot.metrics.values["scheduler.prefill_progress_pct"] = progress.prefillProgressPct
            latestSnapshot.metrics.values["scheduler.prefill_active_requests"] = Double(progress.activeRequests)
            latestSnapshot.metrics.values["scheduler.prefill_waiting_requests"] = Double(progress.waitingRequests)
            latestSnapshot.metrics.values["scheduler.restore_stage_code"] = Self.restoreStageMetricCode(progress.restoreStage)
            latestSnapshot.metrics.values["scheduler.cache_pressure"] = progress.cachePressure
            latestSnapshot.queues.activeRequests = progress.activeRequests
            latestSnapshot.queues.queuedRequests = progress.waitingRequests
        case .cacheStats(let cacheStats):
            latestSnapshot.cache = cacheStats.summary
        case .resourcePressure(let resourcePressure):
            latestSnapshot.resources = resourcePressure.resources
        case .log(let logEvent):
            if logEvent.level.lowercased() == "error" {
                setLastError(logEvent.message)
            }
        case .imageJob(let imageJobChanged):
            upsert(imageJob: imageJobChanged.job)
            imageStatusText = Self.imageStatusText(for: imageJobChanged.job)
        default:
            break
        }

        refreshChatCapabilities()

        notifyStateChanged()
    }

    private func apply(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        latestSnapshot = snapshot
        if let lastBenchReport {
            for metric in lastBenchReport.metrics {
                if let value = Double(metric.value) {
                    latestSnapshot.metrics.values[metric.name] = value
                }
            }
        }
        serverStateText = Self.serverStateText(snapshot.serverState)
        statusTitle = "Melix \(serverStateText)"
        models = snapshot.models
            .filter(ModelCatalogPresentation.isUserVisible)
            .sorted { $0.modelID < $1.modelID }
            .map(makeRuntimeModelRow)
        applyImageDefaultsProjection()
        syncServerSessionsWithModels()
        ensureChatSessionsBoundToServerSessions()
        refreshImageState()
        refreshChatCapabilities()
        refreshLoraSelectionState()
        refreshBenchmarkSelectionState()
        refreshEvaluationSelectionState()
        refreshAgentIntegrationExports()
        synchronizeModelSettingsDrafts()
        notifyStateChanged()
    }

    private func refreshBenchmarkSelectionState() {
        let availableModelIDs = benchmarkModels.map(\.modelID)
        if availableModelIDs.contains(selectedBenchmarkModelID) == false {
            selectedBenchmarkModelID = availableModelIDs.first ?? ""
        }

        let validSuiteIDs = Set(Self.benchmarkSuiteOptions.map(\.id))
        selectedBenchmarkSuiteIDs = selectedBenchmarkSuiteIDs.intersection(validSuiteIDs)
        if selectedBenchmarkSuiteIDs.isEmpty {
            selectedBenchmarkSuiteIDs = ["smoke"]
        }
        selectedBenchContextLengths = Self.normalizedBenchValues(
            selectedBenchContextLengths,
            defaultValues: Self.benchmarkContextLengthOptions.prefix(2).map { $0 }
        )
        selectedBenchBatchSizes = Self.normalizedBenchValues(
            selectedBenchBatchSizes,
            defaultValues: Self.benchmarkBatchSizeOptions.filter { $0 > 1 }.prefix(2).map { $0 }
        )
        selectedBenchGenerationLengths = Self.normalizedBenchValues(
            selectedBenchGenerationLengths,
            defaultValues: Self.benchmarkGenerationLengthOptions.prefix(2).map { $0 }
        )
        selectedBenchMatrixCacheProfiles = normalizedBenchMatrixCacheProfiles()
        selectedBenchMatrixReasoningModes = normalizedBenchMatrixReasoningModes()
        selectedBenchMatrixStructuredOutputModes = normalizedBenchMatrixStructuredOutputModes()
        selectedBenchMatrixConcurrencyLevels = normalizedBenchMatrixConcurrencyLevels()
        benchRepeats = normalizedBenchRepeatsText()
        benchMatrixRepeats = normalizedBenchMatrixRepeatsText()
        benchMatrixRequests = normalizedBenchMatrixRequestsText()
        benchMatrixDurationSeconds = normalizedBenchMatrixDurationSecondsText()
        benchCacheProfile = normalizedBenchCacheProfile()
        benchReasoningMode = normalizedBenchReasoningMode()
        benchStructuredOutputMode = normalizedBenchStructuredOutputMode()
        rebuildBenchmarkDerivedState()
        rebuildBenchmarkMatrixDerivedState()
    }

    private func refreshEvaluationSelectionState() {
        let availableModelIDs = evaluationModels.map(\.modelID)
        if availableModelIDs.contains(selectedEvaluationModelID) == false {
            selectedEvaluationModelID = availableModelIDs.first ?? ""
        }

        let validSuiteIDs = Set(Self.evaluationSuiteOptions.map(\.id))
        selectedEvaluationSuiteIDs = selectedEvaluationSuiteIDs.intersection(validSuiteIDs)
        if selectedEvaluationSuiteIDs.isEmpty {
            selectedEvaluationSuiteIDs = ["mmlu"]
        }
        let availableCompareTargetModelIDs = Set(evaluationCompareTargetModels.map(\.modelID))
        selectedEvaluationCompareTargetModelIDs = selectedEvaluationCompareTargetModelIDs
            .intersection(availableCompareTargetModelIDs)
        evaluationScoringMode = normalizedEvaluationScoringMode()
        evaluationCodeExecPolicy = normalizedEvaluationCodeExecPolicy()
        rebuildEvaluationDerivedState()
    }

    private func refreshBenchmarkHistory(notify: Bool) async {
        let startedAt = Date()
        do {
            let exportDirectory = try Self.ensureBenchmarkExportDirectory()
            let bundle: ControlPlaneBenchmarkExportBundle
            if let operatorCommandRunner {
                bundle = try await operatorCommandRunner.fetchBenchmarkExportBundle(outputDir: exportDirectory.path)
            } else {
                let export = try await client.exportResults(outputDir: exportDirectory.path)
                bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            }
            applyBenchmarkExportBundle(bundle)
            let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
            await metrics.record(name: "menu.bench_history_refresh_ms", valueMs: elapsedMs)
            if selectedBenchmarkPresentationMode == .matrix {
                await metrics.record(name: "menu.bench_matrix_history_refresh_ms", valueMs: elapsedMs)
            }
        } catch {
            recordLocalError(String(describing: error))
        }
        if notify {
            notifyStateChanged()
        }
    }

    private func refreshEvaluationHistory(notify: Bool) async {
        let startedAt = Date()
        do {
            let exportDirectory = try Self.ensureEvaluationExportDirectory()
            let bundle: ControlPlaneBenchmarkExportBundle
            if let operatorCommandRunner {
                bundle = try await operatorCommandRunner.fetchBenchmarkExportBundle(outputDir: exportDirectory.path)
            } else {
                let export = try await client.exportResults(outputDir: exportDirectory.path)
                bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            }
            applyBenchmarkExportBundle(bundle)
            await metrics.record(
                name: "menu.eval_history_refresh_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        if notify {
            notifyStateChanged()
        }
    }

    private func applyBenchmarkExportBundle(_ bundle: ControlPlaneBenchmarkExportBundle) {
        benchmarkExportBundle = bundle
        benchmarkHistory = bundle.benchmarkHistoryEntries().map(Self.makeBenchmarkHistoryEntryState)
        if benchmarkHistory.contains(where: { $0.jobID == selectedBenchmarkHistoryJobID }) == false {
            selectedBenchmarkHistoryJobID = benchmarkHistory.first?.jobID ?? ""
        }
        rebuildBenchmarkDerivedState()
        rebuildBenchmarkMatrixDerivedState()
        rebuildEvaluationDerivedState()
    }

    private func rebuildBenchmarkDerivedState() {
        guard let benchmarkExportBundle else {
            benchmarkMetricCards = []
            benchmarkChartPoints = []
            benchmarkMetricOptions = []
            if selectedBenchmarkHistoryJobID.isEmpty == false {
                selectedBenchmarkHistoryJobID = ""
            }
            if selectedBenchmarkMetricName.isEmpty == false {
                selectedBenchmarkMetricName = ""
            }
            return
        }

        let allRows = benchmarkExportBundle.benchmarkCSVRows()
        benchmarkMetricOptions = Array(Set(allRows.map(\.metricName))).sorted()
        let selectedHistoryJobID = selectedBenchmarkHistoryJobID.isEmpty ? (benchmarkHistory.first?.jobID ?? "") : selectedBenchmarkHistoryJobID
        if selectedBenchmarkHistoryJobID != selectedHistoryJobID {
            selectedBenchmarkHistoryJobID = selectedHistoryJobID
        }

        let selectedRows = benchmarkExportBundle.benchmarkCSVRows(jobID: selectedHistoryJobID.isEmpty ? nil : selectedHistoryJobID)
        benchmarkMetricCards = selectedRows.map(Self.makeBenchmarkMetricCardState)

        let preferredMetricName = selectedRows.first?.metricName ?? benchmarkMetricOptions.first ?? ""
        if benchmarkMetricOptions.contains(selectedBenchmarkMetricName) == false {
            selectedBenchmarkMetricName = preferredMetricName
        }

        let suiteFilter = selectedBenchmarkSuiteIDs.isEmpty ? Set(benchmarkSuites.map(\.id)) : selectedBenchmarkSuiteIDs
        benchmarkChartPoints = allRows
            .filter { row in
                row.metricName == selectedBenchmarkMetricName && suiteFilter.contains(row.suiteID)
            }
            .sorted { lhs, rhs in
                if lhs.createdAtUnixMS == rhs.createdAtUnixMS {
                    return lhs.jobID < rhs.jobID
                }
                return lhs.createdAtUnixMS < rhs.createdAtUnixMS
            }
            .map(Self.makeBenchmarkChartPointState)
    }

    private func rebuildBenchmarkMatrixDerivedState() {
        guard let benchmarkExportBundle else {
            benchmarkMatrixHistory = []
            benchmarkMatrixSummaryCards = []
            benchmarkMatrixSummaryRows = []
            benchmarkMatrixContextChartPoints = []
            benchmarkMatrixThroughputChartPoints = []
            lastBenchmarkMatrixExport = nil
            if selectedBenchmarkMatrixHistoryJobID.isEmpty == false {
                selectedBenchmarkMatrixHistoryJobID = ""
            }
            return
        }

        let matrixHistoryEntries = benchmarkExportBundle.benchmarkMatrixHistoryEntries()
        benchmarkMatrixHistory = Self.makeBenchmarkMatrixHistoryEntryStates(from: matrixHistoryEntries)
        let selectedHistoryJobID = selectedBenchmarkMatrixHistoryJobID.isEmpty
            ? (benchmarkMatrixHistory.first?.jobID ?? "")
            : selectedBenchmarkMatrixHistoryJobID
        if selectedBenchmarkMatrixHistoryJobID != selectedHistoryJobID {
            selectedBenchmarkMatrixHistoryJobID = selectedHistoryJobID
        }

        let selectedRows = benchmarkExportBundle.benchmarkMatrixSummaryCSVRows(jobID: selectedHistoryJobID.isEmpty ? nil : selectedHistoryJobID)
        benchmarkMatrixSummaryRows = selectedRows.map(Self.makeBenchmarkMatrixSummaryRowState)
        benchmarkMatrixSummaryCards = Self.makeBenchmarkMatrixSummaryCardStates(from: selectedRows)
        benchmarkMatrixContextChartPoints = selectedRows.map(Self.makeBenchmarkMatrixContextChartPointState)
            .sorted { lhs, rhs in
                if lhs.xValue == rhs.xValue {
                    return lhs.seriesTitle < rhs.seriesTitle
                }
                return lhs.xValue < rhs.xValue
            }
        benchmarkMatrixThroughputChartPoints = selectedRows.map(Self.makeBenchmarkMatrixThroughputChartPointState)
            .sorted { lhs, rhs in
                if lhs.xValue == rhs.xValue {
                    return lhs.seriesTitle < rhs.seriesTitle
                }
                return lhs.xValue < rhs.xValue
            }
    }

    private func rebuildEvaluationDerivedState() {
        guard let benchmarkExportBundle else {
            evaluationHistory = []
            evaluationMetricCards = []
            evaluationSamplePreview = []
            if selectedEvaluationHistoryJobID.isEmpty == false {
                selectedEvaluationHistoryJobID = ""
            }
            return
        }

        evaluationHistory = benchmarkExportBundle.evaluationHistoryEntries().map(Self.makeEvaluationHistoryEntryState)
        let selectedHistoryJobID = selectedEvaluationHistoryJobID.isEmpty ? (evaluationHistory.first?.jobID ?? "") : selectedEvaluationHistoryJobID
        if selectedEvaluationHistoryJobID != selectedHistoryJobID {
            selectedEvaluationHistoryJobID = selectedHistoryJobID
        }

        let selectedRows = benchmarkExportBundle.evaluationSummaryCSVRows(jobID: selectedHistoryJobID.isEmpty ? nil : selectedHistoryJobID)
        evaluationMetricCards = selectedRows.map(Self.makeEvaluationMetricCardState)
        evaluationSamplePreview = benchmarkExportBundle.evaluationSampleRows(jobID: selectedHistoryJobID.isEmpty ? nil : selectedHistoryJobID)
            .prefix(6)
            .map(Self.makeEvaluationSamplePreviewState)
    }

    private func resolvedBenchmarkModelID() -> String {
        if !selectedBenchmarkModelID.isEmpty {
            return selectedBenchmarkModelID
        }
        return benchmarkModels.first?.modelID ?? ""
    }

    private func resolvedEvaluationModelID() -> String {
        if !selectedEvaluationModelID.isEmpty {
            return selectedEvaluationModelID
        }
        return evaluationModels.first?.modelID ?? ""
    }

    private func resolvedBenchmarkTaskKind() -> String {
        switch selectedBenchmarkTargetMode {
        case .catalogModel:
            let modelID = resolvedBenchmarkModelID()
            guard let model = latestSnapshot.models.first(where: { $0.modelID == modelID }) else {
                return "text-generation"
            }
            return Self.benchmarkTaskKind(for: model)
        case .huggingFaceRepo:
            return Self.inferredTaskKind(forRepoID: benchmarkHFRepoID)
        }
    }

    private func benchmarkParameters() -> [String: String] {
        var parameters: [String: String] = [:]
        let sampleSize = benchmarkSampleSize.trimmingCharacters(in: .whitespacesAndNewlines)
        if sampleSize.isEmpty == false {
            parameters["sample_size"] = sampleSize
        }
        let batchFactor = benchmarkBatchFactor.trimmingCharacters(in: .whitespacesAndNewlines)
        if batchFactor.isEmpty == false {
            parameters["batch_factor"] = batchFactor
        }
        return parameters
    }

    private func evaluationParameters(
        compareTargetModelIDs: [String]?,
        promptSnapshot: EvaluationPromptSnapshot?,
        semanticJudgeParameters: [String: String] = [:]
    ) -> [String: String] {
        var parameters: [String: String] = [:]
        let batchFactor = evaluationBatchFactor.trimmingCharacters(in: .whitespacesAndNewlines)
        if batchFactor.isEmpty == false {
            parameters["batch_factor"] = batchFactor
        }
        let seed = evaluationSeed.trimmingCharacters(in: .whitespacesAndNewlines)
        if seed.isEmpty == false {
            parameters["seed"] = seed
        }
        let fewShot = evaluationFewShot.trimmingCharacters(in: .whitespacesAndNewlines)
        if fewShot.isEmpty == false {
            parameters["few_shot"] = fewShot
        }
        let scoringMode = normalizedEvaluationScoringMode()
        if scoringMode.isEmpty == false {
            parameters["scoring_mode"] = scoringMode
        }
        let codeExecPolicy = normalizedEvaluationCodeExecPolicy()
        if codeExecPolicy.isEmpty == false {
            parameters["code_exec_policy"] = codeExecPolicy
        }
        if let compareTargetModelIDs, compareTargetModelIDs.isEmpty == false {
            parameters["compare_mode"] = "base_vs_targets"
            parameters["compare_target_model_ids"] = compareTargetModelIDs.joined(separator: ",")
        }
        if let promptSnapshot {
            parameters.merge(evaluationPromptParameters(from: promptSnapshot)) { _, new in new }
        }
        parameters.merge(semanticJudgeParameters) { _, new in new }
        return parameters
    }

    private func evaluationSemanticJudgeParameters() throws -> [String: String] {
        let selectedID = selectedEvaluationSemanticJudgeRemoteServerID
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard selectedID.isEmpty == false else {
            return [:]
        }
        guard let server = remoteServers.first(where: { $0.id == selectedID }) else {
            throw MelixCLIError.runtime("Remote server \(selectedID) was not found.")
        }
        let apiKey = try remoteServerStore
            .loadAPIKey(remoteServerID: selectedID)?
            .apiKey
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard apiKey.isEmpty == false else {
            throw MelixCLIError.runtime("Remote server \(selectedID) has no API key configured.")
        }
        let modelID = evaluationSemanticJudgeModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? server.defaultModelID
            : evaluationSemanticJudgeModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard modelID.isEmpty == false else {
            throw MelixCLIError.runtime("Remote server \(selectedID) has no model configured.")
        }
        return [
            "semantic_judge_remote_server_id": server.id,
            "semantic_judge_provider_kind": server.providerKind,
            "semantic_judge_base_url": server.baseURL,
            "semantic_judge_api_key": apiKey,
            "semantic_judge_model_id": modelID,
            "semantic_judge_timeout_seconds": String(server.timeoutSeconds),
            "semantic_judge_rate_limit_per_minute": String(server.rateLimitPerMinute),
        ]
    }

    private func shouldUseEvaluationPrompt(suites: [String]) -> Bool {
        suites.contains("event_extraction")
            || normalizedEvaluationScoringMode() == EvaluationPromptStore.eventExtractionScoringMode
    }

    private func evaluationPromptParameters(from snapshot: EvaluationPromptSnapshot) -> [String: String] {
        let examplesJSON = (try? EvaluationPromptStore.examplesJSONString(snapshot.examples)) ?? "[]"
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
            "eval_prompt_examples_json": examplesJSON,
        ]
    }

    private func validateEvaluationSourceConfiguration() -> String? {
        switch evaluationDatasetSourceKind {
        case .builtinPackage:
            return nil
        case .localCSV, .localJSONL:
            if evaluationSourcePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Enter a local source path before running Evaluation."
            }
        case .huggingFaceDataset:
            if evaluationHFDatasetPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Enter a Hugging Face dataset path before running Evaluation."
            }
        }

        if evaluationFieldInputTextPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Evaluation input text mapping is required for custom dataset sources."
        }
        if evaluationFieldTargetPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Evaluation target mapping is required for custom dataset sources."
        }
        if Double(evaluationThreshold.trimmingCharacters(in: .whitespacesAndNewlines)) == nil {
            return "Evaluation threshold must be numeric."
        }
        return nil
    }

    private func makeEvaluationRequest(
        suiteID: String,
        modelID: String,
        hfRepoID: String,
        compareTargetModelIDs: [String]?,
        promptSnapshot: EvaluationPromptSnapshot?,
        semanticJudgeParameters: [String: String] = [:]
    ) -> ControlPlaneEvaluationRequest {
        let usesCustomSource = evaluationDatasetSourceKind != .builtinPackage
        return ControlPlaneEvaluationRequest(
            modelID: modelID,
            hfRepoID: hfRepoID,
            suiteID: suiteID,
            datasetID: usesCustomSource ? "" : evaluationDatasetID(for: suiteID),
            sampleSize: evaluationSampleSize(for: suiteID),
            source: evaluationRequestSource(),
            fieldMapping: .init(
                systemPath: evaluationFieldSystemPath.trimmingCharacters(in: .whitespacesAndNewlines),
                inputTextPath: evaluationFieldInputTextPath.trimmingCharacters(in: .whitespacesAndNewlines),
                targetPath: evaluationFieldTargetPath.trimmingCharacters(in: .whitespacesAndNewlines),
                sampleIDPath: evaluationFieldSampleIDPath.trimmingCharacters(in: .whitespacesAndNewlines)
            ),
            profile: .init(
                profileType: "final_result",
                resultKind: evaluationResultKind.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? "text"
                    : evaluationResultKind.trimmingCharacters(in: .whitespacesAndNewlines),
                extractionMode: evaluationExtractionMode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? "heuristic_final"
                    : evaluationExtractionMode.trimmingCharacters(in: .whitespacesAndNewlines),
                scoringMode: normalizedEvaluationScoringMode(),
                threshold: Double(evaluationThreshold.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 1.0,
                outputSchemaJSON: evaluationOutputSchemaJSON.trimmingCharacters(in: .whitespacesAndNewlines),
                ignoredPaths: normalizedEvaluationIgnoredPaths()
            ),
            parameters: evaluationParameters(
                compareTargetModelIDs: compareTargetModelIDs,
                promptSnapshot: promptSnapshot,
                semanticJudgeParameters: semanticJudgeParameters
            )
        )
    }

    private func evaluationRequestSource() -> ControlPlaneEvaluationRequest.Source {
        switch evaluationDatasetSourceKind {
        case .builtinPackage:
            return .builtinPackage
        case .localCSV:
            return .localCSV(path: evaluationSourcePath.trimmingCharacters(in: .whitespacesAndNewlines))
        case .localJSONL:
            return .localJSONL(path: evaluationSourcePath.trimmingCharacters(in: .whitespacesAndNewlines))
        case .huggingFaceDataset:
            return .huggingFaceDataset(
                datasetPath: evaluationHFDatasetPath.trimmingCharacters(in: .whitespacesAndNewlines),
                datasetName: evaluationHFDatasetName.trimmingCharacters(in: .whitespacesAndNewlines),
                datasetRevision: evaluationHFDatasetRevision.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? "main"
                    : evaluationHFDatasetRevision.trimmingCharacters(in: .whitespacesAndNewlines),
                split: evaluationHFDatasetSplit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? "train"
                    : evaluationHFDatasetSplit.trimmingCharacters(in: .whitespacesAndNewlines)
            )
        }
    }

    private func evaluationDatasetID(for suiteID: String) -> String {
        Self.evaluationSuiteOptions.first(where: { $0.id == suiteID })?.datasetID ?? "\(suiteID).dev.v1"
    }

    private func normalizedEvaluationIgnoredPaths() -> [String] {
        evaluationIgnoredPaths
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.isEmpty == false }
    }

    private func normalizedBenchGenerationLengths() -> [UInt32] {
        Self.normalizedBenchValues(
            selectedBenchGenerationLengths,
            defaultValues: Self.benchmarkGenerationLengthOptions.prefix(2).map { $0 }
        )
    }

    private func normalizedBenchMatrixCacheProfiles() -> [String] {
        let normalized = ControlPlaneBenchMatrixRequest.normalizedStringValues(selectedBenchMatrixCacheProfiles)
        return normalized.isEmpty ? [Self.benchmarkCacheProfileOptions.first ?? "cold"] : normalized
    }

    private func normalizedBenchMatrixReasoningModes() -> [String] {
        let normalized = ControlPlaneBenchMatrixRequest.normalizedStringValues(selectedBenchMatrixReasoningModes)
        return normalized.isEmpty ? [Self.benchmarkReasoningModeOptions.first ?? "off"] : normalized
    }

    private func normalizedBenchMatrixStructuredOutputModes() -> [String] {
        let normalized = ControlPlaneBenchMatrixRequest.normalizedStringValues(selectedBenchMatrixStructuredOutputModes)
        return normalized.isEmpty ? [Self.benchmarkStructuredOutputModeOptions.first ?? "off"] : normalized
    }

    private func normalizedBenchMatrixConcurrencyLevels() -> [UInt32] {
        Self.normalizedBenchValues(
            selectedBenchMatrixConcurrencyLevels,
            defaultValues: Self.benchmarkConcurrencyOptions.prefix(2).map { $0 }
        )
    }

    private func normalizedBenchMatrixRepeats() -> UInt32 {
        let trimmed = benchMatrixRepeats.trimmingCharacters(in: .whitespacesAndNewlines)
        return max(1, UInt32(trimmed) ?? 1)
    }

    private func normalizedBenchMatrixRepeatsText() -> String {
        let trimmed = benchMatrixRepeats.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "3" : trimmed
    }

    private func normalizedBenchMatrixRequests() -> UInt32 {
        let trimmed = benchMatrixRequests.trimmingCharacters(in: .whitespacesAndNewlines)
        return UInt32(trimmed) ?? 0
    }

    private func normalizedBenchMatrixRequestsText() -> String {
        let trimmed = benchMatrixRequests.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "8" : trimmed
    }

    private func normalizedBenchMatrixDurationSeconds() -> UInt32 {
        let trimmed = benchMatrixDurationSeconds.trimmingCharacters(in: .whitespacesAndNewlines)
        return UInt32(trimmed) ?? 0
    }

    private func normalizedBenchMatrixDurationSecondsText() -> String {
        let trimmed = benchMatrixDurationSeconds.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "60" : trimmed
    }

    private func evaluationSampleSize(for suiteID: String) -> UInt32 {
        let rawSampleSize = evaluationSampleSize.trimmingCharacters(in: .whitespacesAndNewlines)
        if let sampleSize = UInt32(rawSampleSize), sampleSize > 0 {
            return sampleSize
        }
        let fallback = Self.evaluationSuiteOptions.first(where: { $0.id == suiteID })?.defaultSampleSize ?? 8
        return UInt32(fallback)
    }

    private func exportBenchmarkMatrixArtifact(
        formatTitle: String,
        fileName: String,
        builder: (ControlPlaneBenchmarkExportBundle, String?) -> (Int, String),
        missingRowsMessage: String
    ) async {
        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let selectedJobID = selectedBenchmarkMatrixHistoryJobID.isEmpty
                    ? (selectedBenchmarkMatrixHistoryEntry?.jobID ?? "")
                    : selectedBenchmarkMatrixHistoryJobID
                let exportDirectory = try Self.ensureBenchmarkExportDirectory()
                let outputPath = exportDirectory.appendingPathComponent(fileName).path
                let command: MelixCLICommand = formatTitle == "summary.csv"
                    ? .benchMatrixExportSummaryCSV(.init(jobID: selectedJobID, outputPath: outputPath, json: true))
                    : .benchMatrixExportRequestsCSV(.init(jobID: selectedJobID, outputPath: outputPath, json: true))
                let response = try await cliWorkflowRunner.decodeJSON(MelixCLIExportResponse.self, command: command)
                clearCLIWorkflowFailure()
                lastBenchmarkMatrixExport = RuntimeBenchmarkMatrixExportState(
                    outputPath: response.outputPath,
                    rowCount: response.rowCount,
                    formatTitle: formatTitle
                )
                let metricName = formatTitle == "summary.csv"
                    ? "menu.bench_matrix_export_summary_csv_ms"
                    : "menu.bench_matrix_export_requests_csv_ms"
                await metrics.record(
                    name: metricName,
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            let exportDirectory = try Self.ensureBenchmarkExportDirectory()
            let bundle: ControlPlaneBenchmarkExportBundle
            if let operatorCommandRunner {
                bundle = try await operatorCommandRunner.fetchBenchmarkExportBundle(outputDir: exportDirectory.path)
            } else {
                let export = try await client.exportResults(outputDir: exportDirectory.path)
                bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            }
            applyBenchmarkExportBundle(bundle)
            let selectedJobID = selectedBenchmarkMatrixHistoryJobID.isEmpty ? nil : selectedBenchmarkMatrixHistoryJobID
            let (rowCount, payload) = builder(bundle, selectedJobID)
            guard rowCount > 0 else {
                recordLocalError(missingRowsMessage)
                notifyStateChanged()
                return
            }
            let outputURL = exportDirectory.appendingPathComponent(fileName)
            try payload.write(to: outputURL, atomically: true, encoding: .utf8)
            lastBenchmarkMatrixExport = RuntimeBenchmarkMatrixExportState(
                outputPath: outputURL.path,
                rowCount: rowCount,
                formatTitle: formatTitle
            )
            let metricName = formatTitle == "summary.csv"
                ? "menu.bench_matrix_export_summary_csv_ms"
                : "menu.bench_matrix_export_requests_csv_ms"
            await metrics.record(
                name: metricName,
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    private func exportEvaluationArtifact(
        formatTitle: String,
        fileName: String,
        builder: (ControlPlaneBenchmarkExportBundle, String?) -> (Int, String),
        missingRowsMessage: String
    ) async {
        let startedAt = Date()
        if let cliWorkflowRunner {
            do {
                let selectedJobID = selectedEvaluationHistoryJobID.isEmpty
                    ? (selectedEvaluationHistoryEntry?.jobID ?? "")
                    : selectedEvaluationHistoryJobID
                let exportDirectory = try Self.ensureEvaluationExportDirectory()
                let outputPath = exportDirectory.appendingPathComponent(fileName).path
                let command: MelixCLICommand = formatTitle == "summary.csv"
                    ? .evalExportSummaryCSV(.init(jobID: selectedJobID, outputPath: outputPath, json: true))
                    : .evalExportSamplesCSV(.init(jobID: selectedJobID, outputPath: outputPath, json: true))
                let response = try await cliWorkflowRunner.decodeJSON(MelixCLIExportResponse.self, command: command)
                clearCLIWorkflowFailure()
                lastEvaluationExport = RuntimeEvaluationExportState(
                    outputPath: response.outputPath,
                    rowCount: response.rowCount,
                    formatTitle: formatTitle
                )
                await metrics.record(
                    name: "menu.eval_export_csv_ms",
                    valueMs: Date().timeIntervalSince(startedAt) * 1_000
                )
            } catch {
                recordCLIWorkflowErrorIfNeeded(error)
                recordLocalError(String(describing: error))
            }
            notifyStateChanged()
            return
        }
        do {
            let exportDirectory = try Self.ensureEvaluationExportDirectory()
            let bundle: ControlPlaneBenchmarkExportBundle
            if let operatorCommandRunner {
                bundle = try await operatorCommandRunner.fetchBenchmarkExportBundle(outputDir: exportDirectory.path)
            } else {
                let export = try await client.exportResults(outputDir: exportDirectory.path)
                bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            }
            applyBenchmarkExportBundle(bundle)
            let selectedJobID = selectedEvaluationHistoryJobID.isEmpty ? nil : selectedEvaluationHistoryJobID
            let (rowCount, payload) = builder(bundle, selectedJobID)
            guard rowCount > 0 else {
                recordLocalError(missingRowsMessage)
                notifyStateChanged()
                return
            }
            let outputURL = exportDirectory.appendingPathComponent(fileName)
            try payload.write(to: outputURL, atomically: true, encoding: .utf8)
            lastEvaluationExport = RuntimeEvaluationExportState(
                outputPath: outputURL.path,
                rowCount: rowCount,
                formatTitle: formatTitle
            )
            await metrics.record(
                name: "menu.eval_export_csv_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    private func upsert(model: Melix_Controlplane_V1_ModelSummary) {
        let row = makeRuntimeModelRow(model)
        var modelSummary = model
        if modelSummary.features.isEmpty {
            modelSummary.features = ["chat"]
        }
        if let snapshotIndex = latestSnapshot.models.firstIndex(where: { $0.modelID == model.modelID }) {
            latestSnapshot.models[snapshotIndex] = modelSummary
        } else {
            latestSnapshot.models.append(modelSummary)
            latestSnapshot.models.sort { $0.modelID < $1.modelID }
        }
        if let index = models.firstIndex(where: { $0.modelID == model.modelID }) {
            models[index] = row
        } else {
            models.append(row)
            models.sort { $0.modelID < $1.modelID }
        }
        applyImageDefaultsProjection()
        syncServerSessionsWithModels()
        ensureChatSessionsBoundToServerSessions()
        refreshImageState()
        refreshChatCapabilities()
        refreshLoraSelectionState()
        refreshEvaluationSelectionState()
        refreshAgentIntegrationExports()
        synchronizeModelSettingsDrafts()
    }

    private func synchronizeModelSettingsDrafts(force: Bool = false) {
        guard let model = primaryModelSummary else {
            modelSettingsDraftModelID = ""
            modelSettingsAliasDraft = ""
            modelSettingsTypeOverrideDraft = ""
            modelSettingsTTLDraft = ""
            modelSettingsPinOnLoadDraft = false
            modelSettingsMemoryPolicyDraft = "evictable"
            modelSettingsMemoryBudgetDraft = ""
            modelSettingsDiskStreamingModeDraft = "disabled"
            modelSettingsCacheModeDraft = "tiered"
            modelSettingsCacheMemoryBudgetDraft = ""
            modelSettingsCacheMemoryBudgetPctDraft = ""
            modelSettingsCacheBlockSizeTokensDraft = ""
            modelSettingsCacheDirectoryDraft = ""
            modelSettingsMultimodalCacheBudgetDraft = ""
            modelSettingsAccelerationModeDraft = "baseline"
            modelSettingsAccelerationProfileIDDraft = ""
            modelSettingsAdaptiveThinkingModeDraft = "off"
            modelSettingsAdaptiveThinkingBudgetDraft = ""
            modelSettingsToolParserXMLFallbackDraft = false
            modelSettingsOCRSamplingProfileDraft = ""
            modelSettingsOCRTemperatureDraft = ""
            modelSettingsOCRTopPDraft = ""
            modelSettingsOCRMaxTokensDraft = ""
            return
        }

        guard force || modelSettingsDraftModelID != model.modelID else {
            return
        }

        modelSettingsDraftModelID = model.modelID
        modelSettingsAliasDraft = model.settings.alias
        modelSettingsTypeOverrideDraft = model.settings.typeOverride
        modelSettingsTTLDraft = model.settings.ttlSeconds > 0 ? String(model.settings.ttlSeconds) : ""
        modelSettingsPinOnLoadDraft = model.settings.pinOnLoad
        modelSettingsMemoryPolicyDraft = runtimeMemoryPolicyDraftValue(resolvedResidencyPolicy(for: model))
        modelSettingsMemoryBudgetDraft = model.settings.memoryBudgetBytes > 0
            ? String(model.settings.memoryBudgetBytes)
            : ""
        modelSettingsDiskStreamingModeDraft = runtimeDiskStreamingModeDraftValue(model.settings.diskStreamingMode)
        modelSettingsCacheModeDraft = runtimeCacheModeDraftValue(model.settings.cacheMode)
        modelSettingsCacheMemoryBudgetDraft = model.settings.cacheMemoryBudgetBytes > 0
            ? String(model.settings.cacheMemoryBudgetBytes)
            : ""
        modelSettingsCacheMemoryBudgetPctDraft = model.settings.cacheMemoryBudgetPct > 0
            ? String(model.settings.cacheMemoryBudgetPct)
            : ""
        modelSettingsCacheBlockSizeTokensDraft = model.settings.cacheBlockSizeTokens > 0
            ? String(model.settings.cacheBlockSizeTokens)
            : ""
        modelSettingsCacheDirectoryDraft = model.settings.cacheDirectory
        modelSettingsMultimodalCacheBudgetDraft = model.settings.multimodalCacheBudgetBytes > 0
            ? String(model.settings.multimodalCacheBudgetBytes)
            : ""
        modelSettingsAccelerationModeDraft = runtimeAccelerationModeDraftValue(model.settings.defaultAccelerationMode)
        modelSettingsAccelerationProfileIDDraft = model.settings.accelerationProfileID
        modelSettingsAdaptiveThinkingModeDraft = runtimeAdaptiveThinkingDraftValue(model.settings.adaptiveThinking)
        modelSettingsAdaptiveThinkingBudgetDraft = model.settings.adaptiveThinking.budgetTokens > 0
            ? String(model.settings.adaptiveThinking.budgetTokens)
            : ""
        modelSettingsToolParserXMLFallbackDraft = model.settings.ext["tool_parser_xml_fallback"] == "true"
        modelSettingsOCRSamplingProfileDraft = model.settings.ext["ocr_sampling_profile_id"] ?? ""
        modelSettingsOCRTemperatureDraft = model.settings.ext["ocr_default_temperature"] ?? ""
        modelSettingsOCRTopPDraft = model.settings.ext["ocr_default_top_p"] ?? ""
        modelSettingsOCRMaxTokensDraft = model.settings.ext["ocr_default_max_tokens"] ?? ""
    }

    private func normalizedOptionalUInt32Draft(
        _ rawValue: String,
        fieldName: String
    ) -> UInt32? {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return nil
        }
        guard let value = UInt32(trimmed) else {
            recordLocalError("\(fieldName) must be an unsigned integer.")
            notifyStateChanged()
            return nil
        }
        return value
    }

    private func normalizedOptionalUInt64Draft(
        _ rawValue: String,
        fieldName: String
    ) -> UInt64? {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return nil
        }
        guard let value = UInt64(trimmed) else {
            recordLocalError("\(fieldName) must be an unsigned integer.")
            notifyStateChanged()
            return nil
        }
        return value
    }

    private func normalizedOptionalDoubleDraft(
        _ rawValue: String,
        fieldName: String
    ) -> Double? {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return nil
        }
        guard let value = Double(trimmed) else {
            recordLocalError("\(fieldName) must be numeric.")
            notifyStateChanged()
            return nil
        }
        return value
    }

    private func refreshAgentIntegrationExports() {
        let startedAt = Date()
        guard let selectedServerSession else {
            agentIntegrationExports = []
            selectedAgentIntegrationTarget = .openAICompatible
            Task {
                await metrics.record(name: "integration.export_generation_ms", valueMs: 0)
                await metrics.record(name: "integration.export_target_count", valueMs: 0)
            }
            return
        }

        agentIntegrationExports = AgentIntegrationExport.exports(from: selectedServerSession)

        let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
        let exportCount = Double(agentIntegrationExports.count)
        Task {
            await metrics.record(name: "integration.export_generation_ms", valueMs: elapsedMs)
            await metrics.record(name: "integration.export_target_count", valueMs: exportCount)
        }
    }

    private func applyGatewayAccessProjection(to session: inout DesktopServerSessionState) {
        guard let projection = Self.gatewayAccessProjection(from: latestSnapshot) else {
            return
        }
        session.authMode = projection.authMode
        session.authTokenHint = projection.authTokenHint
        session.sharedAccessState = projection.sharedAccessState
        session.accessKeyCount = projection.accessKeyCount
        session.accessKeyHints = projection.accessKeyHints
        session.activeAuthSessionCount = projection.activeAuthSessionCount
        session.rememberedAuthSessionCount = projection.rememberedAuthSessionCount
        session.expiredRememberedSessionCount = projection.expiredRememberedSessionCount
        session.authSessionRetentionSeconds = projection.authSessionRetentionSeconds
        session.lastAuthSessionSignOutLatencyMs = projection.lastAuthSessionSignOutLatencyMs
    }

    private func applyGatewayConfigProjection(to session: inout DesktopServerSessionState) {
        guard let projection = Self.gatewayConfigProjection(from: latestSnapshot, serverSessionID: session.id) else {
            session.effectiveHost = session.host
            session.effectivePort = session.port
            return
        }
        session.host = projection.host
        session.port = projection.port
        session.effectiveHost = projection.effectiveHost
        session.effectivePort = projection.effectivePort
        session.rateLimitPerMinute = projection.rateLimitPerMinute
        session.timeoutSeconds = projection.timeoutSeconds
        session.gatewayConfigSourceText = projection.sourceText
        session.gatewayConfigActiveBinding = projection.activeBinding
        session.gatewayConfigRequiresRestart = projection.requiresRestart
    }

    private func applyServingDefaultsProjection(to session: inout DesktopServerSessionState) {
        guard let projection = Self.servingDefaultsProjection(from: latestSnapshot, serverSessionID: session.id) else {
            let effectiveBatchingDefaults = Self.effectiveBatchingDefaults(
                concurrentProcessingEnabled: session.servingDefaults.concurrentProcessingEnabled,
                maxConcurrentRequests: session.servingDefaults.maxConcurrentRequests,
                prefillBatchSize: session.servingDefaults.prefillBatchSize,
                completionBatchSize: session.servingDefaults.completionBatchSize
            )
            session.servingDefaults.effectiveTemperature = session.servingDefaults.temperature
            session.servingDefaults.effectiveTopP = session.servingDefaults.topP
            session.servingDefaults.effectiveMaxTokens = session.servingDefaults.maxTokens
            session.servingDefaults.effectiveStreamIntervalTokens = session.servingDefaults.streamIntervalTokens
            session.servingDefaults.effectiveMaxConcurrentRequests = effectiveBatchingDefaults.maxConcurrentRequests
            session.servingDefaults.effectiveConcurrentProcessingEnabled = effectiveBatchingDefaults.concurrentProcessingEnabled
            session.servingDefaults.effectivePrefillBatchSize = effectiveBatchingDefaults.prefillBatchSize
            session.servingDefaults.effectiveCompletionBatchSize = effectiveBatchingDefaults.completionBatchSize
            session.servingDefaults.effectiveAccelerationMode = session.servingDefaults.accelerationMode
            if session.servingDefaults.accelerationMode == "speculative_decode" {
                session.servingDefaults.effectiveDraftModelID = session.servingDefaults.draftModelID
                session.servingDefaults.effectiveNumDraftTokens = session.servingDefaults.numDraftTokens
            } else {
                session.servingDefaults.effectiveDraftModelID = ""
                session.servingDefaults.effectiveNumDraftTokens = 0
            }
            return
        }
        session.servingDefaults.temperature = projection.temperature
        session.servingDefaults.topP = projection.topP
        session.servingDefaults.maxTokens = projection.maxTokens
        session.servingDefaults.streamIntervalTokens = projection.streamIntervalTokens
        session.servingDefaults.maxConcurrentRequests = projection.maxConcurrentRequests
        session.servingDefaults.concurrentProcessingEnabled = projection.concurrentProcessingEnabled
        session.servingDefaults.prefillBatchSize = projection.prefillBatchSize
        session.servingDefaults.completionBatchSize = projection.completionBatchSize
        session.servingDefaults.accelerationMode = projection.accelerationMode
        session.servingDefaults.draftModelID = projection.draftModelID
        session.servingDefaults.numDraftTokens = projection.numDraftTokens
        session.servingDefaults.effectiveTemperature = projection.effectiveTemperature
        session.servingDefaults.effectiveTopP = projection.effectiveTopP
        session.servingDefaults.effectiveMaxTokens = projection.effectiveMaxTokens
        session.servingDefaults.effectiveStreamIntervalTokens = projection.effectiveStreamIntervalTokens
        session.servingDefaults.effectiveMaxConcurrentRequests = projection.effectiveMaxConcurrentRequests
        session.servingDefaults.effectiveConcurrentProcessingEnabled = projection.effectiveConcurrentProcessingEnabled
        session.servingDefaults.effectivePrefillBatchSize = projection.effectivePrefillBatchSize
        session.servingDefaults.effectiveCompletionBatchSize = projection.effectiveCompletionBatchSize
        session.servingDefaults.effectiveAccelerationMode = projection.effectiveAccelerationMode
        session.servingDefaults.effectiveDraftModelID = projection.effectiveDraftModelID
        session.servingDefaults.effectiveNumDraftTokens = projection.effectiveNumDraftTokens
        session.servingDefaults.sourceText = projection.sourceText
        session.servingDefaults.modelOverrideApplied = projection.modelOverrideApplied
        session.servingDefaults.updatedAtUnixMS = projection.updatedAtUnixMS
    }

    private func applyImageDefaultsProjection() {
        guard let projection = Self.imageDefaultsProjection(from: latestSnapshot) else {
            effectiveImageGenerateModelID = selectedImageGenerateModelID
            effectiveImageEditModelID = selectedImageEditModelID
            effectiveImageSize = imageSize
            effectiveImageSteps = imageSteps
            effectiveImageGuidance = imageGuidance
            effectiveImageStrength = imageStrength
            effectiveImageNegativePrompt = imageNegativePrompt
            imageRequestTimeoutSeconds = 1_800
            return
        }

        if projection.generateModelID.isEmpty == false {
            selectedImageGenerateModelID = projection.generateModelID
        } else if projection.effectiveGenerateModelID.isEmpty == false {
            selectedImageGenerateModelID = projection.effectiveGenerateModelID
        }
        if projection.editModelID.isEmpty == false {
            selectedImageEditModelID = projection.editModelID
        } else if projection.effectiveEditModelID.isEmpty == false {
            selectedImageEditModelID = projection.effectiveEditModelID
        }

        imageSize = projection.size
        imageSteps = String(projection.steps)
        imageGuidance = Self.formatImageDefaultNumber(projection.guidance)
        imageStrength = Self.formatImageDefaultNumber(projection.strength)
        imageNegativePrompt = projection.negativePrompt
        imageDefaultsSourceText = projection.sourceText
        effectiveImageGenerateModelID = projection.effectiveGenerateModelID
        effectiveImageEditModelID = projection.effectiveEditModelID
        effectiveImageSize = projection.effectiveSize
        effectiveImageSteps = String(projection.effectiveSteps)
        effectiveImageGuidance = Self.formatImageDefaultNumber(projection.effectiveGuidance)
        effectiveImageStrength = Self.formatImageDefaultNumber(projection.effectiveStrength)
        effectiveImageNegativePrompt = projection.effectiveNegativePrompt
        imageRequestTimeoutSeconds = projection.requestTimeoutSeconds
        imageDefaultsUpdatedAtUnixMS = projection.updatedAtUnixMS
    }

    private static func gatewayAccessProjection(
        from snapshot: Melix_Controlplane_V1_ServerSnapshot
    ) -> GatewayAccessProjection? {
        guard snapshot.hasGatewayAccess else {
            return nil
        }

        let summary = snapshot.gatewayAccess
        let keyHints = summary.keys.map(\.tokenHint).filter { !$0.isEmpty }
        let activeAuthSessionCount = Int(snapshot.metrics.values["persistent_session.active_session_count"] ?? 0)
        let rememberedAuthSessionCount = Int(snapshot.metrics.values["persistent_session.remembered_session_count"] ?? 0)
        let expiredRememberedSessionCount = Int(snapshot.metrics.values["persistent_session.expired_session_count"] ?? 0)
        let authSessionRetentionSeconds = Int(snapshot.metrics.values["persistent_session.retention_ttl_seconds"] ?? 0)
        let lastAuthSessionSignOutLatencyMs = snapshot.metrics.values["persistent_session.sign_out_latency_ms"] ?? 0

        switch summary.mode {
        case .none:
            return GatewayAccessProjection(
                authMode: .none,
                authTokenHint: "",
                sharedAccessState: .localOnly,
                accessKeyCount: 0,
                accessKeyHints: [],
                activeAuthSessionCount: activeAuthSessionCount,
                rememberedAuthSessionCount: rememberedAuthSessionCount,
                expiredRememberedSessionCount: expiredRememberedSessionCount,
                authSessionRetentionSeconds: authSessionRetentionSeconds,
                lastAuthSessionSignOutLatencyMs: lastAuthSessionSignOutLatencyMs
            )
        case .bearerToken:
            return GatewayAccessProjection(
                authMode: .bearerToken,
                authTokenHint: keyHints.first ?? "melix-api-key",
                sharedAccessState: .localOnly,
                accessKeyCount: max(keyHints.count, 1),
                accessKeyHints: keyHints,
                activeAuthSessionCount: activeAuthSessionCount,
                rememberedAuthSessionCount: rememberedAuthSessionCount,
                expiredRememberedSessionCount: expiredRememberedSessionCount,
                authSessionRetentionSeconds: authSessionRetentionSeconds,
                lastAuthSessionSignOutLatencyMs: lastAuthSessionSignOutLatencyMs
            )
        case .apiKeys:
            let sharedState: DesktopSharedAccessState = summary.sharedAccessEnabled ? .enabled : .configuredDisabled
            let effectiveAuthMode: DesktopServerAuthMode = summary.sharedAccessEnabled ? .apiKeys : .none
            let keyCount = max(Int(summary.acceptedApiKeyCount), keyHints.count)
            return GatewayAccessProjection(
                authMode: effectiveAuthMode,
                authTokenHint: keyHints.first ?? "",
                sharedAccessState: sharedState,
                accessKeyCount: keyCount,
                accessKeyHints: keyHints,
                activeAuthSessionCount: activeAuthSessionCount,
                rememberedAuthSessionCount: rememberedAuthSessionCount,
                expiredRememberedSessionCount: expiredRememberedSessionCount,
                authSessionRetentionSeconds: authSessionRetentionSeconds,
                lastAuthSessionSignOutLatencyMs: lastAuthSessionSignOutLatencyMs
            )
        default:
            return nil
        }
    }

    private static func gatewayConfigProjection(
        from snapshot: Melix_Controlplane_V1_ServerSnapshot,
        serverSessionID: String
    ) -> GatewayConfigProjection? {
        guard snapshot.hasGatewayConfig else {
            return nil
        }
        guard
            let listener = snapshot.gatewayConfig.listeners.first(where: { $0.serverSessionID == serverSessionID })
                ?? (snapshot.gatewayConfig.listeners.count == 1 ? snapshot.gatewayConfig.listeners.first : nil)
        else {
            return nil
        }

        return GatewayConfigProjection(
            host: listener.requestedHost,
            port: Int(listener.requestedPort),
            effectiveHost: listener.effectiveHost.isEmpty ? listener.requestedHost : listener.effectiveHost,
            effectivePort: listener.effectivePort == 0 ? Int(listener.requestedPort) : Int(listener.effectivePort),
            servedModelID: listener.servedModelID,
            rateLimitPerMinute: Int(listener.rateLimitPerMinute),
            timeoutSeconds: Int(listener.timeoutSeconds),
            sourceText: gatewayConfigSourceText(listener.source),
            activeBinding: listener.activeBinding,
            requiresRestart: listener.requiresRestart
        )
    }

    private static func servingDefaultsProjection(
        from snapshot: Melix_Controlplane_V1_ServerSnapshot,
        serverSessionID: String
    ) -> ServingDefaultsProjection? {
        guard snapshot.hasServingDefaults else {
            return nil
        }
        guard
            let summary = snapshot.servingDefaults.sessions.first(where: { $0.serverSessionID == serverSessionID })
                ?? (snapshot.servingDefaults.sessions.count == 1 ? snapshot.servingDefaults.sessions.first : nil)
        else {
            return nil
        }

        let requestedConcurrentProcessingEnabled: Bool
        let requestedPrefillBatchSize: Int
        let requestedCompletionBatchSize: Int
        if summary.requestedPrefillBatchSize == 0, summary.requestedCompletionBatchSize == 0 {
            requestedConcurrentProcessingEnabled = true
            requestedPrefillBatchSize = 2
            requestedCompletionBatchSize = 2
        } else {
            requestedConcurrentProcessingEnabled = summary.requestedConcurrentProcessingEnabled
            requestedPrefillBatchSize = Int(summary.requestedPrefillBatchSize)
            requestedCompletionBatchSize = Int(summary.requestedCompletionBatchSize)
        }

        let effectiveConcurrentProcessingEnabled: Bool
        let effectivePrefillBatchSize: Int
        let effectiveCompletionBatchSize: Int
        if summary.effectivePrefillBatchSize == 0, summary.effectiveCompletionBatchSize == 0 {
            let effectiveBatchingDefaults = effectiveBatchingDefaults(
                concurrentProcessingEnabled: requestedConcurrentProcessingEnabled,
                maxConcurrentRequests: Int(summary.requestedMaxConcurrentRequests),
                prefillBatchSize: requestedPrefillBatchSize,
                completionBatchSize: requestedCompletionBatchSize
            )
            effectiveConcurrentProcessingEnabled = effectiveBatchingDefaults.concurrentProcessingEnabled
            effectivePrefillBatchSize = effectiveBatchingDefaults.prefillBatchSize
            effectiveCompletionBatchSize = effectiveBatchingDefaults.completionBatchSize
        } else {
            effectiveConcurrentProcessingEnabled = summary.effectiveConcurrentProcessingEnabled
            effectivePrefillBatchSize = Int(summary.effectivePrefillBatchSize)
            effectiveCompletionBatchSize = Int(summary.effectiveCompletionBatchSize)
        }

        let requestedAccelerationMode = runtimeAccelerationModeDraftValue(summary.requestedAccelerationMode)
        let effectiveAccelerationMode = summary.effectiveAccelerationMode == .unspecified
            ? requestedAccelerationMode
            : runtimeAccelerationModeDraftValue(summary.effectiveAccelerationMode)
        let requestedDraftModelID = summary.requestedDraftModelID
        let requestedNumDraftTokens = Int(summary.requestedNumDraftTokens)
        let effectiveDraftModelID = effectiveAccelerationMode == "speculative_decode"
            ? (summary.effectiveDraftModelID.isEmpty ? requestedDraftModelID : summary.effectiveDraftModelID)
            : ""
        let effectiveNumDraftTokens = effectiveAccelerationMode == "speculative_decode"
            ? (summary.effectiveNumDraftTokens == 0 ? requestedNumDraftTokens : Int(summary.effectiveNumDraftTokens))
            : 0

        return ServingDefaultsProjection(
            temperature: summary.requestedTemperature,
            topP: summary.requestedTopP,
            maxTokens: Int(summary.requestedMaxTokens),
            streamIntervalTokens: Int(summary.requestedStreamIntervalTokens),
            maxConcurrentRequests: Int(summary.requestedMaxConcurrentRequests),
            concurrentProcessingEnabled: requestedConcurrentProcessingEnabled,
            prefillBatchSize: requestedPrefillBatchSize,
            completionBatchSize: requestedCompletionBatchSize,
            accelerationMode: requestedAccelerationMode,
            draftModelID: requestedDraftModelID,
            numDraftTokens: requestedNumDraftTokens,
            effectiveTemperature: summary.effectiveTemperature,
            effectiveTopP: summary.effectiveTopP,
            effectiveMaxTokens: Int(summary.effectiveMaxTokens),
            effectiveStreamIntervalTokens: Int(summary.effectiveStreamIntervalTokens),
            effectiveMaxConcurrentRequests: Int(summary.effectiveMaxConcurrentRequests),
            effectiveConcurrentProcessingEnabled: effectiveConcurrentProcessingEnabled,
            effectivePrefillBatchSize: effectivePrefillBatchSize,
            effectiveCompletionBatchSize: effectiveCompletionBatchSize,
            effectiveAccelerationMode: effectiveAccelerationMode,
            effectiveDraftModelID: effectiveDraftModelID,
            effectiveNumDraftTokens: effectiveNumDraftTokens,
            sourceText: servingDefaultsSourceText(summary.source),
            modelOverrideApplied: summary.modelOverrideApplied,
            updatedAtUnixMS: summary.updatedAtUnixMs
        )
    }

    private static func imageDefaultsProjection(
        from snapshot: Melix_Controlplane_V1_ServerSnapshot
    ) -> ImageDefaultsProjection? {
        guard snapshot.hasImageDefaults else {
            return nil
        }
        let summary = snapshot.imageDefaults
        let requestedSize = summary.requestedSize.isEmpty ? (summary.effectiveSize.isEmpty ? "1024x1024" : summary.effectiveSize) : summary.requestedSize
        let requestedSteps = summary.requestedSteps == 0 ? Int(summary.effectiveSteps == 0 ? 28 : summary.effectiveSteps) : Int(summary.requestedSteps)
        let requestedGuidance = summary.requestedGuidance == 0 ? Double(summary.effectiveGuidance == 0 ? 7.5 : summary.effectiveGuidance) : Double(summary.requestedGuidance)
        let requestedStrength = summary.requestedStrength == 0 ? Double(summary.effectiveStrength == 0 ? 1.0 : summary.effectiveStrength) : Double(summary.requestedStrength)
        let requestedNegativePrompt = summary.requestedNegativePrompt.isEmpty ? summary.effectiveNegativePrompt : summary.requestedNegativePrompt

        return ImageDefaultsProjection(
            generateModelID: summary.requestedGenerateModelID,
            editModelID: summary.requestedEditModelID,
            size: requestedSize,
            steps: requestedSteps,
            guidance: requestedGuidance,
            strength: requestedStrength,
            negativePrompt: requestedNegativePrompt,
            effectiveGenerateModelID: summary.effectiveGenerateModelID,
            effectiveEditModelID: summary.effectiveEditModelID,
            effectiveSize: summary.effectiveSize.isEmpty ? requestedSize : summary.effectiveSize,
            effectiveSteps: Int(summary.effectiveSteps == 0 ? UInt32(requestedSteps) : summary.effectiveSteps),
            effectiveGuidance: Double(summary.effectiveGuidance == 0 ? Float(requestedGuidance) : summary.effectiveGuidance),
            effectiveStrength: Double(summary.effectiveStrength == 0 ? Float(requestedStrength) : summary.effectiveStrength),
            effectiveNegativePrompt: summary.effectiveNegativePrompt,
            requestTimeoutSeconds: summary.requestTimeoutSeconds == 0 ? 1_800 : summary.requestTimeoutSeconds,
            sourceText: imageDefaultsSourceText(summary.source),
            updatedAtUnixMS: summary.updatedAtUnixMs
        )
    }

    private static func gatewayConfigSourceText(
        _ source: Melix_Controlplane_V1_GatewayConfigSource
    ) -> String {
        switch source {
        case .builtInDefaults:
            return "Built-in Defaults"
        case .environmentDefaults:
            return "Environment Defaults"
        case .configFileImport:
            return "Config File Import"
        case .operatorOverride:
            return "Operator Override"
        default:
            return "Unknown Source"
        }
    }

    private static func servingDefaultsSourceText(
        _ source: Melix_Controlplane_V1_ServingDefaultsSource
    ) -> String {
        switch source {
        case .builtInDefaults:
            return "Built-in Defaults"
        case .environmentDefaults:
            return "Environment Defaults"
        case .configFileImport:
            return "Config File Import"
        case .operatorOverride:
            return "Operator Override"
        default:
            return "Unknown Source"
        }
    }

    private static func imageDefaultsSourceText(
        _ source: Melix_Controlplane_V1_ImageDefaultsSource
    ) -> String {
        switch source {
        case .builtInDefaults:
            return "Built-in Defaults"
        case .environmentDefaults:
            return "Environment Defaults"
        case .configFileImport:
            return "Config File Import"
        case .operatorOverride:
            return "Operator Override"
        default:
            return "Unknown Source"
        }
    }

    private static func formatImageDefaultNumber(_ value: Double) -> String {
        let rounded = (value * 100).rounded() / 100
        if rounded == rounded.rounded() {
            return String(Int(rounded))
        }
        return String(format: "%.2f", rounded).replacingOccurrences(of: #"\.?0+$"#, with: "", options: .regularExpression)
    }

    private static func effectiveBatchingDefaults(
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: Int,
        prefillBatchSize: Int,
        completionBatchSize: Int
    ) -> (
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: Int,
        prefillBatchSize: Int,
        completionBatchSize: Int
    ) {
        guard concurrentProcessingEnabled else {
            return (false, 1, 1, 1)
        }
        let effectiveBatchCapacity = min(
            max(1, maxConcurrentRequests),
            max(1, prefillBatchSize),
            max(1, completionBatchSize)
        )
        guard effectiveBatchCapacity > 1 else {
            return (false, 1, 1, 1)
        }
        return (true, effectiveBatchCapacity, effectiveBatchCapacity, effectiveBatchCapacity)
    }

    private func upsert(session: Melix_Controlplane_V1_SessionState) {
        var summary = Melix_Controlplane_V1_SessionSummary()
        summary.sessionID = session.sessionID
        summary.activeBranchID = session.activeBranchID
        summary.branchCount = UInt32(session.branches.count)
        summary.latestRequestID = session.latestRequestID
        summary.latestSnapshotID = session.latestSnapshotID

        if let index = latestSnapshot.sessions.firstIndex(where: { $0.sessionID == session.sessionID }) {
            latestSnapshot.sessions[index] = summary
        } else {
            latestSnapshot.sessions.append(summary)
            latestSnapshot.sessions.sort { $0.sessionID < $1.sessionID }
        }
    }

    private func runtimeSession(
        for serverSessionID: String,
        fallbackIndex: Int
    ) -> Melix_Controlplane_V1_ServerSessionRuntimeState? {
        if let exactMatch = latestSnapshot.runtimeSessions.first(where: { $0.serverSessionID == serverSessionID }) {
            return exactMatch
        }
        if latestSnapshot.runtimeSessions.count == 1, fallbackIndex == 0 {
            return latestSnapshot.runtimeSessions.first
        }
        return nil
    }

    private func applyRuntimeSessionProjection(
        to session: inout DesktopServerSessionState,
        runtimeSession: Melix_Controlplane_V1_ServerSessionRuntimeState
    ) {
        session.lifecycle = Self.serverSessionLifecycle(runtimeSession.lifecycleState)
        session.powerState = Self.serverSessionPowerState(runtimeSession.powerState)
        session.wakeReason = Self.serverWakeReason(runtimeSession.wakeReason)
        session.idleTimerSeconds = Int(runtimeSession.idleTimerSeconds)
        session.autoSleepEnabled = runtimeSession.autoSleepEnabled
        session.lightSleepAfterSeconds = Int(runtimeSession.lightSleepAfterSeconds)
        session.deepSleepAfterSeconds = Int(runtimeSession.deepSleepAfterSeconds)
        session.requestedDiskStreamingModeText = runtimeDiskStreamingModeText(runtimeSession.requestedDiskStreamingMode)
        session.effectiveDiskStreamingModeText = runtimeDiskStreamingModeText(runtimeSession.effectiveDiskStreamingMode)
    }

    private func existingModelSummary(for modelID: String) -> Melix_Controlplane_V1_ModelSummary {
        if let model = latestSnapshot.models.first(where: { $0.modelID == modelID }) {
            return model
        }

        if let row = models.first(where: { $0.modelID == modelID }) {
            var model = Melix_Controlplane_V1_ModelSummary()
            model.modelID = row.modelID
            model.kind = row.kind
            model.state = row.state
            model.maxContext = row.maxContext
            model.features = ["chat"]
            return model
        }

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        model.kind = "text"
        model.state = .modelDiscovered
        model.maxContext = 8192
        model.features = ["chat"]
        return model
    }

    private func upsert(imageJob: Melix_Controlplane_V1_ImageJobSummary) {
        if let index = latestSnapshot.imageJobs.firstIndex(where: { $0.jobID == imageJob.jobID }) {
            latestSnapshot.imageJobs[index] = imageJob
        } else {
            latestSnapshot.imageJobs.append(imageJob)
        }
        refreshImageState(preferredJobID: imageJob.jobID)
    }

    private func clearCLIWorkflowFailure() {
        lastCLIWorkflowFailure = nil
    }

    private func recordCLIWorkflowErrorIfNeeded(_ error: Error) {
        guard let workflowError = error as? MelixCLIWorkflowError else {
            return
        }
        lastCLIWorkflowFailure = RuntimeCLIWorkflowFailureState(
            commandID: {
                switch workflowError {
                case .processFailed(let commandID, _, _, _),
                     .invalidJSON(let commandID, _, _),
                     .missingField(let commandID, _, _),
                     .unsupportedCommand(let commandID, _):
                    return commandID
                }
            }(),
            surface: {
                switch workflowError {
                case .processFailed(_, let surface, _, _),
                     .invalidJSON(_, let surface, _),
                     .missingField(_, let surface, _),
                     .unsupportedCommand(_, let surface):
                    return surface
                }
            }(),
            failureKind: workflowError.failureKind,
            detail: workflowError.localizedDescription
        )
    }

    private func applyCLIServerSnapshotIfPresent(
        output: String,
        command: MelixCLICommand,
        surface: MelixCLIWorkflowSurface
    ) throws {
        switch command {
        case .serverStart, .serverPause, .serverResume, .serverWake, .serverStop, .serverSetIdlePolicy:
            let payload = try decodeMelixCLIJSON(
                MelixCLIServerSnapshotPayload.self,
                output: output,
                command: command,
                surface: surface
            )
            applyCLIServerSnapshotPayload(payload)
        default:
            break
        }
    }

    private func applyCLIServerSnapshotPayload(_ payload: MelixCLIServerSnapshotPayload) {
        serverStateText = Self.cliServerStateText(payload.serverState)
        statusTitle = "Melix \(serverStateText)"

        for runtime in payload.runtimeSessions {
            updateServerSessionCollections(serverSessionID: runtime.serverSessionID) { session in
                session.lifecycle = Self.cliServerSessionLifecycle(runtime.lifecycleState)
                session.powerState = Self.cliServerSessionPowerState(runtime.powerState)
                session.wakeReason = Self.cliServerWakeReason(runtime.wakeReason)
                session.idleTimerSeconds = runtime.idleTimerSeconds
                session.autoSleepEnabled = runtime.autoSleepEnabled
                session.lightSleepAfterSeconds = runtime.lightSleepAfterSeconds
                session.deepSleepAfterSeconds = runtime.deepSleepAfterSeconds
                session.updatedAt = Date(timeIntervalSince1970: TimeInterval(runtime.updatedAtUnixMS) / 1_000)
            }
        }
    }

    private func updateServerSessionCollections(
        serverSessionID: String,
        update: (inout DesktopServerSessionState) -> Void
    ) {
        if let index = persistedServerSessions.firstIndex(where: { $0.id == serverSessionID }) {
            var session = persistedServerSessions[index]
            update(&session)
            persistedServerSessions[index] = session
        }
        if let index = serverSessions.firstIndex(where: { $0.id == serverSessionID }) {
            var session = serverSessions[index]
            update(&session)
            serverSessions[index] = session
        }
    }

    private func recordLocalError(_ message: String) {
        let sanitizedMessage = sanitizedRichText(message)
        lastError = sanitizedMessage
        recentEvents.insert(
            DesktopLogEntry(kind: "error", message: sanitizedMessage, detail: "local", level: "error"),
            at: 0
        )
        trimRecentEvents()
    }

    private func record(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        let entry = DesktopLogEntry(
            kind: event.eventType,
            message: Self.eventMessage(for: event),
            detail: event.source.isEmpty ? "control-plane" : event.source,
            level: Self.eventLevel(for: event)
        )
        recentEvents.insert(entry, at: 0)
        trimRecentEvents()
    }

    private func setLastError(_ message: String) {
        lastError = sanitizedRichText(message)
    }

    private static func cliServerStateText(_ value: String) -> String {
        switch value {
        case "server_ready":
            return "Ready"
        case "server_booting":
            return "Booting"
        case "server_degraded":
            return "Degraded"
        case "server_draining":
            return "Draining"
        case "server_failed":
            return "Failed"
        case "server_stopped":
            return "Stopped"
        default:
            return "Unknown"
        }
    }

    private static func cliServerSessionLifecycle(_ value: String) -> DesktopServerSessionLifecycle {
        switch value {
        case "ready":
            return .running
        case "paused":
            return .paused
        case "sleeping":
            return .sleeping
        case "stopped":
            return .stopped
        case "error":
            return .error
        default:
            return .draft
        }
    }

    private static func cliServerSessionPowerState(_ value: String) -> DesktopServerPowerState {
        switch value {
        case "active":
            return .active
        case "light_sleep":
            return .lightSleep
        case "deep_sleep":
            return .deepSleep
        case "stopped":
            return .stopped
        default:
            return .active
        }
    }

    private static func cliServerWakeReason(_ value: String) -> DesktopServerWakeReason {
        switch value {
        case "initial_boot":
            return .initialBoot
        case "request_activity":
            return .requestActivity
        case "operator_resume":
            return .operatorResume
        case "tool_activity":
            return .toolActivity
        case "policy_apply":
            return .policyApply
        default:
            return .operatorResume
        }
    }

    private func sanitizedRichText(_ text: String) -> String {
        RichOutputSanitizer.sanitized(text)
    }

    private func resolvedChatModelID() -> String {
        if let serverModelID = selectedChatServerSession?.modelID
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !serverModelID.isEmpty {
            selectedChatModelID = serverModelID
            return serverModelID
        }
        if models.contains(where: { $0.modelID == selectedChatModelID && $0.kind == "text" }) {
            return selectedChatModelID
        }
        if let textModel = models.first(where: { $0.kind == "text" }) {
            selectedChatModelID = textModel.modelID
            return textModel.modelID
        }
        return selectedChatModelID
    }

    private func resolvedLoraModelID() -> String {
        if loraCapableModels.contains(where: { $0.modelID == selectedLoraModelID }) {
            return selectedLoraModelID
        }
        if let textModel = loraCapableModels.first {
            selectedLoraModelID = textModel.modelID
            return textModel.modelID
        }
        return ""
    }

    private func resolvedImageModelID(for role: RuntimeImageWorkflowRole) -> String {
        let current = selectedImageModelID(for: role)
        if imageModels(for: role).contains(where: { $0.modelID == current }) {
            return current
        }
        if let imageModel = imageModels(for: role).first {
            switch role {
            case .generate:
                selectedImageGenerateModelID = imageModel.modelID
            case .edit:
                selectedImageEditModelID = imageModel.modelID
            }
            return imageModel.modelID
        }
        return current
    }

    private func moveRegistryRoot(rootID: String, offset: Int) async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let index = editableRegistryRootIndex(for: rootID) else {
            return
        }
        let destination = index + offset
        guard destination >= 0, destination < editableRegistryRootPaths().count else {
            return
        }

        var updatedRoots = editableRegistryRootPaths()
        let root = updatedRoots.remove(at: index)
        if let operatorCommandRunner {
            do {
                _ = try await operatorCommandRunner.run(.modelRootsMove(.init(path: root, index: destination)))
                restoreOperatorSessionState()
            } catch {
                recordLocalError(String(describing: error))
                notifyStateChanged()
                return
            }
        }
        updatedRoots.insert(root, at: destination)
        await refreshModelOpsProductState(
            modelID: modelID,
            notify: true,
            rescan: true,
            registryRootsOverride: updatedRoots,
            refreshFoundationAfterSuccess: true
        )
    }

    private func editableRegistryRootPaths() -> [String] {
        if registryHasConfiguredRootOverride {
            return registryConfiguredRootPaths
        }
        return registryRoots.map(\.rootPath)
    }

    private func editableRegistryRootIndex(for rootID: String) -> Int? {
        guard let root = registryRoots.first(where: { $0.id == rootID }) else {
            return nil
        }
        return editableRegistryRootPaths().firstIndex(of: root.rootPath)
    }

    private func resolvedRegistryRootOverride(_ registryRootsOverride: [String]?) -> [String]? {
        if let registryRootsOverride {
            return Self.normalizedRegistryRootPaths(registryRootsOverride)
        }
        if registryHasConfiguredRootOverride {
            return registryConfiguredRootPaths
        }
        return nil
    }

    private func refreshImageState(preferredJobID: String? = nil) {
        _ = resolvedImageModelID(for: .generate)
        _ = resolvedImageModelID(for: .edit)

        imageJobs = latestSnapshot.imageJobs.sorted { lhs, rhs in
            if lhs.updatedAtUnixMs == rhs.updatedAtUnixMs {
                return lhs.jobID > rhs.jobID
            }
            return lhs.updatedAtUnixMs > rhs.updatedAtUnixMs
        }

        if let preferredJobID, imageJobs.contains(where: { $0.jobID == preferredJobID }) {
            selectedImageJobID = preferredJobID
        } else if imageJobs.contains(where: { $0.jobID == selectedImageJobID }) == false {
            selectedImageJobID = imageJobs.first?.jobID ?? ""
        }

        if imageJobs.isEmpty, imageStatusText != "Failed" {
            imageStatusText = "Idle"
        }
    }

    private func refreshChatCapabilities() {
        if let serverModelID = selectedChatServerSession?.modelID {
            selectedChatModelID = serverModelID
        } else if models.contains(where: { $0.modelID == selectedChatModelID }) == false,
                  let textModel = models.first(where: { $0.kind == "text" }) {
            selectedChatModelID = textModel.modelID
        }

        let capabilitySpecs: [(String, String, [String])] = [
            ("text", "Interactive Text", ["chat"]),
            ("ocr", "OCR", ["ocr"]),
            ("vlm", "Vision Analysis", ["vlm", "vision"]),
            ("transcription", "Transcription", ["transcription"]),
            ("speech", "Speech", ["speech"]),
        ]

        chatCapabilities = capabilitySpecs.compactMap { capabilityID, title, featureHints in
            guard let model = latestSnapshot.models.first(where: { summary in
                summary.kind == capabilityID || summary.features.contains(where: { featureHints.contains($0.lowercased()) })
            }) else {
                return nil
            }
            let stateText = Self.modelStateText(model.state)
            return DesktopChatCapabilityRow(
                id: capabilityID,
                title: title,
                modelID: model.modelID,
                detail: "\(model.modelID) • \(stateText)",
                isReady: model.state == .modelWarm || model.state == .modelPinned
            )
        }
    }

    private func refreshLoraSelectionState() {
        if loraCapableModels.contains(where: { $0.modelID == selectedLoraModelID }) == false,
           let textModel = loraCapableModels.first {
            selectedLoraModelID = textModel.modelID
        }

        if adapterPackages.contains(where: { $0.id == selectedAdapterPackageID }) == false {
            selectedAdapterPackageID = adapterPackages.first?.id ?? ""
        }
    }

    public func applyLoraTrainingPreset(_ preset: RuntimeLoraTrainingPreset) {
        selectedLoraTrainingPreset = preset
        switch preset {
        case .custom:
            return
        case .debugFast:
            loraRank = "8"
            loraAlpha = "16"
            loraDropout = "0.0"
            loraBatchSize = "1"
            loraEpochs = "1"
            loraLearningRate = "0.0001"
            loraMaxSeqLength = "1024"
            loraGradientCheckpointing = false
        case .balancedAdapter:
            loraRank = "16"
            loraAlpha = "32"
            loraDropout = "0.05"
            loraBatchSize = "2"
            loraEpochs = "2"
            loraLearningRate = "0.0001"
            loraMaxSeqLength = "2048"
            loraGradientCheckpointing = true
        case .qualityAdapter:
            loraRank = "32"
            loraAlpha = "64"
            loraDropout = "0.05"
            loraBatchSize = "1"
            loraEpochs = "4"
            loraLearningRate = "0.00005"
            loraMaxSeqLength = "2048"
            loraGradientCheckpointing = true
        }
    }

    private func loraTrainingExt() -> [String: String] {
        var ext: [String: String] = [
            "adapter_name": Self.normalizedOptionalString(loraAdapterName) ?? "melix-dev-adapter",
            "dataset_source_kind": loraDatasetSourceKind.rawValue,
            "training_mode": loraTrainingMode.rawValue,
        ]

        if selectedLoraTrainingPreset.isNamedPreset {
            ext["preset_id"] = selectedLoraTrainingPreset.rawValue
        }

        if loraDatasetSourceKind == .localPackage {
            ext["dataset_uri"] = Self.normalizedOptionalString(loraDatasetURI) ?? "datasets/melix-dev"
        } else {
            Self.assignOptional(loraHFDatasetPath, for: "hf_dataset_path", into: &ext)
            Self.assignOptional(loraHFDatasetName, for: "hf_dataset_name", into: &ext)
            Self.assignOptional(loraHFDatasetRevision, for: "hf_dataset_revision", into: &ext)
            Self.assignOptional(loraHFTrainSplit, for: "hf_train_split", into: &ext)
            Self.assignOptional(loraHFValidSplit, for: "hf_valid_split", into: &ext)
            Self.assignOptional(loraChatFeature, for: "chat_feature", into: &ext)
            Self.assignOptional(loraPromptFeature, for: "prompt_feature", into: &ext)
            Self.assignOptional(loraCompletionFeature, for: "completion_feature", into: &ext)
            Self.assignOptional(loraTextFeature, for: "text_feature", into: &ext)
        }

        Self.assignOptional(loraTargetRepo, for: "target_repo", into: &ext)
        Self.assignOptional(loraExperimentGroupID, for: "experiment_group_id", into: &ext)
        Self.assignOptional(loraResumeFromManifestPath, for: "resume_manifest_path", into: &ext)
        Self.assignOptional(loraRank, for: "rank", into: &ext)
        Self.assignOptional(loraAlpha, for: "alpha", into: &ext)
        Self.assignOptional(loraDropout, for: "dropout", into: &ext)
        Self.assignOptional(loraTargetModules, for: "target_modules", into: &ext)
        Self.assignOptional(loraNumLayers, for: "num_layers", into: &ext)
        Self.assignOptional(loraBatchSize, for: "batch_size", into: &ext)
        Self.assignOptional(loraEpochs, for: "epochs", into: &ext)
        Self.assignOptional(loraLearningRate, for: "learning_rate", into: &ext)
        Self.assignOptional(loraMaxSeqLength, for: "max_seq_length", into: &ext)
        Self.assignOptional(loraDerivedModelAlias, for: "derived_model_alias", into: &ext)
        ext["response_only"] = loraResponseOnly ? "true" : "false"
        ext["mask_prompt"] = loraMaskPrompt ? "true" : "false"
        ext["gradient_checkpointing"] = loraGradientCheckpointing ? "true" : "false"
        return ext
    }

    private func loraTrainingCLIParameters() -> [String: String] {
        let ext = loraTrainingExt()
        return ext.filter { key, _ in
            ["adapter_name", "dataset_source_kind", "dataset_uri", "target_repo", "training_mode"].contains(key) == false
        }
    }

    private static func normalizedOptionalString(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func assignOptional(_ value: String, for key: String, into ext: inout [String: String]) {
        guard let normalized = normalizedOptionalString(value) else {
            return
        }
        ext[key] = normalized
    }

    private func appendAssistantDelta(_ text: String, requestID: String) {
        guard !text.isEmpty else { return }
        let entryID = activeAssistantEntryID ?? "assistant-\(requestID)"
        activeAssistantEntryID = entryID
        enqueueChatPresentationText(
            text,
            entryID: entryID,
            kind: .assistant,
            title: "Assistant",
            detail: ""
        )
    }

    private func appendReasoningDelta(_ text: String, requestID: String) {
        guard !text.isEmpty else { return }
        let entryID = activeReasoningEntryID ?? "reasoning-\(requestID)"
        activeReasoningEntryID = entryID
        enqueueChatPresentationText(
            text,
            entryID: entryID,
            kind: .reasoning,
            title: "Reasoning",
            detail: ""
        )
    }

    private func appendToolDelta(callID: String, toolName: String, argumentsFragment: String) {
        let normalizedCallID = callID.isEmpty ? UUID().uuidString : callID
        let entryID = activeToolEntryIDs[normalizedCallID] ?? "tool-\(normalizedCallID)"
        activeToolEntryIDs[normalizedCallID] = entryID
        let title = toolName.isEmpty ? "Tool Call" : "Tool • \(toolName)"
        guard !argumentsFragment.isEmpty else { return }
        enqueueChatPresentationText(
            argumentsFragment,
            entryID: entryID,
            kind: .tool,
            title: title,
            detail: normalizedCallID
        )
    }

    private func finalizeAssistantText(_ assistantText: String, requestID: String) {
        guard !assistantText.isEmpty else { return }
        let entryID = activeAssistantEntryID ?? "assistant-\(requestID)"
        activeAssistantEntryID = entryID
        replaceBodyIfEmpty(assistantText, entryID: entryID, kind: .assistant, title: "Assistant", detail: "")
    }

    private func finalizeReasoningText(_ reasoningText: String, requestID: String) {
        guard !reasoningText.isEmpty else { return }
        let entryID = activeReasoningEntryID ?? "reasoning-\(requestID)"
        activeReasoningEntryID = entryID
        replaceBodyIfEmpty(reasoningText, entryID: entryID, kind: .reasoning, title: "Reasoning", detail: "")
    }

    private func commitAssistantMessageIfNeeded() {
        guard
            let entryID = activeAssistantEntryID,
            let entry = chatTranscript.first(where: { $0.id == entryID }),
            !entry.body.isEmpty
        else {
            return
        }

        if chatConversationMessages.last != ControlPlaneChatRequest.Message(role: "assistant", content: entry.body) {
            chatConversationMessages.append(.init(role: "assistant", content: entry.body))
        }
    }

    private func enqueueChatPresentationText(
        _ text: String,
        entryID: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        detail: String
    ) {
        guard !text.isEmpty else { return }
        if let index = chatPresentationFragments.indices.last,
           chatPresentationFragments[index].entryID == entryID,
           chatPresentationFragments[index].kind == kind,
           chatPresentationFragments[index].title == title,
           chatPresentationFragments[index].detail == detail {
            chatPresentationFragments[index].remainingText += text
        } else {
            chatPresentationFragments.append(
                ChatPresentationFragment(
                    kind: kind,
                    entryID: entryID,
                    title: title,
                    detail: detail,
                    remainingText: text,
                    firstQueuedAt: Date()
                )
            )
        }
        startChatPresentationLoopIfNeeded()
    }

    private func startChatPresentationLoopIfNeeded() {
        if let task = chatPresentationTask, task.isCancelled == false {
            return
        }
        guard chatPresentationFragments.isEmpty == false else {
            return
        }
        chatPresentationTask = Task { [weak self] in
            guard let self else { return }
            await self.runChatPresentationLoop()
        }
    }

    private func runChatPresentationLoop() async {
        defer {
            chatPresentationTask = nil
        }

        while Task.isCancelled == false {
            guard flushNextChatPresentationChunk(forceComplete: false) else {
                return
            }
            do {
                try await Task.sleep(for: Self.chatPresentationFlushInterval)
            } catch {
                return
            }
        }
    }

    private func flushPendingChatPresentation() {
        chatPresentationTask?.cancel()
        chatPresentationTask = nil
        while flushNextChatPresentationChunk(forceComplete: true) {}
    }

    @discardableResult
    private func flushNextChatPresentationChunk(forceComplete: Bool) -> Bool {
        guard chatPresentationFragments.isEmpty == false else {
            return false
        }

        var fragment = chatPresentationFragments.removeFirst()
        let budget = forceComplete ? Int.max : Self.chatPresentationCharactersPerFlush
        let (prefix, remainder) = Self.consumePresentationPrefix(fragment.remainingText, maxCharacters: budget)
        guard prefix.isEmpty == false else {
            return false
        }

        let lagMs = Date().timeIntervalSince(fragment.firstQueuedAt) * 1_000
        chatPresentationMaxLagMs = max(chatPresentationMaxLagMs, lagMs)
        chatPresentationFlushCount += 1
        appendBody(
            prefix,
            toEntryID: fragment.entryID,
            kind: fragment.kind,
            title: fragment.title,
            detail: fragment.detail
        )

        if remainder.isEmpty == false {
            fragment.remainingText = remainder
            chatPresentationFragments.insert(fragment, at: 0)
        }

        notifyStateChanged()
        return true
    }

    private func resetChatPresentationState() {
        chatPresentationTask?.cancel()
        chatPresentationTask = nil
        chatPresentationFragments.removeAll()
        chatPresentationMaxLagMs = 0
        chatPresentationFlushCount = 0
    }

    private func recordChatPresentationMetricsIfNeeded() async {
        guard chatPresentationFlushCount > 0 else {
            return
        }
        await metrics.record(name: "menu.chat_presentation_lag_ms", valueMs: chatPresentationMaxLagMs)
        await metrics.record(name: "menu.chat_presentation_flush_count", valueMs: chatPresentationFlushCount)
    }

    private static func consumePresentationPrefix(
        _ text: String,
        maxCharacters: Int
    ) -> (prefix: String, remainder: String) {
        guard text.isEmpty == false, maxCharacters > 0 else {
            return ("", text)
        }
        let endIndex = text.index(text.startIndex, offsetBy: maxCharacters, limitedBy: text.endIndex) ?? text.endIndex
        return (String(text[..<endIndex]), String(text[endIndex...]))
    }

    private func appendChatEntry(
        id: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        body: String,
        detail: String
    ) {
        chatTranscript.append(
            DesktopChatTranscriptEntry(
                id: id,
                kind: kind,
                title: title,
                body: body,
                detail: detail
            )
        )
    }

    private func isEmptyPendingAssistantEntry(_ entry: DesktopChatTranscriptEntry) -> Bool {
        isChatStreaming
        && entry.kind == .assistant
        && entry.id == activeAssistantEntryID
        && entry.body.isEmpty
    }

    private func persistableChatTranscript() -> [DesktopChatTranscriptEntry] {
        chatTranscript.filter { isEmptyPendingAssistantEntry($0) == false }
    }

    private func removeEmptyPendingAssistantEntryIfNeeded() {
        guard
            let entryID = activeAssistantEntryID,
            let index = chatTranscript.firstIndex(where: { entry in
                entry.id == entryID
                && entry.kind == .assistant
                && entry.body.isEmpty
            })
        else {
            return
        }
        chatTranscript.remove(at: index)
    }

    private func appendBody(
        _ text: String,
        toEntryID entryID: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        detail: String
    ) {
        if let index = chatTranscript.firstIndex(where: { $0.id == entryID }) {
            let existing = chatTranscript[index]
            chatTranscript[index] = DesktopChatTranscriptEntry(
                id: existing.id,
                kind: existing.kind,
                title: existing.title,
                body: existing.body + text,
                detail: existing.detail
            )
            return
        }

        appendChatEntry(id: entryID, kind: kind, title: title, body: text, detail: detail)
    }

    private func replaceBodyIfEmpty(
        _ text: String,
        entryID: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        detail: String
    ) {
        if let index = chatTranscript.firstIndex(where: { $0.id == entryID }) {
            let existing = chatTranscript[index]
            guard existing.body.isEmpty else {
                return
            }
            chatTranscript[index] = DesktopChatTranscriptEntry(
                id: existing.id,
                kind: existing.kind,
                title: existing.title,
                body: text,
                detail: existing.detail
            )
            return
        }

        appendChatEntry(id: entryID, kind: kind, title: title, body: text, detail: detail)
    }

    private func trimRecentEvents() {
        if recentEvents.count > 40 {
            recentEvents.removeSubrange(40...)
        }
    }

    private func startSubscription(lastSeenSeq: UInt64, isReconnect: Bool) async {
        let startedAt = Date()
        let stream = await client.subscribe(lastSeenSeq: lastSeenSeq)

        if isReconnect {
            recentEvents.insert(
                DesktopLogEntry(
                    kind: "reconnect",
                    message: "Reconnected event stream",
                    detail: lastSeenSeq == 0 ? "live" : "seq \(lastSeenSeq)",
                    level: "info"
                ),
                at: 0
            )
            trimRecentEvents()
            await metrics.record(
                name: "desktop.reconnect_success_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        }

        await transitionConnectionState(
            to: "Connected",
            detail: lastSeenSeq == 0 ? "Live event stream" : "Resumed from seq \(lastSeenSeq)"
        )

        subscriptionTask = Task { [weak self] in
            for await event in stream {
                guard let self else { return }
                await self.consume(event: event)
            }
            if Task.isCancelled {
                return
            }
            guard let self else { return }
            await self.handleUnexpectedSubscriptionTermination()
        }
    }

    private func handleUnexpectedSubscriptionTermination() async {
        subscriptionTask = nil
        recentEvents.insert(
            DesktopLogEntry(
                kind: "reconnect",
                message: "Event stream ended; reconnecting",
                detail: lastSeenSeq == 0 ? "live" : "seq \(lastSeenSeq)",
                level: "warning"
            ),
            at: 0
        )
        trimRecentEvents()
        await transitionConnectionState(
            to: "Reconnecting",
            detail: lastSeenSeq == 0 ? "Retrying event stream" : "Retrying from seq \(lastSeenSeq)"
        )

        let startedAt = Date()
        do {
            let snapshot = try await client.serverSnapshot()
            resetAppliedGatewayAccessState()
            apply(snapshot: snapshot)
            await metrics.record(
                name: "desktop.reconnect_attempt_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            await startSubscription(lastSeenSeq: lastSeenSeq, isReconnect: true)
        } catch {
            await metrics.record(name: "desktop.reconnect_failure_count", valueMs: 1)
            await transitionConnectionState(to: "Degraded", detail: "Reconnect failed")
            recordLocalError("Reconnect failed: \(error)")
            notifyStateChanged()
        }
    }

    private func transitionConnectionState(to state: String, detail: String) async {
        guard connectionStateText != state || connectionDetailText != detail else {
            return
        }
        connectionStateText = state
        connectionDetailText = detail
        connectionStateTransitions += 1
        await metrics.record(
            name: "desktop.connection_state_transitions",
            valueMs: connectionStateTransitions
        )
        notifyStateChanged()
    }

    private func resetAppliedGatewayAccessState() {
        lastAppliedGatewaySessionID = ""
        lastAppliedGatewayPrimaryKey = ""
    }

    private func notifyStateChanged() {
        persistSelectedChatSessionState()
        persistOperatorSessionState()
        onStateChanged?()
    }

    private var productUpdateBannerState: DesktopBannerState? {
        guard let productUpdateSummary, productUpdateSummary.isEmpty == false else {
            return nil
        }
        guard productUpdateIsAvailable || productUpdateCheckSucceeded == false else {
            return nil
        }
        return DesktopBannerState(
            id: Self.productUpdateBannerID(summary: productUpdateSummary, detail: productUpdateDetail ?? ""),
            title: productUpdateSummary,
            detail: productUpdateDetail ?? "",
            severity: .info,
            isDismissible: true
        )
    }

    private static func productUpdateBannerID(summary: String, detail: String) -> String {
        "product-update::\(summary)||\(detail)"
    }

    private static func serverStateText(_ state: Melix_Controlplane_V1_ServerState) -> String {
        switch state {
        case .serverBooting:
            return "Booting"
        case .serverReady:
            return "Ready"
        case .serverDegraded:
            return "Degraded"
        case .serverDraining:
            return "Draining"
        case .serverStopped:
            return "Stopped"
        case .serverFailed:
            return "Failed"
        default:
            return "Unknown"
        }
    }

    private static func modelStateText(_ state: Melix_Controlplane_V1_ModelState) -> String {
        switch state {
        case .modelDiscovered:
            return "Discovered"
        case .modelWarm:
            return "Warm"
        case .modelPinned:
            return "Pinned"
        case .modelUnloaded:
            return "Unloaded"
        case .modelLoading:
            return "Loading"
        case .modelEvicting:
            return "Evicting"
        case .modelFailed:
            return "Failed"
        default:
            return "Unknown"
        }
    }

    private static func actionTitle(for state: Melix_Controlplane_V1_ModelState) -> String {
        switch state {
        case .modelWarm, .modelPinned:
            return "Unload"
        default:
            return "Load"
        }
    }

    private static func eventLevel(for event: Melix_Controlplane_V1_ControlPlaneEvent) -> String {
        switch event.payload {
        case .log(let logEvent):
            return logEvent.level
        case .resourcePressure:
            return "warning"
        default:
            return "info"
        }
    }

    private static func eventMessage(for event: Melix_Controlplane_V1_ControlPlaneEvent) -> String {
        switch event.payload {
        case .serverState(let serverStateChanged):
            if let runtimeSession = serverStateChanged.runtimeSessions.first {
                return "Server is now \(serverStateText(serverStateChanged.state)) • \(serverSessionLifecycle(runtimeSession.lifecycleState).rawValue) • \(serverSessionPowerState(runtimeSession.powerState).rawValue)"
            }
            return "Server is now \(serverStateText(serverStateChanged.state))"
        case .modelState(let modelStateChanged):
            return "\(modelStateChanged.modelID) -> \(modelStateText(modelStateChanged.state))"
        case .requestProgress(let progress):
            return requestProgressMessage(progress)
        case .sessionState(let sessionStateChanged):
            return "Session \(sessionStateChanged.state.sessionID) updated"
        case .cacheStats:
            return "Cache summary updated"
        case .log(let logEvent):
            return logEvent.message
        case .resourcePressure(let resourcePressure):
            return "Resource pressure in \(resourcePressure.scope)"
        case .imageJob(let imageJobChanged):
            return "\(imageJobChanged.job.jobID) \(imageJobChanged.job.progress.stage)"
        case .heartbeat:
            return "Heartbeat"
        default:
            return event.eventType
        }
    }

    private static func serverSessionLifecycle(
        _ state: Melix_Controlplane_V1_ServerSessionLifecycleState
    ) -> DesktopServerSessionLifecycle {
        switch state {
        case .loading:
            return .starting
        case .ready:
            return .running
        case .paused:
            return .paused
        case .sleeping:
            return .sleeping
        case .stopped:
            return .stopped
        case .error:
            return .error
        default:
            return .unavailable
        }
    }

    private static func serverSessionPowerState(
        _ state: Melix_Controlplane_V1_ServerSessionPowerState
    ) -> DesktopServerPowerState {
        switch state {
        case .active:
            return .active
        case .lightSleep:
            return .lightSleep
        case .deepSleep:
            return .deepSleep
        case .stopped:
            return .stopped
        default:
            return .unavailable
        }
    }

    private static func serverWakeReason(
        _ reason: Melix_Controlplane_V1_ServerWakeReason
    ) -> DesktopServerWakeReason {
        switch reason {
        case .initialBoot:
            return .initialBoot
        case .operatorResume:
            return .operatorResume
        case .requestActivity:
            return .requestActivity
        case .toolActivity:
            return .toolActivity
        case .policyApply:
            return .policyApply
        default:
            return .unspecified
        }
    }

    private static func imageStatusText(for job: Melix_Controlplane_V1_ImageJobSummary) -> String {
        switch job.state {
        case .imageJobQueued:
            return "Queued • \(job.operation)"
        case .imageJobRunning:
            return "Running • \(job.operation)"
        case .imageJobCompleted:
            return "Completed • \(job.operation)"
        case .imageJobCanceled:
            return "Canceled • \(job.operation)"
        case .imageJobFailed:
            if job.error.code == "deadline_exceeded" {
                return "Timed Out • \(job.operation)"
            }
            return "Failed • \(job.operation)"
        default:
            return job.operation.isEmpty ? "Idle" : job.operation
        }
    }

    private static func requestProgressMessage(_ progress: Melix_Controlplane_V1_RequestProgressEvent) -> String {
        var segments = [requestPhaseText(progress.phase)]
        if progress.prefillTotalTokens > 0 {
            segments.append(
                "\(Int(progress.prefillProgressPct.rounded()))% \(progress.prefillProcessedTokens)/\(progress.prefillTotalTokens)"
            )
        }
        if progress.activeRequests > 0 || progress.waitingRequests > 0 {
            segments.append("active \(progress.activeRequests)")
            segments.append("waiting \(progress.waitingRequests)")
        }
        if !progress.restoreStage.isEmpty {
            segments.append("restore \(progress.restoreStage)")
        }
        if progress.cachePressure > 0 {
            segments.append("pressure \(String(format: "%.2f", progress.cachePressure))")
        }
        return "\(progress.requestID) \(segments.joined(separator: " • "))"
    }

    private static func requestPhaseText(_ phase: Melix_Controlplane_V1_RequestPhase) -> String {
        switch phase {
        case .requestQueued:
            return "queued"
        case .requestAdmitted:
            return "admitted"
        case .requestPrefilling:
            return "prefilling"
        case .requestDecoding:
            return "decoding"
        case .requestCompleted:
            return "completed"
        case .requestAborted:
            return "aborted"
        case .requestFailed:
            return "failed"
        case .requestRejected:
            return "rejected"
        default:
            return "unknown"
        }
    }

    private static func restoreStageMetricCode(_ restoreStage: String) -> Double {
        switch restoreStage.lowercased() {
        case "restored":
            return 1
        case "partial":
            return 2
        default:
            return 0
        }
    }

    private enum APIKeyGenerationError: Error {
        case randomGenerationFailed(Int32)
    }

    private static func makePrimaryAPIKey() throws -> String {
        let byteCount = 32
        var randomBytes = [UInt8](repeating: 0, count: byteCount)
        let status = SecRandomCopyBytes(kSecRandomDefault, byteCount, &randomBytes)
        guard status == errSecSuccess else {
            throw APIKeyGenerationError.randomGenerationFailed(status)
        }
        let payload = Data(randomBytes)
            .base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
        return "melix_sk_\(payload)"
    }

    private static func makeAdapterPackageState(from payload: [String: Any]) -> RuntimeAdapterPackageState {
        let activationStatus = stringValue("activation_status", from: payload)
        let publishedState = stringValue("published_state", from: payload)
        let baseStatus = stringValue("status", from: payload)
        let statusText: String
        if publishedState == "published" || baseStatus == "published" {
            statusText = "Published"
        } else if activationStatus == "activated" || baseStatus == "activated" {
            statusText = "Activated"
        } else if baseStatus == "completed" && activationStatus == "pending_activation" {
            statusText = "Pending activation"
        } else {
            statusText = humanizeStatus(baseStatus)
        }

        return RuntimeAdapterPackageState(
            id: stringValue("adapter_id", from: payload),
            adapterName: stringValue("adapter_name", from: payload),
            sourceModel: stringValue("source_model", from: payload),
            datasetURI: stringValue("dataset_uri", from: payload),
            statusText: statusText,
            activationStatusText: humanizeStatus(activationStatus),
            exportabilityText: humanizeStatus(stringValue("exportable_state", from: payload)),
            publishedStateText: humanizeStatus(publishedState),
            outputPath: stringValue("output_path", from: payload),
            derivedModelID: stringValue("derived_model_id", from: payload),
            derivedModelPath: stringValue("derived_model_path", from: payload),
            targetRepo: stringValue("target_repo", from: payload),
            publishedRepo: stringValue("published_repo", from: payload),
            responseOnlyEnabled: boolValue("response_only", from: payload),
            gradientCheckpointingEnabled: boolValue("gradient_checkpointing", from: payload),
            checkpointCount: intValue("checkpoint_count", fallbackKey: "experiment.checkpoint_count", from: payload),
            resumeReady: boolValue("resume_ready", fallbackKey: "experiment.resume_ready", from: payload),
            tokensPerSecond: doubleValue("tokens_per_second", fallbackKey: "training.tokens_per_second", from: payload),
            peakMemoryGB: doubleValue("peak_memory_gb", fallbackKey: "training.peak_memory_gb", from: payload),
            trainingDurationText: formatDuration(milliseconds: doubleValue("training_duration_ms", from: payload)),
            activationDurationText: formatDuration(milliseconds: doubleValue("activation_duration_ms", from: payload)),
            publishDurationText: formatDuration(milliseconds: doubleValue("adapter_publish_ms", from: payload))
        )
    }

    private static func makeTrainingHistoryEntryState(from payload: [String: Any]) -> RuntimeTrainingHistoryEntryState {
        let manifest = payload["manifest"] as? [String: Any] ?? [:]
        return RuntimeTrainingHistoryEntryState(
            id: stringValue("job_id", from: payload),
            jobID: stringValue("job_id", from: payload),
            modelID: stringValue("source_model", from: payload),
            adapterName: stringValue("adapter_name", from: manifest),
            datasetURI: stringValue("dataset_uri", from: manifest),
            statusText: humanizeStatus(stringValue("status", from: payload)),
            stageText: "\(stringValue("stage", from: payload)) • \(String(format: "%.0f%%", doubleValue("pct", from: payload) * 100))",
            outputPath: stringValue("output_path", from: payload),
            targetRepo: stringValue("target_repo", from: manifest),
            checkpointCount: intValue("checkpoint_count", fallbackKey: "experiment.checkpoint_count", from: manifest),
            resumeReady: boolValue("resume_ready", fallbackKey: "experiment.resume_ready", from: manifest),
            tokensPerSecond: doubleValue("tokens_per_second", fallbackKey: "training.tokens_per_second", from: manifest),
            peakMemoryGB: doubleValue("peak_memory_gb", fallbackKey: "training.peak_memory_gb", from: manifest)
        )
    }

    private static func makeLoraExperimentGroupState(from payload: [String: Any]) -> RuntimeLoraExperimentGroupState? {
        let groupID = stringValue("group_id", from: payload)
        guard groupID.isEmpty == false else {
            return nil
        }
        let resumeReadyRunIDs = (payload["resume_ready_run_ids"] as? [Any] ?? [])
            .compactMap { $0 as? String }
            .filter { $0.isEmpty == false }
        let lineagePayloads = (payload["checkpoint_lineage"] as? [[String: Any]]) ?? []
        let checkpointLineage: [RuntimeLoraCheckpointLineageEntry] = lineagePayloads.compactMap { entry in
            let runID = stringValue("run_id", from: entry)
            guard runID.isEmpty == false else {
                return nil
            }
            return RuntimeLoraCheckpointLineageEntry(
                runID: runID,
                checkpointCount: intValue("checkpoint_count", from: entry),
                resumeReady: boolValue("resume_ready", from: entry)
            )
        }
        return RuntimeLoraExperimentGroupState(
            id: groupID,
            groupID: groupID,
            title: stringValue("title", from: payload),
            adapterName: stringValue("adapter_name", from: payload),
            sourceModel: stringValue("source_model", from: payload),
            runCount: intValue("run_count", from: payload),
            latestPresetTitle: stringValue("latest_preset_title", from: payload),
            latestTokensPerSecond: doubleValue("latest_tokens_per_second", from: payload),
            latestPeakMemoryGB: doubleValue("latest_peak_memory_gb", from: payload),
            latestCheckpointCount: intValue("latest_checkpoint_count", from: payload),
            latestResumeReady: boolValue("latest_resume_ready", from: payload),
            bestLoss: doubleValue("best_loss", from: payload),
            recommendedManifestPath: stringValue("recommended_manifest_path", from: payload),
            bestRunID: stringValue("best_run_id", from: payload),
            resumeReadyRunIDs: resumeReadyRunIDs,
            checkpointLineage: checkpointLineage
        )
    }

    private static func makeDownloadQueueEntryState(from payload: [String: Any]) -> RuntimeDownloadQueueEntryState? {
        let jobID = stringValue("job_id", from: payload)
        let sourceModel = stringValue("source_model", from: payload)
        guard jobID.isEmpty == false, sourceModel.isEmpty == false else {
            return nil
        }
        return RuntimeDownloadQueueEntryState(
            jobID: jobID,
            sourceModel: sourceModel,
            status: stringValue("status", from: payload),
            stage: stringValue("stage", from: payload),
            pct: doubleValue("pct", from: payload),
            outputDir: stringValue("output_dir", from: payload),
            outputPath: stringValue("output_path", from: payload),
            partialPath: stringValue("partial_path", from: payload),
            statePath: stringValue("state_path", from: payload),
            selectedMirror: stringValue("selected_mirror", from: payload),
            downloadedBytes: intValue("downloaded_bytes", from: payload),
            totalBytes: intValue("total_bytes", from: payload),
            resumeUsed: boolValue("resume_used", from: payload),
            resumeFromBytes: intValue("resume_from_bytes", from: payload),
            retryCount: intValue("retry_count", from: payload),
            stallDetectionCount: intValue("stall_detection_count", from: payload),
            stallReason: stringValue("stall_reason", from: payload),
            resumeReady: boolValue("resume_ready", from: payload)
        )
    }

    private static func makeRegistryRootState(from payload: [String: Any]) -> RuntimeRegistryRootState? {
        let rootID = stringValue("root_id", from: payload)
        let rootPath = stringValue("root_path", from: payload)
        guard rootID.isEmpty == false, rootPath.isEmpty == false else {
            return nil
        }
        let discoveredModelIDs = (payload["discovered_model_ids"] as? [Any] ?? [])
            .compactMap { element in
                let value = String(describing: element).trimmingCharacters(in: .whitespacesAndNewlines)
                return value.isEmpty ? nil : value
            }
        return RuntimeRegistryRootState(
            id: rootID,
            rootPath: rootPath,
            rootOrder: intValue("root_order", from: payload),
            accessible: boolValue("accessible", from: payload),
            errorCode: stringValue("error_code", from: payload),
            errorMessage: stringValue("error_message", from: payload),
            discoveredModelIDs: discoveredModelIDs
        )
    }

    private static func makeBenchmarkHistoryEntryState(
        from entry: ControlPlaneBenchmarkHistoryEntry
    ) -> RuntimeBenchmarkHistoryEntryState {
        let datasetParts = [entry.datasetRepo, entry.datasetConfig]
            .filter { $0.isEmpty == false }
            .joined(separator: " • ")
        let splitSuffix = entry.datasetSplit.isEmpty ? "" : " • \(entry.datasetSplit)"
        return RuntimeBenchmarkHistoryEntryState(
            id: "\(entry.jobID):\(entry.suiteID)",
            jobID: entry.jobID,
            modelID: entry.modelID,
            taskKind: entry.taskKind,
            taskTitle: benchmarkTaskTitle(for: entry.taskKind),
            sourceRepo: entry.sourceRepo,
            suiteID: entry.suiteID,
            suiteTitle: entry.suiteTitle,
            datasetLabel: datasetParts + splitSuffix,
            sampleSizeText: entry.sampleSize.map(String.init) ?? "default",
            batchFactorText: entry.batchFactor.map(String.init) ?? "default",
            statusText: humanizeStatus(entry.status),
            metricCountText: "\(entry.metricCount) metrics",
            createdAtText: benchmarkTimestampLabel(entry.createdAtUnixMS),
            createdAtUnixMS: entry.createdAtUnixMS,
            reportPath: entry.reportPath
        )
    }

    private static func makeBenchmarkMetricCardState(
        from row: ControlPlaneBenchmarkCSVRow
    ) -> RuntimeBenchmarkMetricCardState {
        RuntimeBenchmarkMetricCardState(
            id: "\(row.jobID):\(row.suiteID):\(row.metricName)",
            taskKind: row.taskKind,
            suiteTitle: benchmarkSuiteTitle(for: row.suiteID, taskKind: row.taskKind),
            metricName: row.metricName,
            metricLabel: benchmarkMetricLabel(row.metricName),
            value: row.metricValue,
            valueText: String(format: "%.2f %@", row.metricValue, row.unit),
            unit: row.unit
        )
    }

    private static func makeBenchmarkChartPointState(
        from row: ControlPlaneBenchmarkCSVRow
    ) -> RuntimeBenchmarkChartPointState {
        RuntimeBenchmarkChartPointState(
            id: "\(row.jobID):\(row.suiteID):\(row.metricName)",
            jobID: row.jobID,
            taskKind: row.taskKind,
            suiteTitle: benchmarkSuiteTitle(for: row.suiteID, taskKind: row.taskKind),
            metricName: row.metricName,
            value: row.metricValue,
            unit: row.unit,
            createdAtLabel: benchmarkTimestampLabel(row.createdAtUnixMS),
            createdAtUnixMS: row.createdAtUnixMS
        )
    }

    private static func makeBenchmarkMatrixHistoryEntryStates(
        from entries: [ControlPlaneBenchmarkMatrixHistoryEntry]
    ) -> [RuntimeBenchmarkMatrixHistoryEntryState] {
        let grouped = Dictionary(grouping: entries, by: \.jobID)
        return grouped.values
            .compactMap { group in
                guard let representative = group.max(by: { $0.createdAtUnixMS < $1.createdAtUnixMS }) else {
                    return nil
                }
                let suiteTitles = Array(Set(group.map { benchmarkSuiteTitle(for: $0.suiteID, taskKind: $0.taskKind) })).sorted()
                let suiteSummary = suiteTitles.count == 1
                    ? (suiteTitles.first ?? representative.suiteID)
                    : "\(suiteTitles.count) suites"
                let loadBudgetText = representative.requests > 0
                    ? "\(representative.requests) requests • \(representative.repeats)x repeats"
                    : "\(representative.durationSeconds)s duration • \(representative.repeats)x repeats"
                return RuntimeBenchmarkMatrixHistoryEntryState(
                    id: representative.jobID,
                    jobID: representative.jobID,
                    modelID: representative.modelID,
                    taskKind: representative.taskKind,
                    taskTitle: benchmarkTaskTitle(for: representative.taskKind),
                    sourceRepo: representative.sourceRepo,
                    suiteSummary: suiteSummary,
                    cellCountText: "\(group.count) cells",
                    loadBudgetText: loadBudgetText,
                    statusText: humanizeStatus(representative.status),
                    createdAtText: benchmarkTimestampLabel(representative.createdAtUnixMS),
                    createdAtUnixMS: representative.createdAtUnixMS
                )
            }
            .sorted { lhs, rhs in
                if lhs.createdAtUnixMS == rhs.createdAtUnixMS {
                    return lhs.jobID > rhs.jobID
                }
                return lhs.createdAtUnixMS > rhs.createdAtUnixMS
            }
    }

    private static func makeBenchmarkMatrixSummaryCardStates(
        from rows: [ControlPlaneBenchmarkMatrixSummaryCSVRow]
    ) -> [RuntimeBenchmarkMatrixSummaryCardState] {
        guard rows.isEmpty == false else {
            return []
        }

        let count = Double(rows.count)
        let avgTTFT = rows.map(\.ttftMeanMS).reduce(0, +) / count
        let avgLatency = rows.map(\.requestLatencyMeanMS).reduce(0, +) / count
        let avgDecode = rows.map(\.decodeTokensPerSecondMean).reduce(0, +) / count
        let avgThroughput = rows.map(\.throughputRequestsPerSecond).reduce(0, +) / count
        let avgSuccess = rows.map(\.successRate).reduce(0, +) / count

        return [
            RuntimeBenchmarkMatrixSummaryCardState(
                id: "cells",
                title: "Cells",
                valueText: "\(rows.count)",
                detail: "Selected matrix combinations"
            ),
            RuntimeBenchmarkMatrixSummaryCardState(
                id: "ttft",
                title: "Avg TTFT",
                valueText: String(format: "%.2f ms", avgTTFT),
                detail: "Mean across selected cells"
            ),
            RuntimeBenchmarkMatrixSummaryCardState(
                id: "latency",
                title: "Avg Latency",
                valueText: String(format: "%.2f ms", avgLatency),
                detail: "Request latency mean"
            ),
            RuntimeBenchmarkMatrixSummaryCardState(
                id: "decode",
                title: "Avg Decode",
                valueText: String(format: "%.2f tok/s", avgDecode),
                detail: "Decode throughput mean"
            ),
            RuntimeBenchmarkMatrixSummaryCardState(
                id: "throughput",
                title: "Avg Throughput",
                valueText: String(format: "%.2f req/s", avgThroughput),
                detail: "Request throughput mean"
            ),
            RuntimeBenchmarkMatrixSummaryCardState(
                id: "success",
                title: "Avg Success",
                valueText: String(format: "%.1f%%", avgSuccess * 100),
                detail: "Success rate"
            ),
        ]
    }

    private static func makeBenchmarkMatrixSummaryRowState(
        from row: ControlPlaneBenchmarkMatrixSummaryCSVRow
    ) -> RuntimeBenchmarkMatrixSummaryRowState {
        RuntimeBenchmarkMatrixSummaryRowState(
            id: "\(row.jobID):\(row.suiteID):\(row.contextLength):\(row.generationLength):\(row.batchSize):\(row.concurrencyLevel)",
            suiteTitle: benchmarkSuiteTitle(for: row.suiteID, taskKind: row.taskKind),
            configurationSummary: "ctx \(row.contextLength) • gen \(row.generationLength) • batch \(row.batchSize) • conc \(row.concurrencyLevel) • \(humanizedControlTitle(row.cacheProfile)) • \(humanizedControlTitle(row.reasoningMode)) • \(humanizedControlTitle(row.structuredOutputMode))",
            latencyText: String(format: "TTFT %.2f ms • Lat %.2f ms", row.ttftMeanMS, row.requestLatencyMeanMS),
            throughputText: String(format: "Prefill %.2f • Decode %.2f • Req %.2f", row.prefillTokensPerSecondMean, row.decodeTokensPerSecondMean, row.throughputRequestsPerSecond),
            successRateText: String(format: "%.1f%% success", row.successRate * 100),
            peakMemoryText: "Peak \(formatBytes(row.peakMemoryBytesMax))",
            createdAtText: benchmarkTimestampLabel(row.createdAtUnixMS),
            contextLength: row.contextLength,
            batchSize: row.batchSize,
            concurrencyLevel: row.concurrencyLevel,
            ttftMeanMS: row.ttftMeanMS,
            throughputTokensPerSecond: row.throughputTokensPerSecond
        )
    }

    private static func makeBenchmarkMatrixContextChartPointState(
        from row: ControlPlaneBenchmarkMatrixSummaryCSVRow
    ) -> RuntimeBenchmarkMatrixChartPointState {
        RuntimeBenchmarkMatrixChartPointState(
            id: "ctx:\(row.jobID):\(row.suiteID):\(row.contextLength):\(row.batchSize):\(row.concurrencyLevel)",
            seriesTitle: "\(benchmarkSuiteTitle(for: row.suiteID, taskKind: row.taskKind)) • b\(row.batchSize)",
            xLabel: String(row.contextLength),
            xValue: row.contextLength,
            yValue: row.ttftMeanMS,
            unit: "ms"
        )
    }

    private static func makeBenchmarkMatrixThroughputChartPointState(
        from row: ControlPlaneBenchmarkMatrixSummaryCSVRow
    ) -> RuntimeBenchmarkMatrixChartPointState {
        RuntimeBenchmarkMatrixChartPointState(
            id: "throughput:\(row.jobID):\(row.suiteID):\(row.batchSize):\(row.concurrencyLevel)",
            seriesTitle: "\(benchmarkSuiteTitle(for: row.suiteID, taskKind: row.taskKind)) • c\(row.concurrencyLevel)",
            xLabel: String(row.batchSize),
            xValue: row.batchSize,
            yValue: row.throughputTokensPerSecond,
            unit: "tok/s"
        )
    }

    private static func makeEvaluationHistoryEntryState(
        from entry: ControlPlaneEvaluationHistoryEntry
    ) -> RuntimeEvaluationHistoryEntryState {
        RuntimeEvaluationHistoryEntryState(
            id: "\(entry.jobID):\(entry.suiteID)",
            jobID: entry.jobID,
            modelID: entry.modelID,
            taskKind: entry.taskKind,
            taskTitle: benchmarkTaskTitle(for: entry.taskKind),
            sourceRepo: entry.sourceRepo,
            suiteID: entry.suiteID,
            suiteTitle: evaluationSuiteTitle(for: entry.suiteID),
            datasetID: entry.datasetID,
            sampleSizeText: String(entry.sampleSize),
            scoringModeText: evaluationScoringModeLabel(entry.scoringMode),
            statusText: humanizeStatus(entry.status),
            metricCountText: "\(entry.metricCount) metrics",
            createdAtText: benchmarkTimestampLabel(entry.createdAtUnixMS),
            createdAtUnixMS: entry.createdAtUnixMS,
            reportPath: entry.reportPath
        )
    }

    private static func makeEvaluationMetricCardState(
        from row: ControlPlaneEvaluationSummaryCSVRow
    ) -> RuntimeEvaluationMetricCardState {
        RuntimeEvaluationMetricCardState(
            id: "\(row.jobID):\(row.suiteID):\(row.primaryScoreName)",
            suiteTitle: evaluationSuiteTitle(for: row.suiteID),
            metricName: row.primaryScoreName,
            metricLabel: evaluationScoreLabel(row.primaryScoreName),
            value: row.primaryScoreValue,
            valueText: String(format: "%.2f", row.primaryScoreValue),
            unit: "score",
            verdictText: row.verdict,
            thresholdText: decimalMetricText(row.effectThreshold),
            bootstrapCIText: intervalMetricText(lower: row.bootstrapLowerBound, upper: row.bootstrapUpperBound),
            analyticalCIText: intervalMetricText(lower: row.analyticalLowerBound, upper: row.analyticalUpperBound)
        )
    }

    private static func makeEvaluationSamplePreviewState(
        from row: ControlPlaneEvaluationSampleRecord
    ) -> RuntimeEvaluationSamplePreviewState {
        RuntimeEvaluationSamplePreviewState(
            id: "\(row.jobID):\(row.sampleID)",
            sampleID: row.sampleID,
            inputText: row.inputText,
            target: row.target,
            extractedResult: row.extractedResult,
            rawResponse: row.rawResponse,
            typedScoreText: String(format: "%.2f", row.typedScore),
            statusText: [row.extractionStatus, row.validationStatus]
                .filter { $0.isEmpty == false }
                .joined(separator: " • "),
            timeText: String(format: "%.2fs", row.timeS),
            categoryLabel: row.categoryLabel,
            subjectLabel: row.subjectLabel
        )
    }

    private static func decimalMetricText(_ value: Double?) -> String {
        guard let value else {
            return ""
        }
        return String(format: "%.4f", value)
    }

    private static func signedDecimalMetricText(_ value: Double?) -> String {
        guard let value else {
            return ""
        }
        return String(format: "%+.4f", value)
    }

    private static func intervalMetricText(lower: Double?, upper: Double?) -> String {
        guard let lower, let upper else {
            return ""
        }
        return "[\(signedDecimalMetricText(lower)), \(signedDecimalMetricText(upper))]"
    }

    private static func makeHubModelSearchResultState(
        from model: Melix_Controlplane_V1_HubModelSummary
    ) -> RuntimeHubModelSearchResultState {
        RuntimeHubModelSearchResultState(
            repoID: model.repoID,
            author: hubAuthorText(author: model.author, repoID: model.repoID),
            modelName: model.modelName.isEmpty ? model.repoID : model.modelName,
            pipelineTag: model.pipelineTag.isEmpty ? "unknown" : model.pipelineTag,
            compatibilityText: hubCompatibilityText(model.mlxCompatible),
            downloadsText: hubMetricText(model.downloads, suffix: "downloads"),
            likesText: hubMetricText(model.likes, suffix: "likes"),
            localFitStatus: hubLocalFitStatus(model.localFitStatus),
            runSuitabilityText: hubLocalFitStatusText(model.localFitStatus),
            localFitReasons: model.localFitReasons,
            estimatedArtifactBytesText: formatBytes(model.estimatedArtifactBytes),
            estimatedResidentBytesText: formatBytes(model.estimatedResidentBytes),
            parameterCountText: hubParameterCountText(model.parameterCount),
            quantizationSummary: model.quantizationSummary,
            gated: model.gated,
            recommendedAction: model.recommendedAction
        )
    }

    private static func makeHubModelCardState(
        from card: Melix_Controlplane_V1_HubModelCard
    ) -> RuntimeHubModelCardState {
        RuntimeHubModelCardState(
            repoID: card.repoID,
            author: hubAuthorText(author: card.author, repoID: card.repoID),
            modelName: card.modelName.isEmpty ? card.repoID : card.modelName,
            summary: card.summary,
            pipelineTag: card.pipelineTag.isEmpty ? "unknown" : card.pipelineTag,
            compatibilityText: hubCompatibilityText(card.mlxCompatible),
            tags: card.tags,
            baseModels: card.baseModels,
            localFitStatus: hubLocalFitStatus(card.localFitStatus),
            runSuitabilityText: hubLocalFitStatusText(card.localFitStatus),
            localFitReasons: card.localFitReasons,
            estimatedArtifactBytesText: formatBytes(card.estimatedArtifactBytes),
            estimatedResidentBytesText: formatBytes(card.estimatedResidentBytes),
            parameterCountText: hubParameterCountText(card.parameterCount),
            quantizationSummary: card.quantizationSummary,
            gated: card.gated,
            recommendedAction: card.recommendedAction
        )
    }

    private static func makeModelRegistryEntries(
        models: [RuntimeModelRow],
        downloadQueue: [RuntimeDownloadQueueEntryState],
        hubResults: [RuntimeHubModelSearchResultState]
    ) -> [RuntimeRegistryEntryState] {
        let localEntries = models.map { model in
            RuntimeRegistryEntryState(
                id: "local:\(model.modelID)",
                title: model.modelID,
                subtitleText: model.alias.isEmpty ? model.kind : model.alias,
                sourceText: "Local",
                statusText: model.stateText,
                runSuitabilityText: "Installed",
                sizeText: model.memoryText,
                taskText: model.supportedTasks.first ?? model.kind,
                canInspect: false,
                canDownload: false
            )
        }
        let downloadEntries = downloadQueue.map { item in
            RuntimeRegistryEntryState(
                id: "managed-download:\(item.jobID)",
                title: item.sourceModel,
                subtitleText: item.stage.isEmpty ? item.outputDir : item.stage,
                sourceText: "Managed Download",
                statusText: item.statusText,
                runSuitabilityText: "Pending",
                sizeText: item.progressText,
                taskText: item.stage.isEmpty ? "download" : item.stage,
                canInspect: false,
                canDownload: false
            )
        }
        let hubEntries = hubResults.map { result in
            RuntimeRegistryEntryState(
                id: "hub:\(result.repoID)",
                title: result.repoID,
                subtitleText: "\(result.author) • \(result.compatibilityText)",
                sourceText: "Hugging Face",
                statusText: result.recommendedAction.isEmpty ? result.compatibilityText : result.recommendedAction,
                runSuitabilityText: result.runSuitabilityText,
                sizeText: result.sizeText,
                taskText: result.pipelineTag,
                repoID: result.repoID,
                canInspect: true,
                canDownload: result.canDownload
            )
        }
        return localEntries + downloadEntries + hubEntries
    }

    private static func stringValue(_ key: String, from payload: [String: Any]) -> String {
        payload[key] as? String ?? ""
    }

    private static func jsonPayload(from manifestJSON: String) -> [String: Any] {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return [:]
        }
        return payload
    }

    private static func dictionaryValue(_ key: String, from payload: [String: Any]) -> [String: Any] {
        payload[key] as? [String: Any] ?? [:]
    }

    private static func intValue(_ key: String, from payload: [String: Any]) -> Int {
        if let value = payload[key] as? Int {
            return value
        }
        if let number = payload[key] as? NSNumber {
            return number.intValue
        }
        if let value = payload[key] as? String {
            return Int(value) ?? 0
        }
        return 0
    }

    private static func intValue(_ key: String, fallbackKey: String, from payload: [String: Any]) -> Int {
        if payload[key] != nil {
            return intValue(key, from: payload)
        }
        return intValue(fallbackKey, from: payload)
    }

    private static func int64Value(_ key: String, from payload: [String: Any]) -> Int64 {
        if let value = payload[key] as? Int64 {
            return value
        }
        if let value = payload[key] as? Int {
            return Int64(value)
        }
        if let number = payload[key] as? NSNumber {
            return number.int64Value
        }
        if let value = payload[key] as? String {
            return Int64(value) ?? 0
        }
        return 0
    }

    private static func doubleValue(_ key: String, from payload: [String: Any]) -> Double {
        if let value = payload[key] as? Double {
            return value
        }
        if let number = payload[key] as? NSNumber {
            return number.doubleValue
        }
        if let value = payload[key] as? String {
            return Double(value) ?? 0
        }
        return 0
    }

    private static func doubleValue(_ key: String, fallbackKey: String, from payload: [String: Any]) -> Double {
        if payload[key] != nil {
            return doubleValue(key, from: payload)
        }
        return doubleValue(fallbackKey, from: payload)
    }

    private static func boolValue(_ key: String, from payload: [String: Any]) -> Bool {
        if let value = payload[key] as? Bool {
            return value
        }
        if let number = payload[key] as? NSNumber {
            return number.boolValue
        }
        if let value = payload[key] as? String {
            return ["1", "true", "yes", "on"].contains(value.lowercased())
        }
        return false
    }

    private static func boolValue(_ key: String, fallbackKey: String, from payload: [String: Any]) -> Bool {
        if payload[key] != nil {
            return boolValue(key, from: payload)
        }
        return boolValue(fallbackKey, from: payload)
    }

    private static func encodedRegistryRoots(_ roots: [String]) -> String? {
        guard let data = try? JSONSerialization.data(
            withJSONObject: roots,
            options: [.sortedKeys, .withoutEscapingSlashes]
        ) else {
            return nil
        }
        return String(decoding: data, as: UTF8.self)
    }

    private static func normalizedRegistryRootPaths(_ roots: [String]) -> [String] {
        var normalizedRoots: [String] = []
        var seen: Set<String> = []
        for root in roots {
            guard let normalized = normalizedRegistryRootPath(root), seen.contains(normalized) == false else {
                continue
            }
            seen.insert(normalized)
            normalizedRoots.append(normalized)
        }
        return normalizedRoots
    }

    private static func normalizedRegistryRootPath(_ rawPath: String) -> String? {
        let trimmed = rawPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return nil
        }
        let expanded = (trimmed as NSString).expandingTildeInPath
        let standardized = URL(fileURLWithPath: expanded).standardizedFileURL.path
        return standardized.isEmpty ? nil : standardized
    }

    private static func defaultDownloadOutputDirectory(namespace: String, modelID: String) -> String {
        let sanitizedNamespace = sanitizedDownloadPathComponent(namespace, fallback: "melix-downloads")
        let sanitizedModelID = sanitizedDownloadPathComponent(modelID, fallback: "model")
        let rootURL = URL(fileURLWithPath: "/tmp", isDirectory: true)
        return rootURL
            .appendingPathComponent(sanitizedNamespace, isDirectory: true)
            .appendingPathComponent(sanitizedModelID, isDirectory: true)
            .path
    }

    private static func sanitizedDownloadPathComponent(_ rawValue: String, fallback: String) -> String {
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

    private static func humanizeStatus(_ status: String) -> String {
        guard status.isEmpty == false else {
            return "Unknown"
        }
        let separatorNormalized = status.replacingOccurrences(of: "_", with: " ")
        guard let first = separatorNormalized.first else {
            return "Unknown"
        }
        return String(first).uppercased() + separatorNormalized.dropFirst()
    }

    private static func formatDuration(milliseconds: Double) -> String {
        guard milliseconds > 0 else {
            return "n/a"
        }
        if milliseconds >= 1_000 {
            return String(format: "%.2fs", milliseconds / 1_000)
        }
        return String(format: "%.0fms", milliseconds)
    }

    private static func formatBytes(_ bytes: UInt64) -> String {
        guard bytes > 0 else {
            return "0 B"
        }
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB, .useGB]
        formatter.countStyle = .memory
        formatter.includesUnit = true
        return formatter.string(fromByteCount: Int64(bytes))
    }

    private static func hubLocalFitStatus(_ status: String) -> String {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.isEmpty ? "unknown" : normalized
    }

    private static func hubLocalFitStatusText(_ status: String) -> String {
        switch hubLocalFitStatus(status) {
        case "good":
            return "Good"
        case "heavy":
            return "Heavy"
        case "blocked":
            return "Blocked"
        default:
            return "Unknown"
        }
    }

    private static func hubParameterCountText(_ count: UInt64) -> String {
        guard count > 0 else {
            return ""
        }
        let value = Double(count)
        if value >= 1_000_000_000 {
            return String(format: "%.1fB params", value / 1_000_000_000)
        }
        if value >= 1_000_000 {
            return String(format: "%.1fM params", value / 1_000_000)
        }
        return "\(count) params"
    }

    private static func hubAuthorText(author: String, repoID: String) -> String {
        let normalizedAuthor = author.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalizedAuthor.isEmpty == false {
            return normalizedAuthor
        }
        return repoID.split(separator: "/").first.map(String.init) ?? ""
    }

    private static func hubCompatibilityText(_ mlxCompatible: Bool) -> String {
        mlxCompatible ? "MLX" : "Generic"
    }

    private static func hubMetricText(_ value: UInt64, suffix: String) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        let countText = formatter.string(from: NSNumber(value: value)) ?? String(value)
        return "\(countText) \(suffix)"
    }

    private static func humanizedControlTitle(_ value: String) -> String {
        value.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func benchmarkMetricLabel(_ metricName: String) -> String {
        let normalized = metricName.split(separator: ".").last.map(String.init) ?? metricName
        return normalized.replacingOccurrences(of: "_", with: " ")
    }

    private static func evaluationScoreLabel(_ scoreName: String) -> String {
        scoreName.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func evaluationSuiteTitle(for suiteID: String) -> String {
        evaluationSuiteOptions.first(where: { $0.id == suiteID })?.title ?? suiteID
    }

    private static func evaluationScoringModeLabel(_ scoringMode: String) -> String {
        scoringMode.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func benchmarkSuiteTitle(for suiteID: String, taskKind: String) -> String {
        benchmarkSuiteOptions.first(where: { $0.id == suiteID && $0.taskKind == taskKind })?.title
            ?? benchmarkSuiteOptions.first(where: { $0.id == suiteID })?.title
            ?? suiteID
    }

    private static func benchmarkTaskTitle(for taskKind: String) -> String {
        switch taskKind {
        case "image-to-text":
            return "Image to Text"
        case "image-text-to-text":
            return "Image + Text to Text"
        case "text-to-image":
            return "Text to Image"
        case "image-text-to-image":
            return "Image + Text to Image"
        default:
            return "Text Generation"
        }
    }

    private static func benchmarkTaskKind(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        switch model.kind {
        case "vlm":
            return "image-text-to-text"
        case "ocr":
            return "image-to-text"
        case "image", "image_generation":
            let imageTaskKind = model.settings.ext["melix.image.task_kind"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return imageTaskKind.isEmpty ? "text-to-image" : imageTaskKind
        default:
            return "text-generation"
        }
    }

    private static func inferredTaskKind(forRepoID repoID: String) -> String {
        let normalized = repoID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalized.isEmpty == false else {
            return "text-generation"
        }
        if normalized.contains("gemma-4")
            || normalized.contains("gemma4")
            || normalized.contains("paligemma")
            || normalized.contains("llava")
            || normalized.contains("vision")
            || normalized.contains("vlm") {
            return "image-text-to-text"
        }
        if normalized.contains("ocr") {
            return "image-to-text"
        }
        if normalized.contains("inpaint")
            || normalized.contains("edit")
            || normalized.contains("img2img") {
            return "image-text-to-image"
        }
        if normalized.contains("stable-diffusion")
            || normalized.contains("sdxl")
            || normalized.contains("flux")
            || normalized.contains("text-to-image")
            || normalized.contains("t2i") {
            return "text-to-image"
        }
        return "text-generation"
    }

    private static func normalizedBenchValues(
        _ values: [UInt32],
        defaultValues: [UInt32]
    ) -> [UInt32] {
        let normalized = Array(Set(values.filter { $0 > 0 })).sorted()
        return normalized.isEmpty ? defaultValues : normalized
    }

    private func normalizedBenchContextLengths() -> [UInt32] {
        Self.normalizedBenchValues(
            selectedBenchContextLengths,
            defaultValues: Self.benchmarkContextLengthOptions.prefix(2).map { $0 }
        )
    }

    private func normalizedBenchBatchSizes() -> [UInt32] {
        Self.normalizedBenchValues(
            selectedBenchBatchSizes,
            defaultValues: Self.benchmarkBatchSizeOptions.filter { $0 > 1 }.prefix(2).map { $0 }
        )
    }

    private func normalizedBenchRepeats() -> UInt32 {
        let trimmed = benchRepeats.trimmingCharacters(in: .whitespacesAndNewlines)
        return max(1, UInt32(trimmed) ?? 1)
    }

    private func normalizedBenchRepeatsText() -> String {
        let trimmed = benchRepeats.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "3" : trimmed
    }

    private func normalizedBenchCacheProfile() -> String {
        let trimmed = benchCacheProfile.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return Self.benchmarkCacheProfileOptions.first ?? "cold"
        }
        return Self.benchmarkCacheProfileOptions.contains(trimmed) ? trimmed : (Self.benchmarkCacheProfileOptions.first ?? "cold")
    }

    private func normalizedBenchReasoningMode() -> String {
        benchReasoningMode.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func normalizedBenchStructuredOutputMode() -> String {
        benchStructuredOutputMode.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func normalizedEvaluationScoringMode() -> String {
        let trimmed = evaluationScoringMode.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "multiple_choice_accuracy" : trimmed
    }

    private func normalizedEvaluationCodeExecPolicy() -> String {
        let trimmed = evaluationCodeExecPolicy.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "sandboxed" : trimmed
    }

    private static func toggledValues(_ value: UInt32, in values: [UInt32]) -> [UInt32] {
        var set = Set(values)
        if set.contains(value) {
            set.remove(value)
        } else {
            set.insert(value)
        }
        return Array(set).sorted()
    }

    private static func toggledStrings(_ value: String, in values: [String]) -> [String] {
        let normalizedValue = value.trimmingCharacters(in: .whitespacesAndNewlines)
        var set = Set(ControlPlaneBenchMatrixRequest.normalizedStringValues(values))
        if set.contains(normalizedValue) {
            set.remove(normalizedValue)
        } else if normalizedValue.isEmpty == false {
            set.insert(normalizedValue)
        }
        return Array(set).sorted()
    }

    private static func benchmarkTimestampLabel(_ unixMS: Int64) -> String {
        let date = Date(timeIntervalSince1970: Double(unixMS) / 1_000)
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    private static func isBenchmarkEligibleModel(_ model: RuntimeModelRow) -> Bool {
        switch model.kind {
        case "text", "vlm", "ocr", "image", "image_generation":
            return true
        default:
            return false
        }
    }

    private static func ensureBenchmarkExportDirectory() throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-benchmark-exports",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: nil
        )
        return directory
    }

    private static func ensureEvaluationExportDirectory() throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-evaluation-exports",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: nil
        )
        return directory
    }

    private static func benchmarkCSVFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-benchmark-\(sanitizedJobID).csv"
    }

    private static func benchmarkMatrixSummaryCSVFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-benchmark-matrix-summary-\(sanitizedJobID).csv"
    }

    private static func benchmarkMatrixRequestsCSVFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-benchmark-matrix-requests-\(sanitizedJobID).csv"
    }

    private static func evaluationSummaryCSVFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-evaluation-summary-\(sanitizedJobID).csv"
    }

    private static func evaluationSamplesCSVFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-evaluation-samples-\(sanitizedJobID).csv"
    }

    private static func evaluationSamplesJSONLFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-evaluation-samples-\(sanitizedJobID).jsonl"
    }

    private static func canRedoImageJob(_ job: Melix_Controlplane_V1_ImageJobSummary) -> Bool {
        if job.operation == "image_generate" {
            return job.recipe.prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        }
        return job.sourceArtifactID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            || recipeSourceImageURI(from: job).isEmpty == false
    }

    private static func redoGenerationRequest(
        from job: Melix_Controlplane_V1_ImageJobSummary
    ) -> ControlPlaneImageGenerationRequest {
        ControlPlaneImageGenerationRequest(
            modelID: job.modelID,
            prompt: job.recipe.prompt,
            size: job.recipe.size.isEmpty ? "1024x1024" : job.recipe.size,
            steps: job.recipe.steps,
            guidance: job.recipe.guidance,
            negativePrompt: job.recipe.negativePrompt,
            n: max(1, job.recipe.variantCount),
            responseFormat: job.recipe.responseFormat.isEmpty ? "png" : job.recipe.responseFormat,
            artifactNamespace: job.recipe.artifactNamespace
        )
    }

    private static func redoEditRequest(
        from job: Melix_Controlplane_V1_ImageJobSummary
    ) -> ControlPlaneImageEditRequest {
        let sourceArtifactID = job.sourceArtifactID.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = job.editMode == .iterate ? "" : job.recipe.prompt
        let promptDelta: String
        if job.editMode == .iterate {
            let delta = job.promptDelta.trimmingCharacters(in: .whitespacesAndNewlines)
            promptDelta = delta.isEmpty ? job.recipe.prompt : delta
        } else {
            promptDelta = ""
        }

        return ControlPlaneImageEditRequest(
            modelID: job.modelID,
            prompt: prompt,
            imageURL: sourceArtifactID.isEmpty ? recipeSourceImageURI(from: job) : "",
            maskURL: recipeMaskURI(from: job),
            sourceArtifactID: sourceArtifactID,
            promptDelta: promptDelta,
            mode: controlPlaneEditMode(from: job.editMode),
            strength: job.recipe.strength > 0 ? job.recipe.strength : 1,
            size: job.recipe.size.isEmpty ? "1024x1024" : job.recipe.size,
            steps: job.recipe.steps,
            guidance: job.recipe.guidance,
            negativePrompt: job.recipe.negativePrompt,
            n: max(1, job.recipe.variantCount),
            responseFormat: job.recipe.responseFormat.isEmpty ? "png" : job.recipe.responseFormat
        )
    }

    private static func reiterateSourceArtifactID(
        from job: Melix_Controlplane_V1_ImageJobSummary
    ) -> String? {
        job.artifacts
            .last(where: { $0.role == .imageArtifactGenerated && !$0.artifactID.isEmpty })?
            .artifactID
    }

    private static func recipeSourceImageURI(
        from job: Melix_Controlplane_V1_ImageJobSummary
    ) -> String {
        let directURI = job.recipe.sourceImageUri.trimmingCharacters(in: .whitespacesAndNewlines)
        if directURI.isEmpty == false {
            return directURI
        }
        return job.artifacts.first(where: {
            $0.role == .imageArtifactEditSource || $0.role == .imageArtifactInput
        })?.storageUri ?? ""
    }

    private static func recipeMaskURI(
        from job: Melix_Controlplane_V1_ImageJobSummary
    ) -> String {
        let directURI = job.recipe.maskUri.trimmingCharacters(in: .whitespacesAndNewlines)
        if directURI.isEmpty == false {
            return directURI
        }
        return job.artifacts.first(where: { $0.role == .imageArtifactMask })?.storageUri ?? ""
    }

    private static func controlPlaneEditMode(
        from mode: Melix_Controlplane_V1_ImageEditMode
    ) -> ControlPlaneImageEditRequest.Mode {
        switch mode {
        case .variation:
            return .variation
        case .iterate:
            return .iterate
        case .edit, .unspecified, .UNRECOGNIZED:
            return .edit
        }
    }

    private static func isImageModelKind(_ kind: String) -> Bool {
        kind == "image" || kind == "image_generation"
    }

    private static func imageModel(
        _ model: RuntimeModelRow,
        supports role: RuntimeImageWorkflowRole
    ) -> Bool {
        guard isImageModelKind(model.kind) else {
            return false
        }
        switch role {
        case .generate:
            return model.imageSupportsGeneration
        case .edit:
            return model.imageSupportsEdit
        }
    }
}

private func runtimeExperimentSummaryText(checkpointCount: Int, resumeReady: Bool) -> String {
    let checkpointSummary = checkpointCount == 1 ? "1 checkpoint" : "\(checkpointCount) checkpoints"
    return "\(checkpointSummary) • \(resumeReady ? "resume ready" : "resume unavailable")"
}

private func runtimeTrainingPerformanceText(tokensPerSecond: Double, peakMemoryGB: Double) -> String {
    let throughputSummary = tokensPerSecond > 0 ? String(format: "%.1f tok/s", tokensPerSecond) : "n/a tok/s"
    let peakMemorySummary = peakMemoryGB > 0 ? String(format: "%.2f GB peak", peakMemoryGB) : "n/a peak"
    return "\(throughputSummary) • \(peakMemorySummary)"
}

/// Paired runtime-mode presentation fields produced together so the visible
/// badge tag and its VoiceOver phrasing can't drift. ``text`` is "" when the
/// caller should hide the badge entirely (base models / legacy entries).
struct RuntimeModeBadgeFields {
    let text: String
    let accessibilityLabel: String
}

private func runtimeModeBadgeFields(_ model: Melix_Controlplane_V1_ModelSummary) -> RuntimeModeBadgeFields {
    // Map the proto's free-form runtime_mode string into a short badge label
    // suitable for the menubar list, paired with the VoiceOver phrasing used
    // when the badge is rendered. Producing both fields in one switch is the
    // structural prevention for the a11y-vs-tag drift concern raised in
    // PR #53 review — a future rename of a short tag has to land the a11y
    // phrasing in the same case by construction, rather than silently
    // falling through to a default in a different file.
    //
    // Cross-reference: the CLI equivalent is ``runtimeModeLabel`` in
    // ``Sources/MelixCLICore/MelixCLI.swift``. The two functions diverge
    // intentionally on the empty / base-model case: the CLI table renders
    // ``"-"`` in a fixed-width column so every row has a runtime cell,
    // while the menubar hides the badge entirely so base models render
    // without a visual tag. Any future backend that adds a new runtime_mode
    // string must land in both mappers for consistent operator UX.
    switch model.runtimeMode {
    case "adapter_backed_runtime":
        return RuntimeModeBadgeFields(
            text: "adapter",
            accessibilityLabel: "Runtime mode: adapter-backed"
        )
    case "fused_derived_model":
        return RuntimeModeBadgeFields(
            text: "fused",
            accessibilityLabel: "Runtime mode: fused derived model"
        )
    case "":
        return RuntimeModeBadgeFields(text: "", accessibilityLabel: "")
    default:
        return RuntimeModeBadgeFields(
            text: "?",
            accessibilityLabel: "Runtime mode: unrecognized"
        )
    }
}

func makeRuntimeModelRow(_ model: Melix_Controlplane_V1_ModelSummary) -> RuntimeModelRow {
    let imageSupportsGeneration = runtimeImageSupportsGeneration(model)
    let imageSupportsEdit = runtimeImageSupportsEdit(model)
    let runtimeModeBadge = runtimeModeBadgeFields(model)
    let runtimeCacheMissing = ModelRuntimeAvailability.isRuntimeCacheMissing(model)
    return RuntimeModelRow(
        modelID: model.modelID,
        kind: model.kind,
        features: model.features,
        supportedTasks: model.supportedTasks,
        state: model.state,
        stateText: runtimeModelStateText(
            model.state,
            transitionReason: model.residency.transitionReason
        ),
        actionTitle: runtimeCacheMissing ? "Restore Download" : runtimeActionTitle(for: model.state),
        maxContext: model.maxContext,
        alias: model.settings.alias,
        typeOverrideText: model.settings.typeOverride,
        memoryPolicyText: runtimeMemoryPolicyText(model.settings.memoryPolicy),
        diskStreamingModeText: runtimeDiskStreamingModeText(model.settings.diskStreamingMode),
        adaptiveThinkingText: runtimeAdaptiveThinkingText(model.settings.adaptiveThinking),
        accelerationModeText: runtimeAccelerationModeText(model.settings.defaultAccelerationMode),
        accelerationProfileID: model.settings.accelerationProfileID,
        toolParserFallbackText: runtimeToolParserFallbackText(model),
        residencyText: runtimeResidencyText(for: model),
        memoryText: runtimeMemoryText(for: model),
        memoryAlertText: runtimeMemoryAlertText(for: model),
        cachePolicyText: runtimeCachePolicyText(for: model),
        cacheSettingsText: runtimeCacheSettingsText(for: model),
        imageFamilyID: model.settings.ext["melix.image.family_id"] ?? "",
        imageDefaultWorkflowRole: model.settings.ext["melix.image.default_workflow_role"] ?? "",
        imageSupportsGeneration: imageSupportsGeneration,
        imageSupportsEdit: imageSupportsEdit,
        runtimeModeText: runtimeModeBadge.text,
        runtimeModeAccessibilityLabel: runtimeModeBadge.accessibilityLabel,
        runtimeCacheMissing: runtimeCacheMissing,
        runtimeCacheStatusText: runtimeCacheMissing ? ModelRuntimeAvailability.missingRuntimeCacheBadge : "",
        runtimeCacheDetailText: runtimeCacheMissing ? ModelRuntimeAvailability.missingRuntimeCacheMessage : "",
        runtimePathText: ModelRuntimeAvailability.runtimePath(for: model),
        registryDescriptorPathText: ModelRuntimeAvailability.descriptorPath(for: model),
        restoreCommandText: ModelRuntimeAvailability.restoreCommand(for: model),
        restoreRepoID: ModelRuntimeAvailability.restoreRepoID(for: model),
        restoreRevision: ModelRuntimeAvailability.restoreRevision(for: model)
    )
}

private func runtimeImageSupportsGeneration(_ model: Melix_Controlplane_V1_ModelSummary) -> Bool {
    if let explicit = model.settings.ext["melix.image.supports_generation"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        switch explicit {
        case "true", "1", "yes", "on":
            return true
        case "false", "0", "no", "off":
            return false
        default:
            break
        }
    }
    if model.supportedTasks.contains("image_generate") {
        return true
    }
    let taskKind = model.settings.ext["melix.image.task_kind"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    return taskKind != "image-text-to-image"
}

private func runtimeImageSupportsEdit(_ model: Melix_Controlplane_V1_ModelSummary) -> Bool {
    if let explicit = model.settings.ext["melix.image.supports_edit"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        switch explicit {
        case "true", "1", "yes", "on":
            return true
        case "false", "0", "no", "off":
            return false
        default:
            break
        }
    }
    if model.supportedTasks.contains("image_edit") {
        return true
    }
    let taskKind = model.settings.ext["melix.image.task_kind"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    return taskKind == "image-text-to-image"
}

private func runtimeModelStateText(
    _ state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = ""
) -> String {
    let base = switch state {
    case .modelDiscovered:
        "Discovered"
    case .modelWarm:
        "Warm"
    case .modelPinned:
        "Pinned"
    case .modelUnloaded:
        "Unloaded"
    case .modelLoading:
        "Loading"
    case .modelEvicting:
        "Evicting"
    case .modelFailed:
        "Failed"
    default:
        "Unknown"
    }

    guard !transitionReason.isEmpty else {
        return base
    }
    switch state {
    case .modelEvicting, .modelUnloaded, .modelFailed:
        return "\(base) • \(runtimeTransitionReasonText(transitionReason))"
    default:
        return base
    }
}

private func runtimeTransitionReasonText(_ reason: String) -> String {
    let separatorNormalized = reason.replacingOccurrences(of: "_", with: " ")
    guard let first = separatorNormalized.first else {
        return "Unknown"
    }
    return String(first).uppercased() + separatorNormalized.dropFirst()
}

private func runtimeAdaptiveThinkingText(
    _ policy: Melix_Controlplane_V1_AdaptiveThinkingPolicy
) -> String {
    let normalizedMode = policy.mode
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
    guard !normalizedMode.isEmpty, normalizedMode != "off" else {
        return "Off"
    }

    let label = switch normalizedMode {
    case "adaptive":
        "Adaptive"
    case "enabled":
        "Enabled"
    default:
        String(normalizedMode.prefix(1)).uppercased() + normalizedMode.dropFirst()
    }

    guard policy.budgetTokens > 0 else {
        return label
    }
    return "\(label) • \(policy.budgetTokens) tok"
}

private func runtimeActionTitle(for state: Melix_Controlplane_V1_ModelState) -> String {
    switch state {
    case .modelWarm, .modelPinned:
        return "Unload"
    default:
        return "Load"
    }
}

private func runtimeMemoryPolicyText(_ policy: Melix_Controlplane_V1_MemoryResidencyPolicy) -> String {
    switch policy {
    case .memoryResidencyPinned:
        return "Pinned"
    case .memoryResidencyTtl:
        return "TTL"
    case .memoryResidencyEvictable:
        return "Evictable"
    default:
        return "Unspecified"
    }
}

private func runtimeMemoryPolicyDraftValue(
    _ policy: Melix_Controlplane_V1_MemoryResidencyPolicy
) -> String {
    switch policy {
    case .memoryResidencyPinned:
        return "pinned"
    case .memoryResidencyTtl:
        return "ttl"
    case .memoryResidencyEvictable, .unspecified:
        return "evictable"
    default:
        return "evictable"
    }
}

private func runtimeMemoryBudgetText(_ bytes: UInt64) -> String {
    guard bytes > 0 else {
        return ""
    }
    return runtimeFormatBytes(bytes)
}

private func runtimeCacheModeText(_ mode: Melix_Controlplane_V1_CacheMode) -> String {
    switch mode {
    case .rotating:
        return "Rotating"
    case .hybrid:
        return "Hybrid"
    case .tiered:
        return "Tiered"
    default:
        return "Unspecified"
    }
}

private func runtimeCacheModeDraftValue(_ mode: Melix_Controlplane_V1_CacheMode) -> String {
    switch mode {
    case .rotating:
        return "rotating"
    case .hybrid:
        return "hybrid"
    case .tiered, .unspecified:
        return "tiered"
    default:
        return "tiered"
    }
}

private func runtimeCacheCompatibilityText(
    _ compatibility: Melix_Controlplane_V1_CacheCompatibilityState
) -> String {
    switch compatibility {
    case .cacheCompatibilityCompatible:
        return "Compatible"
    case .cacheCompatibilityLimited:
        return "Limited"
    case .cacheCompatibilityDisabled:
        return "Disabled"
    case .cacheCompatibilityUnknown, .unspecified:
        return "Unknown"
    default:
        return "Unknown"
    }
}

private func runtimeCachePolicyText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let compatibility = runtimeCacheCompatibilityText(model.cachePolicy.compatibility)
    let effectiveMode = runtimeCacheModeText(model.cachePolicy.effectiveMode)
    return "\(compatibility) • \(effectiveMode)"
}

private func runtimeCacheSettingsText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    var parts: [String] = []
    let effectiveDirectory = model.cachePolicy.effectiveDirectory
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if !effectiveDirectory.isEmpty {
        parts.append(effectiveDirectory)
    }
    if model.cachePolicy.effectiveBlockSizeTokens > 0 {
        parts.append("block \(model.cachePolicy.effectiveBlockSizeTokens)")
    }
    if model.cachePolicy.effectiveCacheMemoryBudgetBytes > 0 {
        parts.append("cache \(runtimeFormatBytes(model.cachePolicy.effectiveCacheMemoryBudgetBytes))")
    } else if model.cachePolicy.effectiveCacheMemoryBudgetPct > 0 {
        parts.append("cache \(model.cachePolicy.effectiveCacheMemoryBudgetPct)%")
    }
    if model.cachePolicy.effectiveMultimodalCacheBudgetBytes > 0 {
        parts.append("multimodal \(runtimeFormatBytes(model.cachePolicy.effectiveMultimodalCacheBudgetBytes))")
    }
    return parts.joined(separator: " • ")
}

private func runtimeCacheDirectoryText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let requested = model.cachePolicy.requestedDirectory.trimmingCharacters(in: .whitespacesAndNewlines)
    let effective = model.cachePolicy.effectiveDirectory.trimmingCharacters(in: .whitespacesAndNewlines)
    if !requested.isEmpty && requested != effective {
        return "\(requested) -> \(effective)"
    }
    return effective
}

private func runtimeCacheBlockSizeText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let requested = model.cachePolicy.requestedBlockSizeTokens
    let effective = model.cachePolicy.effectiveBlockSizeTokens
    guard requested > 0 || effective > 0 else {
        return ""
    }
    if requested > 0 && requested != effective {
        return "\(requested) -> \(effective) tokens"
    }
    let value = effective > 0 ? effective : requested
    return "\(value) tokens"
}

private func runtimeCacheBudgetText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let requestedBytes = model.cachePolicy.requestedCacheMemoryBudgetBytes
    let effectiveBytes = model.cachePolicy.effectiveCacheMemoryBudgetBytes
    let requestedPct = model.cachePolicy.requestedCacheMemoryBudgetPct
    let effectivePct = model.cachePolicy.effectiveCacheMemoryBudgetPct
    if requestedBytes > 0 || effectiveBytes > 0 {
        if requestedBytes > 0 && requestedBytes != effectiveBytes {
            return "\(runtimeFormatBytes(requestedBytes)) -> \(runtimeFormatBytes(effectiveBytes))"
        }
        let value = effectiveBytes > 0 ? effectiveBytes : requestedBytes
        return runtimeFormatBytes(value)
    }
    if requestedPct > 0 || effectivePct > 0 {
        if requestedPct > 0 && requestedPct != effectivePct {
            return "\(requestedPct)% -> \(effectivePct)%"
        }
        let value = effectivePct > 0 ? effectivePct : requestedPct
        return "\(value)%"
    }
    return ""
}

private func runtimeMultimodalCacheBudgetText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let requested = model.cachePolicy.requestedMultimodalCacheBudgetBytes
    let effective = model.cachePolicy.effectiveMultimodalCacheBudgetBytes
    guard requested > 0 || effective > 0 else {
        return ""
    }
    if requested > 0 && requested != effective {
        return "\(runtimeFormatBytes(requested)) -> \(runtimeFormatBytes(effective))"
    }
    let value = effective > 0 ? effective : requested
    return runtimeFormatBytes(value)
}

private func runtimeInitialCacheBlocksText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    guard model.cachePolicy.initialCacheBlocks > 0 else {
        return ""
    }
    return String(model.cachePolicy.initialCacheBlocks)
}

private func runtimeAccelerationModeText(_ mode: Melix_Controlplane_V1_AccelerationMode) -> String {
    switch mode {
    case .speculativeDecode:
        return "Speculative Decode"
    case .acceleratedPrefill:
        return "Accelerated Prefill"
    case .sparsePrefill:
        return "Sparse Prefill"
    case .activeKvQuantized:
        return "Active KV Quantized"
    case .baseline:
        return "Baseline"
    default:
        return "Unspecified"
    }
}

private func runtimeAccelerationModeDraftValue(_ mode: Melix_Controlplane_V1_AccelerationMode) -> String {
    switch mode {
    case .speculativeDecode:
        return "speculative_decode"
    case .acceleratedPrefill:
        return "accelerated_prefill"
    case .activeKvQuantized:
        return "active_kv_quantized"
    case .sparsePrefill:
        return "sparse_prefill"
    case .baseline, .unspecified:
        return "baseline"
    default:
        return "baseline"
    }
}

private func servingDefaultsAccelerationMode(
    from rawValue: String
) -> Melix_Controlplane_V1_AccelerationMode {
    switch rawValue {
    case "speculative_decode":
        return .speculativeDecode
    default:
        return .baseline
    }
}

private func runtimeDiskStreamingModeText(_ mode: Melix_Controlplane_V1_DiskStreamingMode) -> String {
    switch mode {
    case .diskStreamingPreferDisk:
        return "Prefer Disk"
    case .diskStreamingRequireDisk:
        return "Require Disk"
    case .diskStreamingDisabled, .unspecified:
        return "Disabled"
    default:
        return "Disabled"
    }
}

private func runtimeDiskStreamingModeDraftValue(_ mode: Melix_Controlplane_V1_DiskStreamingMode) -> String {
    switch mode {
    case .diskStreamingPreferDisk:
        return "prefer_disk"
    case .diskStreamingRequireDisk:
        return "require_disk"
    case .diskStreamingDisabled, .unspecified:
        return "disabled"
    default:
        return "disabled"
    }
}

private func runtimeAdaptiveThinkingDraftValue(
    _ policy: Melix_Controlplane_V1_AdaptiveThinkingPolicy
) -> String {
    let normalizedMode = policy.mode
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
    return normalizedMode.isEmpty ? "off" : normalizedMode
}

private func runtimeToolParserFallbackText(_ model: Melix_Controlplane_V1_ModelSummary) -> String {
    model.settings.ext["tool_parser_xml_fallback"] == "true" ? "XML" : "Off"
}

private func runtimeEffectiveOCRSamplingProfileText(
    for model: Melix_Controlplane_V1_ModelSummary,
    generationConfigAvailable: Bool
) -> String {
    let explicitValue = model.settings.ext["ocr_sampling_profile_id"]?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !explicitValue.isEmpty {
        return explicitValue
    }
    return generationConfigAvailable && model.kind == "ocr" ? "generation-config" : ""
}

private func runtimeEffectiveOCRSamplingValue(
    explicitValue: String,
    generationConfigValue: String
) -> String {
    let normalizedExplicit = explicitValue.trimmingCharacters(in: .whitespacesAndNewlines)
    if !normalizedExplicit.isEmpty {
        return normalizedExplicit
    }
    return generationConfigValue.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func runtimeResidencyText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let residencyState = resolvedResidencyState(for: model)
    let policy = resolvedResidencyPolicy(for: model)
    let pinRequested = resolvedPinRequested(for: model)
    let pinned = resolvedPinned(for: model)
    let ttlSeconds = resolvedTTLSeconds(for: model)
    let effectiveDiskStreamingMode = resolvedEffectiveDiskStreamingMode(for: model)

    var parts = [
        runtimeResidencyStateText(residencyState),
        runtimeMemoryPolicyText(policy),
        runtimeDiskStreamingModeText(effectiveDiskStreamingMode),
    ]
    if pinRequested && !pinned {
        parts.append("Pin requested")
    }
    if ttlSeconds > 0 {
        parts.append("TTL \(ttlSeconds)s")
    }
    return parts.joined(separator: " • ")
}

private func runtimeMemoryText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    var parts: [String] = []
    if model.estimatedBytes > 0 {
        parts.append("\(runtimeFormatBytes(model.estimatedBytes)) estimated")
    }
    if model.settings.memoryBudgetBytes > 0 {
        parts.append("\(runtimeFormatBytes(model.settings.memoryBudgetBytes)) budget")
    }
    if model.inflightRequests > 0 {
        parts.append("\(model.inflightRequests) inflight")
    }
    if parts.isEmpty {
        return "No live footprint reported"
    }
    return parts.joined(separator: " • ")
}

private func runtimeMemoryAlertText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let reason = model.residency.transitionReason.trimmingCharacters(in: .whitespacesAndNewlines)
    guard runtimeIsMemoryProtectionReason(reason) else {
        return ""
    }
    var parts = ["Memory protection", runtimeTransitionReasonText(reason)]
    if model.residency.memoryBudgetBytes > 0 {
        parts.append("budget \(runtimeFormatBytes(model.residency.memoryBudgetBytes))")
    }
    if model.residency.memoryHeadroomBytes > 0 {
        parts.append("headroom \(runtimeFormatBytes(model.residency.memoryHeadroomBytes))")
    }
    if model.residency.requiredBytes > 0 {
        parts.append("required \(runtimeFormatBytes(model.residency.requiredBytes))")
    }
    return parts.joined(separator: " • ")
}

private func resolvedResidencyState(
    for model: Melix_Controlplane_V1_ModelSummary
) -> Melix_Controlplane_V1_ResidencyState {
    if model.residency.state != .unspecified {
        return model.residency.state
    }
    switch model.state {
    case .modelDiscovered:
        return .discovered
    case .modelLoading:
        return .loading
    case .modelWarm:
        return .warm
    case .modelPinned:
        return .pinned
    case .modelEvicting:
        return .evicting
    case .modelUnloaded:
        return .unloaded
    case .modelFailed:
        return .failed
    default:
        return .unspecified
    }
}

private func resolvedResidencyPolicy(
    for model: Melix_Controlplane_V1_ModelSummary
) -> Melix_Controlplane_V1_MemoryResidencyPolicy {
    if model.residency.policy != .unspecified {
        return model.residency.policy
    }
    if model.settings.pinOnLoad {
        return .memoryResidencyPinned
    }
    if model.settings.memoryPolicy != .unspecified {
        return model.settings.memoryPolicy
    }
    if model.settings.ttlSeconds > 0 {
        return .memoryResidencyTtl
    }
    return .memoryResidencyEvictable
}

private func resolvedPinRequested(for model: Melix_Controlplane_V1_ModelSummary) -> Bool {
    model.residency.pinRequested || model.settings.pinOnLoad
}

private func resolvedPinned(for model: Melix_Controlplane_V1_ModelSummary) -> Bool {
    model.residency.pinned || model.pinned || model.state == .modelPinned
}

private func resolvedTTLSeconds(for model: Melix_Controlplane_V1_ModelSummary) -> UInt32 {
    max(model.residency.ttlSeconds, model.settings.ttlSeconds)
}

private func resolvedEffectiveDiskStreamingMode(
    for model: Melix_Controlplane_V1_ModelSummary
) -> Melix_Controlplane_V1_DiskStreamingMode {
    if model.residency.effectiveDiskStreamingMode != .unspecified {
        return model.residency.effectiveDiskStreamingMode
    }
    switch model.state {
    case .modelWarm, .modelPinned:
        return model.settings.diskStreamingMode == .unspecified ? .diskStreamingDisabled : model.settings.diskStreamingMode
    default:
        return .diskStreamingDisabled
    }
}

private func runtimeResidencyStateText(_ state: Melix_Controlplane_V1_ResidencyState) -> String {
    switch state {
    case .discovered:
        return "Discovered"
    case .loading:
        return "Loading"
    case .warm:
        return "Warm"
    case .pinned:
        return "Pinned"
    case .evicting:
        return "Evicting"
    case .unloaded:
        return "Unloaded"
    case .failed:
        return "Failed"
    default:
        return "Unknown"
    }
}

private func runtimeIsMemoryProtectionReason(_ reason: String) -> Bool {
    let normalized = reason.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !normalized.isEmpty else {
        return false
    }
    return normalized.contains("memory_budget")
        || normalized.contains("unsafe_load")
        || normalized.contains("prefill_memory_guard")
        || normalized.contains("quadratic_prefill_guard")
}

private func runtimeFormatBytes(_ bytes: UInt64) -> String {
    let formatter = ByteCountFormatter()
    formatter.countStyle = .binary
    formatter.allowedUnits = [.useKB, .useMB, .useGB]
    formatter.includesUnit = true
    formatter.includesCount = true
    return formatter.string(fromByteCount: Int64(bytes))
}
