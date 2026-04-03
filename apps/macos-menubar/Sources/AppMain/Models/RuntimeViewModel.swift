import Foundation
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

public struct RuntimeModelRow: Identifiable, Equatable, Sendable {
    public let modelID: String
    public let kind: String
    public let state: Melix_Controlplane_V1_ModelState
    public let stateText: String
    public let actionTitle: String
    public let maxContext: UInt32
    public let alias: String
    public let memoryPolicyText: String
    public let adaptiveThinkingText: String
    public let accelerationModeText: String
    public let accelerationProfileID: String
    public let residencyText: String
    public let memoryText: String
    public let memoryAlertText: String

    public var id: String {
        modelID
    }

    public var isLoaded: Bool {
        switch state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }
}

public struct RuntimeModelInfoState: Equatable, Sendable {
    public let modelID: String
    public let modelKind: String
    public let maxContext: UInt32
    public let supportedParsers: [String]
    public let supportedModalities: [String]
    public let ocrPromptProfileText: String
    public let ocrSamplingProfileText: String
    public let ocrStopSequencesText: String
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
    public let smokeTestPassed: Bool
    public let calibrationSampleCount: Int
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

public struct RuntimeDoctorReportState: Equatable, Sendable {
    public let markdown: String
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
    public let trainingDurationText: String
    public let activationDurationText: String
    public let publishDurationText: String
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
}

public struct RuntimeBenchMetricState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let value: String

    public init(name: String, value: String) {
        self.id = name
        self.name = name
        self.value = value
    }
}

public struct RuntimeBenchReportState: Equatable, Sendable {
    public let reportPath: String
    public let markdown: String
    public let metrics: [RuntimeBenchMetricState]
}

public struct RuntimeBenchmarkSuiteOptionState: Identifiable, Equatable, Sendable {
    public let id: String
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
}

private struct GatewayAccessProjection: Equatable, Sendable {
    let authMode: DesktopServerAuthMode
    let authTokenHint: String
    let sharedAccessState: DesktopSharedAccessState
    let accessKeyCount: Int
    let accessKeyHints: [String]
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
    public private(set) var models: [RuntimeModelRow] = []
    public private(set) var serverSessions: [DesktopServerSessionState] = []
    public private(set) var chatSessions: [DesktopChatSessionState] = []
    public private(set) var lastError: String?
    public private(set) var protocolVersion = "melix.controlplane.v1"
    public private(set) var serverVersion = "0.1.0"
    public private(set) var daemonInstanceID = ""
    public private(set) var features: [String] = []
    public private(set) var selectedModelInfo: RuntimeModelInfoState?
    public private(set) var lastModelOperation: RuntimeModelOperationState?
    public private(set) var lastDoctorReport: RuntimeDoctorReportState?
    public private(set) var lastBenchReport: RuntimeBenchReportState?
    public private(set) var benchmarkHistory: [RuntimeBenchmarkHistoryEntryState] = []
    public private(set) var benchmarkMetricCards: [RuntimeBenchmarkMetricCardState] = []
    public private(set) var benchmarkChartPoints: [RuntimeBenchmarkChartPointState] = []
    public private(set) var benchmarkMetricOptions: [String] = []
    public private(set) var lastBenchmarkCSVExport: RuntimeBenchmarkCSVExportState?
    public private(set) var adapterPackages: [RuntimeAdapterPackageState] = []
    public private(set) var trainingHistory: [RuntimeTrainingHistoryEntryState] = []
    public private(set) var chatTranscript: [DesktopChatTranscriptEntry] = []
    public private(set) var chatCapabilities: [DesktopChatCapabilityRow] = []
    public private(set) var agentIntegrationExports: [AgentIntegrationExport] = []
    public private(set) var chatStatusText = "Idle"
    public private(set) var lastChatUsageText = ""
    public private(set) var isChatStreaming = false
    public private(set) var lastChatRequestID = ""
    public private(set) var imageJobs: [Melix_Controlplane_V1_ImageJobSummary] = []
    public private(set) var imageStatusText = "Idle"
    public private(set) var selectedImageJobID = ""
    public private(set) var selectedAgentIntegrationTarget: AgentIntegrationExportTarget = .openAICompatible
    public var chatComposerText = ""
    public var selectedChatModelID = "melix-dev-text"
    public var selectedLoraModelID = "melix-dev-text"
    public var selectedBenchmarkModelID = "melix-dev-text"
    public var selectedBenchmarkSuiteIDs: Set<String> = ["smoke"]
    public var benchmarkSampleSize = ""
    public var benchmarkBatchFactor = ""
    public var selectedBenchmarkHistoryJobID = ""
    public var selectedBenchmarkMetricName = ""
    public var loraDatasetSourceKind: RuntimeLoraDatasetSourceKind = .localPackage
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
    public var imagePromptText = ""
    public var imageEditSourceURL = ""
    public var imageEditMaskURL = ""
    public var imageSize = "1024x1024"
    public var imageVariantCount: UInt32 = 1
    public var selectedImageModelID = "melix-dev-image"
    public let availableQuantizationProfileIDs = ["q2", "q3", "q4", "q5", "q6", "q7", "q8"]
    public var selectedQuantizationProfileID = "q4"
    public var openCommandCenterAction: (@MainActor @Sendable () -> Void)?

