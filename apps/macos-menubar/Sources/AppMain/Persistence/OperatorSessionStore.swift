import Foundation
import MelixCLICore

public struct OperatorSessionState: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var selectedSurface: DesktopSurface
    public var selectedToolSection: DesktopToolSection
    public var selectedServerSessionID: String
    public var selectedRuntimeJobID: String
    public var serverSessions: [DesktopServerSessionState]
    public var dismissedBannerIDs: [String]
    public var downloadQueue: [RuntimeDownloadQueueEntryState]
    public var registryRoots: [String]
    public var paneVisibility: [DesktopPaneVisibilityState]

    public init(
        schemaVersion: Int = 6,
        selectedSurface: DesktopSurface,
        selectedToolSection: DesktopToolSection = .modelsLibrary,
        selectedServerSessionID: String,
        selectedRuntimeJobID: String = "",
        serverSessions: [DesktopServerSessionState],
        dismissedBannerIDs: [String] = [],
        downloadQueue: [RuntimeDownloadQueueEntryState] = [],
        registryRoots: [String] = [],
        paneVisibility: [DesktopPaneVisibilityState] = DesktopPaneVisibilityState.defaultStates
    ) {
        self.schemaVersion = max(schemaVersion, 6)
        self.selectedSurface = selectedSurface
        self.selectedToolSection = selectedToolSection
        self.selectedServerSessionID = selectedServerSessionID
        self.selectedRuntimeJobID = selectedRuntimeJobID
        self.serverSessions = serverSessions
        self.dismissedBannerIDs = dismissedBannerIDs
        self.downloadQueue = downloadQueue
        self.registryRoots = registryRoots
        self.paneVisibility = DesktopPaneVisibilityState.mergedWithDefaults(paneVisibility)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case selectedSurface = "selected_surface"
        case selectedToolSection = "selected_tool_section"
        case selectedServerSessionID = "selected_server_session_id"
        case selectedRuntimeJobID = "selected_runtime_job_id"
        case serverSessions = "server_sessions"
        case dismissedBannerIDs = "dismissed_banner_ids"
        case downloadQueue = "download_queue"
        case registryRoots = "registry_roots"
        case paneVisibility = "pane_visibility"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let selectedSurfaceID = try container.decodeIfPresent(String.self, forKey: .selectedSurface) ?? "chat"
        let selectedToolSectionID = try container.decodeIfPresent(String.self, forKey: .selectedToolSection) ?? "modelsLibrary"
        let selectedToolSection = DesktopToolSection(operatorSessionID: selectedToolSectionID)
        self.init(
            schemaVersion: try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 4,
            selectedSurface: DesktopSurface(operatorSessionID: selectedSurfaceID, selectedToolSection: selectedToolSection),
            selectedToolSection: selectedToolSection,
            selectedServerSessionID: try container.decodeIfPresent(String.self, forKey: .selectedServerSessionID) ?? "",
            selectedRuntimeJobID: try container.decodeIfPresent(String.self, forKey: .selectedRuntimeJobID) ?? "",
            serverSessions: try container.decodeIfPresent([DesktopServerSessionState].self, forKey: .serverSessions) ?? [],
            dismissedBannerIDs: try container.decodeIfPresent([String].self, forKey: .dismissedBannerIDs) ?? [],
            downloadQueue: try container.decodeIfPresent([RuntimeDownloadQueueEntryState].self, forKey: .downloadQueue) ?? [],
            registryRoots: try container.decodeIfPresent([String].self, forKey: .registryRoots) ?? [],
            paneVisibility: try container.decodeIfPresent([DesktopPaneVisibilityState].self, forKey: .paneVisibility)
                ?? DesktopPaneVisibilityState.defaultStates
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(selectedSurface.operatorSessionID, forKey: .selectedSurface)
        try container.encode(selectedToolSection.operatorSessionID, forKey: .selectedToolSection)
        try container.encode(selectedServerSessionID, forKey: .selectedServerSessionID)
        try container.encode(selectedRuntimeJobID, forKey: .selectedRuntimeJobID)
        try container.encode(serverSessions, forKey: .serverSessions)
        try container.encode(dismissedBannerIDs, forKey: .dismissedBannerIDs)
        try container.encode(downloadQueue, forKey: .downloadQueue)
        try container.encode(registryRoots, forKey: .registryRoots)
        try container.encode(paneVisibility, forKey: .paneVisibility)
    }

    public mutating func ensurePaneVisibilityDefaults() {
        schemaVersion = max(schemaVersion, 6)
        paneVisibility = DesktopPaneVisibilityState.mergedWithDefaults(paneVisibility)
    }
}