    public var onStateChanged: (@MainActor @Sendable () -> Void)?

    private let client: any ControlPlaneXPCClient
    private let metrics: MenuBarMetricsStore
    private let operatorSessionStore: any OperatorSessionStoring
    private let serverSessionAPIKeyStore: any ServerSessionAPIKeyStoring
    private var subscriptionTask: Task<Void, Never>?
    private var lastSeenSeq: UInt64 = 0
    private var latestSnapshot = Melix_Controlplane_V1_ServerSnapshot()
    private var recentEvents: [DesktopLogEntry] = []
    private var connectionStateTransitions = 0.0
    private var chatConversationMessages: [ControlPlaneChatRequest.Message] = []
    private var activeAssistantEntryID: String?
    private var activeReasoningEntryID: String?
    private var activeToolEntryIDs: [String: String] = [:]
    private var persistedServerSessions: [DesktopServerSessionState] = []
    private var operatorStateRestored = false
    private var lastPersistedOperatorSessionState: OperatorSessionState?
    private var gatewayAPIKeyPersistFailures = 0.0
    private var lastAppliedGatewaySessionID = ""
    private var lastAppliedGatewayPrimaryKey = ""
    private var gatewayApplyTask: Task<Void, Never>?
    private var benchmarkExportBundle: ControlPlaneBenchmarkExportBundle?

    private static let benchmarkSuiteOptions = [
        RuntimeBenchmarkSuiteOptionState(
            id: "smoke",
            title: "UltraChat Smoke",
            datasetPath: "HuggingFaceH4/ultrachat_200k",
            datasetName: "default",
            datasetSplit: "train_sft",
            defaultSampleSize: 1,
            defaultBatchFactor: 1
        ),
        RuntimeBenchmarkSuiteOptionState(
            id: "latency",
            title: "Dolly Latency",
            datasetPath: "databricks/databricks-dolly-15k",
            datasetName: "default",
            datasetSplit: "train",
            defaultSampleSize: 5,
            defaultBatchFactor: 1
        ),
    ]