public protocol OperatorSessionStoring: Sendable {
    func load() throws -> OperatorSessionState?
    func save(_ state: OperatorSessionState) throws
}

public struct NullOperatorSessionStore: OperatorSessionStoring {
    public init() {}

    public func load() throws -> OperatorSessionState? {
        nil
    }

    public func save(_ state: OperatorSessionState) throws {
        _ = state
    }
}

public struct OperatorSessionStore: OperatorSessionStoring {
    private let store: MelixOperatorSessionStore

    public init(melixHome: MelixHome) {
        self.store = MelixOperatorSessionStore(melixHome: melixHome)
    }

    public func load() throws -> OperatorSessionState? {
        try store.load().map(OperatorSessionState.init(sharedState:))
    }

    public func save(_ state: OperatorSessionState) throws {
        try store.save(state.sharedState)
    }
}

private extension OperatorSessionState {
    init(sharedState: MelixOperatorSessionState) {
        let selectedToolSection = DesktopToolSection(operatorSessionID: sharedState.selectedToolSectionID)
        self.init(
            schemaVersion: sharedState.schemaVersion,
            selectedSurface: DesktopSurface(
                operatorSessionID: sharedState.selectedSurfaceID,
                selectedToolSection: selectedToolSection
            ),
            selectedToolSection: selectedToolSection,
            selectedServerSessionID: sharedState.selectedServerSessionID,
            selectedRuntimeJobID: sharedState.selectedRuntimeJobID,
            serverSessions: sharedState.serverSessions.map(DesktopServerSessionState.init(sharedState:)),
            dismissedBannerIDs: sharedState.dismissedBannerIDs,
            downloadQueue: sharedState.downloadQueue.map(RuntimeDownloadQueueEntryState.init(sharedState:)),
            registryRoots: sharedState.registryRoots,
            paneVisibility: sharedState.paneVisibility.map(DesktopPaneVisibilityState.init(sharedState:))
        )
    }

    var sharedState: MelixOperatorSessionState {
        MelixOperatorSessionState(
            schemaVersion: schemaVersion,
            selectedSurfaceID: selectedSurface.operatorSessionID,
            selectedToolSectionID: selectedToolSection.operatorSessionID,
            selectedServerSessionID: selectedServerSessionID,
            selectedRuntimeJobID: selectedRuntimeJobID,
            serverSessions: serverSessions.map(\.sharedState),
            dismissedBannerIDs: dismissedBannerIDs,
            downloadQueue: downloadQueue.map(\.sharedState),
            registryRoots: registryRoots,
            paneVisibility: paneVisibility.map(\.sharedState)
        )
    }
}

private extension DesktopPaneVisibilityState {
    init(sharedState: MelixOperatorPaneVisibilityState) {
        self.init(
            surface: DesktopSurface(paneVisibilityID: sharedState.surfaceID),
            showsSidebar: sharedState.showsSidebar,
            showsInspector: sharedState.showsInspector
        )
    }

    var sharedState: MelixOperatorPaneVisibilityState {
        MelixOperatorPaneVisibilityState(
            surfaceID: surface.paneVisibilityID,
            showsSidebar: showsSidebar,
            showsInspector: showsInspector
        )
    }
}