    public init(
        client: any ControlPlaneXPCClient,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        operatorSessionStore: any OperatorSessionStoring = NullOperatorSessionStore(),
        serverSessionAPIKeyStore: any ServerSessionAPIKeyStoring = NullServerSessionAPIKeyStore()
    ) {
        self.client = client
        self.metrics = metrics
        self.operatorSessionStore = operatorSessionStore
        self.serverSessionAPIKeyStore = serverSessionAPIKeyStore
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

    public func selectToolSection(_ section: DesktopToolSection) {
        selectedSurface = .tools
        selectedToolSection = section
        notifyStateChanged()
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

    public func selectBenchmarkHistory(jobID: String) {
        selectedBenchmarkHistoryJobID = jobID
        rebuildBenchmarkDerivedState()
        notifyStateChanged()
    }

    public func selectBenchmarkMetric(_ metricName: String) {
        selectedBenchmarkMetricName = metricName
        rebuildBenchmarkDerivedState()
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
        let modelID = models.first(where: { $0.kind == "text" })?.modelID ?? selectedChatModelID
        let nextIndex = serverSessions.count + 1
        let session = DesktopServerSessionState(
            id: "server-session-\(UUID().uuidString)",
            title: nextIndex == 1 ? "Primary Server" : "Server \(nextIndex)",
            modelID: modelID,
            port: 8080 + max(0, serverSessions.count),
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

    public func updateSelectedServerSessionMaxConcurrentRequests(_ value: Int) {
        updateSelectedServerSession { session in
            session.servingDefaults.maxConcurrentRequests = max(1, value)
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
        replaceServerSession(id: serverSession.id) { session in
            session.lifecycle = .starting
            session.lastError = ""
            session.updatedAt = Date()
        }
        notifyStateChanged()
        await loadModel(modelID: serverSession.modelID)
    }

    public func stopSelectedServerSession() async {
        guard let serverSession = selectedServerSession else {
            return
        }
        replaceServerSession(id: serverSession.id) { session in
            session.lifecycle = .stopping
            session.updatedAt = Date()
        }
        notifyStateChanged()
        await unloadModel(modelID: serverSession.modelID)
        replaceServerSession(id: serverSession.id) { session in
            session.lifecycle = .stopped
            session.updatedAt = Date()
        }
        notifyStateChanged()
    }

    public func createChatSession() {
        guard let serverSession = selectedServerSession ?? serverSessions.first else {
            lastError = "Create a Server Session before opening chat."
            chatStatusText = "No Server Session"
            selectedSurface = .server
            notifyStateChanged()
            return
        }

        let nextIndex = chatSessions.count + 1
        let session = DesktopChatSessionState(
            id: "chat-session-\(UUID().uuidString)",
            title: nextIndex == 1 ? "Chat 1" : "Chat \(nextIndex)",
            serverSessionID: serverSession.id
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

    @discardableResult
    public func exportSelectedChatSession() -> String? {
        guard let session = selectedChatSession else {
            return nil
        }
        let sanitizedName = session.title.replacingOccurrences(of: " ", with: "-").lowercased()
        let exportURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(sanitizedName)-export.md")
        let lines = session.transcript.map { entry in
            "## \(entry.title)\n\n\(entry.body)\n"
        }
        let payload = """
        # \(session.title)

        - Server Session: \(session.serverSessionID)
        - Branch: \(session.branchTitle)
        - Status: \(session.statusText)

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
        models.first { $0.modelID == "melix-dev-text" } ?? models.first
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
        guard let selectedChatSession else {
            return selectedServerSession
        }
        return serverSession(id: selectedChatSession.serverSessionID) ?? selectedServerSession
    }

    public var selectedAgentIntegrationExport: AgentIntegrationExport? {
        agentIntegrationExports.first(where: { $0.target == selectedAgentIntegrationTarget })
        ?? agentIntegrationExports.first
    }

    public var desktopBannerState: DesktopBannerState? {
        if serverStateText == "Failed" || connectionStateText == "Degraded" {
            return DesktopBannerState(
                title: "Operator Attention Required",
                detail: lastError ?? connectionDetailText,
                severity: .critical
            )
        }
        if serverStateText == "Degraded" || serverStateText == "Draining" || connectionStateText == "Reconnecting" {
            return DesktopBannerState(
                title: "Runtime Needs Monitoring",
                detail: connectionDetailText,
                severity: .warning
            )
        }
        if let failingServer = serverSessions.first(where: { $0.lifecycle == .error }) {
            return DesktopBannerState(
                title: "\(failingServer.title) Needs Recovery",
                detail: failingServer.lastError,
                severity: .critical
            )
        }
        if let audioSetupAction = audioSetupActions.first {
            return DesktopBannerState(
                title: "Audio Setup Required",
                detail: audioSetupAction.detail,
                severity: .warning
            )
        }
        return nil
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

    public var imageModels: [RuntimeModelRow] {
        models.filter { $0.kind == "image" || $0.kind == "image_generation" }
    }

    public var selectedImageJob: Melix_Controlplane_V1_ImageJobSummary? {
        guard !selectedImageJobID.isEmpty else {
            return imageJobs.first
        }
        return imageJobs.first(where: { $0.jobID == selectedImageJobID }) ?? imageJobs.first
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
            lastError: lastError,
            recentEvents: recentEvents
        )
    }

    public var benchmarkModels: [RuntimeModelRow] {
        models.filter(Self.isBenchmarkEligibleModel)
    }

    public var benchmarkSuites: [RuntimeBenchmarkSuiteOptionState] {
        Self.benchmarkSuiteOptions
    }

    public var selectedBenchmarkHistoryEntry: RuntimeBenchmarkHistoryEntryState? {
        benchmarkHistory.first(where: { $0.jobID == selectedBenchmarkHistoryJobID })
            ?? benchmarkHistory.first
    }

    private var selectedServerSessionID = ""
    private var selectedChatSessionID = ""

    public func start() async {
        let restoreStartedAt = Date()
        restoreOperatorSessionState()
        operatorStateRestored = true
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
            lastError = startupFailureMessage(error)
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
        let startedAt = Date()
        do {
            let model = try await client.loadModel(modelID: modelID)
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

    public func submitChatPrompt() async {
        let prompt = chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            return
        }
        guard !isChatStreaming else {
            return
        }

        guard let serverSession = selectedChatServerSession else {
            chatStatusText = "No Server Session"
            lastError = "Create and start a Server Session before sending chat prompts."
            selectedSurface = .server
            notifyStateChanged()
            return
        }
        guard serverSession.isRunning else {
            chatStatusText = "No Server Session"
            lastError = "Start a running Server Session before sending chat prompts."
            selectedSurface = .chat
            notifyStateChanged()
            return
        }

        let modelID = resolvedChatModelID()
        chatComposerText = ""
        let startedAt = Date()
        let userMessage = ControlPlaneChatRequest.Message(role: "user", content: prompt)
        chatConversationMessages.append(userMessage)
        appendChatEntry(
            id: "user-\(UUID().uuidString)",
            kind: .user,
            title: "User",
            body: prompt,
            detail: modelID
        )
        chatStatusText = "Preparing"
        lastChatUsageText = ""
        isChatStreaming = true
        notifyStateChanged()

        if models.contains(where: { $0.modelID == modelID && $0.isLoaded }) == false {
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
                case .reasoningDelta(let text):
                    reasoningDeltaCount += 1
                    appendReasoningDelta(text, requestID: execution.requestID)
                case .toolCallDelta(let callID, let toolName, let argumentsFragment):
                    toolDeltaCount += 1
                    appendToolDelta(callID: callID, toolName: toolName, argumentsFragment: argumentsFragment)
                case .usage(let promptTokens, let completionTokens):
                    lastChatUsageText = "\(promptTokens) prompt • \(completionTokens) completion"
                case .completed(let finishReason, let assistantText, let reasoningText):
                    chatStatusText = finishReason.isEmpty ? "Completed" : "Completed • \(finishReason)"
                    finalizeAssistantText(assistantText, requestID: execution.requestID)
                    finalizeReasoningText(reasoningText, requestID: execution.requestID)
                case .failed(let code, let message):
                    chatStatusText = code.isEmpty ? "Failed" : "Failed • \(code)"
                    let failureMessage = message.isEmpty ? "Chat request failed." : message
                    lastError = failureMessage
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
            commitAssistantMessageIfNeeded()
        } catch {
            lastError = String(describing: error)
            chatStatusText = "Failed"
            appendChatEntry(
                id: "error-\(UUID().uuidString)",
                kind: .error,
                title: "Error",
                body: String(describing: error),
                detail: modelID
            )
        }

        isChatStreaming = false
        activeAssistantEntryID = nil
        activeReasoningEntryID = nil
        activeToolEntryIDs.removeAll()
        notifyStateChanged()
    }

    public func clearChatTranscript() {
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

    public func selectImageJob(jobID: String) {
        selectedImageJobID = jobID
        notifyStateChanged()
    }

    public func submitImageGeneration() async {
        let prompt = imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            return
        }

        let modelID = resolvedImageModelID()
        if models.contains(where: { $0.modelID == modelID && $0.isLoaded }) == false {
            await loadModel(modelID: modelID)
        }

        let startedAt = Date()
        imageStatusText = "Submitting"
        notifyStateChanged()

        do {
            let job = try await client.generateImage(
                ControlPlaneImageGenerationRequest(
                    modelID: modelID,
                    prompt: prompt,
                    size: imageSize,
                    n: max(1, imageVariantCount)
                )
            )
            upsert(imageJob: job)
            imageStatusText = Self.imageStatusText(for: job)
            imagePromptText = ""
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

    public func submitImageEdit() async {
        let sourceURL = imageEditSourceURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sourceURL.isEmpty else {
            imageStatusText = "Failed"
            recordLocalError("Image edit source is required.")
            notifyStateChanged()
            return
        }

        let modelID = resolvedImageModelID()
        if models.contains(where: { $0.modelID == modelID && $0.isLoaded }) == false {
            await loadModel(modelID: modelID)
        }

        let startedAt = Date()
        imageStatusText = "Submitting"
        notifyStateChanged()

        do {
            let job = try await client.editImage(
                ControlPlaneImageEditRequest(
                    modelID: modelID,
                    prompt: imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines),
                    imageURL: sourceURL,
                    maskURL: imageEditMaskURL.trimmingCharacters(in: .whitespacesAndNewlines),
                    strength: 1,
                    size: imageSize,
                    n: max(1, imageVariantCount)
                )
            )
            upsert(imageJob: job)
            imageStatusText = Self.imageStatusText(for: job)
            imagePromptText = ""
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
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await loadModel(modelID: modelID)
    }

    public func unloadModel(modelID: String) async {
        let startedAt = Date()
        do {
            let model = try await client.unloadModel(modelID: modelID)
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

    public func updateModelSettings(
        modelID: String,
        alias: String,
        pinOnLoad: Bool,
        memoryPolicy: String,
        accelerationMode: String,
        accelerationProfileID: String
    ) async {
        let startedAt = Date()
        do {
            let model = try await client.updateModelSettings(
                modelID: modelID,
                values: [
                    "alias": alias,
                    "pin_on_load": pinOnLoad ? "true" : "false",
                    "memory_policy": memoryPolicy,
                    "default_acceleration_mode": accelerationMode,
                    "acceleration_profile_id": accelerationProfileID,
                ]
            )
            await metrics.record(
                name: "menu.model_settings_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            recordLocalError(String(describing: error))
        }
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
            accelerationMode: "speculative_decode",
            accelerationProfileID: "draft-q4"
        )
    }

    public func fetchModelInfo(modelID: String) async {
        let startedAt = Date()
        do {
            let info = try await client.modelInfo(modelID: modelID)
            let snapshotModel = latestSnapshot.models.first(where: { $0.modelID == modelID })
            await metrics.record(
                name: "menu.model_info_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            selectedModelInfo = RuntimeModelInfoState(
                modelID: modelID,
                modelKind: info.modelKind,
                maxContext: info.maxContext,
                supportedParsers: info.supportedParsers,
                supportedModalities: info.supportedModalities,
                ocrPromptProfileText: snapshotModel?.settings.ext["ocr_prompt_profile_id"] ?? "",
                ocrSamplingProfileText: snapshotModel?.settings.ext["ocr_sampling_profile_id"] ?? "",
                ocrStopSequencesText: snapshotModel?.settings.ext["ocr_stop_sequences"] ?? ""
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
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
            let result = try await client.runModelOperation(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                quantProfileID: quantProfileID,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
            await metrics.record(
                name: "menu.model_operation_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
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
                smokeTestPassed: result.hasArtifact && result.artifact.smokeTestPassed,
                calibrationSampleCount: calibrationSampleCount(from: result.manifestJson)
            )
            if refreshProductToolingState {
                await refreshModelOpsProductState(modelID: modelID, notify: false)
            }
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
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

    public func downloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "download",
            outputDir: "/tmp/melix-download"
        )
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
            outputDir: "/tmp/melix-audio-models"
        )
        await refreshDesktopFoundation()
    }

    public func uploadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        let linkedQuantizationExt = latestQuantizedArtifactUploadExt()
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
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "train_lora",
            outputDir: "",
            ext: loraTrainingExt(),
            refreshProductToolingState: true
        )
    }

    public func activateLatestAdapter() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let adapter = selectedAdapterPackage, !adapter.outputPath.isEmpty else {
            return
        }

        var ext: [String: String] = [
            "artifact_path": adapter.outputPath,
        ]
        if let alias = Self.normalizedOptionalString(loraDerivedModelAlias) {
            ext["derived_model_alias"] = alias
        }
        await runModelOperation(
            modelID: modelID,
            operation: "activate_adapter",
            outputDir: "",
            ext: ext,
            refreshProductToolingState: true
        )
        await refreshDesktopFoundation()
    }

    public func refreshModelOpsProductState() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty else {
            return
        }
        await refreshModelOpsProductState(modelID: modelID, notify: true)
    }

    public func publishLatestAdapter() async {
        let modelID = resolvedLoraModelID()
        guard !modelID.isEmpty, let adapter = selectedAdapterPackage else {
            return
        }

        await runModelOperation(
            modelID: modelID,
            operation: "upload",
            outputDir: "/tmp/melix-upload-adapter",
            ext: [
                "target_repo": adapter.targetRepo.isEmpty ? "melix/adapters/\(adapter.adapterName)" : adapter.targetRepo,
                "artifact_kind": "adapter",
                "artifact_path": adapter.outputPath,
                "adapter_name": adapter.adapterName,
            ],
            refreshProductToolingState: true
        )
    }

    private func calibrationSampleCount(from manifestJSON: String) -> Int {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let calibration = payload["calibration"] as? [String: Any],
            let sampleCount = calibration["sample_count"] as? Int
        else {
            return 0
        }
        return sampleCount
    }

    private func latestQuantizedArtifactUploadExt() -> [String: String] {
        guard
            let lastModelOperation,
            lastModelOperation.operation == "quantize",
            lastModelOperation.artifactKind == "quantized_model_bundle"
        else {
            return [:]
        }
        var ext: [String: String] = [
            "artifact_kind": "model",
            "artifact_path": lastModelOperation.outputPath,
        ]
        if !lastModelOperation.manifestPath.isEmpty {
            ext["quantization_manifest_path"] = lastModelOperation.manifestPath
        }
        if !lastModelOperation.quantProfileID.isEmpty {
            ext["quant_profile_id"] = lastModelOperation.quantProfileID
        }
        return ext
    }

    private func startupFailureMessage(_ error: Error) -> String {
        "Startup failed: \(error). Open Melix Console for details."
    }

    public func runDoctor() async {
        let startedAt = Date()
        do {
            let report = try await client.runDoctor()
            await metrics.record(
                name: "menu.ops_doctor_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            lastDoctorReport = RuntimeDoctorReportState(markdown: report)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func runBench() async {
        let modelID = resolvedBenchmarkModelID()
        guard !modelID.isEmpty else {
            recordLocalError("Select a text model before running Benchmark.")
            notifyStateChanged()
            return
        }
        let suites = selectedBenchmarkSuiteIDs.sorted()
        guard suites.isEmpty == false else {
            recordLocalError("Select at least one benchmark dataset before running Benchmark.")
            notifyStateChanged()
            return
        }
        let startedAt = Date()
        do {
            let result = try await client.runBench(
                ControlPlaneBenchRequest(
                    modelID: modelID,
                    suites: suites,
                    parameters: benchmarkParameters()
                )
            )
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
        await refreshBenchmarkHistory(notify: true)
    }

    public func exportSelectedBenchmarkCSV() async {
        let startedAt = Date()
        do {
            let exportDirectory = try Self.ensureBenchmarkExportDirectory()
            let export = try await client.exportResults(outputDir: exportDirectory.path)
            let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
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

    private func refreshModelOpsProductState(modelID: String, notify: Bool) async {
        let startedAt = Date()
        do {
            let result = try await client.runModelOperation(
                modelID: modelID,
                operation: "registry_snapshot",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: [:]
            )
            await metrics.record(
                name: "menu.model_ops_refresh_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            applyModelOpsSnapshot(manifestJSON: result.manifestJson)
        } catch {
            recordLocalError(String(describing: error))
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
        adapterPackages = adapters.map(Self.makeAdapterPackageState)
        trainingHistory = jobs
            .filter { Self.stringValue("operation", from: $0) == "train_lora" }
            .map(Self.makeTrainingHistoryEntryState)
        refreshLoraSelectionState()
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
        if selectedServerSessionID.isEmpty || serverSession(id: session.serverSessionID) != nil {
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
        if serverSessions.isEmpty {
            chatSessions = []
            selectedChatSessionID = ""
            return
        }

        if selectedServerSession == nil {
            selectedServerSessionID = serverSessions.first?.id ?? ""
        }

        if chatSessions.isEmpty, let serverSession = selectedServerSession {
            let session = DesktopChatSessionState(
                id: "chat-session-\(UUID().uuidString)",
                title: "Chat 1",
                serverSessionID: serverSession.id
            )
            chatSessions = [session]
            loadChatSession(session)
            return
        }

        chatSessions = chatSessions.map { session in
            guard serverSession(id: session.serverSessionID) == nil else {
                return session
            }
            var rebound = session
            rebound.serverSessionID = serverSessions.first?.id ?? rebound.serverSessionID
            rebound.updatedAt = Date()
            return rebound
        }

        if selectedChatSession == nil, let first = chatSessions.first {
            loadChatSession(first)
        } else if let selectedChatSession {
            loadChatSession(selectedChatSession)
        }
    }

    private func syncServerSessionsWithModels() {
        let textModels = models.filter { row in
            row.kind == "text" || latestSnapshot.models.first(where: { $0.modelID == row.modelID })?.features.contains("chat") == true
        }

        if persistedServerSessions.isEmpty, let firstTextModel = textModels.first {
            let seeded = makeServerSession(for: firstTextModel, title: "Primary Server", port: 8080)
            persistedServerSessions = [seeded]
            selectedServerSessionID = seeded.id
        }

        guard persistedServerSessions.isEmpty == false else {
            serverSessions = []
            return
        }

        serverSessions = persistedServerSessions.enumerated().map { offset, session in
            var updated = session
            if let model = models.first(where: { $0.modelID == session.modelID }) {
                updated.lastKnownModelStateText = model.stateText
                switch session.lifecycle {
                case .draft, .running, .stopped, .error, .unavailable:
                    updated.lifecycle = session.lifecycle
                case .starting:
                    updated.lifecycle = model.isLoaded ? .running : .starting
                case .stopping:
                    updated.lifecycle = model.isLoaded ? .stopping : .stopped
                }
            } else if let fallbackModel = textModels.first {
                updated.modelID = fallbackModel.modelID
                updated.lastKnownModelStateText = fallbackModel.stateText
                updated.lifecycle = session.lifecycle == .stopped ? .stopped : .running
            } else {
                updated.lifecycle = .unavailable
                updated.lastKnownModelStateText = "Unavailable"
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
        port: Int
    ) -> DesktopServerSessionState {
        var session = DesktopServerSessionState(
            id: "server-session-\(UUID().uuidString)",
            title: title,
            modelID: model.modelID,
            port: port,
            lifecycle: .running,
            lastKnownModelStateText: model.stateText
        )
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
            updated.lastError = error
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
            selectedServerSessionID = restoredState.selectedServerSessionID
            if restoredState.serverSessions.isEmpty == false {
                persistedServerSessions = restoredState.serverSessions
                serverSessions = restoredState.serverSessions
            }
            lastPersistedOperatorSessionState = restoredState
        } catch {
            recordLocalError("Operator session restore failed: \(error)")
        }
    }

    private func currentOperatorSessionState() -> OperatorSessionState {
        OperatorSessionState(
            selectedSurface: selectedSurface,
            selectedServerSessionID: selectedServerSessionID,
            serverSessions: persistedServerSessions
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

    private func maybeApplyStoredGatewayAccessForSelectedRunningSession() {
        guard let selectedServerSession else {
            scheduleGatewayAccessClear(serverSessionID: lastAppliedGatewaySessionID)
            return
        }
        guard selectedServerSession.isRunning else {
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
            current.transcript = chatTranscript
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
            serverStateText = Self.serverStateText(serverStateChanged.state)
            statusTitle = "Melix \(serverStateText)"
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
                lastError = logEvent.message
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
            .sorted { $0.modelID < $1.modelID }
            .map(makeRuntimeModelRow)
        syncServerSessionsWithModels()
        ensureChatSessionsBoundToServerSessions()
        refreshImageState()
        refreshChatCapabilities()
        refreshLoraSelectionState()
        refreshBenchmarkSelectionState()
        refreshAgentIntegrationExports()
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
        rebuildBenchmarkDerivedState()
    }

    private func refreshBenchmarkHistory(notify: Bool) async {
        let startedAt = Date()
        do {
            let exportDirectory = try Self.ensureBenchmarkExportDirectory()
            let export = try await client.exportResults(outputDir: exportDirectory.path)
            let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: export.exportBundleJSON)
            applyBenchmarkExportBundle(bundle)
            await metrics.record(
                name: "menu.bench_history_refresh_ms",
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

        let suiteFilter = selectedBenchmarkSuiteIDs.isEmpty ? Set(Self.benchmarkSuiteOptions.map(\.id)) : selectedBenchmarkSuiteIDs
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

    private func resolvedBenchmarkModelID() -> String {
        if !selectedBenchmarkModelID.isEmpty {
            return selectedBenchmarkModelID
        }
        return benchmarkModels.first?.modelID ?? ""
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
        syncServerSessionsWithModels()
        ensureChatSessionsBoundToServerSessions()
        refreshImageState()
        refreshChatCapabilities()
        refreshLoraSelectionState()
        refreshAgentIntegrationExports()
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
    }

    private static func gatewayAccessProjection(
        from snapshot: Melix_Controlplane_V1_ServerSnapshot
    ) -> GatewayAccessProjection? {
        guard snapshot.hasGatewayAccess else {
            return nil
        }

        let summary = snapshot.gatewayAccess
        let keyHints = summary.keys.map(\.tokenHint).filter { !$0.isEmpty }

        switch summary.mode {
        case .none:
            return GatewayAccessProjection(
                authMode: .none,
                authTokenHint: "",
                sharedAccessState: .localOnly,
                accessKeyCount: 0,
                accessKeyHints: []
            )
        case .bearerToken:
            return GatewayAccessProjection(
                authMode: .bearerToken,
                authTokenHint: keyHints.first ?? "melix-api-key",
                sharedAccessState: .localOnly,
                accessKeyCount: max(keyHints.count, 1),
                accessKeyHints: keyHints
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
                accessKeyHints: keyHints
            )
        default:
            return nil
        }
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

    private func recordLocalError(_ message: String) {
        lastError = message
        recentEvents.insert(
            DesktopLogEntry(kind: "error", message: message, detail: "local", level: "error"),
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

    private func resolvedChatModelID() -> String {
        if let serverModelID = selectedChatServerSession?.modelID,
           models.contains(where: { $0.modelID == serverModelID }) {
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

    private func resolvedImageModelID() -> String {
        if models.contains(where: { $0.modelID == selectedImageModelID && Self.isImageModelKind($0.kind) }) {
            return selectedImageModelID
        }
        if let imageModel = models.first(where: { Self.isImageModelKind($0.kind) }) {
            selectedImageModelID = imageModel.modelID
            return imageModel.modelID
        }
        return selectedImageModelID
    }

    private func refreshImageState(preferredJobID: String? = nil) {
        if models.contains(where: { $0.modelID == selectedImageModelID && Self.isImageModelKind($0.kind) }) == false,
           let imageModel = models.first(where: { Self.isImageModelKind($0.kind) }) {
            selectedImageModelID = imageModel.modelID
        }

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

    private func loraTrainingExt() -> [String: String] {
        var ext: [String: String] = [
            "adapter_name": Self.normalizedOptionalString(loraAdapterName) ?? "melix-dev-adapter",
            "dataset_source_kind": loraDatasetSourceKind.rawValue,
        ]

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
        appendBody(text, toEntryID: entryID, kind: .assistant, title: "Assistant", detail: requestID)
    }

    private func appendReasoningDelta(_ text: String, requestID: String) {
        guard !text.isEmpty else { return }
        let entryID = activeReasoningEntryID ?? "reasoning-\(requestID)"
        activeReasoningEntryID = entryID
        appendBody(text, toEntryID: entryID, kind: .reasoning, title: "Reasoning", detail: requestID)
    }

    private func appendToolDelta(callID: String, toolName: String, argumentsFragment: String) {
        let normalizedCallID = callID.isEmpty ? UUID().uuidString : callID
        let entryID = activeToolEntryIDs[normalizedCallID] ?? "tool-\(normalizedCallID)"
        activeToolEntryIDs[normalizedCallID] = entryID
        let title = toolName.isEmpty ? "Tool Call" : "Tool • \(toolName)"
        appendBody(argumentsFragment, toEntryID: entryID, kind: .tool, title: title, detail: normalizedCallID)
    }

    private func finalizeAssistantText(_ assistantText: String, requestID: String) {
        guard !assistantText.isEmpty else { return }
        let entryID = activeAssistantEntryID ?? "assistant-\(requestID)"
        activeAssistantEntryID = entryID
        replaceBodyIfEmpty(assistantText, entryID: entryID, kind: .assistant, title: "Assistant", detail: requestID)
    }

    private func finalizeReasoningText(_ reasoningText: String, requestID: String) {
        guard !reasoningText.isEmpty else { return }
        let entryID = activeReasoningEntryID ?? "reasoning-\(requestID)"
        activeReasoningEntryID = entryID
        replaceBodyIfEmpty(reasoningText, entryID: entryID, kind: .reasoning, title: "Reasoning", detail: requestID)
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
            trainingDurationText: formatDuration(milliseconds: doubleValue("training_duration_ms", from: payload)),
            activationDurationText: formatDuration(milliseconds: doubleValue("activation_duration_ms", from: payload)),
            publishDurationText: formatDuration(milliseconds: doubleValue("adapter_publish_ms", from: payload))
        )
    }

    private static func makeTrainingHistoryEntryState(from payload: [String: Any]) -> RuntimeTrainingHistoryEntryState {
        RuntimeTrainingHistoryEntryState(
            id: stringValue("job_id", from: payload),
            jobID: stringValue("job_id", from: payload),
            modelID: stringValue("source_model", from: payload),
            adapterName: stringValue("adapter_name", from: payload["manifest"] as? [String: Any] ?? [:]),
            datasetURI: stringValue("dataset_uri", from: payload["manifest"] as? [String: Any] ?? [:]),
            statusText: humanizeStatus(stringValue("status", from: payload)),
            stageText: "\(stringValue("stage", from: payload)) • \(String(format: "%.0f%%", doubleValue("pct", from: payload) * 100))",
            outputPath: stringValue("output_path", from: payload),
            targetRepo: stringValue("target_repo", from: payload["manifest"] as? [String: Any] ?? [:])
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
            suiteTitle: benchmarkSuiteTitle(for: row.suiteID),
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
            suiteTitle: benchmarkSuiteTitle(for: row.suiteID),
            metricName: row.metricName,
            value: row.metricValue,
            unit: row.unit,
            createdAtLabel: benchmarkTimestampLabel(row.createdAtUnixMS),
            createdAtUnixMS: row.createdAtUnixMS
        )
    }

    private static func stringValue(_ key: String, from payload: [String: Any]) -> String {
        payload[key] as? String ?? ""
    }

    private static func doubleValue(_ key: String, from payload: [String: Any]) -> Double {
        if let value = payload[key] as? Double {
            return value
        }
        if let number = payload[key] as? NSNumber {
            return number.doubleValue
        }
        return 0
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

    private static func benchmarkMetricLabel(_ metricName: String) -> String {
        let normalized = metricName.split(separator: ".").last.map(String.init) ?? metricName
        return normalized.replacingOccurrences(of: "_", with: " ")
    }

    private static func benchmarkSuiteTitle(for suiteID: String) -> String {
        benchmarkSuiteOptions.first(where: { $0.id == suiteID })?.title ?? suiteID
    }

    private static func benchmarkTimestampLabel(_ unixMS: Int64) -> String {
        let date = Date(timeIntervalSince1970: Double(unixMS) / 1_000)
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    private static func isBenchmarkEligibleModel(_ model: RuntimeModelRow) -> Bool {
        model.kind == "text"
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

    private static func benchmarkCSVFileName(jobID: String?) -> String {
        let sanitizedJobID = (jobID?.isEmpty == false ? jobID! : "all-runs")
            .replacingOccurrences(of: "/", with: "-")
        return "melix-benchmark-\(sanitizedJobID).csv"
    }

    private static func isImageModelKind(_ kind: String) -> Bool {
        kind == "image" || kind == "image_generation"
    }
}

func makeRuntimeModelRow(_ model: Melix_Controlplane_V1_ModelSummary) -> RuntimeModelRow {
    RuntimeModelRow(
        modelID: model.modelID,
        kind: model.kind,
        state: model.state,
        stateText: runtimeModelStateText(
            model.state,
            transitionReason: model.residency.transitionReason
        ),
        actionTitle: runtimeActionTitle(for: model.state),
        maxContext: model.maxContext,
        alias: model.settings.alias,
        memoryPolicyText: runtimeMemoryPolicyText(model.settings.memoryPolicy),
        adaptiveThinkingText: runtimeAdaptiveThinkingText(model.settings.adaptiveThinking),
        accelerationModeText: runtimeAccelerationModeText(model.settings.defaultAccelerationMode),
        accelerationProfileID: model.settings.accelerationProfileID,
        residencyText: runtimeResidencyText(for: model),
        memoryText: runtimeMemoryText(for: model),
        memoryAlertText: runtimeMemoryAlertText(for: model)
    )
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

private func runtimeResidencyText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let residencyState = resolvedResidencyState(for: model)
    let policy = resolvedResidencyPolicy(for: model)
    let pinRequested = resolvedPinRequested(for: model)
    let pinned = resolvedPinned(for: model)
    let ttlSeconds = resolvedTTLSeconds(for: model)

    var parts = [
        runtimeResidencyStateText(residencyState),
        runtimeMemoryPolicyText(policy),
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
    return "Memory protection • \(runtimeTransitionReasonText(reason))"
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