private extension DesktopServerServingDefaultsState {
    init(sharedState: MelixOperatorServerServingDefaultsState) {
        self.init(
            temperature: sharedState.temperature,
            topP: sharedState.topP,
            maxTokens: sharedState.maxTokens,
            streamIntervalTokens: sharedState.streamIntervalTokens,
            maxConcurrentRequests: sharedState.maxConcurrentRequests,
            concurrentProcessingEnabled: sharedState.concurrentProcessingEnabled,
            prefillBatchSize: sharedState.prefillBatchSize,
            completionBatchSize: sharedState.completionBatchSize,
            accelerationProfile: sharedState.accelerationProfile,
            accelerationMode: sharedState.accelerationMode,
            draftModelID: sharedState.draftModelID,
            numDraftTokens: sharedState.numDraftTokens,
            sourceText: "Operator Override"
        )
    }

    var sharedState: MelixOperatorServerServingDefaultsState {
        MelixOperatorServerServingDefaultsState(
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: maxConcurrentRequests,
            concurrentProcessingEnabled: concurrentProcessingEnabled,
            prefillBatchSize: prefillBatchSize,
            completionBatchSize: completionBatchSize,
            accelerationProfile: accelerationProfile,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens
        )
    }
}

private extension DesktopServerSessionState {
    init(sharedState: MelixOperatorServerSessionState) {
        self.init(
            id: sharedState.id,
            title: sharedState.title,
            modelID: sharedState.defaultModelID,
            servedModelIDs: sharedState.servedModelIDs,
            host: sharedState.host,
            port: sharedState.port,
            rateLimitPerMinute: sharedState.rateLimitPerMinute,
            timeoutSeconds: sharedState.timeoutSeconds,
            modelIdleTimeoutSeconds: sharedState.modelIdleTimeoutSeconds,
            servingDefaults: DesktopServerServingDefaultsState(sharedState: sharedState.servingDefaults),
            lifecycle: DesktopServerSessionLifecycle(sharedState: sharedState.lifecycle),
            autoSleepEnabled: sharedState.autoSleepEnabled,
            lightSleepAfterSeconds: sharedState.lightSleepAfterSeconds,
            deepSleepAfterSeconds: sharedState.deepSleepAfterSeconds,
            lastError: sharedState.lastError,
            lastKnownModelStateText: sharedState.lastKnownModelStateText,
            createdAt: sharedState.createdAt,
            updatedAt: sharedState.updatedAt
        )
    }

    var sharedState: MelixOperatorServerSessionState {
        MelixOperatorServerSessionState(
            id: id,
            title: title,
            defaultModelID: defaultModelID,
            servedModelIDs: servedModelIDs,
            host: host,
            port: port,
            rateLimitPerMinute: rateLimitPerMinute,
            timeoutSeconds: timeoutSeconds,
            modelIdleTimeoutSeconds: modelIdleTimeoutSeconds,
            servingDefaults: servingDefaults.sharedState,
            autoSleepEnabled: autoSleepEnabled,
            lightSleepAfterSeconds: lightSleepAfterSeconds,
            deepSleepAfterSeconds: deepSleepAfterSeconds,
            lifecycle: lifecycle.sharedState,
            lastError: lastError,
            lastKnownModelStateText: lastKnownModelStateText,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

private extension RuntimeDownloadQueueEntryState {
    init(sharedState: MelixOperatorDownloadQueueEntryState) {
        self.init(
            jobID: sharedState.jobID,
            sourceModel: sharedState.sourceModel,
            status: sharedState.status,
            stage: sharedState.stage,
            pct: sharedState.pct,
            outputDir: sharedState.outputDir,
            outputPath: sharedState.outputPath,
            partialPath: sharedState.partialPath,
            statePath: sharedState.statePath,
            selectedMirror: sharedState.selectedMirror,
            downloadedBytes: sharedState.downloadedBytes,
            totalBytes: sharedState.totalBytes,
            resumeUsed: sharedState.resumeUsed,
            resumeFromBytes: sharedState.resumeFromBytes,
            retryCount: sharedState.retryCount,
            stallDetectionCount: sharedState.stallDetectionCount,
            stallReason: sharedState.stallReason,
            resumeReady: sharedState.resumeReady
        )
    }

    var sharedState: MelixOperatorDownloadQueueEntryState {
        MelixOperatorDownloadQueueEntryState(
            jobID: jobID,
            sourceModel: sourceModel,
            status: status,
            stage: stage,
            pct: pct,
            outputDir: outputDir,
            outputPath: outputPath,
            partialPath: partialPath,
            statePath: statePath,
            selectedMirror: selectedMirror,
            downloadedBytes: downloadedBytes,
            totalBytes: totalBytes,
            resumeUsed: resumeUsed,
            resumeFromBytes: resumeFromBytes,
            retryCount: retryCount,
            stallDetectionCount: stallDetectionCount,
            stallReason: stallReason,
            resumeReady: resumeReady
        )
    }
}

private extension DesktopServerSessionLifecycle {
    init(sharedState: MelixOperatorServerSessionLifecycle) {
        switch sharedState {
        case .draft:
            self = .draft
        case .starting:
            self = .starting
        case .running:
            self = .running
        case .paused:
            self = .paused
        case .sleeping:
            self = .sleeping
        case .stopping:
            self = .stopping
        case .stopped:
            self = .stopped
        case .error:
            self = .error
        case .unavailable:
            self = .unavailable
        }
    }

    var sharedState: MelixOperatorServerSessionLifecycle {
        switch self {
        case .draft:
            return .draft
        case .starting:
            return .starting
        case .running:
            return .running
        case .paused:
            return .paused
        case .sleeping:
            return .sleeping
        case .stopping:
            return .stopping
        case .stopped:
            return .stopped
        case .error:
            return .error
        case .unavailable:
            return .unavailable
        }
    }
}

private extension DesktopSurface {
    init(operatorSessionID rawValue: String, selectedToolSection: DesktopToolSection = .modelsLibrary) {
        switch Self.normalizedOperatorSessionID(rawValue) {
        case "commandcenter":
            self = .commandCenter
        case "image":
            self = .image
        case "server", "servers":
            self = .server
        case "models":
            self = .models
        case "workflows":
            self = .workflows
        case "jobs":
            self = .jobs
        case "diagnostics":
            self = .diagnostics
        case "tools":
            self = selectedToolSection.domain.surface
        case "api":
            self = .api
        case "settings":
            self = .settings
        default:
            self = .chat
        }
    }

    var operatorSessionID: String {
        switch self {
        case .chat:
            return "chat"
        case .commandCenter:
            return "commandCenter"
        case .image:
            return "image"
        case .server:
            return "server"
        case .models:
            return "models"
        case .workflows:
            return "workflows"
        case .jobs:
            return "jobs"
        case .diagnostics:
            return "diagnostics"
        case .tools:
            return "tools"
        case .api:
            return "api"
        case .settings:
            return "settings"
        }
    }

    private static func normalizedOperatorSessionID(_ rawValue: String) -> String {
        rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .filter(\.isLetter)
    }
}

private extension DesktopToolSection {
    init(operatorSessionID rawValue: String) {
        switch Self.normalizedOperatorSessionID(rawValue) {
        case "downloads":
            self = .downloads
        case "training":
            self = .training
        case "workflowrecipes":
            self = .workflowRecipes
        case "syntheticdatasets":
            self = .syntheticDatasets
        case "batchruns":
            self = .batchRuns
        case "jobs":
            self = .jobs
        case "diagnostics":
            self = .diagnostics
        case "logs":
            self = .logs
        case "settings":
            self = .settings
        default:
            self = .modelsLibrary
        }
    }

    var operatorSessionID: String {
        switch self {
        case .modelsLibrary:
            return "modelsLibrary"
        case .downloads:
            return "downloads"
        case .training:
            return "training"
        case .workflowRecipes:
            return "workflowRecipes"
        case .syntheticDatasets:
            return "syntheticDatasets"
        case .batchRuns:
            return "batchRuns"
        case .jobs:
            return "jobs"
        case .diagnostics:
            return "diagnostics"
        case .logs:
            return "logs"
        case .settings:
            return "settings"
        }
    }

    private static func normalizedOperatorSessionID(_ rawValue: String) -> String {
        rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .filter(\.isLetter)
    }
}
